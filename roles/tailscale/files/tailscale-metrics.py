#!/usr/bin/env python3
"""Write tailscaled's client metrics and the path to each active peer for node_exporter's textfile collector."""
import json
import os
import subprocess
import sys


def tailscale(*args):
    return subprocess.run(["tailscale", *args], check=True, capture_output=True, text=True).stdout


def label(value):
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def peer_path(peer):
    if peer.get("CurAddr"):
        return "direct"
    if peer.get("PeerRelay"):
        return "peer_relay"
    return "derp"


def peer_metrics(status):
    rows = {"path": [], "rx": [], "tx": []}
    for peer in (status.get("Peer") or {}).values():
        name = label((peer.get("DNSName") or "").split(".")[0] or peer.get("HostName", ""))
        rows["rx"].append(f'tailscale_peer_rx_bytes_total{{peer="{name}"}} {peer.get("RxBytes", 0)}')
        rows["tx"].append(f'tailscale_peer_tx_bytes_total{{peer="{name}"}} {peer.get("TxBytes", 0)}')
        if peer.get("Active"):
            path = peer_path(peer)
            # Relay is the peer's home DERP region even when traffic bypasses it.
            relay = label(peer.get("Relay", "")) if path == "derp" else ""
            rows["path"].append(f'tailscale_peer_path{{peer="{name}",path="{path}",relay="{relay}"}} 1')
    return [
        "# HELP tailscale_peer_path Path to a peer with recent traffic: direct, peer_relay or derp (relay names its region).",
        "# TYPE tailscale_peer_path gauge",
        *rows["path"],
        "# HELP tailscale_peer_rx_bytes_total Bytes received from a peer since tailscaled started.",
        "# TYPE tailscale_peer_rx_bytes_total counter",
        *rows["rx"],
        "# HELP tailscale_peer_tx_bytes_total Bytes sent to a peer since tailscaled started.",
        "# TYPE tailscale_peer_tx_bytes_total counter",
        *rows["tx"],
    ]


def main(path):
    text = tailscale("metrics", "print").rstrip("\n") + "\n"
    text += "\n".join(peer_metrics(json.loads(tailscale("status", "--json")))) + "\n"
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


if __name__ == "__main__":
    main(sys.argv[1])
