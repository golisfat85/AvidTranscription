@echo off
REM Install the Avid Transcription panel into Avid Media Composer (Windows).
REM Run once after installing the Python package.

SET PANEL_NAME=AvidTranscription
SET SCRIPT_DIR=%~dp0
SET PANEL_SRC=%SCRIPT_DIR%..\avid_panel

SET AVID_PANELS_DIR=%APPDATA%\Avid\Avid Media Composer\SupportingFiles\Panels
SET DEST=%AVID_PANELS_DIR%\%PANEL_NAME%

echo Installing Avid Transcription panel...
echo   Source      : %PANEL_SRC%
echo   Destination : %DEST%

IF NOT EXIST "%DEST%" mkdir "%DEST%"
xcopy /E /Y /I "%PANEL_SRC%\*" "%DEST%\"

echo.
echo Panel installed successfully.
echo.
echo Next steps:
echo   1. Start the transcription server:
echo        avid-transcription --server
echo      or double-click:
echo        %SCRIPT_DIR%start_server.bat
echo.
echo   2. Open Avid Media Composer.
echo   3. Go to  Windows ^> Panels ^> AvidTranscription
echo      (You may need to restart Media Composer once after first install.)
echo.
pause
