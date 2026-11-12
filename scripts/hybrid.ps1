param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'status',
    [switch]$WebOnly,
    [switch]$SkipVercel
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'DriveScene2Label/hybrid'
$runtimeEnv = Join-Path $runtimeRoot 'compose.env'
$localRoot = Join-Path $repoRoot '.local/hybrid'
$composeArgs = @('compose', '--env-file', $runtimeEnv, '-f', 'compose.hybrid.yml', '-f', 'compose.gpu.yml', '-f', 'compose.hybrid-auth.yml')
$tunnelConfig = $null
if (Test-Path -LiteralPath (Join-Path $runtimeRoot 'tunnel.json')) {
    $tunnelConfig = Get-Content -LiteralPath (Join-Path $runtimeRoot 'tunnel.json') -Raw | ConvertFrom-Json
    if ($tunnelConfig.provider -ne 'microsoft' -or $tunnelConfig.tunnelId -notmatch '^[a-zA-Z0-9-]+\.[a-z0-9]+$') {
        throw 'Invalid protected tunnel.json. See docs/hybrid-setup.md.'
    }
}
function Test-DockerReady {
    # Windows PowerShell 5 treats native stderr as an error record. A stopped daemon is expected here.
    $probeErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } finally { $ErrorActionPreference = $probeErrorPreference }
}
if (-not (Test-Path -LiteralPath $runtimeEnv)) { throw 'Prepare the protected runtime files first; see docs/hybrid-setup.md.' }
Push-Location $repoRoot
try {
    if ($Action -eq 'status') {
        & python scripts/hybrid/cloud.py rds-status
        & docker @composeArgs ps
        & python scripts/hybrid/operations.py status --env-file $runtimeEnv
        if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the backend maintenance state.' }
        & nvidia-smi -L
        if ($tunnelConfig) { Write-Output "Private Microsoft tunnel: $($tunnelConfig.origin)" }
        elseif (Test-Path "$localRoot/tunnel.stderr.log") {
            Select-String -Path "$localRoot/tunnel.stderr.log" -Pattern 'https://[^ ]+\.trycloudflare.com'
        }
        exit $LASTEXITCODE
    }
    if ($Action -eq 'stop') {
        & docker @composeArgs stop
        if ($LASTEXITCODE -ne 0) { throw 'Container stop failed' }
        foreach ($helper in @('tunnel', 'dev-tunnel', 'aws-refresh')) {
            $pidPath = Join-Path $localRoot "$helper.pid"
            if (Test-Path $pidPath) {
                $helperId = [int](Get-Content $pidPath)
                $process = Get-CimInstance Win32_Process -Filter "ProcessId=$helperId"
                if ($process -and ($process.CommandLine -like '*cloudflared*tunnel*127.0.0.1:4180*' -or $process.CommandLine -like '*refresh-s3-session.py*--watch*' -or ($tunnelConfig -and $process.CommandLine -like "*devtunnel*host*$($tunnelConfig.tunnelId)*"))) {
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
    & python scripts/hybrid/cloud.py rds-start
    if ($LASTEXITCODE -ne 0) { throw 'RDS is not ready. Check aws login --profile ds2l-seoul --region ap-northeast-2 and retry.' }
    if (-not (Test-DockerReady)) {
        $dockerDesktop = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
        if (-not (Test-Path -LiteralPath $dockerDesktop)) { throw 'Docker Desktop is not installed.' }
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
        $dockerReady = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Seconds 3
            if (Test-DockerReady) { $dockerReady = $true; break }
        }
        if (-not $dockerReady) { throw 'Docker Desktop did not become ready within three minutes.' }
    }
    & python scripts/hybrid/refresh-s3-session.py --directory (Join-Path $runtimeRoot 'aws')
    if ($LASTEXITCODE -ne 0) { throw 'Renew AWS login with aws login --profile ds2l-seoul, then retry.' }
    & python scripts/hybrid/operations.py prepare --env-file $runtimeEnv
    if ($LASTEXITCODE -ne 0) { throw 'Local operations credential preparation failed.' }
    & docker @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed' }
    # Repeated start must not recreate containers or interrupt an active GPU job.
    if ($WebOnly) { & docker @composeArgs up -d --no-build --no-recreate --no-deps --wait --wait-timeout 180 backend auth-gateway }
    else { & docker @composeArgs up -d --no-build --no-recreate --wait --wait-timeout 180 }
    if ($LASTEXITCODE -ne 0) { throw 'Local service startup failed' }
    & python scripts/hybrid/operations.py resume --env-file $runtimeEnv
    if ($LASTEXITCODE -ne 0) { throw 'Backend started but writes remain unavailable. Check maintenance state before using the app.' }
    $helpers = @(
        @{ Name='aws-refresh'; File=(Get-Command python).Source; Args=('"' + (Join-Path $repoRoot 'scripts/hybrid/refresh-s3-session.py') + '" --directory "' + (Join-Path $runtimeRoot 'aws') + '" --watch') }
    )
    if ($tunnelConfig) {
        $helpers += @{ Name='dev-tunnel'; File=(Join-Path $repoRoot '.local/tools/devtunnel.exe'); Args="host $($tunnelConfig.tunnelId)" }
    } else {
        $helpers += @{ Name='tunnel'; File=(Join-Path $repoRoot '.local/tools/cloudflared.exe'); Args='tunnel --no-autoupdate --url http://127.0.0.1:4180 --protocol http2' }
    }
    foreach ($helper in $helpers) {
        $pidPath = Join-Path $localRoot ($helper.Name + '.pid')
        if (Test-Path $pidPath) {
            $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$([int](Get-Content $pidPath))"
            if ($existing -and ($existing.CommandLine -like '*cloudflared*tunnel*127.0.0.1:4180*' -or $existing.CommandLine -like '*refresh-s3-session.py*--watch*' -or ($tunnelConfig -and $existing.CommandLine -like "*devtunnel*host*$($tunnelConfig.tunnelId)*"))) { continue }
        }
        if (-not (Test-Path -LiteralPath $helper.File)) { throw "Missing helper: $($helper.File)" }
        $process = Start-Process -FilePath $helper.File -ArgumentList $helper.Args -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $localRoot ($helper.Name + '.stdout.log')) `
            -RedirectStandardError (Join-Path $localRoot ($helper.Name + '.stderr.log'))
        $process.Id | Set-Content -LiteralPath $pidPath
    }
    if (-not $SkipVercel) {
        if ($tunnelConfig) { & python scripts/hybrid/dev_tunnel.py sync }
        else { & python scripts/hybrid/cloud.py vercel-sync }
        if ($LASTEXITCODE -ne 0) { throw 'Local services are running, but the public connection is not verified. Check the tunnel log and the preceding Vercel error, then retry start. Log in again only for an authentication error.' }
    }
    Write-Output 'Local services ready. RDS is available, S3 credentials refreshed, existing data and running jobs preserved.'
} finally { Pop-Location }
