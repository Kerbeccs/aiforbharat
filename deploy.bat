@echo off
REM Quick deployment script for DevOps Butler (Windows)

echo 🤖 DevOps Butler - Deployment Helper
echo ======================================
echo.

REM Check if .env exists
if not exist .env (
    echo ⚠️  .env file not found!
    echo Creating from .env.example...
    copy .env.example .env
    echo ✅ Created .env - Please edit it with your credentials
    echo.
    pause
    exit /b 1
)

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.11+
    pause
    exit /b 1
)

echo ✅ Python found
python --version

REM Check if venv exists
if not exist venv (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate venv
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
pip install -q -r requirements.txt

REM Install Playwright
echo 🌐 Installing Playwright browsers...
playwright install chromium

echo.
echo ✅ Setup complete!
echo.
echo 🚀 Starting DevOps Butler...
echo    Access at: http://localhost:8000
echo.

REM Start server
python start.py
