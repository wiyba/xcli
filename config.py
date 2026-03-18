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


def reality():
    return {
        "private_key": os.environ.get("XCLI_PRIVATE_KEY", ""),
        "public_key": os.environ.get("XCLI_PUBLIC_KEY", ""),
        "short_id": os.environ.get("XCLI_SHORT_ID", ""),
        "sni": os.environ.get("XCLI_SNI", "vk.com"),
    }
