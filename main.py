import argparse
import asyncio
import base64
import contextlib
import json
import math
import os
import sys
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
        "tag": "vless-tcp",
        "users": [{"email": user, "account": {"uuid": uuid, "flow": "xtls-rprx-vision"}}],
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


def fetch_usage():
    out = {h["name"]: {} for h in HOSTS}
    with httpx.Client() as c:
        for h in HOSTS:
            with contextlib.suppress(Exception):
                r = c.get(f"https://{h['fqdn']}:8443/traffic", headers=AUTH, timeout=10)
                r.raise_for_status()
                out[h["name"]] = r.json().get("users", {})
    return out


def main():
    p = argparse.ArgumentParser(prog="xcli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("ls")
    sub.add_parser("status")
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
        with httpx.Client() as c:
            for h in HOSTS:
                try:
                    ok = c.get(f"https://{h['fqdn']}:8443/", timeout=5).status_code == 200
                except Exception:
                    ok = False
                print(f"{h['name']:12} {'up' if ok else 'down'}")
        return

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
        live = fetch_usage()
        cols = ["user"] + [h["name"] for h in HOSTS] + ["quota"]
        widths = [len(c) for c in cols]
        rows = []
        for r in db.all(conn):
            row = [r["user"]] + [str(math.ceil(live[h["name"]].get(r["user"], 0) / GB)) for h in HOSTS] + [str(r["quota"])]
            rows.append(row)
            widths = [max(w, len(v)) for w, v in zip(widths, row)]
        fmt = lambda r: "  ".join(v.ljust(w) for v, w in zip(r, widths))
        print(fmt(cols))
        for r in rows:
            print(fmt(r))

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
