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


def yaml(value, indent=""):
    """Block YAML of JSON-like data; region ids stay integer keys, which JSON cannot write."""
    if isinstance(value, dict):
        return "".join(f"{indent}{key}:{nested(item, indent)}" for key, item in value.items())
    return "".join(f"{indent}-{nested(item, indent, True)}" for item in value)


def nested(item, indent, in_list=False):
    if isinstance(item, (dict, list)) and item:
        body = yaml(item, indent + "  ")
        return " " + body.lstrip() if in_list and isinstance(item, dict) else "\n" + body
    return f" {json.dumps(item)}\n"


def main(regions_path, out_path, state_path):
    with open(regions_path) as f:
        regions = json.load(f)
    try:
        with open(state_path) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    for region in regions.values():
        for node in region["nodes"]:
            if not node.get("stunonly"):
                state[node["name"]] = update(state, node["name"], answers(node))
    up = {}
    for rid, region in regions.items():
        nodes = [n for n in region["nodes"] if not n.get("stunonly") and state[n["name"]]["up"]]
        if nodes:
            up[rid] = {**region, "nodes": [n for n in region["nodes"] if n.get("stunonly") or n in nodes]}
    text = yaml({"regions": {int(rid): region for rid, region in (up or regions).items()}})
    for path, content in ((state_path, json.dumps(state)), (out_path, text)):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    print(json.dumps({"up": sorted(up, key=int), "all": sorted(regions, key=int)}))


if __name__ == "__main__":
    main(*sys.argv[1:])
