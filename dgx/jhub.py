"""Drive your DGX JupyterHub account from the PC: run shell commands, upload and download files.

Uses a JupyterHub API token stored in a local file (default: ~/.dgx_token); the token is never printed.
  python dgx/jhub.py run "hostname; nproc"            # run a shell command, print its output
  python dgx/jhub.py upload LOCAL REMOTE               # REMOTE is relative to your JupyterHub home
  python dgx/jhub.py download REMOTE LOCAL
  python dgx/jhub.py status                            # is your server running?
"""
import argparse
import base64
import json
import os
import re
import ssl
import sys
import time
import warnings
from pathlib import Path
from urllib.parse import quote

import requests

warnings.filterwarnings("ignore")  # the hub uses a self-signed certificate
# The hub address and account name live outside the repository: environment variables DGX_HUB / DGX_USER,
# or dgx/hub_settings.json ({"hub": "https://<host>:8000", "user": "<account>"}), which is git-ignored.
_SETTINGS = Path(__file__).with_name("hub_settings.json")
_LOCAL = json.loads(_SETTINGS.read_text(encoding="utf-8")) if _SETTINGS.exists() else {}
HUB = os.environ.get("DGX_HUB") or _LOCAL.get("hub", "")
USER = os.environ.get("DGX_USER") or _LOCAL.get("user", "")
if not HUB or not USER:
    sys.exit(f"Set DGX_HUB and DGX_USER, or create {_SETTINGS} (see the comment above).")
TOKEN_FILE = Path.home() / ".dgx_token"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\r")


def token() -> str:
    if not TOKEN_FILE.exists():
        sys.exit(f"No token file at {TOKEN_FILE}. Create one from {HUB}/hub/token.")
    return TOKEN_FILE.read_text(encoding="utf-8-sig").strip()


def session() -> requests.Session:
    s = requests.Session()
    s.verify = False
    s.trust_env = False  # otherwise a system CA-bundle variable overrides verify=False
    s.headers["Authorization"] = f"token {token()}"
    return s


def server_url(s: requests.Session, start: bool = True, wait: int = 300) -> str:
    """Return the base URL of the user's single-user server, starting it if needed."""
    u = quote(USER)
    info = s.get(f"{HUB}/hub/api/users/{u}", timeout=30)
    info.raise_for_status()
    srv = info.json().get("servers", {}).get("", {})
    if srv.get("ready"):
        return HUB + srv["url"].rstrip("/")
    if not start:
        sys.exit("Server is not running.")
    r = s.post(f"{HUB}/hub/api/users/{u}/server", timeout=60)
    if r.status_code not in (201, 202, 400):  # 400 = already starting
        r.raise_for_status()
    t0 = time.time()
    while time.time() - t0 < wait:
        srv = s.get(f"{HUB}/hub/api/users/{u}", timeout=30).json().get("servers", {}).get("", {})
        if srv.get("ready"):
            return HUB + srv["url"].rstrip("/")
        time.sleep(5)
    sys.exit("Server did not become ready in time.")


def run(cmd: str, timeout: int = 1800) -> int:
    """Run a shell command in a fresh Jupyter terminal; stream its output; return its exit code."""
    import websocket  # websocket-client

    s = session()
    base = server_url(s)
    term = s.post(f"{base}/api/terminals", timeout=30)
    term.raise_for_status()
    name = term.json()["name"]
    ws_url = base.replace("https://", "wss://") + f"/terminals/websocket/{name}"
    ws = websocket.create_connection(ws_url, header=[f"Authorization: token {token()}"],
                                     sslopt={"cert_reqs": ssl.CERT_NONE}, timeout=timeout)
    marker = f"__HOT_OCEANS_DONE_{int(time.time())}__"
    ws.send(json.dumps(["stdin", f"stty -echo; {cmd}; echo {marker}$?\r"]))
    buf, code, t0 = "", None, time.time()
    try:
        while time.time() - t0 < timeout:
            msg = json.loads(ws.recv())
            if msg[0] != "stdout":
                continue
            buf += ANSI.sub("", msg[1])
            m = re.search(re.escape(marker) + r"(\d+)", buf)
            if m:
                code = int(m.group(1))
                buf = buf[:m.start()]
                break
    finally:
        ws.close()
        s.delete(f"{base}/api/terminals/{name}", timeout=30)
    lines = [ln for ln in buf.split("\n") if "stty -echo" not in ln and marker not in ln]
    print("\n".join(lines).strip())
    if code is None:
        print(f"[jhub] no completion marker within {timeout}s (command may still be running)")
        return 124
    return code


def upload(local: str, remote: str):
    s = session()
    base = server_url(s)
    parts = remote.strip("/").split("/")
    for i in range(1, len(parts)):  # make parent folders
        s.put(f"{base}/api/contents/{quote('/'.join(parts[:i]))}", json={"type": "directory"}, timeout=60)
    data = base64.b64encode(Path(local).read_bytes()).decode()
    r = s.put(f"{base}/api/contents/{quote(remote.strip('/'))}",
              json={"type": "file", "format": "base64", "content": data}, timeout=600)
    r.raise_for_status()
    print(f"[jhub] uploaded {local} -> ~/{remote} ({Path(local).stat().st_size:,} bytes)")


def download(remote: str, local: str):
    s = session()
    base = server_url(s)
    with s.get(f"{base}/files/{quote(remote.strip('/'))}", stream=True, timeout=600) as r:
        r.raise_for_status()
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        with open(local, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    print(f"[jhub] downloaded ~/{remote} -> {local} ({Path(local).stat().st_size:,} bytes)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("command"); r.add_argument("--timeout", type=int, default=1800)
    u = sub.add_parser("upload"); u.add_argument("local"); u.add_argument("remote")
    d = sub.add_parser("download"); d.add_argument("remote"); d.add_argument("local")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "run":
        sys.exit(run(a.command, a.timeout))
    if a.cmd == "upload":
        upload(a.local, a.remote)
    elif a.cmd == "download":
        download(a.remote, a.local)
    else:
        print("server:", server_url(session(), start=False))


if __name__ == "__main__":
    main()
