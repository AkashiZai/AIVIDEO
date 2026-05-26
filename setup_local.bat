@echo off
echo ============================================
echo   CaptionForge AI - Local Setup Script
echo   Using RTX 4060 + large-v3 model
echo ============================================
echo.

REM Refresh PATH to find newly installed Python
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

echo [1/4] Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11 first.
    pause
    exit /b 1
)

echo.
echo [2/4] Installing backend dependencies...
cd /d "%~dp0backend"
pip install --upgrade pip
pip install fastapi==0.115.12 uvicorn[standard]==0.34.2 python-multipart==0.0.20 websockets>=12.0 numpy>=1.24.0

echo.
echo [3/4] Installing faster-whisper with CUDA support...
pip install faster-whisper>=1.1.0 ctranslate2>=4.0.0

echo.
echo [4/4] Checking ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo WARNING: ffmpeg not found. Installing via pip...
    pip install imageio-ffmpeg
    echo NOTE: You may also need to install ffmpeg manually:
    echo   winget install Gyan.FFmpeg
)

echo.
echo ============================================
echo   Setup complete! Run start_local.bat
echo   to start the backend server.
echo ============================================
pause
