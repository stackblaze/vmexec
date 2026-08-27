@echo off
color 0B
echo ==========================================================
echo           Building VM Backup Release Package
echo ==========================================================
echo.

:: Ensure run from script directory
cd /d "%~dp0"

echo [1/3] Preparing Build Directory...
if exist "VMBackupEnterprise_Release.zip" del /q "VMBackupEnterprise_Release.zip"
if exist "build_temp" rmdir /s /q "build_temp"

mkdir "build_temp"

echo [2/3] Copying Core Application Files...
:: Copy every module rather than an explicit list. The old list had drifted and
:: silently omitted api\, services\, static\ and several transports, producing
:: a release zip that could not start.
xcopy *.py "build_temp\" /Y /Q >nul
xcopy *.bat "build_temp\" /Y /Q >nul
copy requirements.txt build_temp\ >nul
xcopy api "build_temp\api" /E /I /Y /Q >nul
xcopy services "build_temp\services" /E /I /Y /Q >nul
xcopy templates "build_temp\templates" /E /I /Y /Q >nul
xcopy static "build_temp\static" /E /I /Y /Q >nul
xcopy scripts "build_temp\scripts" /E /I /Y /Q >nul
:: vendor\vddk stays EMPTY on purpose: the VDDK is proprietary and cannot be
:: redistributed. install-vddk.sh / the Settings page explain how to supply it.
mkdir "build_temp\vendor\vddk" 2>nul

echo Waiting for file system to settle...
timeout /t 2 /nobreak >nul

echo [3/3] Zipping the Release Package...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'build_temp\*' -DestinationPath 'VMBackupEnterprise_Release.zip' -Force"

echo Cleaning up temp files...
rmdir /s /q "build_temp"

echo.
echo ==========================================================
echo SUCCESS! Your production deployment file is ready:
echo File: VMBackupEnterprise_Release.zip
echo ==========================================================
echo.
echo To upgrade or install on the Win2019 server:
echo 1. Copy 'VMBackupEnterprise_Release.zip' to the server.
echo 2. Extract it into your existing installation folder (overwrite identical files).
echo    - Important: This will NOT overwrite or delete your 'data' folder (your DB/Logs are safe).
echo 3. Right click 'setup.bat' in the server and 'Run as Administrator'.
echo.
pause
