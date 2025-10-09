@echo off
setlocal

REM Build NexusRFIDReader executable on Windows using PyInstaller and spec
REM Usage: build.bat [--target win|linux]  (default: win)

set APP_NAME=NexusRFIDReader
set SPEC_FILE=%~dp0..\..\NexusRFIDReader.spec
set PROJECT_ROOT=%~dp0..\..\

set TARGET=win
if /I "%~1"=="--target" (
  set TARGET=%~2
)

if not exist "%SPEC_FILE%" (
  echo Spec file not found at %SPEC_FILE%
  exit /b 1
)

pushd "%PROJECT_ROOT%"

if /I "%TARGET%"=="win" (
  pyinstaller --clean --noconfirm "%SPEC_FILE%"
  if errorlevel 1 (
    echo Build failed.
    popd
    exit /b 1
  )
  echo Build completed. See dist\%APP_NAME%\%APP_NAME%.exe
) else if /I "%TARGET%"=="linux" (
  where wsl >nul 2>&1
  if errorlevel 1 (
    echo WSL not found. Install WSL to build Linux target from Windows, or build on Linux.
    popd
    exit /b 1
  )
  echo Building Linux binary via WSL...
  wsl bash -lc "cd '$(wslpath -a '%PROJECT_ROOT%')' && pyinstaller --clean --noconfirm NexusRFIDReader.spec"
  if errorlevel 1 (
    echo WSL build failed.
    popd
    exit /b 1
  )
  echo Linux build completed under dist/NexusRFIDReader/NexusRFIDReader
) else (
  echo Unknown target: %TARGET%
  popd
  exit /b 1
)

popd
endlocal

