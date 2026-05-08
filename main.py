import argparse
import asyncio
import base64
import contextlib
import datetime
import json
import math
import os
import sys
import time
import urllib.parse

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db
from config import (
    AUTH, BROWSERS, DB_PATH, GB, HOSTS, POLL_SEC, RECONCILE_SEC,
    SUPPORT_URL, USERS_FILE,
)

DIR = os.path.dirname(__file__)
usage = {h["name"]: {} for h in HOSTS}

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def adu_payload(user, uuid):
    return json.dumps({
        "inbounds": [{
            "tag": "vless-tcp",
            "port": 443,
            "protocol": "vless",
            "settings": {
                "decryption": "none",
                "clients": [{"email": user, "id": uuid, "flow": "xtls-rprx-vision"}],
            },
        }],
    })


async def poll_loop(client):
    while True:
        for h in HOSTS:
            with contextlib.suppress(Exception):
                r = await client.get(f"https://{h['fqdn']}:8443/traffic", headers=AUTH, timeout=10)
                r.raise_for_status()
                usage[h["name"]] = {u: int(v) for u, v in r.json().get("users", {}).items()}
        await asyncio.sleep(POLL_SEC)


async def reconcile_loop(client):
    while True:
        await asyncio.sleep(RECONCILE_SEC)
        with contextlib.suppress(Exception):
            conn = db.connect(DB_PATH)
            db.sync(conn, json.load(open(USERS_FILE)))
            for u in db.all(conn):
                if u["admin"]:
                    continue
                over = u["quota"] > 0 and math.ceil(usage["relay"].get(u["user"], 0) / GB) > u["quota"]
                for h in HOSTS:
                    ok = not u["blocked"] and (h["name"] != "relay" or not over)
                    url = f"https://{h['fqdn']}:8443"
                    with contextlib.suppress(Exception):
                        if ok:
                            await client.post(f"{url}/adu", headers=AUTH, content=adu_payload(u["user"], u["uuid"]), timeout=10)
                        else:
                            await client.post(f"{url}/rmu?tag=vless-tcp", headers=AUTH, content=u["user"], timeout=10)
            conn.close()


def uri_for(user, h):
    q = urllib.parse.urlencode({
        "security": "reality", "encryption": "none", "type": "tcp",
        "flow": "xtls-rprx-vision", "alpn": "h2", "headerType": "none",
        "pbk": h["pbk"], "sni": h["sni"], "sid": h["sid"], "fp": "chrome",
    })
    label = f"{h['flag']} {h['name']}"
    return f"vless://{user['uuid']}@{h['server']}:443?{q}#{urllib.parse.quote(label)}"


@contextlib.asynccontextmanager
async def lifespan(_):
    conn = db.connect(DB_PATH)
    db.sync(conn, json.load(open(USERS_FILE)))
    conn.close()
    client = httpx.AsyncClient()
    tasks = [asyncio.create_task(poll_loop(client)), asyncio.create_task(reconcile_loop(client))]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        await client.aclose()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(DIR, "static")), name="static")
templates = Jinja2Templates(directory=DIR)


@app.get("/")
@app.head("/")
def root():
    return Response(status_code=418)


@app.get("/{sid}")
@app.head("/{sid}")
def subscription(sid: str, request: Request):
    user = next((u for u in json.load(open(USERS_FILE)) if u["uuid"][:8] == sid), None)
    if not user:
        return Response(status_code=418)

    conn = db.connect(DB_PATH)
    row = next((r for r in db.all(conn) if r["user"] == user["user"]), None)
    conn.close()
    quota = (row or {}).get("quota", 0)
    used = math.ceil(usage["relay"].get(user["user"], 0) / GB)

    base = f"{request.url.scheme}://{request.url.netloc}"
    sub_url = f"{base}/{sid}"
    links = [{"uri": uri_for(user, h), "label": f"{h['flag']} {h['name']}", "host": h["name"]} for h in HOSTS]

    ua = request.headers.get("user-agent", "")
    accept = request.headers.get("accept", "")
    if "text/html" in accept or any(b in ua for b in BROWSERS):
        return templates.TemplateResponse("index.html", {
            "request": request, "username": user["user"], "sub_url": sub_url,
            "links": links, "relay_used": used, "quota": quota,
        })

    body = "\n".join(e["uri"] for e in links)
    total = 0 if user["admin"] else quota * GB
    headers = {
        "profile-title": "base64:" + base64.b64encode(f"веба впн for {user['user']}".encode()).decode(),
        "subscription-userinfo": f"upload=0; download={usage['relay'].get(user['user'], 0)}; total={total}; expire=2276640000",
        "support-url": SUPPORT_URL,
    }
    return PlainTextResponse(base64.b64encode(body.encode()).decode(), headers=headers)


def find(conn, user):
    row = next((r for r in db.all(conn) if r["user"] == user), None)
    if not row:
        sys.exit(f"no such user: {user}")
    return row


def fetch_all():
    out = {h["name"]: {} for h in HOSTS}
    with httpx.Client() as c:
        for h in HOSTS:
            with contextlib.suppress(Exception):
                r = c.get(f"https://{h['fqdn']}:8443/traffic", headers=AUTH, timeout=10)
                r.raise_for_status()
                out[h["name"]] = r.json()
    return out


def fetch_usage():
    return {h: data.get("users", {}) for h, data in fetch_all().items()}


def parse_ts(ts):
    ts = int(ts)
    return ts / 1e9 if ts > 10**11 else float(ts)


def ago(secs):
    secs = int(secs)
    if secs < 60: return f"{secs}s"
    if secs < 3600: return f"{secs//60}m {secs%60}s"
    if secs < 86400: return f"{secs//3600}h {(secs%3600)//60}m"
    return f"{secs//86400}d {(secs%86400)//3600}h"


def print_table(rows):
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))


def main():
    p = argparse.ArgumentParser(prog="xcli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("ls")
    sub.add_parser("status").add_argument(
        "field", nargs="?",
        help="online | ips | inbounds | outbounds (omit for server health)",
    )
    sub.add_parser("sync")
    sub.add_parser("poll")
    for c in ("block", "unblock", "export"):
        sub.add_parser(c).add_argument("user")
    q = sub.add_parser("quota")
    q.add_argument("user")
    q.add_argument("amount", help="GB: absolute, +N, or -N")
    args = p.parse_args()
    cmd = args.cmd

    if cmd == "run":
        uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")
        return

    if cmd == "status":
        if not args.field:
            with httpx.Client() as c:
                for h in HOSTS:
                    try:
                        ok = c.get(f"https://{h['fqdn']}:8443/", timeout=5).status_code == 200
                    except Exception:
                        ok = False
                    print(f"{h['name']:12} {'up' if ok else 'down'}")
            return

        live = fetch_all()

        if args.field == "online":
            users = sorted({u for h in HOSTS for u in live[h["name"]].get("online", {})})
            rows = [["user"] + [h["name"] for h in HOSTS]]
            for u in users:
                rows.append([u] + [str(live[h["name"]].get("online", {}).get(u, 0)) for h in HOSTS])
            print_table(rows)
            return

        if args.field == "ips":
            now = time.time()
            for h in HOSTS:
                iplist = live[h["name"]].get("iplist", {})
                if not iplist:
                    continue
                print(f"== {h['name']} ==")
                for user in sorted(iplist):
                    print(f"  {user}")
                    for ip, ts in sorted(iplist[user].items(), key=lambda x: -int(x[1])):
                        secs = parse_ts(ts)
                        dt = datetime.datetime.fromtimestamp(secs).strftime("%Y-%m-%d %H:%M:%S")
                        print(f"    {ip:<40}  {dt}  ({ago(now - secs)} ago)")
            return

        if args.field in ("inbounds", "outbounds"):
            tags = sorted({t for h in HOSTS for t in live[h["name"]].get(args.field, {})})
            rows = [["tag"] + [h["name"] for h in HOSTS]]
            for t in tags:
                row = [t]
                for h in HOSTS:
                    e = live[h["name"]].get(args.field, {}).get(t, {})
                    up, dn = e.get("uplink", 0), e.get("downlink", 0)
                    row.append(f"{up/GB:.2f}↑/{dn/GB:.2f}↓")
                rows.append(row)
            print_table(rows)
            return

        sys.exit(f"unknown field: {args.field}. options: online, ips, inbounds, outbounds")

    if cmd == "poll":
        live = fetch_usage()
        for h in HOSTS:
            print(f"== {h['name']} ==")
            for u, v in sorted(live[h["name"]].items(), key=lambda x: -x[1]):
                print(f"  {u:20} {v / GB:7.2f} GB")
        return

    if cmd == "export":
        user = next((u for u in json.load(open(USERS_FILE)) if u["user"] == args.user), None)
        if not user:
            sys.exit(f"no such user: {args.user}")
        print(f"https://sub.wiyba.org/{user['uuid'][:8]}\n")
        for h in HOSTS:
            print(uri_for(user, h))
        return

    conn = db.connect(DB_PATH)
    db.sync(conn, json.load(open(USERS_FILE)))

    if cmd == "sync":
        print(f"synced {len(db.all(conn))} users")

    elif cmd == "ls":
        live = fetch_all()
        users = {h["name"]: live[h["name"]].get("users", {}) for h in HOSTS}
        online = {h["name"]: live[h["name"]].get("online", {}) for h in HOSTS}
        rows = [["on", "user"] + [h["name"] for h in HOSTS] + ["quota"]]
        for r in db.all(conn):
            on = "".join(h["name"][0] for h in HOSTS if int(online[h["name"]].get(r["user"], 0)) > 0) or "-"
            row = [on, r["user"]] + [str(math.ceil(users[h["name"]].get(r["user"], 0) / GB)) for h in HOSTS] + [str(r["quota"])]
            rows.append(row)
        print_table(rows)

    elif cmd == "quota":
        row = find(conn, args.user)
        a = args.amount
        if a.startswith("+"):
            new = row["quota"] + int(a[1:])
        elif a.startswith("-"):
            new = row["quota"] - int(a[1:])
        else:
            new = int(a)
        db.set_quota(conn, args.user, new)
        print(f"{args.user}: {row['quota']} -> {new} GB")

    elif cmd in ("block", "unblock"):
        row = find(conn, args.user)
        db.set_blocked(conn, args.user, 1 if cmd == "block" else 0)
        with httpx.Client() as c:
            for h in HOSTS:
                url = f"https://{h['fqdn']}:8443"
                with contextlib.suppress(Exception):
                    if cmd == "block":
                        c.post(f"{url}/rmu?tag=vless-tcp", headers=AUTH, content=args.user, timeout=10)
                    else:
                        c.post(f"{url}/adu", headers=AUTH, content=adu_payload(row["user"], row["uuid"]), timeout=10)
        print(f"{args.user}: {cmd}ed")

    conn.close()


if __name__ == "__main__":
    main()
