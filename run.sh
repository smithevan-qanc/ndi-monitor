#!/bin/bash

# NDI Monitor Web App - macOS Quick Start Script

echo "🎬 Starting NDI Monitor Web App (macOS Simulated Version)..."
echo ""

# Check if dependencies are installed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    python3 -m pip install -r requirements.txt
    echo ""
fi

echo "🚀 Starting server on http://127.0.0.1:8000"
echo ""
echo "📝 Instructions:"
echo "   1. Open http://127.0.0.1:8000 in your browser"
echo "   2. Hover over the right edge to open settings"
echo "   3. Select a simulated source and click 'Monitor'"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
