import json
import os
import re
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import load_hosts, load_users, reality
from sub import build_clash, build_plain, build_singbox, make_base_headers, make_links

app = FastAPI()
_dir = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_dir, "templates"))

_BROWSER_KW = (
    "Mozilla",
    "Chrome",
    "Safari",
    "Firefox",
    "Opera",
    "Edge",
    "TelegramBot",
    "WhatsApp",
)
_RE_SINGBOX = re.compile(r"sing-box|Hiddify|SFI|SFA|SFM", re.IGNORECASE)
_RE_CLASH = re.compile(r"Clash|Stash|mihomo", re.IGNORECASE)


def _find_user(sid):
    for u in load_users():
        if u["sid"] == sid:
            return u
    return None


@app.get("/")
@app.head("/")
def root():
    return Response(status_code=418)


@app.get("/health")
@app.head("/health")
def health():
    return Response(status_code=200)


@app.get("/robots.txt")
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.head("/{sid}")
@app.get("/{sid}")
async def subscription(sid: str, request: Request):
    user = _find_user(sid)
    if not user:
        return Response(status_code=418)

    base_url = f"{request.url.scheme}://{request.url.netloc}"
    sub_url = f"{base_url}/{sid}"
    ua = request.headers.get("user-agent", "")
    accept = request.headers.get("accept", "")
    is_browser = "text/html" in accept or any(k in ua for k in _BROWSER_KW)

    if not is_browser:
        title_b64, base_headers = make_base_headers(user["name"], base_url, sid)
        if _RE_SINGBOX.search(ua):
            return build_singbox(user["uuid"], base_headers)
        if _RE_CLASH.search(ua):
            return build_clash(user["uuid"], base_headers)
        return build_plain(user["uuid"], title_b64, base_headers)

    links = make_links(user["uuid"])
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "username": user["name"],
            "sub_url": sub_url,
            "links": links,
        },
    )


_SUB_BASE = os.environ.get("XCLI_SUB_BASE", "https://sub.wiyba.org")


def _xray_config(host):
    r = reality()
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "0.0.0.0",
                "port": host["port"],
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"id": u["uuid"], "flow": "xtls-rprx-vision"}
                        for u in load_users()
                    ],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": f"{r['sni']}:443",
                        "serverNames": [r["sni"]],
                        "privateKey": r["private_key"],
                        "shortIds": [r["short_id"]],
                    },
                },
            }
        ],
        "outbounds": [{"protocol": "freedom"}],
    }


def _cli_generate(args):
    if not args:
        print("Usage: generate users [name] | generate hosts [address]")
        sys.exit(1)

    kind = args[0]

    if kind == "users":
        users = load_users()
        if len(args) > 1:
            target = args[1]
            for u in users:
                if u["name"] == target:
                    print(f"{_SUB_BASE}/{u['sid']}")
                    return
            print(f"user not found: {target}")
            sys.exit(1)
        col = max(len(u["name"]) for u in users)
        for u in users:
            print(f"{u['name'].ljust(col)}  {_SUB_BASE}/{u['sid']}")
        return

    if kind == "hosts":
        hosts = load_hosts()
        if len(args) > 1:
            target = args[1]
            for h in hosts:
                if h["name"] == target or h["server"] == target:
                    print(json.dumps(_xray_config(h), indent=2, ensure_ascii=False))
                    return
            print(f"host not found: {target}")
            sys.exit(1)
        for i, h in enumerate(hosts):
            if i > 0:
                print()
            print(f"{h['server']}:\n")
            print(json.dumps(_xray_config(h), indent=2, ensure_ascii=False))
        return

    print("Usage: generate users [name] | generate hosts [address]")
    sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    args = sys.argv[2:]

    if cmd == "run":
        uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")
        sys.exit(0)

    if cmd == "generate":
        _cli_generate(args)
        sys.exit(0)

    print("Usage:")
    print("  xcli run")
    print("  xcli generate users [name]")
    print("  xcli generate hosts [address]")
    sys.exit(1)
