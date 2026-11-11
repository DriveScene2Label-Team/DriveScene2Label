param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'status',
    [switch]$WebOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'DriveScene2Label/hybrid'
$runtimeEnv = Join-Path $runtimeRoot 'compose.env'
$localRoot = Join-Path $repoRoot '.local/hybrid'
$composeArgs = @('compose', '--env-file', $runtimeEnv, '-f', 'compose.hybrid.yml', '-f', 'compose.gpu.yml', '-f', 'compose.hybrid-auth.yml')
if (-not (Test-Path -LiteralPath $runtimeEnv)) { throw 'Prepare the protected runtime files first; see docs/hybrid-setup.md.' }
Push-Location $repoRoot
try {
    if ($Action -eq 'status') {
        & docker @composeArgs ps
        & python scripts/hybrid/operations.py status --env-file $runtimeEnv
        if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the backend maintenance state.' }
        & nvidia-smi -L
        if (Test-Path "$localRoot/tunnel.stderr.log") {
            Select-String -Path "$localRoot/tunnel.stderr.log" -Pattern 'https://[^ ]+\.trycloudflare.com'
        }
        exit $LASTEXITCODE
    }
    if ($Action -eq 'stop') {
        & docker @composeArgs stop
        if ($LASTEXITCODE -ne 0) { throw 'Container stop failed' }
        foreach ($helper in @('tunnel', 'aws-refresh')) {
            $pidPath = Join-Path $localRoot "$helper.pid"
            if (Test-Path $pidPath) {
                $helperId = [int](Get-Content $pidPath)
                $process = Get-CimInstance Win32_Process -Filter "ProcessId=$helperId"
                if ($process -and ($process.CommandLine -like '*cloudflared*tunnel*127.0.0.1:4180*' -or $process.CommandLine -like '*refresh-s3-session.py*--watch*')) {
                    Stop-Process -Id $helperId
                }
            }
        }
        Write-Output 'Local services stopped; AWS RDS and S3 are unchanged. Volumes are preserved.'
        exit 0
    }
    if (-not $WebOnly) {
        & nvidia-smi -L
        if ($LASTEXITCODE -ne 0) { throw 'GPU is unavailable. Reconnect/reboot the eGPU, or use -WebOnly for data viewing.' }
    }
    & python scripts/hybrid/refresh-s3-session.py --directory (Join-Path $runtimeRoot 'aws')
    if ($LASTEXITCODE -ne 0) { throw 'Renew AWS login with aws login --profile ds2l-seoul, then retry.' }
    & python scripts/hybrid/operations.py prepare --env-file $runtimeEnv
    if ($LASTEXITCODE -ne 0) { throw 'Local operations credential preparation failed.' }
    & docker @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed' }
    if ($WebOnly) { & docker @composeArgs up -d --no-build --no-deps backend auth-gateway }
    else { & docker @composeArgs up -d --no-build }
    if ($LASTEXITCODE -ne 0) { throw 'Local service startup failed' }
    & python scripts/hybrid/operations.py resume --env-file $runtimeEnv
    if ($LASTEXITCODE -ne 0) { throw 'Backend started but writes remain unavailable. Check maintenance state before using the app.' }
    $helpers = @(
        @{ Name='aws-refresh'; File=(Get-Command python).Source; Args=('"' + (Join-Path $repoRoot 'scripts/hybrid/refresh-s3-session.py') + '" --directory "' + (Join-Path $runtimeRoot 'aws') + '" --watch') },
        @{ Name='tunnel'; File=(Join-Path $repoRoot '.local/tools/cloudflared.exe'); Args='tunnel --no-autoupdate --url http://127.0.0.1:4180 --protocol http2' }
    )
    foreach ($helper in $helpers) {
        $pidPath = Join-Path $localRoot ($helper.Name + '.pid')
        if (Test-Path $pidPath) {
            $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$([int](Get-Content $pidPath))"
            if ($existing -and ($existing.CommandLine -like '*cloudflared*tunnel*127.0.0.1:4180*' -or $existing.CommandLine -like '*refresh-s3-session.py*--watch*')) { continue }
        }
        if (-not (Test-Path -LiteralPath $helper.File)) { throw "Missing helper: $($helper.File)" }
        $process = Start-Process -FilePath $helper.File -ArgumentList $helper.Args -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $localRoot ($helper.Name + '.stdout.log')) `
            -RedirectStandardError (Join-Path $localRoot ($helper.Name + '.stderr.log'))
        $process.Id | Set-Content -LiteralPath $pidPath
    }
    Write-Output 'Local services started. If the tunnel URL changed, update Vercel BACKEND_URL and redeploy before using the public site.'
} finally { Pop-Location }
