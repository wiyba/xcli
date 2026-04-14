import json, os

HOSTS = [
    {"name": "london", "label": "\U0001f1ec\U0001f1e7", "server": "london.wiyba.org", "port": 443},
    {"name": "moscow", "label": "\U0001f1f7\U0001f1fa", "server": "moscow.wiyba.org", "port": 443},
    {"name": "relay", "label": "\U0001f3f3\ufe0f", "server": "158.160.216.59", "port": 443},
]

USERS_FILE = os.environ.get("XCLI_USERS_FILE", "/run/secrets/xcli-users")


def load_users():
    return [{"name": u["email"], "uuid": u["id"], "sid": u["id"][:8]} for u in json.load(open(USERS_FILE))]


def reality():
    return {
        "public_key": os.environ.get("XCLI_PUBLIC_KEY", "u-2Rr_En_Jx0agQKMG7DlwlLPus2hPLBPMXlOM_-lVU"),
        "short_id": os.environ.get("XCLI_SHORT_ID", "4ba9b78acaa91b44"),
        "sni": os.environ.get("XCLI_SNI", "yandex.ru"),
    }
