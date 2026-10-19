# Build a standalone Cyctitles for Windows.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1            # onedir (folder, with CUDA)
#   powershell -ExecutionPolicy Bypass -File build.ps1 -OneFile   # single .exe (with CUDA)
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Lite      # single .exe, CPU-only
#                                                                 # (used by the installer)
#
# Output: dist\Cyctitles\Cyctitles.exe  (onedir)
#         dist\Cyctitles.exe            (onefile / lite)

param(
    [switch]$OneFile,
    [switch]$Lite
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Virtual environment not found. Run the setup steps in README.md first." -ForegroundColor Red
    exit 1
}

Write-Host "Ensuring PyInstaller is installed..."
$uv = $null
$cmd = Get-Command uv -ErrorAction SilentlyContinue
if ($cmd) { $uv = $cmd.Source }
if (-not $uv) {
    foreach ($candidate in @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe")
    )) {
        if (Test-Path -LiteralPath $candidate) { $uv = $candidate; break }
    }
}
if ($uv) {
    & $uv pip install --python $python pyinstaller
} else {
    & $python -m pip install pyinstaller
}
if (-not $?) { exit 1 }

if ($Lite) {
    $spec = "cyctitles_lite.spec"
} elseif ($OneFile) {
    $spec = "cyctitles_onefile.spec"
} else {
    $spec = "cyctitles.spec"
}

Write-Host "Building with PyInstaller ($spec)..."
& $python -m PyInstaller --noconfirm --clean $spec
if (-not $?) { exit 1 }

Write-Host ""
if ($Lite -or $OneFile) {
    Write-Host "Done. Run dist\Cyctitles.exe" -ForegroundColor Green
} else {
    Write-Host "Done. Run dist\Cyctitles\Cyctitles.exe" -ForegroundColor Green
}
