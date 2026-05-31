import asyncio
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Keep browsers inside the project so Render build artifacts include them.
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    str(Path(__file__).parent / "ms-playwright"),
)

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
# Half of full HD — faster capture and smaller images on Render free tier.
DESKTOP_VIEWPORT = {"width": 960, "height": 540}
BROWSER_ARGS = [
    "--disable-http2",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
]
PAGE_TIMEOUT_MS = 45000
PAGE_SETTLE_MS = 1500
CAPTURE_TIMEOUT_SEC = 120

_playwright_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")


class _BrowserPool:
    """Reuse one Chromium instance inside the playwright worker thread."""

    def __init__(self):
        self._playwright = None
        self._browser = None

    async def capture(self, site, filepath):
        from playwright.async_api import async_playwright

        if self._browser is None or not self._browser.is_connected():
            if self._playwright:
                await self._playwright.stop()
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=BROWSER_ARGS,
            )

        context = await self._browser.new_context(
            viewport=DESKTOP_VIEWPORT,
            device_scale_factor=1,
            user_agent=DESKTOP_UA,
        )
        page = await context.new_page()
        try:

            async def _route_handler(route):
                if route.request.resource_type in ("media", "font"):
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _route_handler)
            await page.goto(
                site["url"],
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )
            await page.wait_for_timeout(PAGE_SETTLE_MS)
            await page.screenshot(path=str(filepath), full_page=False, type="jpeg", quality=80)
        finally:
            await context.close()


_browser_pool = _BrowserPool()


async def _capture_screenshot_async(site):
    filename = f"{site['id']}-{int(time.time() * 1000)}.jpg"
    filepath = SCREENSHOTS_DIR / filename
    await _browser_pool.capture(site, filepath)
    return {
        "filename": filename,
        "url": f"/screenshots/{filename}",
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def capture_screenshot(site):
    future = _playwright_executor.submit(_run_async, _capture_screenshot_async(site))
    return future.result(timeout=CAPTURE_TIMEOUT_SEC)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return send_from_directory("public", "index.html")


@app.route("/api/config")
def api_config():
    return jsonify(
        {
            "viewport": DESKTOP_VIEWPORT,
            "format": "jpeg",
        }
    )


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
