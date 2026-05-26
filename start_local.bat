@echo off
echo ============================================
echo   CaptionForge AI - Local Backend
echo   GPU: RTX 4060 + Whisper large-v3
echo   Thai: Gemini AI Post-Correction
echo ============================================
echo.

REM Refresh PATH — Python + CUDA libraries from pip packages
set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python311"
set "CUDA_LIBS=%PYDIR%\Lib\site-packages\nvidia\cublas\bin;%PYDIR%\Lib\site-packages\nvidia\cudnn\bin;%PYDIR%\Lib\site-packages\nvidia\cuda_runtime\bin"
set "PATH=%CUDA_LIBS%;%PYDIR%;%PYDIR%\Scripts;%PATH%"

REM Gemini API key for Thai AI correction (paste your key here)
REM Get a free key from: https://aistudio.google.com/apikey
if not defined GEMINI_API_KEY (
    set "GEMINI_API_KEY=AIzaSyB5jjLrRIj-3n0HOg_wzPHsMBbt9ihF3eg"
)

cd /d "%~dp0backend"

echo Starting backend on http://localhost:8000 ...
echo Make sure frontend vite proxy points to localhost:8000
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
