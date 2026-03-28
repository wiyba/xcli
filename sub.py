import base64, json, os, urllib.parse

from fastapi.responses import PlainTextResponse

from config import HOSTS, reality


def _vless_uri(uuid, host, r):
    params = urllib.parse.urlencode({
        "security": "reality", "alpn": "h2", "encryption": "none",
        "pbk": r["public_key"], "headerType": "none", "fp": "chrome",
        "type": "tcp", "flow": "xtls-rprx-vision",
        "sni": r["sni"], "sid": r["short_id"],
    })
    return f"vless://{uuid}@{host['server']}:{host['port']}?{params}#{host['name']}"


def make_links(uuid):
    r = reality()
    return [{"uri": _vless_uri(uuid, h, r), "label": h["name"], "host": h["server"]} for h in HOSTS]


def make_base_headers(name, base_url, sid):
    profile = f"веба впн for {name}"
    title_b64 = base64.b64encode(profile.encode()).decode()
    return title_b64, {
        "profile-update-interval": "12",
        "subscription-userinfo": "upload=0; download=0; total=0; expire=0",
        "content-disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(profile)}",
        "profile-web-page-url": f"{base_url}/{sid}",
    }


def build_singbox(uuid, base_headers):
    r = reality()
    config = json.load(open(os.path.join(os.path.dirname(__file__), "templates", "singbox.json")))
    names = []
    for h in HOSTS:
        names.append(h["name"])
        config["outbounds"].append({
            "type": "vless", "tag": h["name"],
            "server": h["server"], "server_port": h["port"],
            "uuid": uuid, "flow": "xtls-rprx-vision",
            "tls": {
                "enabled": True, "server_name": r["sni"], "alpn": ["h2"],
                "utls": {"enabled": True, "fingerprint": "chrome"},
                "reality": {"enabled": True, "public_key": r["public_key"], "short_id": r["short_id"]},
            },
        })
    config["outbounds"][0]["outbounds"] = names
    return PlainTextResponse(json.dumps(config, indent=2, ensure_ascii=False), media_type="application/json", headers=base_headers)


def build_clash(uuid, base_headers):
    r = reality()
    proxies, groups = "", ""
    for h in HOSTS:
        proxies += (
            f"  - name: {h['name']}\n    type: vless\n    server: {h['server']}\n"
            f"    port: {h['port']}\n    uuid: {uuid}\n    flow: xtls-rprx-vision\n"
            f"    network: tcp\n    tls: true\n    udp: true\n    servername: {r['sni']}\n"
            f"    client-fingerprint: chrome\n    alpn:\n      - h2\n"
            f"    reality-opts:\n      public-key: {r['public_key']}\n      short-id: {r['short_id']}\n"
        )
        groups += f"  - name: {h['name'].upper()}\n    type: select\n    proxies:\n      - {h['name']}\n"
    template = open(os.path.join(os.path.dirname(__file__), "templates", "clash.yaml")).read()
    return PlainTextResponse(template.format(proxies=proxies.rstrip("\n"), proxy_groups=groups.rstrip("\n")), media_type="text/yaml", headers=base_headers)


def build_plain(uuid, title_b64, base_headers):
    r = reality()
    body = "\n".join(_vless_uri(uuid, h, r) for h in HOSTS)
    return PlainTextResponse(base64.b64encode(body.encode()).decode(), headers={**base_headers, "profile-title": f"base64:{title_b64}"})
