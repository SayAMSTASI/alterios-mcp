[CmdletBinding()]
param(
    [ValidateSet("Check", "Install", "Update", "Rollback", "Solutions")]
    [string]$Action = "Update",

    [string]$Package,
    [string]$ExpectedSha256,
    [string]$Repository = "SayAMSTASI/alterios-mcp",
    [string]$StatePath = "$env:LOCALAPPDATA\alterios-mcp",
    [string]$VenvPath = "$env:LOCALAPPDATA\alterios-mcp\venv",
    [string]$DotenvPath,
    [string]$PythonCommand = "python",
    [switch]$StopRunningMcp,
    [switch]$SkipSmoke,
    [switch]$NoAutomaticRollback,
    [switch]$SkipSelfUpdate
)

$ErrorActionPreference = "Stop"
$state = [System.IO.Path]::GetFullPath($StatePath)
$venv = [System.IO.Path]::GetFullPath($VenvPath)
$packages = Join-Path $state "packages"
$rollbackPackages = Join-Path $state "rollback"
$python = Join-Path $venv "Scripts\python.exe"
$doctor = Join-Path $venv "Scripts\alterios-doctor.exe"
$suggestFixes = Join-Path $venv "Scripts\alterios-suggest-fixes.exe"
$releaseSmoke = Join-Path $venv "Scripts\alterios-release-smoke.exe"
$managerPath = Join-Path $state "manage_release.ps1"
$apiHeaders = @{ "User-Agent" = "alterios-mcp-release-manager"; "Accept" = "application/vnd.github+json" }

function Get-InstalledVersion {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { return "not-installed" }
    $version = & $python -c "import importlib.metadata as m; print(next((d.version for d in m.distributions() if d.metadata.get('Name') == 'alterios-mcp'), 'not-installed'))"
    if ($LASTEXITCODE -ne 0) { return "not-installed" }
    return [string]$version
}

function Get-GitHubRelease {
    param([string]$Version)

    $uri = if ($Version) {
        "https://api.github.com/repos/$Repository/releases/tags/v$Version"
    } else {
        "https://api.github.com/repos/$Repository/releases/latest"
    }
    return Invoke-RestMethod -Uri $uri -Headers $apiHeaders -Method Get
}

function Save-ReleaseAsset {
    param(
        [Parameter(Mandatory = $true)]$Asset,
        [Parameter(Mandatory = $true)][string]$DestinationDirectory
    )

    [System.IO.Directory]::CreateDirectory($DestinationDirectory) | Out-Null
    $destination = Join-Path $DestinationDirectory ([string]$Asset.name)
    Invoke-WebRequest -Uri ([string]$Asset.browser_download_url) -Headers $apiHeaders -OutFile $destination -UseBasicParsing
    return $destination
}

function Assert-FileChecksum {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Sha256
    )

    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
    $expected = $Sha256.Trim().ToUpperInvariant()
    if ($actual -ne $expected) {
        throw "SHA-256 mismatch for $Path. Expected $expected, got $actual."
    }
}

function Get-ExpectedChecksum {
    param(
        [Parameter(Mandatory = $true)][string]$ChecksumPath,
        [Parameter(Mandatory = $true)][string]$FileName
    )

    $checksumLine = Get-Content -LiteralPath $ChecksumPath -Encoding UTF8 | Where-Object { $_ -match "\s+$([regex]::Escape($FileName))$" } | Select-Object -First 1
    if (-not $checksumLine) { throw "SHA256SUMS.txt does not contain $FileName." }
    return ($checksumLine -split '\s+')[0]
}

function Resolve-ReleaseWheel {
    param(
        [string]$Version,
        [Parameter(Mandatory = $true)][string]$DestinationDirectory
    )

    $release = Get-GitHubRelease -Version $Version
    $wheelAsset = $release.assets | Where-Object { $_.name -match '^alterios_mcp-.+-py3-none-any\.whl$' } | Select-Object -First 1
    $checksumAsset = $release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" } | Select-Object -First 1
    if (-not $wheelAsset) { throw "Release $($release.tag_name) does not contain an Alterios MCP wheel." }
    if (-not $checksumAsset) { throw "Release $($release.tag_name) does not contain SHA256SUMS.txt." }

    $wheelPath = Save-ReleaseAsset -Asset $wheelAsset -DestinationDirectory $DestinationDirectory
    $checksumPath = Save-ReleaseAsset -Asset $checksumAsset -DestinationDirectory $DestinationDirectory
    $expected = Get-ExpectedChecksum -ChecksumPath $checksumPath -FileName ([string]$wheelAsset.name)
    Assert-FileChecksum -Path $wheelPath -Sha256 $expected

    return [pscustomobject]@{
        Path = $wheelPath
        Version = ([string]$release.tag_name).TrimStart("v")
        Verified = $true
        ReleaseUrl = [string]$release.html_url
    }
}

function Resolve-PackageInput {
    param([string]$InputPackage)

    if (-not $InputPackage) {
        return Resolve-ReleaseWheel -DestinationDirectory $packages
    }

    [System.IO.Directory]::CreateDirectory($packages) | Out-Null
    if ($InputPackage -match '^https?://') {
        $name = [System.IO.Path]::GetFileName(([System.Uri]$InputPackage).AbsolutePath)
        if (-not $name) { $name = "alterios-mcp-package.whl" }
        $path = Join-Path $packages $name
        Invoke-WebRequest -Uri $InputPackage -OutFile $path -UseBasicParsing
    } else {
        $path = [System.IO.Path]::GetFullPath($InputPackage)
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Package does not exist: $path" }
    }
    if ($ExpectedSha256) { Assert-FileChecksum -Path $path -Sha256 $ExpectedSha256 }
    $match = [regex]::Match([System.IO.Path]::GetFileName($path), '^alterios_mcp-(?<version>[^-]+)-')
    return [pscustomobject]@{
        Path = $path
        Version = if ($match.Success) { $match.Groups['version'].Value } else { "unknown" }
        Verified = [bool]$ExpectedSha256
        ReleaseUrl = $null
    }
}

function Get-RunningMcpProcesses {
    if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) { return @() }
    $venvPrefix = $venv.TrimEnd('\') + '\'
    return @(Get-CimInstance Win32_Process | Where-Object {
        $exe = [string]$_.ExecutablePath
        $commandLine = [string]$_.CommandLine
        $insideVenv = $exe.StartsWith($venvPrefix, [System.StringComparison]::OrdinalIgnoreCase)
        $isMcp = $_.Name -ieq "alterios-mcp.exe" -or $commandLine -match 'alterios[_-]mcp'
        $insideVenv -and $isMcp
    })
}

function Stop-Or-BlockRunningMcp {
    $running = @(Get-RunningMcpProcesses)
    if (-not $running) { return }
    if (-not $StopRunningMcp) {
        $ids = ($running | Select-Object -ExpandProperty ProcessId) -join ", "
        throw "Alterios MCP is running from the target venv (PIDs: $ids). Option 1: close the MCP client and retry. Option 2: retry with -StopRunningMcp."
    }
    foreach ($process in $running) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }
    Start-Sleep -Milliseconds 500
}

function Invoke-PackageInstall {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$ForceReinstall
    )

    $arguments = @("-m", "pip", "install", "--upgrade")
    if ($ForceReinstall) { $arguments += "--force-reinstall" }
    $arguments += $Path
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Package installation failed: $Path" }
}

function Invoke-PostInstallChecks {
    if ($SkipSmoke) { return }
    $doctorArgs = @("--json", "--skip-startup-benchmark")
    if ($DotenvPath) { $doctorArgs += "--require-config" }
    & $doctor @doctorArgs
    if ($LASTEXITCODE -ne 0) { throw "alterios-doctor failed after $Action." }
    & $releaseSmoke --json --skip-startup-benchmark
    if ($LASTEXITCODE -ne 0) { throw "alterios-release-smoke failed after $Action." }
}

function Invoke-PreUpdateCheck {
    if ($Action -ne "Update" -or $SkipSmoke) { return }
    $doctorArgs = @("--json", "--skip-startup-benchmark")
    if ($DotenvPath) { $doctorArgs += "--require-config" }
    & $doctor @doctorArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Pre-update doctor failed. Run -Action Solutions and repair the current installation before updating."
    }
}

function Save-PreviousReleaseWheel {
    param([string]$Version)

    if (-not $Version -or $Version -eq "not-installed") { return $null }
    try {
        $versionDirectory = Join-Path $rollbackPackages "v$Version"
        $resolved = Resolve-ReleaseWheel -Version $Version -DestinationDirectory $versionDirectory
        return $resolved.Path
    } catch {
        Write-Warning "Could not cache release v$Version for automatic rollback: $($_.Exception.Message)"
        return $null
    }
}

function Save-ManagerAndState {
    param(
        [string]$Before,
        [string]$After,
        [string]$PackagePath
    )

    [System.IO.Directory]::CreateDirectory($state) | Out-Null
    if ($PSCommandPath -and ([System.IO.Path]::GetFullPath($PSCommandPath) -ne [System.IO.Path]::GetFullPath($managerPath))) {
        Copy-Item -LiteralPath $PSCommandPath -Destination $managerPath -Force
    }
    [ordered]@{
        updated_at = [DateTime]::UtcNow.ToString("o")
        action = $Action
        before = $Before
        after = $After
        package = $PackagePath
        venv = $venv
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state "release-state.json") -Encoding UTF8
}

function Invoke-LatestManagerIfNeeded {
    if ($Action -ne "Update" -or $Package -or $SkipSelfUpdate) { return $false }
    try {
        $release = Get-GitHubRelease
        $managerAsset = $release.assets | Where-Object { $_.name -eq "manage_release.ps1" } | Select-Object -First 1
        $checksumAsset = $release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" } | Select-Object -First 1
        if (-not $managerAsset -or -not $checksumAsset) { return $false }
        $managerUpdateDirectory = Join-Path $state "manager-update"
        [System.IO.Directory]::CreateDirectory($managerUpdateDirectory) | Out-Null
        $latestManager = Save-ReleaseAsset -Asset $managerAsset -DestinationDirectory $managerUpdateDirectory
        $managerChecksums = Save-ReleaseAsset -Asset $checksumAsset -DestinationDirectory $managerUpdateDirectory
        $managerExpected = Get-ExpectedChecksum -ChecksumPath $managerChecksums -FileName "manage_release.ps1"
        Assert-FileChecksum -Path $latestManager -Sha256 $managerExpected
        if ($PSCommandPath) {
            $currentHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
            $latestHash = (Get-FileHash -LiteralPath $latestManager -Algorithm SHA256).Hash
            if ($currentHash -eq $latestHash) { return $false }
        }
        $forward = @{
            Action = "Update"
            Repository = $Repository
            StatePath = $state
            VenvPath = $venv
            PythonCommand = $PythonCommand
            SkipSelfUpdate = $true
        }
        if ($DotenvPath) { $forward.DotenvPath = $DotenvPath }
        if ($ExpectedSha256) { $forward.ExpectedSha256 = $ExpectedSha256 }
        if ($StopRunningMcp) { $forward.StopRunningMcp = $true }
        if ($SkipSmoke) { $forward.SkipSmoke = $true }
        if ($NoAutomaticRollback) { $forward.NoAutomaticRollback = $true }
        & $latestManager @forward
        exit $LASTEXITCODE
    } catch {
        Write-Warning "Could not refresh manage_release.ps1; continuing with the current manager: $($_.Exception.Message)"
        return $false
    }
}

if ($DotenvPath) {
    $resolvedDotenv = [System.IO.Path]::GetFullPath($DotenvPath)
    if (-not (Test-Path -LiteralPath $resolvedDotenv -PathType Leaf)) {
        throw "Dotenv file does not exist: $resolvedDotenv"
    }
    $env:ALTERIOS_DOTENV_PATH = $resolvedDotenv
}

Invoke-LatestManagerIfNeeded | Out-Null

if ($Action -eq "Check") {
    $before = Get-InstalledVersion
    $latest = Get-GitHubRelease
    $latestVersion = ([string]$latest.tag_name).TrimStart("v")
    [ordered]@{
        installed_version = $before
        latest_version = $latestVersion
        update_available = $before -eq "not-installed" -or ([version]$latestVersion -gt [version]$before)
        release_url = [string]$latest.html_url
        update_command = "& '$managerPath' -Action Update"
    } | ConvertTo-Json
    exit 0
}

if ($Action -eq "Solutions") {
    if (Test-Path -LiteralPath $suggestFixes -PathType Leaf) {
        $solutionArgs = @("--json", "--processes")
        if ($DotenvPath) { $solutionArgs += "--require-config" }
        & $suggestFixes @solutionArgs
        exit $LASTEXITCODE
    }
    [ordered]@{
        status = "not-installed"
        options = @(
            "Run this manager with -Action Install",
            "Create the venv manually and install a verified release wheel"
        )
    } | ConvertTo-Json
    exit 1
}

if ($Action -eq "Install") {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($venv)) | Out-Null
        & $PythonCommand -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment: $venv" }
    }
} elseif (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Virtual environment does not exist: $venv. Run -Action Install first."
}

$before = Get-InstalledVersion
$resolvedPackage = $null
$rollbackPath = $null

if ($Action -eq "Rollback") {
    if ($Package) {
        $resolvedPackage = Resolve-PackageInput -InputPackage $Package
    } else {
        $candidate = Get-ChildItem -LiteralPath $rollbackPackages -Filter "alterios_mcp-*.whl" -File -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if (-not $candidate) { throw "No cached rollback wheel found. Pass -Package explicitly." }
        $cachedChecksums = Join-Path $candidate.DirectoryName "SHA256SUMS.txt"
        if (-not (Test-Path -LiteralPath $cachedChecksums -PathType Leaf)) { throw "Cached rollback checksum file is missing: $cachedChecksums" }
        $cachedExpected = Get-ExpectedChecksum -ChecksumPath $cachedChecksums -FileName $candidate.Name
        Assert-FileChecksum -Path $candidate.FullName -Sha256 $cachedExpected
        $resolvedPackage = [pscustomobject]@{ Path = $candidate.FullName; Version = "cached"; Verified = $true; ReleaseUrl = $null }
    }
} else {
    $resolvedPackage = Resolve-PackageInput -InputPackage $Package
}

if ($Action -eq "Update" -and $before -ne "not-installed" -and $resolvedPackage.Version -ne "unknown") {
    if ([version]$resolvedPackage.Version -le [version]$before) {
        Invoke-PostInstallChecks
        Save-ManagerAndState -Before $before -After $before -PackagePath $resolvedPackage.Path
        Write-Host "Alterios MCP is already current: $before. Update does not downgrade packages; use -Action Rollback explicitly."
        exit 0
    }
}

if ($Action -eq "Update") {
    Invoke-PreUpdateCheck
    $rollbackPath = Save-PreviousReleaseWheel -Version $before
    if ($before -ne "not-installed" -and -not $rollbackPath -and -not $NoAutomaticRollback) {
        throw "A verified rollback wheel could not be prepared. Retry with release access or explicitly pass -NoAutomaticRollback."
    }
}

Stop-Or-BlockRunningMcp
try {
    Invoke-PackageInstall -Path $resolvedPackage.Path -ForceReinstall:($Action -eq "Rollback")
    Invoke-PostInstallChecks
} catch {
    $installError = $_
    if ($Action -eq "Update" -and $rollbackPath -and -not $NoAutomaticRollback) {
        Write-Warning "Update validation failed. Restoring alterios-mcp $before."
        Invoke-PackageInstall -Path $rollbackPath -ForceReinstall
        Invoke-PostInstallChecks
        throw "Update failed and alterios-mcp $before was restored. Cause: $($installError.Exception.Message)"
    }
    throw
}

$after = Get-InstalledVersion
Save-ManagerAndState -Before $before -After $after -PackagePath $resolvedPackage.Path
Write-Host "Alterios MCP $Action completed: $before -> $after"
Write-Host "MCP executable: $(Join-Path $venv 'Scripts\alterios-mcp.exe')"
Write-Host "Future update: & '$managerPath' -Action Update"
Write-Host "Restart the MCP client so the old server process is replaced."
