import base64
import json
import os
import urllib.parse

from fastapi.responses import PlainTextResponse

from config import FINGERPRINT, HOSTS

_DIR = os.path.dirname(__file__)
TRANSPORTS = ("tcp", "xhttp")


def _endpoint(uuid, h, transport):
    port = h["port_xhttp"] if transport == "xhttp" else h["port_tcp"]
    label = f"{h['label']} {transport}"
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


def make_links(uuid):
    return _endpoints(uuid)


def make_base_headers(name, base_url, sid):
    profile = f"веба впн for {name}"
    title_b64 = base64.b64encode(profile.encode()).decode()
    return title_b64, {
        "profile-update-interval": "12",
        "subscription-userinfo": "upload=0; download=0; total=0; expire=0",
        "content-disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(profile)}",
        "profile-web-page-url": f"{base_url}/{sid}",
    }


def _singbox_outbound(uuid, h, transport):
    out = {
        "type": "vless",
        "tag": f"{h['name']}-{transport}",
        "server": h["server"],
        "server_port": h["port_xhttp"] if transport == "xhttp" else h["port_tcp"],
        "uuid": uuid,
        "tls": {
            "enabled": True,
            "server_name": h["sni"],
            "utls": {"enabled": True, "fingerprint": FINGERPRINT},
            "reality": {"enabled": True, "public_key": h["public_key"], "short_id": h["short_id"]},
        },
    }
    if transport == "xhttp":
        out["transport"] = {"type": "xhttp", "path": h["xhttp_path"]}
    else:
        out["flow"] = "xtls-rprx-vision"
        out["tls"]["alpn"] = ["h2"]
    return out


def build_singbox(uuid, base_headers):
    with open(os.path.join(_DIR, "templates", "singbox.json")) as f:
        config = json.load(f)
    tags = []
    for h in HOSTS:
        for t in TRANSPORTS:
            config["outbounds"].append(_singbox_outbound(uuid, h, t))
            tags.append(f"{h['name']}-{t}")
    config["outbounds"][0]["outbounds"] = tags
    return PlainTextResponse(
        json.dumps(config, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers=base_headers,
    )


def _clash_proxy(uuid, h, transport):
    port = h["port_xhttp"] if transport == "xhttp" else h["port_tcp"]
    lines = [
        f"  - name: {h['name']}-{transport}",
        f"    type: vless",
        f"    server: {h['server']}",
        f"    port: {port}",
        f"    uuid: {uuid}",
        f"    network: {transport}",
        f"    tls: true",
        f"    udp: true",
        f"    servername: {h['sni']}",
        f"    client-fingerprint: {FINGERPRINT}",
        f"    reality-opts:",
        f"      public-key: {h['public_key']}",
        f"      short-id: {h['short_id']}",
    ]
    if transport == "xhttp":
        lines += [
            f"    xhttp-opts:",
            f"      path: {h['xhttp_path']}",
        ]
    else:
        lines += [
            f"    flow: xtls-rprx-vision",
            f"    alpn:",
            f"      - h2",
        ]
    return "\n".join(lines) + "\n"


def build_clash(uuid, base_headers):
    proxies = "".join(_clash_proxy(uuid, h, t) for h in HOSTS for t in TRANSPORTS)
    groups = "".join(
        f"  - name: {h['name'].upper()}\n"
        f"    type: url-test\n"
        f"    proxies:\n"
        + "".join(f"      - {h['name']}-{t}\n" for t in TRANSPORTS)
        for h in HOSTS
    )
    with open(os.path.join(_DIR, "templates", "clash.yaml")) as f:
        template = f.read()
    return PlainTextResponse(
        template.format(proxies=proxies.rstrip("\n"), proxy_groups=groups.rstrip("\n")),
        media_type="text/yaml",
        headers=base_headers,
    )


def build_plain(uuid, title_b64, base_headers):
    body = "\n".join(e["uri"] for e in _endpoints(uuid))
    return PlainTextResponse(
        base64.b64encode(body.encode()).decode(),
        headers={**base_headers, "profile-title": f"base64:{title_b64}"},
    )
