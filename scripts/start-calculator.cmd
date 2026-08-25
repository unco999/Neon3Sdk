@echo off
setlocal EnableExtensions

rem One-click release calculator example.
set "SDK_ROOT=%~dp0.."
for %%I in ("%SDK_ROOT%") do set "SDK_ROOT=%%~fI"
if "%NEON_ROOT%"=="" set "NEON_ROOT=%SDK_ROOT%\release"
if "%NEON_PROFILE%"=="" set "NEON_PROFILE=release"

if not exist "%SDK_ROOT%\packages\node-sdk\package.json" (
    echo SDK package not found: %SDK_ROOT%
    exit /B 1
)
if not exist "%SDK_ROOT%\packages\node-sdk\node_modules" (
    echo Installing Node SDK dependencies...
    call npm --prefix "%SDK_ROOT%\packages\node-sdk" install
    if errorlevel 1 exit /B 1
)

echo Starting Neon3 calculator with %NEON_PROFILE% runtime from %NEON_ROOT%.
set "NEON_ROOT=%NEON_ROOT%"
set "NEON_PROFILE=%NEON_PROFILE%"
if not exist "%NEON_ROOT%\target\%NEON_PROFILE%\neon-wgpu-runtime.exe" (
    echo Building the SDK release runtime from GitHub...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SDK_ROOT%\scripts\build-neon3-release.ps1" -SdkRoot "%SDK_ROOT%" -ReleaseRoot "%NEON_ROOT%"
    if errorlevel 1 exit /B 1
)
echo Starting Neon3 calculator with %NEON_PROFILE% runtime from %NEON_ROOT%.
call npm --prefix "%SDK_ROOT%\packages\node-sdk" run calculator -- %*
exit /B %ERRORLEVEL%
