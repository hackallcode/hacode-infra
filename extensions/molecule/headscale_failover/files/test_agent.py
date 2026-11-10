"""The failover agent: python3 test_agent.py <headscale-failover> ; ETCD_BIN=<etcd> also runs it against a real etcd."""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

loader = importlib.machinery.SourceFileLoader("hf", sys.argv.pop(1))
spec = importlib.util.spec_from_loader("hf", loader)
hf = importlib.util.module_from_spec(spec)
loader.exec_module(hf)

ETCD_BIN = os.environ.get("ETCD_BIN")


def make_db(path, nodes=("ru",)):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY, given_name TEXT, last_seen TEXT, endpoints TEXT)")
    for i, name in enumerate(nodes, 1):
        conn.execute("INSERT INTO nodes VALUES (?, ?, ?, ?)", (i, name, "t0", "e0"))
    conn.commit()
    conn.close()


def add_node(path, name):
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO nodes (given_name, last_seen, endpoints) VALUES (?, 't', 'e')", (name,))
    conn.commit()
    conn.close()


def node_names(path):
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute("SELECT given_name FROM nodes ORDER BY id")]
    finally:
        conn.close()


class Pure(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "db.sqlite")
        make_db(self.db)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_election_order_is_queue_order(self):
        kvs = [{"key": hf.b64("/m/election/ru"), "create_revision": "7"},
               {"key": hf.b64("/m/election/nl"), "create_revision": "9"}]
        self.assertEqual(hf.election_order(kvs, "/m/election/"), [("ru", 7), ("nl", 9)])

    def test_reconnect_columns_do_not_change_the_hash(self):
        before = hf.logical_hash(self.db)
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE nodes SET last_seen = 't1', endpoints = 'e1'")
        conn.commit()
        conn.close()
        self.assertEqual(hf.logical_hash(self.db), before)

    def test_litestream_bookkeeping_does_not_change_the_snapshot_hash(self):
        before = hf.logical_hash(self.db)
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE _litestream_seq (id INTEGER PRIMARY KEY, seq INTEGER)")
        conn.execute("INSERT INTO _litestream_seq VALUES (1, 10)")
        conn.commit()
        conn.close()
        self.assertEqual(hf.logical_hash(self.db), before)

    def test_real_changes_do(self):
        before = hf.logical_hash(self.db)
        add_node(self.db, "nl")
        self.assertNotEqual(hf.logical_hash(self.db), before)

    def test_snapshot_restores_with_uncheckpointed_writes(self):
        writer = sqlite3.connect(self.db)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO nodes (given_name) VALUES ('in-wal')")
        writer.commit()
        data = hf.snapshot_bytes(self.db)
        writer.close()
        other = os.path.join(self.dir, "other.sqlite")
        make_db(other, nodes=("stale",))
        hf.restore_db(other, data)
        self.assertFalse(os.path.exists(other + "-wal"))
        self.assertEqual(node_names(other), ["ru", "in-wal"])

    def test_restore_refuses_garbage(self):
        with self.assertRaises((ValueError, sqlite3.DatabaseError)):
            hf.restore_db(self.db, b"not a database" * 100)
        self.assertEqual(node_names(self.db), ["ru"])

    def test_token_check(self):
        self.assertTrue(hf.authorized("Bearer s3cret", "s3cret"))
        self.assertFalse(hf.authorized("Bearer other", "s3cret"))
        self.assertFalse(hf.authorized(None, "s3cret"))
        self.assertFalse(hf.authorized("Bearer ", ""))


class FakeHeadscale:
    def __init__(self, directory):
        os.makedirs(directory, exist_ok=True)
        self.db = os.path.join(directory, "db.sqlite")
        self.up = False
        self.starts = 0

    def running(self):
        return self.up

    def start(self):
        self.up, self.starts = True, self.starts + 1
        return True

    def stop(self):
        self.up = False
        return True


class FakeDns:
    def __init__(self):
        self.ip = None

    def get(self):
        return self.ip

    def set(self, ip):
        self.ip = ip


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(ETCD_BIN, "ETCD_BIN not set")
class WithEtcd(unittest.TestCase):
    TTL = 5

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        client, peer = free_port(), free_port()
        self.url = f"http://127.0.0.1:{client}"
        self.proc = subprocess.Popen(
            [ETCD_BIN, "--data-dir", os.path.join(self.dir, "etcd"), "--listen-client-urls", self.url,
             "--advertise-client-urls", self.url, "--listen-peer-urls", f"http://127.0.0.1:{peer}",
             "--initial-advertise-peer-urls", f"http://127.0.0.1:{peer}",
             "--initial-cluster", f"default=http://127.0.0.1:{peer}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen(self.url + "/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        self.dns = FakeDns()
        self.agents = {}
        for name, ip in (("ru", "192.0.2.10"), ("nl", "192.0.2.20")):
            cfg = {"name": name, "self_ip": ip, "candidate": True, "prefix": "/mesh", "lease_ttl": self.TTL,
                   "snapshot_debounce": 0, "snapshot_limit": 512 * 1024, "desired_wait": 3, "desired_fresh": 60,
                   "state_dir": os.path.join(self.dir, name)}
            self.agents[name] = hf.Agent(cfg, hf.Etcd([self.url]), FakeHeadscale(os.path.join(self.dir, name)),
                                         self.dns, log=lambda *a: None)
        make_db(self.agents["ru"].headscale.db, nodes=("seeded",))
        self.seed(self.agents["ru"])

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait()
        shutil.rmtree(self.dir)

    def seed(self, agent):
        data = hf.gzip.compress(hf.snapshot_bytes(agent.headscale.db))
        meta = {"term": 0, "by": agent.name, "at": 0, "bytes": len(data), "hash": hf.logical_hash(agent.headscale.db)}
        agent.etcd.txn([hf.cmp_created(agent.k_db, 0)],
                       [hf.op_put(agent.k_db, data), hf.op_put(agent.k_db_meta, json.dumps(meta))])

    def tick_all(self, times=1, only=None):
        for _ in range(times):
            for name, agent in self.agents.items():
                if only is None or name in only:
                    agent.tick()

    def leader(self):
        serving = [n for n, a in self.agents.items() if a.headscale.up]
        self.assertLessEqual(len(serving), 1, f"two serving at once: {serving}")
        return serving[0] if serving else None

    def test_first_candidate_leads_from_the_seed(self):
        self.tick_all(2)
        self.assertEqual(self.leader(), "ru")
        self.assertEqual(self.dns.ip, "192.0.2.10")
        self.assertEqual(node_names(self.agents["ru"].headscale.db), ["seeded"])
        self.assertEqual(self.agents["nl"].status["action"], "standby")

    def test_manual_switch_hands_over_the_latest_data(self):
        self.tick_all(2)
        add_node(self.agents["ru"].headscale.db, "made-on-ru")
        self.tick_all(1)
        self.agents["nl"].request()
        for _ in range(10):
            self.tick_all(1)
            if self.leader() == "nl":
                break
            time.sleep(0.5)
        self.assertEqual(self.leader(), "nl")
        self.assertEqual(self.dns.ip, "192.0.2.20")
        self.assertEqual(node_names(self.agents["nl"].headscale.db), ["seeded", "made-on-ru"])
        self.assertIsNone(self.agents["nl"].etcd.get(self.agents["nl"].k_desired))
        history = [h["event"] for h in hf.kv_json(self.agents["nl"].etcd.get(self.agents["nl"].k_history))]
        self.assertIn("handed over to nl on request", history)

    def test_a_leader_cut_off_from_etcd_fences_before_the_other_takes_over(self):
        self.enable_panels()
        self.tick_all(2)
        ru, nl = self.agents["ru"], self.agents["nl"]
        ru.etcd = hf.Etcd(["http://127.0.0.1:9"], timeout=0.2)
        fenced_at = taken_at = None
        start = time.monotonic()
        while time.monotonic() - start < self.TTL * 3 and taken_at is None:
            ru.tick()
            nl.tick()
            if fenced_at is None and not ru.headscale.up:
                fenced_at = time.monotonic()
            if nl.headscale.up:
                taken_at = time.monotonic()
            self.leader()
            time.sleep(0.3)
        self.assertIsNotNone(fenced_at, "the cut-off leader kept serving")
        self.assertIsNotNone(taken_at, "nobody took over")
        self.assertLess(fenced_at, taken_at)
        self.assertFalse(ru.panel.up)
        self.assertTrue(nl.panel.up)
        self.assertEqual(self.dns.ip, "192.0.2.20")

    def test_a_restart_keeps_changes_not_yet_in_etcd(self):
        self.tick_all(2)
        ru = self.agents["ru"]
        ru.write_snapshot(force=True)
        add_node(ru.headscale.db, "not-yet-in-etcd")
        restarted = hf.Agent(ru.cfg, hf.Etcd([self.url]), ru.headscale, self.dns, log=lambda *a: None)
        self.agents["ru"] = restarted
        self.tick_all(2)
        self.assertIn("not-yet-in-etcd", node_names(restarted.headscale.db))
        restarted.cfg = dict(restarted.cfg, snapshot_debounce=0)
        self.tick_all(1)
        self.assertEqual(hf.kv_json(restarted.etcd.get(restarted.k_db_meta))["hash"],
                         hf.logical_hash(restarted.headscale.db))

    def test_the_watchdog_fences_while_etcd_calls_hang(self):
        self.tick_all(2)
        ru = self.agents["ru"]

        class Hanging:
            def __getattr__(self, name):
                def hang(*args, **kwargs):
                    time.sleep(60)
                return hang

        ru.etcd = Hanging()
        start = time.monotonic()
        while time.monotonic() - start < self.TTL and ru.headscale.up:
            ru.watchdog_check()
            time.sleep(0.2)
        self.assertFalse(ru.headscale.up, "the watchdog kept a leader without a lease serving")
        self.assertLess(time.monotonic() - start, self.TTL * 0.8)

    def test_the_api_view_comes_from_the_last_tick(self):
        self.tick_all(2)
        view = self.agents["nl"].view
        self.assertEqual(view["queue"], ["ru", "nl"])
        self.assertEqual(view["snapshot"]["by"], "ru")
        self.assertEqual([(m["ok"], m["raft_leader"]) for m in view["members"]], [(True, True)])

    def test_a_stale_leader_cannot_write_the_database(self):
        self.tick_all(2)
        ru = self.agents["ru"]
        stale_term = ru.term
        original_meta = hf.kv_json(ru.etcd.get(ru.k_db_meta))
        ru.etcd.txn([hf.cmp_created(ru.k_mine, stale_term)], [hf.op_delete(ru.k_mine)])
        add_node(ru.headscale.db, "written-after-losing-the-lead")
        ru.snapshot_hash = None
        self.assertFalse(ru.write_snapshot(force=True))
        meta = hf.kv_json(ru.etcd.get(ru.k_db_meta))
        self.assertEqual(meta, original_meta)

    def test_agent_restart_keeps_a_serving_headscale(self):
        self.tick_all(2)
        ru = self.agents["ru"]
        ru.write_snapshot(force=True)
        starts = ru.headscale.starts
        restarted = hf.Agent(ru.cfg, hf.Etcd([self.url]), ru.headscale, self.dns, log=lambda *a: None)
        restarted.watchdog_check()
        self.assertTrue(restarted.headscale.up, "the watchdog fenced before the first renewal")
        self.agents["ru"] = restarted
        self.tick_all(3)
        self.assertTrue(restarted.headscale.up)
        self.assertEqual(restarted.headscale.starts, starts)

    def enable_panels(self):
        for name, agent in self.agents.items():
            agent.panel = FakeHeadscale(os.path.join(self.dir, name, "panel"))
            with sqlite3.connect(agent.panel.db) as c:
                c.execute("CREATE TABLE users (sub TEXT PRIMARY KEY, headscale_user_id TEXT, role TEXT, updated_at INTEGER)")
                c.execute("CREATE TABLE auth_sessions (id TEXT PRIMARY KEY, user_sub TEXT)")
                if name == "ru":
                    c.execute("INSERT INTO users VALUES ('veronika', '6', 'user', 1)")
        ru = self.agents["ru"]
        meta = hf.kv_json(ru.etcd.get(ru.k_db_meta))
        meta["panel_hash"] = hf.logical_hash(ru.panel.db, set())
        ru.etcd.txn([], [hf.op_put(ru.k_panel, hf.gzip.compress(hf.snapshot_bytes(ru.panel.db))),
                         hf.op_put(ru.k_db_meta, json.dumps(meta))])

    def test_panel_links_roles_and_sessions_travel_on_handover(self):
        self.enable_panels()
        self.tick_all(2)
        ru, nl = self.agents["ru"], self.agents["nl"]
        with sqlite3.connect(ru.panel.db) as c:
            c.execute("INSERT INTO auth_sessions VALUES ('session', 'veronika')")
            c.execute("UPDATE users SET updated_at=2")
        # No normal snapshot tick: resign must capture the final writes itself.
        nl.request()
        self.tick_all(2)
        self.assertEqual(self.leader(), "nl")
        self.assertFalse(ru.panel.up)
        self.assertTrue(nl.panel.up)
        with sqlite3.connect(nl.panel.db) as c:
            self.assertEqual(c.execute("SELECT * FROM users").fetchall(), [('veronika', '6', 'user', 2)])
            self.assertEqual(c.execute("SELECT * FROM auth_sessions").fetchall(), [('session', 'veronika')])

    def test_new_leader_restart_keeps_unsnapshotted_panel_changes(self):
        self.enable_panels()
        self.tick_all(2)
        nl = self.agents["nl"]
        nl.request()
        self.tick_all(2)
        self.assertEqual(self.leader(), "nl")
        add_node(nl.headscale.db, "after-takeover")
        with sqlite3.connect(nl.panel.db) as c:
            c.execute("UPDATE users SET updated_at=3")
        restarted = hf.Agent(nl.cfg, hf.Etcd([self.url]), nl.headscale, self.dns,
                             panel=nl.panel, log=lambda *a: None)
        self.agents["nl"] = restarted
        self.tick_all(2)
        self.assertIn("after-takeover", node_names(restarted.headscale.db))
        with sqlite3.connect(restarted.panel.db) as c:
            self.assertEqual(c.execute("SELECT updated_at FROM users").fetchone(), (3,))

    def test_panel_only_changes_are_snapshotted(self):
        self.enable_panels()
        self.tick_all(2)
        ru = self.agents["ru"]
        before = hf.kv_value(ru.etcd.get(ru.k_panel))
        with sqlite3.connect(ru.panel.db) as c:
            c.execute("UPDATE users SET updated_at=5")
        self.tick_all(1)
        self.assertNotEqual(before, hf.kv_value(ru.etcd.get(ru.k_panel)))

    def test_watchdog_also_fences_a_panel_when_headscale_is_already_stopped(self):
        self.enable_panels()
        self.tick_all(2)
        ru = self.agents["ru"]
        ru.headscale.stop()
        ru.renewed_at = time.monotonic() - self.TTL
        ru.lease_until = time.monotonic() - 1
        ru.watchdog_check()
        self.assertFalse(ru.panel.up)

    def test_standby_stops_an_independently_started_panel(self):
        self.enable_panels()
        self.tick_all(2)
        nl = self.agents["nl"]
        nl.panel.start()
        nl.tick()
        self.assertFalse(nl.panel.up)

    def test_takeover_refuses_to_overwrite_an_unmigrated_panel(self):
        self.enable_panels()
        ru = self.agents["ru"]
        ru.etcd.txn([], [hf.op_delete(ru.k_panel)])
        self.tick_all(1)
        self.assertFalse(ru.headscale.up)
        self.assertIn("migrate", ru.status["error"])
        with sqlite3.connect(ru.panel.db) as c:
            self.assertEqual(c.execute("SELECT sub FROM users").fetchall(), [('veronika',)])

    def test_stale_leader_cannot_replace_panel_snapshot(self):
        self.enable_panels()
        self.tick_all(2)
        ru = self.agents["ru"]
        before = hf.kv_value(ru.etcd.get(ru.k_panel))
        ru.etcd.txn([], [hf.op_delete(ru.k_mine)])
        with sqlite3.connect(ru.panel.db) as c:
            c.execute("DELETE FROM users")
        self.assertFalse(ru.write_snapshot(force=True))
        self.assertEqual(before, hf.kv_value(ru.etcd.get(ru.k_panel)))

    def hold_edit(self, ru, age=0):
        meta = hf.kv_json(ru.etcd.get(ru.k_db_meta))
        ru.etcd.put(ru.k_db_meta, json.dumps(dict(meta, by="nl")))
        open(ru.hold_file, "w").close()
        os.utime(ru.hold_file, (time.time() - age, time.time() - age))
        ru.headscale.stop()
        add_node(ru.headscale.db, "edited-while-held")

    def test_a_hold_keeps_a_database_edit(self):
        self.tick_all(2)
        ru = self.agents["ru"]
        self.hold_edit(ru)
        self.tick_all(3)
        self.assertEqual(ru.status["action"], "held")
        self.assertFalse(ru.headscale.up)
        self.assertEqual(self.agents["nl"].status["action"], "standby")
        ru.headscale.start()
        os.remove(ru.hold_file)
        self.tick_all(2)
        self.assertEqual(self.leader(), "ru")
        self.assertIn("edited-while-held", node_names(ru.headscale.db))
        meta = hf.kv_json(ru.etcd.get(ru.k_db_meta))
        self.assertEqual((meta["by"], meta["hash"]), ("ru", hf.logical_hash(ru.headscale.db)))

    def test_a_stale_hold_does_not_count(self):
        self.tick_all(2)
        ru = self.agents["ru"]
        self.hold_edit(ru, age=hf.HOLD_MAX + 1)
        self.tick_all(2)
        self.assertTrue(ru.headscale.up)
        self.assertNotIn("edited-while-held", node_names(ru.headscale.db))


if __name__ == "__main__":
    unittest.main()
