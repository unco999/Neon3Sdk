<#
.SYNOPSIS
  Deterministic local release-readiness pipeline for Neon3, its SDK bundle,
  and the Bevy integration plugin.

.DESCRIPTION
  This script deliberately does not commit, push, tag, publish to crates.io,
  npm, or PyPI.  It verifies the real Canvas producer -> UI runtime -> WGPU
  consumer path using Neon3's existing public RPC probe, runs each dependent
  package's focused checks, and emits JSONL records plus a final manifest.

  -BuildRuntime is intentionally gated by a tag pointing at the local Neon3
  HEAD.  That prevents an SDK runtime bundle from claiming a release version
  that has not been created from the exact validated source.
#>
[CmdletBinding()]
param(
    [string]$NeonRoot = "D:\Neon3",
    [string]$SdkRoot = "D:\Neon3Sdk",
    [string]$BevyRoot = "D:\bevy-nui-plugins",
    [string]$ReleaseRef = "",
    [switch]$BuildRuntime,
    [string]$ManifestPath = ""
)

$ErrorActionPreference = "Stop"
$startedAt = [DateTime]::UtcNow.ToString("o")
$records = New-Object System.Collections.Generic.List[object]
$script:lastStepPassed = $false

function Emit([string]$Callback, [hashtable]$Data) {
    $record = [ordered]@{ callback = $Callback; timestamp_utc = [DateTime]::UtcNow.ToString("o") } + $Data
    $records.Add([pscustomobject]$record)
    [Console]::Out.WriteLine(($record | ConvertTo-Json -Depth 12 -Compress))
}

function Require-Directory([string]$Name, [string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Name directory does not exist: $Path"
    }
}

function Invoke-Step([string]$Name, [string]$WorkingDirectory, [scriptblock]$Action) {
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $script:lastStepPassed = $false
    try {
        & $Action
        $exit = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        if ($exit -ne 0) { throw "$Name exited with code $exit" }
        Emit "release.step" @{ name = $Name; cwd = $WorkingDirectory; result = "passed"; duration_ms = $clock.ElapsedMilliseconds }
        $script:lastStepPassed = $true
    } catch {
        Emit "release.step" @{ name = $Name; cwd = $WorkingDirectory; result = "failed"; duration_ms = $clock.ElapsedMilliseconds; error = $_.Exception.Message }
    }
}

function Assert-RuntimePin([string]$Version) {
    $pythonRuntime = Join-Path $SdkRoot "packages\python-sdk\src\neon3_sdk\runtime.py"
    $nodeRuntime = Join-Path $SdkRoot "packages\node-sdk\src\runtime.ts"
    foreach ($path in @($pythonRuntime, $nodeRuntime)) {
        $source = Get-Content -LiteralPath $path -Raw
        if ($source -notmatch "NEON3_RUNTIME_VERSION" -or ($source -notmatch [regex]::Escape("`"latest`"") -and $source -notmatch [regex]::Escape("`"$Version`""))) {
            throw "Runtime selection mismatch in $path. Use latest or update both SDK runtime constants to $Version before distributing this bundle."
        }
    }
}

try {
    Require-Directory "Neon3" $NeonRoot
    Require-Directory "Neon3Sdk" $SdkRoot
    Require-Directory "bevy-nui-plugins" $BevyRoot
    foreach ($command in @("git", "cargo", "python", "npm")) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Required command not found: $command" }
    }

    $neonHead = (& git -C $NeonRoot rev-parse HEAD).Trim()
    $neonBranch = (& git -C $NeonRoot branch --show-current).Trim()
    $neonStatus = @(& git -C $NeonRoot status --porcelain)
    $ahead = [int]((& git -C $NeonRoot rev-list --count '@{u}..HEAD' 2>$null).Trim())
    Emit "release.preflight" @{ neon_head = $neonHead; neon_branch = $neonBranch; dirty = ($neonStatus.Count -gt 0); ahead_of_upstream = $ahead; release_ref = $ReleaseRef; build_runtime = [bool]$BuildRuntime; result = if ($neonStatus.Count -eq 0) { "passed" } else { "failed" } }
    if ($neonStatus.Count -gt 0) { throw "Neon3 has uncommitted changes; commit or stash before creating a release bundle." }
    if ($BuildRuntime) {
        if ([string]::IsNullOrWhiteSpace($ReleaseRef)) { throw "-BuildRuntime requires -ReleaseRef (for example v0.2.2)." }
        Assert-RuntimePin $ReleaseRef
        $tagCommit = (& git -C $NeonRoot rev-parse "$ReleaseRef^{commit}" 2>$null).Trim()
        if ($LASTEXITCODE -ne 0 -or $tagCommit -ne $neonHead) { throw "ReleaseRef '$ReleaseRef' must be a tag/ref that resolves to Neon3 HEAD $neonHead." }
        if ($ahead -gt 0) { throw "Neon3 is $ahead commit(s) ahead of upstream. Push the release commit/tag before building the distributable SDK bundle." }
    }

    $passed = $true
    Invoke-Step "neon.canvas.probe-build" $NeonRoot { Push-Location $NeonRoot; try { & cargo build -p neon-ui-runtime --bin neon-ui-runtime --bin canvas_window_probe -p neon-wgpu-runtime --bin neon-wgpu-runtime } finally { Pop-Location } }
    $passed = $script:lastStepPassed -and $passed
    Invoke-Step "neon.canvas.window-probe" $NeonRoot { Push-Location $NeonRoot; try { & cargo run -p neon-ui-runtime --bin canvas_window_probe } finally { Pop-Location } }
    $passed = $script:lastStepPassed -and $passed
    Invoke-Step "neon.workspace-check" $NeonRoot { Push-Location $NeonRoot; try { & cargo check --workspace } finally { Pop-Location } }
    $passed = $script:lastStepPassed -and $passed
    Invoke-Step "sdk.python-tests" (Join-Path $SdkRoot "packages\python-sdk") { Push-Location (Join-Path $SdkRoot "packages\python-sdk"); try { & python -m unittest discover -s tests -v } finally { Pop-Location } }
    $passed = $script:lastStepPassed -and $passed
    Invoke-Step "sdk.node-tests" (Join-Path $SdkRoot "packages\node-sdk") { Push-Location (Join-Path $SdkRoot "packages\node-sdk"); try { & npm test } finally { Pop-Location } }
    $passed = $script:lastStepPassed -and $passed
    Invoke-Step "bevy.plugin-check" $BevyRoot { Push-Location $BevyRoot; try { & cargo check } finally { Pop-Location } }
    $passed = $script:lastStepPassed -and $passed

    if ($BuildRuntime) {
        Invoke-Step "sdk.runtime-bundle" $SdkRoot { & (Join-Path $SdkRoot "scripts\build-neon3-release.ps1") -SourceRoot $NeonRoot -Ref $ReleaseRef -SdkRoot $SdkRoot }
        $passed = $script:lastStepPassed -and $passed
    }

    $finalResult = if ($passed) { "passed" } else { "failed" }
    $manifest = [ordered]@{ callback = "release.result"; started_at_utc = $startedAt; finished_at_utc = [DateTime]::UtcNow.ToString("o"); neon = @{ root = $NeonRoot; head = $neonHead; branch = $neonBranch; ahead_of_upstream = $ahead }; sdk_root = $SdkRoot; bevy_root = $BevyRoot; release_ref = $ReleaseRef; runtime_bundle_built = [bool]$BuildRuntime; steps = $records; result = $finalResult }
    if ([string]::IsNullOrWhiteSpace($ManifestPath)) { $ManifestPath = Join-Path $SdkRoot "release\neon3-stack-validation.json" }
    $manifestDirectory = Split-Path -Parent $ManifestPath
    New-Item -ItemType Directory -Force -Path $manifestDirectory | Out-Null
    $manifest | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
    Emit "release.result" @{ manifest_path = $ManifestPath; release_ref = $ReleaseRef; runtime_bundle_built = [bool]$BuildRuntime; result = $finalResult }
    if (-not $passed) { exit 1 }
} catch {
    Emit "release.result" @{ result = "failed"; error = $_.Exception.Message }
    exit 1
}
