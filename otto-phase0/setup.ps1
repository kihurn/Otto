# Otto Phase 0 setup: makes a private Python folder (.venv) and installs everything into it.
# Run from this folder with:  powershell -ExecutionPolicy Bypass -File .\setup.ps1

$py = ".\.venv\Scripts\python.exe"

function Step($text) { Write-Host ""; Write-Host "== $text ==" -ForegroundColor Cyan }
function Check($what) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $what. Copy the red text above and send it to Claude." -ForegroundColor Red
        exit 1
    }
}

Step "1/4 Making the .venv folder"
if (-not (Test-Path $py)) { python -m venv .venv; Check "creating .venv" }
& $py --version

Step "2/4 Updating pip"
& $py -m pip install --upgrade pip --quiet; Check "updating pip"

Step "3/4 Installing PyTorch with GPU support (about 3 GB, be patient)"
& $py -m pip install torch --index-url https://download.pytorch.org/whl/cu132; Check "installing PyTorch"

Step "4/4 Installing Laya, faster-whisper and helpers"
& $py -m pip install -r requirements.txt; Check "installing requirements"

Step "Quick check"
& $py -c "import torch, laya, faster_whisper; print('torch', torch.__version__, '| GPU visible:', torch.cuda.is_available()); print('laya', laya.__version__, '| faster-whisper', faster_whisper.__version__)"
Check "quick check"

Write-Host ""
Write-Host "Setup done. Next: .\.venv\Scripts\python.exe run_all.py" -ForegroundColor Green
