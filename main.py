import os, re

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import load_users
from sub import build_clash, build_plain, build_singbox, make_base_headers, make_links

_dir = os.path.dirname(__file__)

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_dir, "templates"))

_BROWSER = ("Mozilla", "Chrome", "Safari", "Firefox", "Opera", "Edge", "TelegramBot", "WhatsApp")
_SINGBOX = re.compile(r"sing-box|Hiddify|SFI|SFA|SFM", re.I)
_CLASH = re.compile(r"Clash|Stash|mihomo", re.I)


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


@app.get("/{sid}")
@app.head("/{sid}")
async def subscription(sid: str, request: Request):
    user = next((u for u in load_users() if u["sid"] == sid), None)
    if not user:
        return Response(status_code=418)

    base_url = f"{request.url.scheme}://{request.url.netloc}"
    ua = request.headers.get("user-agent", "")
    accept = request.headers.get("accept", "")

    if "text/html" not in accept and not any(k in ua for k in _BROWSER):
        title_b64, headers = make_base_headers(user["name"], base_url, sid)
        if _SINGBOX.search(ua):
            return build_singbox(user["uuid"], headers)
        if _CLASH.search(ua):
            return build_clash(user["uuid"], headers)
        return build_plain(user["uuid"], title_b64, headers)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "username": user["name"],
        "sub_url": f"{base_url}/{sid}",
        "links": make_links(user["uuid"]),
    })


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")
