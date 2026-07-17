[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Install", "Update", "Rollback")]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [string]$Package,

    [string]$VenvPath = "$env:LOCALAPPDATA\alterios-mcp\venv",
    [string]$DotenvPath,
    [string]$PythonCommand = "python",
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$venv = [System.IO.Path]::GetFullPath($VenvPath)
$python = Join-Path $venv "Scripts\python.exe"
$doctor = Join-Path $venv "Scripts\alterios-doctor.exe"
$releaseSmoke = Join-Path $venv "Scripts\alterios-release-smoke.exe"

if ($Action -eq "Install") {
    if (-not (Test-Path -LiteralPath $python)) {
        & $PythonCommand -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment: $venv" }
    }
} elseif (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment does not exist: $venv"
}

$before = & $python -c "import importlib.metadata as m; print(m.version('alterios-mcp'))" 2>$null
if ($LASTEXITCODE -ne 0) { $before = "not-installed" }

& $python -m pip install --upgrade $Package
if ($LASTEXITCODE -ne 0) { throw "Package $Action failed." }

if ($DotenvPath) {
    $resolvedDotenv = [System.IO.Path]::GetFullPath($DotenvPath)
    if (-not (Test-Path -LiteralPath $resolvedDotenv -PathType Leaf)) {
        throw "Dotenv file does not exist: $resolvedDotenv"
    }
    $env:ALTERIOS_DOTENV_PATH = $resolvedDotenv
}

if (-not $SkipSmoke) {
    $doctorArgs = @("--json", "--skip-startup-benchmark")
    if ($DotenvPath) { $doctorArgs += "--require-config" }
    & $doctor @doctorArgs
    if ($LASTEXITCODE -ne 0) { throw "alterios-doctor failed after $Action." }
    & $releaseSmoke --json --skip-startup-benchmark
    if ($LASTEXITCODE -ne 0) { throw "alterios-release-smoke failed after $Action." }
}

$after = & $python -c "import importlib.metadata as m; print(m.version('alterios-mcp'))"
Write-Host "Alterios MCP $Action completed: $before -> $after"
Write-Host "MCP executable: $(Join-Path $venv 'Scripts\alterios-mcp.exe')"
Write-Host "Restart the MCP client so the old server process is replaced."
