import argparse
import json
import os
import sys
import urllib.request

from config import HOSTS, load_users
from db import (
    all_rows,
    connect,
    ensure,
    set_host_bytes,
    set_relay_enabled,
    topup,
)

GB = 1024**3
TOKEN_PATH = os.environ.get("XCLI_AGENT_TOKEN_PATH", "/run/secrets/xray-agent")


def _sync(conn):
    ensure(conn, [u["name"] for u in load_users()])


def cmd_serve(_args):
    import uvicorn

    from serve import app

    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")


def _agent(ip, method, path, body=None):
    token = open(TOKEN_PATH).read().strip()
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://{ip}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def cmd_collect(_args):
    conn = connect()
    users = {u["name"]: u for u in load_users()}
    ensure(conn, users.keys())

    for h in HOSTS:
        try:
            remote = json.loads(_agent(h["server"], "GET", "/usage"))
            for user, bytes_ in remote.get("users", {}).items():
                if user in users:
                    set_host_bytes(conn, user, h["name"], int(bytes_))
        except Exception as e:
            print(f"collect {h['name']}: {e}", file=sys.stderr)

    relay_ip = next(h["server"] for h in HOSTS if h["name"] == "relay")
    for r in all_rows(conn):
        name = r["user"]
        u = users.get(name)
        if not u:
            continue
        desired = 1 if u["admin"] or r["limit"] > r["relay"] else 0
        if desired == r["relay_enabled"]:
            continue
        try:
            if desired:
                _agent(
                    relay_ip,
                    "POST",
                    "/user",
                    {"op": "add", "email": name, "uuid": u["uuid"]},
                )
            else:
                _agent(
                    relay_ip,
                    "POST",
                    "/user",
                    {"op": "remove", "email": name},
                )
            set_relay_enabled(conn, name, desired)
        except Exception as e:
            print(f"reconcile {name}: {e}", file=sys.stderr)
    conn.close()


def cmd_topup(args):
    conn = connect()
    _sync(conn)
    topup(conn, args.user, int(args.gb * GB))
    conn.close()
    cmd_balance(argparse.Namespace(user=args.user))


def cmd_balance(args):
    conn = connect()
    _sync(conn)
    admins = {u["name"]: u["admin"] for u in load_users()}
    rows = all_rows(conn)
    conn.close()
    if args.user:
        rows = [r for r in rows if r["user"] == args.user]
        if not rows:
            print(f"no such user: {args.user}", file=sys.stderr)
            sys.exit(1)

    def fmt(n):
        return f"{n / GB:.2f}"

    cols = ("user", "admin", "limit", "used(relay)", "london", "stockholm")
    widths = [len(c) for c in cols]
    out = []
    for r in rows:
        row = (
            r["user"],
            "y" if admins.get(r["user"]) else "",
            fmt(r["limit"]),
            fmt(r["relay"]),
            fmt(r["london"]),
            fmt(r["stockholm"]),
        )
        out.append(row)
        widths = [max(w, len(v)) for w, v in zip(widths, row)]

    fmt_row = lambda r: "  ".join(v.ljust(w) for v, w in zip(r, widths))
    print(fmt_row(cols))
    print(fmt_row(["-" * w for w in widths]))
    for r in out:
        print(fmt_row(r))


def main():
    p = argparse.ArgumentParser(prog="xcli")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run subscription server")
    s.set_defaults(f=cmd_serve)

    s = sub.add_parser("topup", help="add GB to user quota")
    s.add_argument("user")
    s.add_argument("gb", type=float)
    s.set_defaults(f=cmd_topup)

    s = sub.add_parser("balance", help="show balances (GB)")
    s.add_argument("user", nargs="?")
    s.set_defaults(f=cmd_balance)

    s = sub.add_parser("collect", help="pull stats and reconcile relay")
    s.set_defaults(f=cmd_collect)

    args = p.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
