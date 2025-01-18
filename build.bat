@echo off
python -c "import pyinstaller" 2>nul
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller is not installed. Installing now...
    pip install pyinstaller
) else (
    echo PyInstaller is already installed
)
pyinstaller --onefile --noconsole gui.py -n DanisenBot
pause