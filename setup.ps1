# Otto setup. Run from the Otto folder with:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# Makes Otto's private Python (3.12) OUTSIDE OneDrive, at  C:\Users\<you>\.otto\venv
# and installs everything into it. Safe to run again (e.g. after an update).

$venv = Join-Path $env:USERPROFILE ".otto\venv"
$py = Join-Path $venv "Scripts\python.exe"

function Step($text) { Write-Host ""; Write-Host "== $text ==" -ForegroundColor Cyan }
function Check($what) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $what. Copy the red text above and send it to Claude." -ForegroundColor Red
        exit 1
    }
}

Step "1/7 Finding Python 3.12"
& py -3.12 --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python 3.12 wasn't found. Install it with:  winget install -e --id Python.Python.3.12" -ForegroundColor Red
    exit 1
}

Step "2/7 Making Otto's private Python at $venv"
if (-not (Test-Path $py)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $venv) | Out-Null
    & py -3.12 -m venv $venv; Check "creating the private Python"
}
& $py -m pip install --upgrade pip --quiet; Check "updating pip"

Step "3/7 PyTorch with GPU support (about 3 GB, be patient)"
& $py -m pip install torch --index-url https://download.pytorch.org/whl/cu132; Check "installing PyTorch"

Step "4/7 Laya, Whisper, Kokoro and the Windows helpers"
& $py -m pip install -r requirements.txt; Check "installing requirements"

Step "5/7 English language model for Kokoro's pronunciation"
& $py -m pip install "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
Check "installing the English language model"

Step "6/7 Adding Otto to your PATH, so  otto  works in any terminal"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not ($userPath -split ";" | Where-Object { $_ -eq $PSScriptRoot })) {
    [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $PSScriptRoot), "User")
    Write-Host "Added $PSScriptRoot to your PATH. Open a NEW terminal for it to take effect." -ForegroundColor Green
} else { Write-Host "Already on your PATH." }

Step "7/7 Quick check"
& $py -c "import torch, laya, faster_whisper, kokoro, pywinauto, pynput; print('torch', torch.__version__, '| GPU visible:', torch.cuda.is_available()); print('laya', laya.__version__)"
Check "quick check"

$es = @("C:\Program Files\Everything\es.exe", "C:\Program Files (x86)\Everything\es.exe", (Join-Path $PSScriptRoot "tools\es.exe")) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($es) { Write-Host "Everything's es.exe found: $es" -ForegroundColor Green }
else { Write-Host "Note: es.exe (Everything command line) not found yet. File search needs it; see README step 3." -ForegroundColor Yellow }

if (-not (Test-Path (Join-Path $PSScriptRoot ".env")) -and -not (Test-Path (Join-Path $env:USERPROFILE ".otto\.env")) -and [string]::IsNullOrEmpty($env:OTTO_C0RE_KEY)) {
    Write-Host "Note: no .env with your keys found yet. See README step 2." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup done. Open a NEW terminal and type:  otto check   then   otto" -ForegroundColor Green
