# Build the optional CUDA pack (cuda.zip) for the installer.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File installer\make_cuda_pack.ps1
#
# Output: installer\Output\cuda.zip  (layout: cuda/<pkg>/bin/*.dll)
#
# Upload cuda.zip to a GitHub Release. The installer downloads it when the user
# keeps the "NVIDIA GPU support" component selected, then unpacks it next to
# Cyctitles.exe as a "cuda" folder (picked up by cyctitles.cuda_env).

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = "..\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Virtual environment not found (.venv)." -ForegroundColor Red
    exit 1
}

$staging = Join-Path $env:TEMP "cyctitles_cuda_staging"
if (Test-Path $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null

# Copy every nvidia/<pkg>/bin/*.dll into staging\cuda\<pkg>\bin
& $python -c @"
import nvidia, shutil
from pathlib import Path
staging = Path(r'$staging')
dest_root = staging / 'cuda'
for base in nvidia.__path__:
    for pkg in Path(base).iterdir():
        bin_dir = pkg / 'bin'
        if bin_dir.is_dir() and any(bin_dir.glob('*.dll')):
            dest = dest_root / pkg.name / 'bin'
            dest.mkdir(parents=True, exist_ok=True)
            for dll in bin_dir.glob('*.dll'):
                shutil.copy2(dll, dest / dll.name)
            print('packed', pkg.name)
"@
if (-not $?) { exit 1 }

$outDir = Join-Path $PSScriptRoot "Output"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
$zip = Join-Path $outDir "cuda.zip"
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }

# Use 7-Zip if available (much faster than Compress-Archive for ~2 GB).
$sevenZip = @(
    "$env:ProgramFiles\7-Zip\7z.exe",
    "${env:ProgramFiles(x86)}\7-Zip\7z.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($sevenZip) {
    & $sevenZip a -tzip -mx=5 $zip (Join-Path $staging "cuda")
} else {
    Write-Host "7-Zip not found; using Compress-Archive (slow for large files)..." -ForegroundColor Yellow
    Compress-Archive -Path (Join-Path $staging "cuda") -DestinationPath $zip -CompressionLevel Optimal
}
if (-not $?) { exit 1 }

Remove-Item -LiteralPath $staging -Recurse -Force

$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host ""
Write-Host "Done. $zip ($mb MB)" -ForegroundColor Green
Write-Host "Upload it to a GitHub Release and put the URL in installer\Cyctitles.iss."
