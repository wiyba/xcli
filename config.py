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
RECONCILE_SEC = 600
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
        "name": "relay",
        "fqdn": "relay.wiyba.org",
        "flag": "\U0001f1f7\U0001f1fa",
        "sni": "yandex.ru",
        "pbk": read("xray-relay-key-pub"),
        "sid": read("xray-relay-sid"),
    },
    {
        "name": "moscow",
        "fqdn": "moscow.wiyba.org",
        "flag": "\U0001f1f7\U0001f1fa",
        "sni": "yandex.ru",
        "pbk": read("xray-moscow-key-pub"),
        "sid": read("xray-moscow-sid"),
    },
    {
        "name": "london",
        "fqdn": "london.wiyba.org",
        "flag": "\U0001f1ec\U0001f1e7",
        "sni": "www.google.com",
        "pbk": read("xray-london-key-pub"),
        "sid": read("xray-london-sid"),
    },
    {
        "name": "stockholm",
        "fqdn": "stockholm.wiyba.org",
        "flag": "\U0001f1f8\U0001f1ea",
        "sni": "www.google.com",
        "pbk": read("xray-stockholm-key-pub"),
        "sid": read("xray-stockholm-sid"),
    },
    {
        "name": "helsinki",
        "fqdn": "helsinki.wiyba.org",
        "flag": "\U0001f1eb\U0001f1ee",
        "sni": "www.google.com",
        "pbk": read("xray-helsinki-key-pub"),
        "sid": read("xray-helsinki-sid"),
    },
]

for _h in HOSTS:
    _h["server"] = resolve(_h["fqdn"])
