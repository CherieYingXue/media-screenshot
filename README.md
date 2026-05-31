# News Media Screenshot App

Capture live homepage screenshots from major news sites with one tap.

## Sites included

- CNN, NY Times, Washington Post, CNBC, Bloomberg, Fox News, NY Post, LA Times

## Quick start

Double-click **start.bat**, or run:

```bash
pip install -r requirements.txt
playwright install chromium
python server.py
```

Open the URL printed in the terminal. Use the **phone URL** (same Wi-Fi) on your cellphone.

## Phone access

1. Start the server on your PC (`start.bat` or `python server.py`)
2. Connect your phone to the **same Wi-Fi** as the PC
3. Open the link shown as `On your phone: http://192.168.x.x:3847`

If that does not work, allow port 3847 through Windows Firewall for private networks.
