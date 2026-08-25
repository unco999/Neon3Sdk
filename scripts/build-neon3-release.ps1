param(
    [string]$Repository = "https://github.com/unco999/Neon3-CiJian.git",
    [string]$Ref = "",
    [string]$SdkRoot = "",
    [string]$ReleaseRoot = "",
    [switch]$Offline
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SdkRoot)) { $SdkRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..")) }
if ([string]::IsNullOrWhiteSpace($ReleaseRoot)) { $ReleaseRoot = Join-Path $SdkRoot "release" }
$SdkRoot = [IO.Path]::GetFullPath($SdkRoot)
$ReleaseRoot = [IO.Path]::GetFullPath($ReleaseRoot)
$cacheRoot = Join-Path $SdkRoot ".cache\neon3"
$sourceRoot = Join-Path $cacheRoot "source"
$sourceCargo = Join-Path $sourceRoot "Cargo.toml"

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { throw "Rust/Cargo is required to build Neon3 from GitHub." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is required to download Neon3 from GitHub." }
New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null

if ([string]::IsNullOrWhiteSpace($Ref)) {
    $Ref = "master"
    if (-not $Offline) {
        $remoteHead = @(& git ls-remote --symref $Repository HEAD 2>$null)
        foreach ($line in $remoteHead) {
            if ($line -match '^ref:\s+refs/heads/([^\s]+)\s+HEAD') { $Ref = $Matches[1]; break }
        }
    }
}

if (-not (Test-Path -LiteralPath $sourceCargo)) {
    if ($Offline) { throw "Offline build requested but the cached Neon3 source is missing: $sourceRoot" }
    if (Test-Path -LiteralPath $sourceRoot) { Remove-Item -LiteralPath $sourceRoot -Recurse -Force }
    Write-Host "Downloading Neon3 from $Repository ($Ref)..."
    & git clone --depth 1 --branch $Ref $Repository $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw "Unable to clone Neon3 from $Repository" }
} elseif (-not $Offline) {
    Write-Host "Refreshing Neon3 source from $Repository ($Ref)..."
    & git -C $sourceRoot fetch --depth 1 origin $Ref
    if ($LASTEXITCODE -eq 0) {
        & git -C $sourceRoot reset --hard FETCH_HEAD
        if ($LASTEXITCODE -ne 0) { throw "Unable to update the cached Neon3 source." }
    } else {
        Write-Warning "GitHub refresh failed; using the existing cached source."
    }
}

Push-Location $sourceRoot
try {
    Write-Host "Building Neon3 release services..."
    & cargo build --release -p neon-eventd -p neon-ui-runtime -p neon-wgpu-runtime
    if ($LASTEXITCODE -ne 0) { throw "Neon3 release build failed with exit code $LASTEXITCODE" }
    $commit = (& git rev-parse HEAD).Trim()
} finally {
    Pop-Location
}

$target = Join-Path $sourceRoot "target\release"
$releaseTarget = Join-Path $ReleaseRoot "target\release"
New-Item -ItemType Directory -Force -Path $releaseTarget | Out-Null
foreach ($name in @("neon-eventd.exe", "neon-ui-runtime.exe", "neon-wgpu-runtime.exe")) {
    $source = Join-Path $target $name
    if (-not (Test-Path -LiteralPath $source)) { throw "Expected release binary missing: $source" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $releaseTarget $name) -Force
}
$assets = Join-Path $sourceRoot "assets"
if (Test-Path -LiteralPath $assets) { Copy-Item -LiteralPath $assets -Destination (Join-Path $ReleaseRoot "assets") -Recurse -Force }

$metadata = [ordered]@{
    status = "passed"
    repository = $Repository
    ref = $Ref
    commit = $commit
    release_root = $ReleaseRoot
    binaries = @("neon-eventd.exe", "neon-ui-runtime.exe", "neon-wgpu-runtime.exe")
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ReleaseRoot "neon3-release.json") -Encoding UTF8
$metadata | ConvertTo-Json -Compress
