import os


def read(name):
    return open(f"/run/secrets/{name}").read().strip()


SUPPORT_URL = "https://t.me/wiybaa"
DB_PATH = os.environ.get("XCLI_DB", "/var/lib/xcli/db.sqlite")
USERS_FILE = "/run/secrets/xray-users.json"
AUTH = {"Authorization": "Bearer " + read("xray-admin")}
GB = 1024 ** 3
POLL_SEC = 60
RECONCILE_SEC = 600
BROWSERS = ("Mozilla", "Chrome", "Safari", "Firefox", "Opera", "Edge", "TelegramBot", "WhatsApp")

HOSTS = [
    {
        "name": "relay",
        "fqdn": "relay.wiyba.org",
        "server": "158.160.216.59",
        "flag": "\U0001f1f7\U0001f1fa",
        "sni": "yandex.ru",
        "pbk": read("xray-relay-key-pub"),
        "sid": read("xray-relay-sid"),
    },
    {
        "name": "london",
        "fqdn": "london.wiyba.org",
        "server": "45.154.197.120",
        "flag": "\U0001f1ec\U0001f1e7",
        "sni": "vk.com",
        "pbk": read("xray-london-key-pub"),
        "sid": read("xray-london-sid"),
    },
    {
        "name": "stockholm",
        "fqdn": "stockholm.wiyba.org",
        "server": "207.2.120.106",
        "flag": "\U0001f1f8\U0001f1ea",
        "sni": "vk.com",
        "pbk": read("xray-stockholm-key-pub"),
        "sid": read("xray-stockholm-sid"),
    },
]
