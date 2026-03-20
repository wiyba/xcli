import base64
import json
import os
import urllib.parse

from fastapi.responses import PlainTextResponse

from config import load_hosts, reality


def _vless_uri(uuid, host, r):
    params = urllib.parse.urlencode(
        {
            "security": "reality",
            "alpn": "h2",
            "encryption": "none",
            "pbk": r["public_key"],
            "headerType": "none",
            "fp": "firefox",
            "type": "tcp",
            "flow": "xtls-rprx-vision",
            "sni": r["sni"],
            "sid": r["short_id"],
        }
    )
    return f"vless://{uuid}@{host['server']}:{host['port']}?{params}#{host['name']}"


def make_links(uuid):
    r = reality()
    return [
        {"uri": _vless_uri(uuid, h, r), "label": h["name"], "host": h["server"]}
        for h in load_hosts()
    ]


def make_base_headers(name, base_url, sid):
    profile_name = f"веба впн for {name}"
    title_b64 = base64.b64encode(profile_name.encode()).decode()
    headers = {
        "profile-update-interval": "12",
        "subscription-userinfo": "upload=0; download=0; total=0; expire=0",
        "content-disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(profile_name)}",
        "profile-web-page-url": f"{base_url}/{sid}",
    }
    return title_b64, headers


def build_singbox(uuid, base_headers):
    r = reality()
    tpl = os.path.join(os.path.dirname(__file__), "templates", "singbox.json")
    with open(tpl) as f:
        config = json.load(f)
    proxy_names = []
    for h in load_hosts():
        proxy_names.append(h["name"])
        config["outbounds"].append(
            {
                "type": "vless",
                "tag": h["name"],
                "server": h["server"],
                "server_port": h["port"],
                "uuid": uuid,
                "flow": "xtls-rprx-vision",
                "tls": {
                    "enabled": True,
                    "server_name": r["sni"],
                    "alpn": ["h2"],
                    "utls": {"enabled": True, "fingerprint": "firefox"},
                    "reality": {
                        "enabled": True,
                        "public_key": r["public_key"],
                        "short_id": r["short_id"],
                    },
                },
            }
        )
    config["outbounds"][0]["outbounds"] = proxy_names
    return PlainTextResponse(
        json.dumps(config, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers=base_headers,
    )


def build_clash(uuid, base_headers):
    r = reality()
    hosts = load_hosts()
    proxies = ""
    proxy_groups = ""
    for h in hosts:
        proxies += (
            f"  - name: {h['name']}\n"
            f"    type: vless\n"
            f"    server: {h['server']}\n"
            f"    port: {h['port']}\n"
            f"    uuid: {uuid}\n"
            f"    flow: xtls-rprx-vision\n"
            f"    network: tcp\n"
            f"    tls: true\n"
            f"    udp: true\n"
            f"    servername: {r['sni']}\n"
            f"    client-fingerprint: firefox\n"
            f"    alpn:\n"
            f"      - h2\n"
            f"    reality-opts:\n"
            f"      public-key: {r['public_key']}\n"
            f"      short-id: {r['short_id']}\n"
        )
        proxy_groups += (
            f"  - name: {h['name'].upper()}\n"
            f"    type: select\n"
            f"    proxies:\n"
            f"      - {h['name']}\n"
        )
    tpl = os.path.join(os.path.dirname(__file__), "templates", "clash.yaml")
    with open(tpl) as f:
        template = f.read()
    return PlainTextResponse(
        template.format(
            proxies=proxies.rstrip("\n"),
            proxy_groups=proxy_groups.rstrip("\n"),
        ),
        media_type="text/yaml",
        headers=base_headers,
    )


def build_plain(uuid, title_b64, base_headers):
    r = reality()
    body = "\n".join(_vless_uri(uuid, h, r) for h in load_hosts())
    return PlainTextResponse(
        base64.b64encode(body.encode()).decode(),
        headers={
            **base_headers,
            "profile-title": f"base64:{title_b64}",
        },
    )
