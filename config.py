import json
import os
import subprocess

HOSTS = [
    {"name": "london", "server": "london.wiyba.org", "port": 443},
    {"name": "stockholm", "server": "stockholm.wiyba.org", "port": 443},
    {"name": "moscow", "server": "moscow.wiyba.org", "port": 443},
    {"name": "relay", "server": "158.160.216.59", "port": 443},
]

SECRETS_FILE = os.environ.get("XCLI_SECRETS_FILE", "/etc/nixos/secrets/secrets.yaml")


def _sops_decrypt(key):
    os.environ.setdefault("SOPS_AGE_KEY_FILE", "/etc/nixos/secrets/sops-age.key")
    result = subprocess.run(
        ["sops", "-d", "--extract", f'["{key}"]', SECRETS_FILE],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _sops_set(key, value):
    os.environ.setdefault("SOPS_AGE_KEY_FILE", "/etc/nixos/secrets/sops-age.key")
    set_arg = f'["{key}"] {json.dumps(value)}'
    subprocess.run(["sops", "--set", set_arg, SECRETS_FILE], check=True)


def load_users_raw():
    return json.loads(_sops_decrypt("xcli-users"))


def save_users_raw(users):
    _sops_set("xcli-users", json.dumps(users, ensure_ascii=False))


_users_cache = None


def load_users():
    global _users_cache
    if _users_cache is None:
        _users_cache = [
            {"name": u["name"], "uuid": u["id"], "sid": u["id"].split("-")[0]}
            for u in load_users_raw()
        ]
    return _users_cache


def load_hosts():
    return HOSTS


def reality():
    return {
        "public_key": os.environ.get(
            "XCLI_PUBLIC_KEY", "u-2Rr_En_Jx0agQKMG7DlwlLPus2hPLBPMXlOM_-lVU"
        ),
        "short_id": os.environ.get("XCLI_SHORT_ID", "4ba9b78acaa91b44"),
        "sni": os.environ.get("XCLI_SNI", "yandex.ru"),
    }
