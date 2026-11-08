"""Read or pin node addresses in the headscale database (headscale has no API for it).

A node is found by its given name, which is unique, or else by the hostname it reports, which a rename does not change.

node-ips.py <db>          print {"<given name or hostname>": ["<ipv4>", "<ipv6>"]} of live nodes
node-ips.py <db> <json>   set {"<given name or hostname>": ["<ipv4>", "<ipv6>"]}; headscale must be stopped
"""

import json
import os
import sqlite3
import sys


def rows(db):
    return db.execute("SELECT id, given_name, hostname, ipv4, ipv6 FROM nodes WHERE deleted_at IS NULL").fetchall()


def nodes(db):
    live = rows(db)
    return {**{hostname: [ipv4 or "", ipv6 or ""] for _, _, hostname, ipv4, ipv6 in live},
            **{given: [ipv4 or "", ipv6 or ""] for _, given, _, ipv4, ipv6 in live}}


def find(live, key):
    return [row[0] for row in live if row[1] == key] or [row[0] for row in live if row[2] == key]


def pin(db, pins):
    live = rows(db)
    found = {key: find(live, key) for key in pins}
    twins = sorted(key for key, ids in found.items() if len(ids) > 1)
    if twins:
        sys.exit("several nodes with the hostname: " + ", ".join(twins))
    pinned = {ids[0] for ids in found.values() if ids}
    taken = {ip: given for node, given, _, *ips in live if node not in pinned for ip in ips if ip}
    clashes = [f"{ip} ({taken[ip]})" for ips in pins.values() for ip in ips if ip in taken]
    if clashes:
        sys.exit("addresses in use: " + ", ".join(clashes))
    with db:
        for name, (ipv4, ipv6) in pins.items():
            if found[name]:
                db.execute("UPDATE nodes SET ipv4 = ?, ipv6 = ? WHERE id = ?", (ipv4, ipv6, found[name][0]))


def main():
    path = sys.argv[1]
    if len(sys.argv) == 2:
        print(json.dumps(nodes(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) if os.path.exists(path) else {}))
    else:
        pin(sqlite3.connect(path), json.loads(sys.argv[2]))


main()
