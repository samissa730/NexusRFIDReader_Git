@echo off

echo Building NexusRFID Reader executable...

:: Check if PyInstaller is installed
pyinstaller --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller is not installed. Installing...
    pip install pyinstaller
)

:: Set the icon path
set ICON_PATH=ui\img\icon.png
if not exist "%ICON_PATH%" (
    echo Warning: Icon file not found at %ICON_PATH%
    set ICON_PATH=
)

:: Build command
if defined ICON_PATH (
    pyinstaller --clean --onefile --icon="%ICON_PATH%" --name=NexusRFIDReader main.py
) else (
    pyinstaller --clean --onefile --name=NexusRFIDReader main.py
)

:: Check if build was successful
if exist "dist\NexusRFIDReader.exe" (
    echo Build successful! Executable created at: dist\NexusRFIDReader.exe
) else (
    echo Build failed!
    pause
    exit /b 1
)

pause
