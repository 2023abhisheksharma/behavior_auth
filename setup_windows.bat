@echo off
setlocal enabledelayedexpansion

echo ================================================================
echo  🛡️  CHRONOS-AUTH: ONE-CLICK WINDOWS INSTALLER
echo ================================================================
echo Setting up continuous biometric authentication on Windows...
echo.

cd /d "%~dp0"

:: 1. Check Python installation
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found on your system!
    echo Please download Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: 2. Setup Virtual Environment
if not exist "python_engine\venv" (
    echo [*] Creating Python virtual environment...
    python -m venv python_engine\venv
)

echo [*] Installing required machine learning libraries...
call python_engine\venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
:: 3. Train the calibrated model if missing
if not exist "python_engine\models\chronos\chronos_classifier.pkl" (
    echo [*] Calibrating initial AI biometric weights...
    python python_engine\train_chronos.py >nul 2>&1
)

:: 4. Create Desktop Shortcut via VBScript
echo [*] Creating Desktop Shortcut 'Chronos Auth'...
set SCRIPT="%TEMP%\create_shortcut.vbs"
echo Set oWS = WScript.CreateObject("WScript.Shell") >> %SCRIPT%
echo sLinkFile = oWS.ExpandEnvironmentStrings("%USERPROFILE%\Desktop\Chronos-Auth.lnk") >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "%~dp0app_windows.bat" >> %SCRIPT%
echo oLink.WorkingDirectory = "%~dp0" >> %SCRIPT%
echo oLink.Description = "Chronos Continuous Behavioral Authentication Hub" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%
cscript /nologo %SCRIPT%
del %SCRIPT%

echo.
echo ================================================================
echo  🎉 INSTALLATION COMPLETE!
echo ================================================================
echo • Desktop Shortcut: 'Chronos-Auth' created on your Desktop.
echo • Launching application hub now...
echo ================================================================
echo.

call "%~dp0app_windows.bat"
