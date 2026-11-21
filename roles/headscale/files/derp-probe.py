"""Write the DERP map headscale serves: the regions whose relays this host reaches.

A client relays to a peer through the peer's home region, so a region that some nodes cannot reach cuts them off from
every peer homed there; a region this host does not reach is left out until it answers again.

derp-probe.py <regions.json> <derp.yml> <state.json>

A node changes state after FLIPS checks in a row disagree with it; one never checked takes the first result. A region
without a node up is left out; with none up anywhere, the whole map is written: this host is the one cut off.
"""

import json
import os
import socket
import ssl
import sys

FLIPS = 3
TIMEOUT = 3


def answers(node):
    host, name = node.get("ipv4") or node["hostname"], node.get("certname") or node["hostname"]
    context = ssl.create_default_context()
    if node.get("insecurefortests"):
        context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
    try:
        with socket.create_connection((host, node.get("derpport") or 443), timeout=TIMEOUT) as raw:
            with context.wrap_socket(raw, server_hostname=name) as tls:
                tls.sendall(f"GET /derp/probe HTTP/1.1\r\nHost: {name}\r\nConnection: close\r\n\r\n".encode())
                return tls.recv(64).split(b" ", 2)[1:2] == [b"200"]
    except (OSError, IndexError):
        return False


def update(state, name, up):
    known = state.get(name)
    if known is None or known["up"] == up:
        return {"up": up, "streak": 0}
    if known["streak"] + 1 >= FLIPS:
        return {"up": up, "streak": 0}
    return {"up": known["up"], "streak": known["streak"] + 1}


def main(regions_path, out_path, state_path):
    with open(regions_path) as f:
        regions = json.load(f)
    try:
        with open(state_path) as f:
            known = json.load(f)
    except (OSError, ValueError):
        known = {}
    state = {node["name"]: update(known, node["name"], answers(node))
             for region in regions.values() for node in region["nodes"] if not node.get("stunonly")}
    up = {}
    for rid, region in regions.items():
        nodes = [n for n in region["nodes"] if not n.get("stunonly") and state[n["name"]]["up"]]
        if nodes:
            up[rid] = {**region, "nodes": [n for n in region["nodes"] if n.get("stunonly") or n in nodes]}
    # Each region as JSON, which is YAML, under its id as an integer key, which JSON cannot write.
    text = "regions:\n" + "".join(f"  {int(rid)}: {json.dumps(region)}\n" for rid, region in (up or regions).items())
    for path, content in ((state_path, json.dumps(state)), (out_path, text)):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    print(json.dumps({"up": sorted(up, key=int), "all": sorted(regions, key=int)}))


if __name__ == "__main__":
    main(*sys.argv[1:])
