#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/ms-playwright"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
python -m playwright install chromium
