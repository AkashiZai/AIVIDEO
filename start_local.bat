@echo off
echo ============================================
echo   CaptionForge AI - Local Backend
echo   GPU: RTX 4060 + Whisper large-v3
echo ============================================
echo.

REM Refresh PATH
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

cd /d "%~dp0backend"

echo Starting backend on http://localhost:8000 ...
echo Make sure frontend vite proxy points to localhost:8000
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
