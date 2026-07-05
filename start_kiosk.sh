#!/bin/bash

# Kiosk Startup Script
# Starts Flask server and opens the browser in kiosk mode

# Port and Host configurations
PORT=${KIOSK_PORT:-8080}
HOST=${KIOSK_HOST:-"127.0.0.1"}
URL="http://$HOST:$PORT/kiosk/"

# Clean up background server on exit
cleanup() {
    echo "Stopping Flask server (PID: $FLASK_PID)..."
    kill $FLASK_PID 2>/dev/null
    exit 0
}
trap cleanup EXIT INT TERM

echo "=========================================="
echo "Starting Touchscreen Kiosk Portal..."
echo "URL: $URL"
echo "=========================================="

# 1. Start Flask app in the background
# Try using virtual environment first, otherwise python3/python
if [ -f "./venv/bin/python" ]; then
    PYTHON_CMD="./venv/bin/python"
elif [ -f "./venv/bin/python3" ]; then
    PYTHON_CMD="./venv/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: Python is not installed or not in PATH." >&2
    exit 1
fi

# Run the Flask app
$PYTHON_CMD app.py &
FLASK_PID=$!

# 2. Wait for the Flask app to become healthy
echo "Waiting for Flask server to start..."
MAX_ATTEMPTS=30
ATTEMPT=0
while true; do
    if curl -s -f "$URL/health" &>/dev/null; then
        echo "Flask server is up and healthy."
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        echo "Error: Flask server failed to start within 30 seconds." >&2
        kill $FLASK_PID 2>/dev/null
        exit 1
    fi
    sleep 1
done

# 3. Detect operating system and launch browser in kiosk mode
OS_TYPE=$(uname -s)

if [ "$OS_TYPE" = "Darwin" ]; then
    # macOS
    echo "Detected macOS. Launching Google Chrome..."
    CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if [ -f "$CHROME_PATH" ]; then
        "$CHROME_PATH" \
            --kiosk \
            --no-first-run \
            --no-default-browser-check \
            --disable-session-crashed-bubble \
            --disable-infobars \
            "$URL"
    else
        # Fallback to default open command
        open -a "Google Chrome" --args --kiosk "$URL" || open "$URL"
    fi
else
    # Linux / Raspberry Pi
    echo "Detected Linux. Searching for compatible browser..."
    
    # Common kiosk-friendly browser commands
    BROWSERS=("chromium-browser" "chromium" "google-chrome" "firefox")
    BROWSER_CMD=""
    
    for b in "${BROWSERS[@]}"; do
        if command -v "$b" &>/dev/null; then
            BROWSER_CMD="$b"
            break
        fi
    done
    
    if [ -z "$BROWSER_CMD" ]; then
        echo "Warning: No standard browser (Chromium, Chrome, Firefox) found."
        echo "Please open your browser manually and navigate to: $URL"
        # Wait for user input to keep server alive
        read -p "Press Enter to exit..."
    else
        echo "Launching $BROWSER_CMD in kiosk mode..."
        if [ "$BROWSER_CMD" = "firefox" ]; then
            # Firefox kiosk mode
            firefox --kiosk "$URL"
        else
            # Chromium / Chrome kiosk mode
            $BROWSER_CMD \
                --kiosk \
                --noerrdialogs \
                --disable-infobars \
                --disable-session-crashed-bubble \
                --disable-translate \
                --check-for-update-interval=31536000 \
                "$URL"
        fi
    fi
fi
