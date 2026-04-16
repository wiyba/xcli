import base64
import urllib.parse

from fastapi.responses import PlainTextResponse

from config import FINGERPRINT, HOSTS

TRANSPORTS = ("tcp", "xhttp")
_EMOJI = {"tcp": "\u26a1", "xhttp": "\U0001f512"}


def _label(h, transport):
    return f"{h['label'].upper()} {_EMOJI[transport]}"


def _endpoint(uuid, h, transport):
    port = h["port_xhttp"] if transport == "xhttp" else h["port_tcp"]
    label = _label(h, transport)
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


def _mihomo_proxy(uuid, h, transport):
    port = h["port_xhttp"] if transport == "xhttp" else h["port_tcp"]
    name = f"{h['name']}-{transport}"
    lines = [
        f"  - name: {name}",
        f"    type: vless",
        f"    server: {h['server']}",
        f"    port: {port}",
        f"    uuid: \"{uuid}\"",
        f"    network: {transport}",
        f"    tls: true",
        f"    udp: true",
        f"    servername: {h['sni']}",
        f"    client-fingerprint: {FINGERPRINT}",
        f"    reality-opts:",
        f"      public-key: \"{h['public_key']}\"",
        f"      short-id: \"{h['short_id']}\"",
    ]
    if transport == "xhttp":
        lines += [
            f"    xhttp-opts:",
            f"      path: \"{h['xhttp_path']}\"",
        ]
    else:
        lines += [
            f"    flow: xtls-rprx-vision",
            f"    alpn:",
            f"      - h2",
        ]
    return name, "\n".join(lines)


_RULES = """\
  - GEOSITE,tiktok,LONDON
  - GEOSITE,youtube,LONDON
  - GEOSITE,flibusta,LONDON
  - GEOSITE,rutracker,LONDON
  - GEOSITE,category-ai-!cn,LONDON
  - GEOSITE,figma,LONDON
  - GEOSITE,canva,LONDON
  - GEOSITE,adobe,LONDON
  - GEOSITE,notion,LONDON
  - GEOSITE,atlassian,LONDON
  - GEOSITE,slack,LONDON
  - GEOSITE,spotify,LONDON
  - GEOSITE,netflix,LONDON
  - GEOSITE,deezer,LONDON
  - GEOSITE,jetbrains,LONDON
  - GEOSITE,jetbrains-ai,LONDON
  - GEOSITE,vercel,LONDON
  - GEOSITE,heroku,LONDON
  - GEOSITE,digitalocean,LONDON
  - GEOSITE,dropbox,LONDON
  - GEOSITE,paypal,LONDON
  - GEOSITE,stripe,LONDON
  - GEOSITE,wise,LONDON
  - GEOSITE,zendesk,LONDON
  - GEOSITE,autodesk,LONDON
  - GEOSITE,salesforce,LONDON
  - GEOSITE,godaddy,LONDON
  - GEOSITE,wix,LONDON
  - GEOSITE,patreon,LONDON
  - GEOIP,PRIVATE,DIRECT
  - IP-CIDR6,::/0,LONDON
  - MATCH,RELAY"""


def build_mihomo(uuid, base_headers):
    proxies_yaml = ""
    groups = {}
    for h in HOSTS:
        group_name = h["name"].upper()
        groups.setdefault(group_name, [])
        for t in TRANSPORTS:
            name, yaml = _mihomo_proxy(uuid, h, t)
            proxies_yaml += yaml + "\n"
            groups[group_name].append(name)

    groups_yaml = ""
    for gname, members in groups.items():
        groups_yaml += f"  - name: {gname}\n    type: select\n    proxies:\n"
        for m in members:
            groups_yaml += f"      - {m}\n"

    config = f"""\
mixed-port: 7890
mode: rule
log-level: warning
dns:
  enable: true
  nameserver:
    - 1.1.1.1
    - 8.8.8.8
  ipv6: false
proxies:
{proxies_yaml.rstrip()}
proxy-groups:
{groups_yaml.rstrip()}
rules:
{_RULES}
"""
    return PlainTextResponse(
        config,
        media_type="text/yaml",
        headers=base_headers,
    )


def build_plain(uuid, title_b64, base_headers):
    body = "\n".join(e["uri"] for e in _endpoints(uuid))
    return PlainTextResponse(
        base64.b64encode(body.encode()).decode(),
        headers={**base_headers, "profile-title": f"base64:{title_b64}"},
    )
