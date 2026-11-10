$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m PyInstaller --noconfirm --clean --windowed --onedir --name WealthathonSimulator --collect-data wealthathon main.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ".\dist\WealthathonSimulator\WealthathonSimulator.exe" --self-test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Compress-Archive -Path ".\dist\WealthathonSimulator" -DestinationPath ".\WealthathonSimulator_Windows.zip" -Force
Write-Output "Built WealthathonSimulator_Windows.zip"
