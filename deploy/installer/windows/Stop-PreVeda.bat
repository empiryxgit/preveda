@echo off
cd /d "%~dp0"
set F=app\deploy\docker
if exist "%F%\docker-compose.drives.yml" (
  docker compose -f "%F%\docker-compose.yml" -f "%F%\docker-compose.drives.yml" down
) else (
  docker compose -f "%F%\docker-compose.yml" down
)
echo Stopped. Your saved results are kept. Run Install-PreVeda.bat to start again.
pause
