#!/usr/bin/env python3
"""nats-server's monitoring JSON as node_exporter textfile metrics."""
import json
import os
import re
import sys
import time
import urllib.request

monitor_port, OUT, routes_expected = sys.argv[1:4]
MONITOR = f"http://127.0.0.1:{monitor_port}"
ROUTES_EXPECTED = int(routes_expected)
UNITS = {"ns": 1e-9, "µs": 1e-6, "us": 1e-6, "ms": 1e-3, "s": 1, "m": 60, "h": 3600}


def get(path):
    with urllib.request.urlopen(MONITOR + path, timeout=5) as r:
        return json.load(r)


def go_duration_seconds(duration):
    return sum(float(n) * UNITS[u] for n, u in re.findall(r"([\d.]+)(ns|µs|us|ms|s|m|h)", duration or ""))


def label(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def collect():
    lines = []
    try:
        healthy = get("/healthz?js-enabled-only=true").get("status") == "ok"
    except Exception:
        healthy = False
    lines.append(f"nats_up {int(healthy)}")
    lines.append(f"nats_routes_expected {ROUTES_EXPECTED}")
    try:
        varz, routez = get("/varz"), get("/routez")
        jsz = get("/jsz?accounts=true&streams=true&config=true")
    except Exception:
        return lines
    me = varz.get("server_name")

    rtts = {}
    for route in routez.get("routes", []):
        remote = route.get("remote_name") or route.get("remote_id")
        rtt = go_duration_seconds(route.get("rtt"))
        rtts[remote] = min(rtt, rtts.get(remote, rtt))
    lines.append(f"nats_routes {len(rtts)}")
    lines += [f'nats_route_rtt_seconds{{remote="{label(r)}"}} {v}' for r, v in sorted(rtts.items())]

    meta = jsz.get("meta_cluster") or {}
    lines.append(f"nats_jetstream_meta_leader {int(meta.get('leader') == me)}")
    if meta.get("leader") == me:
        for peer in meta.get("replicas") or []:
            current = peer.get("current") and not peer.get("offline")
            lines.append(f'nats_jetstream_peer_current{{peer="{label(peer["name"])}"}} {int(bool(current))}')

    for account in jsz.get("account_details") or []:
        for stream in account.get("stream_detail") or []:
            name = label(stream["name"])
            cluster = stream.get("cluster") or {}
            lines.append(f'nats_stream_bytes{{stream="{name}"}} {stream["state"]["bytes"]}')
            max_bytes = (stream.get("config") or {}).get("max_bytes", -1)
            if max_bytes > 0:
                lines.append(f'nats_stream_max_bytes{{stream="{name}"}} {max_bytes}')
            if cluster.get("leader") == me:
                lines.append(f'nats_stream_leader{{stream="{name}"}} 1')
                for peer in cluster.get("replicas") or []:
                    current = peer.get("current") and not peer.get("offline")
                    lines.append(f'nats_stream_replica_current{{stream="{name}",peer="{label(peer["name"])}"}} '
                                 f'{int(bool(current))}')
    return lines


lines = collect() + [f"nats_metrics_timestamp_seconds {int(time.time())}"]
tmp = OUT + ".tmp"
with open(tmp, "w") as f:
    f.write("\n".join(lines) + "\n")
os.replace(tmp, OUT)
