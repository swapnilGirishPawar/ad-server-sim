@echo off
title Ad Server Simulator  (keep this window open)
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
  echo(
  echo   The simulator is not set up on this computer yet.
  echo   Please ask a developer to do the one-time setup in setup.md.
  echo(
  pause
  exit /b 1
)

echo(
echo   Starting the Ad Server Simulator...
echo   Your web browser will open at  http://localhost:8090  in a few seconds.
echo(
echo   KEEP THIS WINDOW OPEN while you use the tool.
echo   To STOP the tool, just close this window.
echo(

rem Open the dashboard in the browser after a short delay (gives the server time to start)
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://localhost:8090'"

".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8090
