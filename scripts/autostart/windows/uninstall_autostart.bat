@echo off
setlocal

set APP_NAME=NexusRFIDReader

reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v %APP_NAME% /f

if %ERRORLEVEL% EQU 0 (
  echo Removed autostart entry for %APP_NAME%.
) else (
  echo No autostart entry found or failed to remove.
)

endlocal
@echo off
setlocal

set APP_NAME=NexusRFIDReader

reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v %APP_NAME% /f

if %ERRORLEVEL% EQU 0 (
  echo Removed autostart entry for %APP_NAME%.
) else (
  echo No autostart entry found or failed to remove.
)

endlocal

