param(
    [ValidateSet('dev', 'build', 'typecheck', 'test')]
    [string]$Action = 'dev'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot 'frontend'
$nodeVersion = (Get-Content -LiteralPath (Join-Path $frontendRoot '.node-version') -Raw).Trim()
$portableNode = Join-Path $repoRoot ".local/tools/node-v$nodeVersion-win-x64"
$previousPath = $env:PATH
$taskExitCode = 1
Push-Location $frontendRoot
try {
    if (Test-Path -LiteralPath (Join-Path $portableNode 'node.exe')) {
        $env:PATH = "$portableNode;$env:PATH"
    }
    $activeNode = [version]((& node --version).Trim().TrimStart('v'))
    $supported = ($activeNode.Major -eq 22 -and $activeNode -ge [version]'22.22.2') -or
        ($activeNode.Major -eq 24 -and $activeNode -ge [version]'24.15.0') -or $activeNode.Major -ge 26
    if (-not $supported) { throw "Use Node $nodeVersion (see docs/hybrid-setup.md)." }
    & npm.cmd run $Action
    $taskExitCode = $LASTEXITCODE
} finally {
    $env:PATH = $previousPath
    Pop-Location
}
exit $taskExitCode
