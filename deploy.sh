#!/bin/bash
# Quick deployment script for DevOps Butler

echo "🤖 DevOps Butler - Deployment Helper"
echo "======================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found!"
    echo "Creating from .env.example..."
    cp .env.example .env
    echo "✅ Created .env - Please edit it with your credentials"
    echo ""
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.11+"
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "🔧 Activating virtual environment..."
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt

# Install Playwright
echo "🌐 Installing Playwright browsers..."
playwright install chromium

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 Starting DevOps Butler..."
echo "   Access at: http://localhost:8000"
echo ""

# Start server
python start.py
