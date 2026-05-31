import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

app = Flask(__name__, static_folder="public", static_url_path="")
PORT = int(os.environ.get("PORT", 3847))
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

SITES = [
    {"id": "cnn", "name": "CNN", "url": "https://www.cnn.com"},
    {"id": "nytimes", "name": "New York Times", "url": "https://www.nytimes.com"},
    {"id": "washingtonpost", "name": "Washington Post", "url": "https://www.washingtonpost.com"},
    {"id": "cnbc", "name": "CNBC", "url": "https://www.cnbc.com"},
    {"id": "foxnews", "name": "Fox News", "url": "https://www.foxnews.com"},
    {"id": "nypost", "name": "NY Post", "url": "https://nypost.com"},
    {"id": "latimes", "name": "LA Times", "url": "https://www.latimes.com"},
]

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}

# Playwright sync API must run outside Flask/gunicorn's asyncio loop.
_playwright_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")
_browser = None
_playwright = None


def _get_browser():
    global _playwright, _browser
    from playwright.sync_api import sync_playwright

    if _browser is None or not _browser.is_connected():
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=["--disable-http2", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
    return _browser


def _capture_screenshot_sync(site):
    filename = f"{site['id']}-{int(time.time() * 1000)}.png"
    filepath = SCREENSHOTS_DIR / filename
    url = site["url"]

    browser = _get_browser()
    context = browser.new_context(
        viewport=DESKTOP_VIEWPORT,
        device_scale_factor=1,
        user_agent=DESKTOP_UA,
    )
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(filepath), full_page=False)
    except Exception as chromium_err:
        context.close()
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        try:
            fx = pw.firefox.launch(headless=True)
            fx_ctx = fx.new_context(viewport=DESKTOP_VIEWPORT, user_agent=DESKTOP_UA)
            fx_page = fx_ctx.new_page()
            try:
                fx_page.goto(url, wait_until="domcontentloaded", timeout=60000)
                fx_page.wait_for_timeout(3000)
                fx_page.screenshot(path=str(filepath), full_page=False)
            finally:
                fx_ctx.close()
                fx.close()
        except Exception:
            raise chromium_err
        finally:
            pw.stop()
    else:
        context.close()

    return {
        "filename": filename,
        "url": f"/screenshots/{filename}",
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def capture_screenshot(site):
    future = _playwright_executor.submit(_capture_screenshot_sync, site)
    return future.result(timeout=180)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return send_from_directory("public", "index.html")


@app.route("/api/sites")
def list_sites():
    return jsonify(SITES)


@app.route("/api/screenshot/<site_id>", methods=["POST"])
def screenshot_one(site_id):
    site = next((s for s in SITES if s["id"] == site_id), None)
    if not site:
        return jsonify({"error": "Site not found"}), 404
    try:
        result = capture_screenshot(site)
        return jsonify({"site": site["name"], **result})
    except Exception as e:
        return jsonify({"error": f"Failed to capture {site['name']}: {e}"}), 500


@app.route("/api/screenshot-all", methods=["POST"])
def screenshot_all():
    results = []
    for site in SITES:
        try:
            result = capture_screenshot(site)
            results.append({"site": site["name"], "siteId": site["id"], "ok": True, **result})
        except Exception as e:
            results.append({"site": site["name"], "siteId": site["id"], "ok": False, "error": str(e)})
    return jsonify({"results": results})


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    return send_from_directory(SCREENSHOTS_DIR, filename)


def get_local_ip():
    """Prefer a typical home Wi-Fi address (192.168.x.x or 10.x.x.x)."""
    candidates = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            candidates.append(ip)
    except OSError:
        pass
    for prefix in ("192.168.", "10."):
        for ip in candidates:
            if ip.startswith(prefix):
                return ip
    if candidates:
        return candidates[0]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "localhost"


if __name__ == "__main__":
    ip = get_local_ip()
    print("\n========================================")
    print("  Media Screenshot App is running!")
    print("========================================")
    print(f"  On this PC:    http://localhost:{PORT}")
    print(f"  On your phone: http://{ip}:{PORT}")
    print("  (Phone must be on the same Wi-Fi)")
    print("========================================\n")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=False)
