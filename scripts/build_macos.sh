#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python3 -m pytest -q
python3 -m PyInstaller --noconfirm --clean --windowed --onedir --name WealthathonSimulator --collect-data wealthathon main.py
"dist/WealthathonSimulator.app/Contents/MacOS/WealthathonSimulator" --self-test
rm -f WealthathonSimulator_macOS.zip
ditto -c -k --sequesterRsrc --keepParent dist/WealthathonSimulator.app WealthathonSimulator_macOS.zip
echo "Built WealthathonSimulator_macOS.zip"
