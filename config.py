import os


def _read_lines(path):
    try:
        with open(path) as f:
            return [l.strip() for l in f if l.strip()]
    except FileNotFoundError:
        return []


def load_users():
    path = os.environ.get("XCLI_USERS_FILE", "/run/secrets/xcli-users")
    users = []
    for line in _read_lines(path):
        parts = line.split(":")
        if len(parts) != 2:
            continue
        name, uuid = parts
        users.append({"name": name, "uuid": uuid, "sid": uuid.split("-")[0]})
    return users


def load_hosts():
    path = os.environ.get("XCLI_HOSTS_FILE", "/run/secrets/xcli-hosts")
    hosts = []
    for line in _read_lines(path):
        parts = line.split(":")
        if len(parts) != 3:
            continue
        name, server, port = parts
        hosts.append({"name": name, "server": server, "port": int(port)})
    return hosts


def _read_secret(env_key, secret_path):
    val = os.environ.get(env_key, "")
    if val:
        return val
    try:
        with open(secret_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def reality():
    return {
        "private_key": _read_secret("XCLI_PRIVATE_KEY", "/run/secrets/xcli-private-key"),
        "public_key": os.environ.get("XCLI_PUBLIC_KEY", "u-2Rr_En_Jx0agQKMG7DlwlLPus2hPLBPMXlOM_-lVU"),
        "short_id": os.environ.get("XCLI_SHORT_ID", "AAAA5555"),
        "sni": os.environ.get("XCLI_SNI", "vk.com"),
    }
