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
DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}
BROWSER_ARGS = ["--disable-http2", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]

_playwright_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")


async def _capture_with_chromium(playwright, site, filepath):
    browser = await playwright.chromium.launch(headless=True, args=BROWSER_ARGS)
    context = await browser.new_context(
        viewport=DESKTOP_VIEWPORT,
        device_scale_factor=1,
        user_agent=DESKTOP_UA,
    )
    page = await context.new_page()
    try:
        await page.goto(site["url"], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(filepath), full_page=False)
    finally:
        await context.close()
        await browser.close()


async def _capture_with_firefox(playwright, site, filepath):
    browser = await playwright.firefox.launch(headless=True)
    context = await browser.new_context(viewport=DESKTOP_VIEWPORT, user_agent=DESKTOP_UA)
    page = await context.new_page()
    try:
        await page.goto(site["url"], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(filepath), full_page=False)
    finally:
        await context.close()
        await browser.close()


async def _capture_screenshot_async(site):
    from playwright.async_api import async_playwright

    filename = f"{site['id']}-{int(time.time() * 1000)}.png"
    filepath = SCREENSHOTS_DIR / filename

    async with async_playwright() as playwright:
        try:
            await _capture_with_chromium(playwright, site, filepath)
        except Exception as chromium_err:
            try:
                await _capture_with_firefox(playwright, site, filepath)
            except Exception:
                raise chromium_err

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
