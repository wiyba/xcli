import os
import socket


def read(name):
    return open(f"/run/secrets/{name}").read().strip()


def resolve(fqdn):
    try:
        return socket.gethostbyname(fqdn)
    except (socket.gaierror, OSError):
        return fqdn


SUPPORT_URL = "https://t.me/wiybaa"
DB_PATH = os.environ.get("XCLI_DB", "/var/lib/xcli/db.sqlite")
USERS_FILE = "/run/secrets/xray-users.json"
AUTH = {"Authorization": "Bearer " + read("xray-admin")}
GB = 1024**3
POLL_SEC = 60
BROWSERS = (
    "Mozilla",
    "Chrome",
    "Safari",
    "Firefox",
    "Opera",
    "Edge",
    "TelegramBot",
    "WhatsApp",
)

HOSTS = [
    {
        "name": "helsinki",
        "fqdn": "helsinki.wiyba.org",
        "flag": "\U0001f1eb\U0001f1ee",
        "sni": "www.google.com",
        "pbk": read("xray-helsinki-key-pub"),
        "sid": read("xray-helsinki-sid"),
    },
    {
        "name": "stockholm",
        "fqdn": "stockholm.wiyba.org",
        "flag": "\U0001f1f8\U0001f1ea",
        "sni": "stockholm.wiyba.org",
        "pbk": read("xray-stockholm-key-pub"),
        "sid": read("xray-stockholm-sid"),
    },
    {
        "name": "home",
        "fqdn": "home.wiyba.org",
        "flag": "\U0001f1f7\U0001f1fa",
        "sni": "home.wiyba.org",
        "pbk": read("xray-home-key-pub"),
        "sid": read("xray-home-sid"),
    },
]

for _h in HOSTS:
    _h["server"] = _h["fqdn"] if _h["name"] == "home" else resolve(_h["fqdn"])
