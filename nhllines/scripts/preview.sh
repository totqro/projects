#!/bin/bash
# Quick preview of the web dashboard

echo "Starting local web server..."
echo "Open your browser to: http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

python3 -m http.server 8000
