@echo off

:: Check if the script is running with administrative privileges  
net session >nul 2>&1  
if %ERRORLEVEL% NEQ 0 (  
    echo Requesting administrative privileges...  
    powershell -Command "Start-Process -FilePath '%0' -Verb RunAs"  
    exit /b  
)  

set "TASK_NAME=NexusRFIDReaderMonitor"

:: Remove the scheduled task
schtasks /delete /tn "%TASK_NAME%" /f

if %ERRORLEVEL% EQU 0 (  
    echo Task "%TASK_NAME%" removed successfully.
) else (  
    echo Task "%TASK_NAME%" was not found or could not be removed.
)  

:: Get the directory of the running script  
set "SCRIPT_DIR=%~dp0.."
set "MONITOR_SCRIPT=monitor_nexus_rfid.bat"

:: Remove the monitoring script if it exists
if exist "%SCRIPT_DIR%\%MONITOR_SCRIPT%" (
    del "%SCRIPT_DIR%\%MONITOR_SCRIPT%"
    echo Monitoring script "%MONITOR_SCRIPT%" removed.
) else (
    echo Monitoring script "%MONITOR_SCRIPT%" was not found.
)

pause
