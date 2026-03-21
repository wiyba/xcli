import re
import sys
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

from config import load_users, load_users_raw, save_users_raw
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


def _cli_user(args):
    if not args:
        print("Usage: xcli user list | add <name> | remove <name>")
        sys.exit(1)

    action = args[0]

    if action == "list":
        users = load_users_raw()
        if not users:
            print("no users")
            return
        col = max(len(u["name"]) for u in users)
        for u in users:
            sid = u["id"].split("-")[0]
            print(f"{u['name'].ljust(col)}  {_SUB_BASE}/{sid}")
        return

    if action == "add":
        if len(args) < 2:
            print("Usage: xcli user add <name>")
            sys.exit(1)
        name = args[1]
        users = load_users_raw()
        if any(u["name"] == name for u in users):
            print(f"user already exists: {name}")
            sys.exit(1)
        new_uuid = str(uuid4())
        users.append({"name": name, "id": new_uuid, "flow": "xtls-rprx-vision"})
        save_users_raw(users)
        sid = new_uuid.split("-")[0]
        print(f"added {name}  {_SUB_BASE}/{sid}")
        return

    if action == "remove":
        if len(args) < 2:
            print("Usage: xcli user remove <name>")
            sys.exit(1)
        name = args[1]
        users = load_users_raw()
        new_users = [u for u in users if u["name"] != name]
        if len(new_users) == len(users):
            print(f"user not found: {name}")
            sys.exit(1)
        save_users_raw(new_users)
        print(f"removed {name}")
        return

    print("Usage: xcli user list | add <name> | remove <name>")
    sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    args = sys.argv[2:]

    if cmd == "run":
        uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")
        sys.exit(0)

    if cmd == "user":
        _cli_user(args)
        sys.exit(0)

    print("Usage:")
    print("  xcli run")
    print("  xcli user list | add <name> | remove <name>")
    sys.exit(1)
