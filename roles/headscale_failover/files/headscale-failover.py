#!/usr/bin/env python3
"""headscale failover on etcd: one leader runs headscale, the database travels through etcd.

run <config>     candidate agent: hold an etcd lease, queue in the election, serve as leader, fence without the lease;
                 an HTTP API reports this server and takes manual switch requests
seed <config>    put this server's database into etcd as the first snapshot (migration, empty cluster)
"""
import base64
import gzip
import hashlib
import hmac
import json
import os
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HISTORY_LENGTH = 50
# A hold file older than this was left behind by a dead run and no longer counts.
HOLD_MAX = 300
# Columns that change on every reconnect; a snapshot is not rewritten for them alone.
VOLATILE_COLUMNS = {"last_seen", "endpoints", "host_info", "updated_at", "disco_key"}


def b64(data):
    return base64.b64encode(data if isinstance(data, bytes) else data.encode()).decode()


def unb64(text):
    return base64.b64decode(text or "")


def prefix_end(prefix):
    return prefix[:-1] + chr(ord(prefix[-1]) + 1)


class EtcdError(Exception):
    pass


class Etcd:
    """etcd v3 over its JSON gateway, trying each endpoint in turn."""

    def __init__(self, endpoints, ca=None, cert=None, key=None, timeout=1):
        self.endpoints, self.timeout = list(endpoints), timeout
        self.ctx = None
        if ca:
            self.ctx = ssl.create_default_context(cafile=ca)
            self.ctx.load_cert_chain(cert, key)

    def call(self, path, body):
        last = None
        for i, endpoint in enumerate(list(self.endpoints)):
            req = urllib.request.Request(endpoint + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                    if i:
                        self.endpoints.insert(0, self.endpoints.pop(i))
                    return json.loads(r.read() or b"{}")
            except (OSError, ValueError) as e:
                last = e
        raise EtcdError(str(last))

    def grant(self, ttl):
        return self.call("/v3/lease/grant", {"TTL": ttl})["ID"]

    def keepalive(self, lease):
        """Remaining TTL after renewing, 0 when the lease is gone."""
        return int(self.call("/v3/lease/keepalive", {"ID": lease}).get("result", {}).get("TTL", 0))

    def get(self, key):
        kvs = self.call("/v3/kv/range", {"key": b64(key)}).get("kvs", [])
        return kvs[0] if kvs else None

    def prefix(self, prefix):
        return self.call("/v3/kv/range", {"key": b64(prefix), "range_end": b64(prefix_end(prefix)),
                                          "sort_target": "CREATE", "sort_order": "ASCEND"}).get("kvs", [])

    def put(self, key, value):
        self.call("/v3/kv/put", {"key": b64(key), "value": b64(value)})

    def txn(self, compare, success, failure=()):
        return bool(self.call("/v3/kv/txn", {"compare": list(compare), "success": list(success),
                                             "failure": list(failure)}).get("succeeded"))

    def members(self):
        return self.call("/v3/cluster/member/list", {}).get("members", [])


def cmp_created(key, revision):
    return {"key": b64(key), "target": "CREATE", "result": "EQUAL", "create_revision": str(revision)}


def op_put(key, value, lease=None):
    put = {"key": b64(key), "value": b64(value)}
    if lease:
        put["lease"] = lease
    return {"request_put": put}


def op_delete(key):
    return {"request_delete_range": {"key": b64(key)}}


def kv_value(kv):
    return unb64(kv["value"]) if kv and kv.get("value") else b""


def kv_json(kv, default=None):
    try:
        return json.loads(kv_value(kv)) if kv else default
    except ValueError:
        return default


def election_order(kvs, prefix):
    """[(name, create_revision)] in queue order: the first one leads."""
    return [(unb64(kv["key"]).decode()[len(prefix):], int(kv["create_revision"])) for kv in kvs]


def read_only(db_path):
    """A connection that cannot write; mode=ro fails on a WAL database whose -shm does not exist yet."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA query_only=1")
    return conn


def logical_hash(db_path, volatile_columns=VOLATILE_COLUMNS):
    """Hash of what matters in the database: every table but the per-reconnect columns."""
    h = hashlib.sha256()
    conn = read_only(db_path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT GLOB '_litestream*' ORDER BY name")]
        for table in tables:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")') if r[1] not in volatile_columns]
            h.update(table.encode())
            if not cols:
                continue
            col_list = ", ".join(f'"{c}"' for c in cols)
            for row in conn.execute(f'SELECT {col_list} FROM "{table}" ORDER BY 1'):
                h.update(repr(row).encode())
    finally:
        conn.close()
    return h.hexdigest()


def snapshot_bytes(db_path):
    """A consistent copy of the database while headscale writes to it (SQLite backup API)."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "db.sqlite")
        src = read_only(db_path)
        dst = sqlite3.connect(copy)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with open(copy, "rb") as f:
            return f.read()


def restore_db(db_path, data):
    """Replace the database files with a snapshot; headscale must be stopped."""
    tmp = db_path + ".restore"
    with open(tmp, "wb") as f:
        f.write(data)
    conn = sqlite3.connect(tmp)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("snapshot failed its integrity check")
    finally:
        conn.close()
    for suffix in ("-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)
    os.replace(tmp, db_path)


def write_atomic(path, text):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def authorized(header, token):
    return bool(token) and hmac.compare_digest(header or "", f"Bearer {token}")


class Cloudflare:
    def __init__(self, token, zone, name):
        self.token, self.zone, self.name = token, zone, name

    def _call(self, method, path, body=None):
        req = urllib.request.Request(
            "https://api.cloudflare.com/client/v4" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)["result"]

    def _records(self):
        zone_id = self._call("GET", f"/zones?name={self.zone}")[0]["id"]
        return zone_id, self._call("GET", f"/zones/{zone_id}/dns_records?type=A&name={self.name}")

    def get(self):
        _, records = self._records()
        return records[0]["content"] if records else None

    def set(self, ip):
        zone_id, records = self._records()
        body = {"type": "A", "name": self.name, "content": ip, "ttl": records[0]["ttl"] if records else 60}
        if records:
            self._call("PATCH", f"/zones/{zone_id}/dns_records/{records[0]['id']}", body)
        else:
            self._call("POST", f"/zones/{zone_id}/dns_records", body)


class Headscale:
    """The headscale compose project on this host."""

    def __init__(self, directory, name="headscale", database="db.sqlite"):
        self.directory, self.name = directory, name
        self.db = os.path.join(directory, "data", database)

    def _compose(self, *args):
        return subprocess.run(["docker", "compose", *args], cwd=self.directory, check=False,
                              capture_output=True, text=True).returncode == 0

    def running(self):
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", self.name],
                           capture_output=True, text=True, check=False)
        return r.stdout.strip() == "true"

    def start(self):
        return self._compose("up", "-d", "--wait")

    def stop(self):
        return self._compose("stop")


class Agent:
    """One tick at a time; etcd decides who leads, the agent makes this host follow."""

    def __init__(self, cfg, etcd, headscale, dns, clock=time.monotonic, wall=time.time, log=print, panel=None):
        self.cfg, self.etcd, self.headscale, self.dns = cfg, etcd, headscale, dns
        self.panel = panel
        self.clock, self.wall, self.log = clock, wall, log
        self.name = cfg["name"]
        p = cfg["prefix"].rstrip("/")
        self.k_election = f"{p}/election/"
        self.k_mine = self.k_election + self.name
        self.k_desired, self.k_db, self.k_db_meta, self.k_history = (f"{p}/desired", f"{p}/db", f"{p}/db-meta",
                                                                     f"{p}/history")
        self.k_panel = f"{p}/headplane-db"
        self.panel_hash = None
        self.lease_file = os.path.join(cfg["state_dir"], "lease.json") if cfg.get("state_dir") else None
        self.lease = load_json(self.lease_file, {}).get("id") if self.lease_file else None
        self.hold_file = os.path.join(cfg["state_dir"], "hold") if cfg.get("state_dir") else None
        self.was_held = False
        self.lease_until = 0.0
        self.renewed_at = 0.0
        self.term = None
        self.serving_term = None
        self.resigned_until = 0.0
        self.snapshot_hash = None
        self.changed_since = None
        self.lock = threading.Lock()
        self.ticks = 0
        self.view = {"members": [], "queue": [], "snapshot": None, "history": []}
        self.status = {"action": "starting", "leader": None, "term": None, "desired": None,
                       "lease_ok": False, "etcd_ok": False, "error": None}

    # ----- lease and candidacy -----

    def keep_lease(self):
        ttl = self.cfg["lease_ttl"]
        if self.lease and self.clock() - self.renewed_at < ttl / 3:
            return
        sent = self.clock()
        left = 0
        if self.lease:
            left = self.etcd.keepalive(self.lease)
            if left <= 0:
                self.log("lease expired")
                self.lease, self.term = None, None
        if not self.lease:
            self.lease, self.term = self.etcd.grant(ttl), None
            left = ttl
            if self.lease_file:
                write_atomic(self.lease_file, json.dumps({"id": self.lease}))
        self.renewed_at = sent
        self.lease_until = sent + left

    def lease_ok(self):
        return self.lease is not None and self.clock() < self.lease_until - self.cfg["lease_ttl"] * 0.3

    def campaign(self):
        if not self.cfg["candidate"] or self.clock() < self.resigned_until:
            return
        mine = self.etcd.get(self.k_mine)
        if not (mine and mine.get("lease") == self.lease):
            self.etcd.txn([cmp_created(self.k_mine, 0)],
                          [op_put(self.k_mine, json.dumps({"name": self.name, "ip": self.cfg["self_ip"]}),
                                  self.lease)])
            mine = self.etcd.get(self.k_mine)
        self.term = int(mine["create_revision"]) if mine and mine.get("lease") == self.lease else None

    # ----- history -----

    def record(self, event):
        for _ in range(5):
            kv = self.etcd.get(self.k_history)
            history = kv_json(kv, [])
            history = (history + [{"at": int(self.wall()), "server": self.name, "event": event}])[-HISTORY_LENGTH:]
            compare = [{"key": b64(self.k_history), "target": "MOD", "result": "EQUAL",
                        "mod_revision": kv["mod_revision"] if kv else "0"}]
            if self.etcd.txn(compare, [op_put(self.k_history, json.dumps(history))]):
                return

    # ----- leading -----

    def services_running(self):
        return self.headscale.running() or bool(self.panel and self.panel.running())

    def stop_services(self):
        # Close panel writes before taking the final handover snapshot.
        panel_stopped = not self.panel or self.panel.stop()
        headscale_stopped = self.headscale.stop()
        if not panel_stopped or not headscale_stopped:
            raise RuntimeError("could not stop all failover services")

    def start_panel(self):
        if self.panel and not self.panel.running():
            if not self.lease_ok():
                raise RuntimeError("lease expired before starting headplane")
            if not self.panel.start():
                raise RuntimeError("headplane did not start")

    def become_leader(self):
        kv = self.etcd.get(self.k_db)
        if not kv:
            raise RuntimeError("no database snapshot in etcd: run `seed` on the server that has it")
        data = gzip.decompress(kv_value(kv))
        panel_data = kv_value(self.etcd.get(self.k_panel)) if self.panel else None
        if self.panel and not panel_data and os.path.exists(self.panel.db):
            raise RuntimeError("no Headplane snapshot: migrate the existing panel database before enabling failover")
        with self.lock:
            if not self.lease_ok():
                raise RuntimeError("the lease ran out before headscale could start")
            self.stop_services()
            restore_db(self.headscale.db, data)
            if panel_data:
                restore_db(self.panel.db, gzip.decompress(panel_data))
            if self.dns.get() != self.cfg["self_ip"]:
                self.dns.set(self.cfg["self_ip"])
            if not self.lease_ok():
                raise RuntimeError("lease expired before starting headscale")
            if not self.headscale.start():
                raise RuntimeError("headscale did not start")
            self.start_panel()
        self.panel_hash = logical_hash(self.panel.db, set()) if panel_data else None
        self.snapshot_hash = logical_hash(self.headscale.db)
        self.changed_since = None
        self.serving_term = self.term
        self.record(f"became leader (term {self.term})")

    def adopt(self):
        """Keep a running headscale (agent restart): no restore, no restart.

        Safe when the newest snapshot is this server's own - nobody wrote after it, so the local database holds it
        and maybe more - or when it holds exactly the snapshot's data.
        """
        meta = kv_json(self.etcd.get(self.k_db_meta), {})
        if not self.headscale.running():
            return False
        if meta.get("by") != self.name and meta.get("hash") != logical_hash(self.headscale.db):
            return False
        if self.panel:
            panel_hash = logical_hash(self.panel.db, set()) if os.path.exists(self.panel.db) else None
            if meta.get("by") != self.name and meta.get("panel_hash") != panel_hash:
                return False
            self.panel_hash = meta.get("panel_hash")
            self.start_panel()
        if self.dns.get() != self.cfg["self_ip"]:
            self.dns.set(self.cfg["self_ip"])
        self.snapshot_hash, self.changed_since, self.serving_term = meta.get("hash"), None, self.term
        return True

    def write_snapshot(self, force=False):
        """Put the database into etcd if it changed; False when this server no longer leads."""
        current = logical_hash(self.headscale.db)
        panel_hash = logical_hash(self.panel.db, set()) if self.panel else None
        if current == self.snapshot_hash and panel_hash == self.panel_hash and not force:
            self.changed_since = None
            return True
        if not force:
            now = self.clock()
            if self.changed_since is None:
                self.changed_since = now
            if now - self.changed_since < self.cfg["snapshot_debounce"]:
                return True
        data = gzip.compress(snapshot_bytes(self.headscale.db))
        if len(data) > self.cfg["snapshot_limit"]:
            raise RuntimeError(f"snapshot is {len(data)} bytes, over the {self.cfg['snapshot_limit']} limit")
        meta = {"term": self.term, "by": self.name, "at": int(self.wall()), "bytes": len(data), "hash": current}
        ops = [op_put(self.k_db, data)]
        if self.panel:
            panel_data = gzip.compress(snapshot_bytes(self.panel.db))
            if len(data) + len(panel_data) > self.cfg["snapshot_limit"]:
                raise RuntimeError("combined Headscale and Headplane snapshot exceeds snapshot_limit")
            meta.update(panel_hash=panel_hash, panel_bytes=len(panel_data), bytes=len(data) + len(panel_data))
            ops.append(op_put(self.k_panel, panel_data))
        ops.append(op_put(self.k_db_meta, json.dumps(meta)))
        ok = self.etcd.txn([cmp_created(self.k_mine, self.term)], ops)
        if ok:
            self.snapshot_hash, self.panel_hash, self.changed_since = current, panel_hash, None
        return ok

    def resign(self, to):
        self.stop_services()
        if not self.write_snapshot(force=True):
            raise RuntimeError("lost leadership before the final snapshot")
        self.serving_term = None
        self.etcd.txn([cmp_created(self.k_mine, self.term)], [op_delete(self.k_mine)])
        self.term = None
        self.resigned_until = self.clock() + self.cfg["desired_wait"]
        self.record(f"handed over to {to} on request")

    def watchdog_check(self):
        """Stop headscale once the lease may have run out, whatever the tick is stuck on; no etcd calls."""
        if self.renewed_at and not self.lease_ok() and self.services_running():
            with self.lock:
                self.log("fence: the lease is running out, stopping headscale")
                self.stop_services()
                self.serving_term = None
                self.status["action"] = "fenced"

    def fence(self, why):
        if self.services_running():
            self.log(f"fence: {why}, stopping headscale")
            with self.lock:
                self.stop_services()
        if self.serving_term is not None:
            self.serving_term = None
            try:
                self.record(f"stopped: {why}")
            except EtcdError:
                pass

    # ----- one tick -----

    def tick(self):
        try:
            self.keep_lease()
            self.status["etcd_ok"] = True
        except EtcdError as e:
            self.status.update(etcd_ok=False, error=f"etcd: {e}")
        if not self.lease_ok():
            self.status.update(action="fenced", lease_ok=False)
            self.fence("no etcd quorum")
            return
        self.status["lease_ok"] = True
        try:
            self.campaign()
            order = election_order(self.etcd.prefix(self.k_election), self.k_election)
            desired = kv_json(self.etcd.get(self.k_desired))
            leader, term = order[0] if order else (None, None)
            self.status.update(leader=leader, term=term, desired=(desired or {}).get("name"), error=None)
            self.refresh_view([n for n, _ in order])
            if leader == self.name and term == self.term:
                self.lead(desired, [n for n, _ in order])
            else:
                if self.serving_term is not None or self.services_running():
                    self.fence(f"{leader or 'nobody'} leads")
                self.status["action"] = "standby"
        except (EtcdError, RuntimeError, ValueError, OSError, sqlite3.Error) as e:
            self.status["error"] = str(e)
            self.log(f"tick: {e}")

    def refresh_view(self, queue):
        """What the API shows, read here so that requests never wait on etcd."""
        view = dict(self.view, queue=queue, snapshot=kv_json(self.etcd.get(self.k_db_meta)),
                    history=kv_json(self.etcd.get(self.k_history), []))
        if self.ticks % 5 == 0 or not view["members"]:
            view["members"] = [self.member_health(m) for m in self.etcd.members()]
        self.ticks += 1
        self.view = view

    def member_health(self, member):
        """Whether an etcd member answers on its own address, and whether it is the Raft leader."""
        client = (member.get("clientURLs") or [None])[0]
        health = {"name": member.get("name"), "client": client, "ok": False, "raft_leader": False}
        if not client:
            return health
        probe = Etcd([client], timeout=1)
        probe.ctx = self.etcd.ctx
        try:
            status = probe.call("/v3/maintenance/status", {})
        except EtcdError:
            return health
        health["ok"] = True
        health["raft_leader"] = status.get("leader") == status.get("header", {}).get("member_id")
        return health

    def held(self):
        """A deploy is editing the stopped database: keep the lease, leave headscale and the snapshot alone."""
        try:
            return bool(self.hold_file) and self.wall() - os.path.getmtime(self.hold_file) < HOLD_MAX
        except OSError:
            return False

    def lead(self, desired, queue):
        if self.held():
            self.status["action"] = "held"
            self.was_held = True
            return
        target = (desired or {}).get("name")
        fresh = bool(desired) and self.wall() - desired.get("at", 0) <= self.cfg["desired_fresh"]
        if fresh and target != self.name and target in queue:
            self.status["action"] = "handing over"
            self.resign(target)
            return
        if desired and (target == self.name or not fresh):
            self.etcd.txn([{"key": b64(self.k_desired), "target": "VALUE", "result": "EQUAL",
                            "value": b64(json.dumps(desired))}], [op_delete(self.k_desired)])
        if self.serving_term != self.term or not self.headscale.running():
            self.status["action"] = "taking over"
            if not self.adopt():
                self.become_leader()
        self.start_panel()
        if not self.write_snapshot(force=self.was_held):
            self.fence("lost the lead while writing the database")
            return
        self.was_held = False
        self.status["action"] = "serve"

    # ----- manual switch -----

    def request(self, name=None):
        self.etcd.put(self.k_desired, json.dumps({"name": name or self.name, "at": int(self.wall())}))


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def make_agent(cfg):
    etcd = Etcd(cfg["etcd"]["endpoints"], cfg["etcd"].get("ca"), cfg["etcd"].get("cert"), cfg["etcd"].get("key"))
    dns = Cloudflare(open(cfg["token_file"]).read().strip(), cfg["zone"], cfg["server_name"])
    panel = Headscale(cfg["headplane_dir"], "headplane", "hp_persist.db") if cfg.get("headplane_dir") else None
    return Agent(cfg, etcd, Headscale(cfg["headscale_dir"]), dns, panel=panel)


def metrics_text(agent, meta):
    s = agent.status
    values = {
        "headscale_failover_leader": int(s["leader"] == agent.name and s["action"] == "serve"),
        "headscale_failover_has_leader": int(s["leader"] is not None),
        "headscale_failover_serving": int(agent.headscale.running()),
        "headscale_failover_lease_ok": int(bool(s["lease_ok"])),
        "headscale_failover_etcd_ok": int(bool(s["etcd_ok"])),
        "headscale_failover_error": int(bool(s["error"])),
        "headscale_failover_snapshot_timestamp_seconds": (meta or {}).get("at", 0),
        "headscale_failover_snapshot_bytes": (meta or {}).get("bytes", 0),
        "headscale_failover_last_tick_timestamp_seconds": int(agent.wall()),
    }
    return "".join(f"{k} {v}\n" for k, v in values.items())


def state_body(agent):
    return {"name": agent.name, "self_ip": agent.cfg["self_ip"], "candidate": agent.cfg["candidate"],
            "serving": agent.headscale.running(), **agent.status, **agent.view}


def serve_api(agent, listen, token):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def route(self, method):
            routes = {("GET", "/state"): self.state, ("POST", "/takeover"): self.takeover}
            handler = routes.get((method, self.path))
            if handler is None:
                return self.reply(404, {"error": "not found"})
            if not authorized(self.headers.get("Authorization"), token):
                return self.reply(401, {"error": "unauthorized"})
            return handler()

        def state(self):
            self.reply(200, state_body(agent))

        def takeover(self):
            try:
                agent.request()
            except EtcdError as e:
                return self.reply(503, {"error": f"etcd: {e}"})
            self.reply(202, {"takeover_requested": True})

        def do_GET(self):  # noqa: N802 - http.server's naming
            self.route("GET")

        def do_POST(self):  # noqa: N802
            self.route("POST")

        def log_message(self, *args):
            pass

    host, _, port = listen.rpartition(":")
    server = ThreadingHTTPServer((host, int(port)), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run(cfg):
    agent = make_agent(cfg)
    if cfg.get("api_listen"):
        token = open(cfg["api_token_file"]).read().strip()
        threading.Thread(target=start_api, args=(agent, cfg["api_listen"], token), daemon=True).start()
    threading.Thread(target=watchdog, args=(agent,), daemon=True).start()
    textfile = os.path.join(cfg["textfile_dir"], "headscale_failover.prom")
    while True:
        started = time.monotonic()
        agent.tick()
        try:
            write_atomic(textfile, metrics_text(agent, agent.view["snapshot"]))
        except OSError:
            pass
        time.sleep(max(0.0, cfg["tick"] - (time.monotonic() - started)))


def watchdog(agent):
    while True:
        try:
            agent.watchdog_check()
        except (RuntimeError, OSError) as e:
            agent.log(f"watchdog: {e}")
        time.sleep(0.5)


def start_api(agent, listen, token):
    """The tailnet address may come up after the agent: keep trying to bind."""
    while True:
        try:
            serve_api(agent, listen, token)
            return
        except OSError:
            time.sleep(5)


def seed(cfg):
    agent = make_agent(cfg)
    data = gzip.compress(snapshot_bytes(agent.headscale.db))
    meta = {"term": 0, "by": agent.name, "at": int(time.time()), "bytes": len(data),
            "hash": logical_hash(agent.headscale.db)}
    ops = [op_put(agent.k_db, data)]
    if agent.panel and os.path.exists(agent.panel.db):
        panel_data = gzip.compress(snapshot_bytes(agent.panel.db))
        meta.update(panel_hash=logical_hash(agent.panel.db, set()), panel_bytes=len(panel_data),
                    bytes=len(data) + len(panel_data))
        ops.append(op_put(agent.k_panel, panel_data))
    if meta["bytes"] > cfg["snapshot_limit"]:
        raise SystemExit("snapshot exceeds snapshot_limit")
    ops.append(op_put(agent.k_db_meta, json.dumps(meta)))
    if not agent.etcd.txn([cmp_created(agent.k_db, 0)], ops):
        raise SystemExit("etcd already holds a database snapshot")
    print(f"seeded {len(data)} bytes from {agent.headscale.db}")


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    cfg = load_json(path, None)
    if cfg is None:
        raise SystemExit(f"cannot read {path}")
    {"run": run, "seed": seed}[cmd](cfg)


if __name__ == "__main__":
    main()
