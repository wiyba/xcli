import base64
import os
import urllib.parse

import uvicorn
import yaml
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
_MIHOMO = ("clash", "mihomo", "stash", "meta", "flclash")

ANNOUNCE = ""
SUPPORT_URL = "https://t.me/wiybaa"
UPDATE_INTERVAL_HOURS = 12

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(_dir, "static")), name="static")
templates = Jinja2Templates(directory=_dir)


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def _links(uuid, hosts):
    out = []
    for h in hosts:
        common = {
            "security": "reality",
            "encryption": "none",
            "pbk": h["public_key"],
            "sni": h["sni"],
            "sid": h["short_id"],
            "fp": FINGERPRINT,
        }
        tcp = {
            **common,
            "type": "tcp",
            "flow": "xtls-rprx-vision",
            "alpn": "h2",
            "headerType": "none",
        }
        xhttp = {**common, "type": "xhttp", "path": h["xhttp_path"]}
        tcp_label = f"{h['flag']} tcp"
        xhttp_label = f"{h['flag']} xhttp"
        out.append(
            {
                "uri": f"vless://{uuid}@{h['server']}:{h['port_tcp']}?{urllib.parse.urlencode(tcp)}#{tcp_label}",
                "label": tcp_label,
                "host": h["name"],
            }
        )
        out.append(
            {
                "uri": f"vless://{uuid}@{h['server']}:{h['port_xhttp']}?{urllib.parse.urlencode(xhttp)}#{xhttp_label}",
                "label": xhttp_label,
                "host": h["name"],
            }
        )
    return out


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _mihomo(uuid, hosts):
    proxies = []
    for h in hosts:
        reality = {"public-key": h["public_key"], "short-id": h["short_id"]}
        proxies.append(
            {
                "name": h["name"],
                "type": "vless",
                "server": h["server"],
                "port": h["port_tcp"],
                "uuid": uuid,
                "flow": "xtls-rprx-vision",
                "network": "tcp",
                "tls": True,
                "udp": True,
                "servername": h["sni"],
                "client-fingerprint": FINGERPRINT,
                "alpn": ["h2"],
                "reality-opts": reality,
            }
        )
        proxies.append(
            {
                "name": f"{h['name']}-alt",
                "type": "vless",
                "server": h["server"],
                "port": h["port_xhttp"],
                "uuid": uuid,
                "network": "xhttp",
                "tls": True,
                "udp": True,
                "servername": h["sni"],
                "client-fingerprint": FINGERPRINT,
                "xhttp-opts": {"path": h["xhttp_path"]},
                "reality-opts": reality,
            }
        )

    groups = [
        {
            "name": h["name"].upper(),
            "type": "select",
            "proxies": [h["name"], f"{h['name']}-alt"],
        }
        for h in hosts
    ]
    default_group = hosts[0]["name"].upper()

    config = {
        "mixed-port": 7890,
        "mode": "rule",
        "log-level": "warning",
        "dns": {
            "enable": True,
            "enhanced-mode": "fake-ip",
            "default-nameserver": ["1.1.1.1", "8.8.8.8"],
            "nameserver": [
                "https://1.1.1.1/dns-query",
                "https://8.8.8.8/dns-query",
            ],
        },
        "tun": {
            "enable": True,
            "stack": "gvisor",
            "auto-route": True,
            "auto-detect-interface": True,
            "strict-route": True,
        },
        "proxies": proxies,
        "proxy-groups": groups,
        "rules": [
            "GEOSITE,private,DIRECT",
            "DOMAIN-SUFFIX,wiyba.org,DIRECT",
            f"MATCH,{default_group}",
        ],
    }
    return yaml.dump(config, Dumper=_NoAliasDumper, sort_keys=False, allow_unicode=True)


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

    hosts = [h for h in HOSTS if h["name"] in user["hosts"]]
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    ua = request.headers.get("user-agent", "")
    ua_low = ua.lower()
    accept = request.headers.get("accept", "")
    headers = _headers(user["name"], base_url, sid)

    if any(k in ua_low for k in _MIHOMO):
        return PlainTextResponse(
            _mihomo(user["uuid"], hosts),
            headers=headers,
            media_type="application/x-yaml",
        )

    if "text/html" in accept or any(k in ua for k in _BROWSER):
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "username": user["name"],
                "sub_url": f"{base_url}/{sid}",
                "links": _links(user["uuid"], hosts),
            },
        )

    body = "\n".join(e["uri"] for e in _links(user["uuid"], hosts))
    return PlainTextResponse(_b64(body), headers=headers)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")
