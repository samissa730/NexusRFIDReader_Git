@echo off
setlocal

if "%~1"=="" (
  echo Usage: install_autostart.bat "C:\path\to\NexusRFIDReader.exe"
  exit /b 1
)

set EXE_PATH=%~1
set APP_NAME=NexusRFIDReader

reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v %APP_NAME% /t REG_SZ /d "%EXE_PATH%" /f

if %ERRORLEVEL% EQU 0 (
  echo Added autostart entry for %APP_NAME%.
) else (
  echo Failed to add autostart entry.
  exit /b 1
)

endlocal
@echo off
setlocal

if "%~1"=="" (
  echo Usage: install_autostart.bat "C:\path\to\NexusRFIDReader.exe"
  exit /b 1
)

set EXE_PATH=%~1
set APP_NAME=NexusRFIDReader

REM Create HKCU Run entry
reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v %APP_NAME% /t REG_SZ /d "%EXE_PATH%" /f

if %ERRORLEVEL% EQU 0 (
  echo Added autostart entry for %APP_NAME%.
) else (
  echo Failed to add autostart entry.
  exit /b 1
)

endlocal

