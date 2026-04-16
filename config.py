import json
import os

SECRETS_DIR = os.environ.get("XCLI_SECRETS_DIR", "/run/secrets")
USERS_FILE = os.environ.get(
    "XCLI_USERS_FILE", os.path.join(SECRETS_DIR, "xcli-users.json")
)

FINGERPRINT = "chrome"


def _read(name):
    with open(os.path.join(SECRETS_DIR, name)) as f:
        return f.read().strip()


HOSTS = [
    {
        "name": "relay",
        "label": "\U0001f1f7\U0001f1fa",
        "server": "158.160.216.59",
        "port_tcp": 443,
        "port_xhttp": 8443,
        "sni": "yastatic.net",
        "public_key": _read("xray-relay-key-pub"),
        "short_id": _read("xray-relay-sid"),
        "xhttp_path": _read("xray-relay-xhttp-path"),
    },
    {
        "name": "london",
        "label": "\U0001f1ec\U0001f1e7",
        "server": "45.154.197.120",
        "port_tcp": 443,
        "port_xhttp": 8443,
        "sni": "fonts.gstatic.com",
        "public_key": _read("xray-london-key-pub"),
        "short_id": _read("xray-london-sid"),
        "xhttp_path": _read("xray-london-xhttp-path"),
    },
]


def load_users():
    with open(USERS_FILE) as f:
        return [
            {"name": name, "uuid": uuid, "sid": uuid[:8]}
            # {"name": name, "uuid": uuid, "sid": uuid[:8] + uuid[9:13]}
            for name, uuid in json.load(f).items()
        ]
