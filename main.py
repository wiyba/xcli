import base64
import os
import urllib.parse

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import FINGERPRINT, HOSTS, load_users

_dir = os.path.dirname(__file__)
_BROWSER = (
    "Mozilla",
    "Chrome",
    "Safari",
    "Firefox",
    "Opera",
    "Edge",
    "TelegramBot",
    "WhatsApp",
)
_EMOJI = {"tcp": "\u26a1", "xhttp": "\U0001f512"}
TRANSPORTS = ("tcp", "xhttp")

ANNOUNCE = "\u26a1 - быстрота\n\U0001f512 - устойчивость"
SUPPORT_URL = "https://t.me/wiybaa"
UPDATE_INTERVAL_HOURS = 12

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(_dir, "static")), name="static")
templates = Jinja2Templates(directory=_dir)


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def _endpoint(uuid, h, transport):
    port = h["port_xhttp"] if transport == "xhttp" else h["port_tcp"]
    label = f"{h['label'].upper()} {_EMOJI[transport]}"
    params = {
        "security": "reality",
        "encryption": "none",
        "pbk": h["public_key"],
        "sni": h["sni"],
        "sid": h["short_id"],
        "fp": FINGERPRINT,
        "type": transport,
    }
    if transport == "xhttp":
        params["path"] = h["xhttp_path"]
    else:
        params.update({"flow": "xtls-rprx-vision", "alpn": "h2", "headerType": "none"})
    uri = f"vless://{uuid}@{h['server']}:{port}?{urllib.parse.urlencode(params)}#{urllib.parse.quote(label)}"
    return {"uri": uri, "label": label, "host": h["name"]}


def _endpoints(uuid):
    return [_endpoint(uuid, h, t) for h in HOSTS for t in TRANSPORTS]


def _headers(name, base_url, sid):
    profile = f"веба впн for {name}"
    return {
        "profile-title": f"base64:{_b64(profile)}",
        "profile-update-interval": str(UPDATE_INTERVAL_HOURS),
        "subscription-userinfo": "upload=0; download=0; total=0; expire=2276640000",
        "announce": f"base64:{_b64(ANNOUNCE)}",
        "support-url": SUPPORT_URL,
        "profile-web-page-url": f"{base_url}/{sid}",
        "content-disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(profile)}",
    }


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
    links = _endpoints(user["uuid"])

    if "text/html" not in accept and not any(k in ua for k in _BROWSER):
        body = "\n".join(e["uri"] for e in links)
        return PlainTextResponse(
            base64.b64encode(body.encode()).decode(),
            headers=_headers(user["name"], base_url, sid),
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "username": user["name"],
            "sub_url": f"{base_url}/{sid}",
            "links": links,
        },
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")
