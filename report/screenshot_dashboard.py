"""Screenshot the running Streamlit dashboard with headless Edge/Chrome over the DevTools protocol.
Start the dashboard first (light theme), e.g.
    streamlit run dashboard/app.py --server.headless true --server.port 8502 --theme.base light -- --mode full
then:  python report/screenshot_dashboard.py http://localhost:8502  ->  report/figures/fig14_dashboard_*.png"""
import base64
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
import websocket

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8502"
OUT = Path(__file__).resolve().parent / "figures"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
PORT = 9333
W, H = 1500, 1000

exe = next(b for b in BROWSERS if Path(b).exists())
prof = tempfile.mkdtemp(prefix="hot-oceans-shot-")
proc = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={PORT}", f"--remote-allow-origins=http://localhost:{PORT}", f"--user-data-dir={prof}",
                         "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--hide-scrollbars",
                         f"--window-size={W},{H}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(30):
        try:
            pages = requests.get(f"http://localhost:{PORT}/json", timeout=2).json()
            page = next(p for p in pages if p.get("type") == "page")
            break
        except Exception:
            time.sleep(1)
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120, suppress_origin=True)
    n = [0]

    def cdp(method, **params):
        n[0] += 1
        ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == n[0]:
                return msg.get("result", {})

    def js(expr):
        return cdp("Runtime.evaluate", expression=expr, returnByValue=True).get("result", {}).get("value")

    def wait_ready(min_wait=8, max_wait=180):
        time.sleep(min_wait)
        t0 = time.time()
        while time.time() - t0 < max_wait:   # Streamlit shows a "Running..." status widget while the script runs
            busy = js("!!document.querySelector('[data-testid=\"stStatusWidget\"]')")
            skeleton = js("!!document.querySelector('[data-testid=\"stSkeleton\"], .stSkeleton')")
            if not busy and not skeleton:
                time.sleep(4)
                return
            time.sleep(2)

    def shot(name):
        data = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=False)["data"]
        (OUT / name).write_bytes(base64.b64decode(data))
        print("saved", name)

    cdp("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1.4, mobile=False)
    cdp("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
    cdp("Page.enable")
    cdp("Page.navigate", url=URL)
    wait_ready(min_wait=20)
    shot("fig14_dashboard_map.png")
    print("tabs found:", js("Array.from(document.querySelectorAll('[role=\"tab\"]')).map(t => t.innerText.trim())"))
    for label, name, height in (("Lakshadweep", "fig14_dashboard_case.png", 1500),
                                ("Events", "fig14_dashboard_events.png", 1500)):
        cdp("Emulation.setDeviceMetricsOverride", width=W, height=height, deviceScaleFactor=1.4, mobile=False)
        # Click the tab the way a user does (BaseWeb tabs react to pointer events, not element.click()).
        box = js("(() => { const t = Array.from(document.querySelectorAll('[role=\"tab\"]'))"
                 f".find(x => x.innerText.trim().startsWith('{label}')); if (!t) return null;"
                 " t.scrollIntoView(); const r = t.getBoundingClientRect();"
                 " return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if not box:
            print("tab not found:", label)
            continue
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            cdp("Input.dispatchMouseEvent", type=kind, x=box[0], y=box[1], button="left", clickCount=1)
        wait_ready(min_wait=8)
        js("window.scrollTo(0, 0)")
        time.sleep(2)
        shot(name)
finally:
    proc.terminate()
