import json
import os

SECRETS_DIR = os.environ.get("XCLI_SECRETS_DIR", "/run/secrets")
USERS_FILE = os.environ.get(
    "XCLI_USERS_FILE", os.path.join(SECRETS_DIR, "xcli-users.json")
)
DB_PATH = os.environ.get("XCLI_DB", "/var/lib/xcli/db.sqlite")

FINGERPRINT = "chrome"


def _read(name):
    return open(os.path.join(SECRETS_DIR, name)).read().strip()


HOSTS = [
    {
        "name": "relay",
        "flag": "\U0001f1f7\U0001f1fa",
        "server": "158.160.216.59",
        "port_tcp": 443,
        "port_xhttp": 8443,
        "sni": "yandex.ru",
        "public_key": _read("xray-relay-key-pub"),
        "short_id": _read("xray-relay-sid"),
        "xhttp_path": _read("xray-relay-xhttp-path"),
    },
    {
        "name": "london",
        "flag": "\U0001f1ec\U0001f1e7",
        "server": "45.154.197.120",
        "port_tcp": 443,
        "port_xhttp": 8443,
        "sni": "fonts.gstatic.com",
        "public_key": _read("xray-london-key-pub"),
        "short_id": _read("xray-london-sid"),
        "xhttp_path": _read("xray-london-xhttp-path"),
    },
    {
        "name": "stockholm",
        "flag": "\U0001f1f8\U0001f1ea",
        "server": "207.2.120.106",
        "port_tcp": 443,
        "port_xhttp": 8443,
        "sni": "fonts.googleapis.com",
        "public_key": _read("xray-stockholm-key-pub"),
        "short_id": _read("xray-stockholm-sid"),
        "xhttp_path": _read("xray-stockholm-xhttp-path"),
    },
]


def load_users():
    return [
        {
            "name": name,
            "uuid": u["uuid"],
            "sid": u["uuid"][:8],
            "admin": u.get("admin", False),
        }
        for name, u in json.load(open(USERS_FILE)).items()
    ]
