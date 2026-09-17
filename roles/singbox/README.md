# hacode.infra.singbox

Install [sing-box](https://sing-box.sagernet.org/) as a systemd-managed VLESS
egress client. Multi-instance: each entry in `singbox_instances` becomes its own
`sing-box@<name>.service` with a dedicated tun, routing table, fwmark and ipset,
so you can run several independent tunnels to different servers on one host.

## Routing modes (`routing_mode` per instance)

- **`k3s-pods`** — tunnel the egress of pods in `scope_namespaces`. Pod IPs are
  kept in an ipset maintained in real time by a `kubectl` watch
  (`singbox-podwatch@<name>.service`), so short-lived pods are captured before
  their first egress, and marked with an fwmark that policy-routes them into the
  tun. Host traffic and other namespaces are untouched. Works for gVisor
  (`runsc`) pods too — the capture is at the node's kernel forwarding path, not
  inside the pod. It needs a CNI whose forwarding path honours `ip rule`:
  Cilium resolves the route in BPF, which skips policy rules, so the packets
  are marked and still leave through the node's own address — use `dests`
  there.
- **`dests`** — route `route_dests` through the tun in the main table. No marks,
  no ipsets and no policy rules, so a BPF forwarding path finds them too; every
  other destination keeps its route, including the ssh you are holding.
- **`host`** — tunnel the whole host's egress (default route in a side table).
  The VLESS server, `local_dests` and `host_exclude_cidrs` stay on the direct
  route so the box remains reachable.
- **`none`** — bring the tun up only; route into it yourself.

`direct_domains` sends the named hosts out of the tunnel and straight off the
node's own address. Routes cannot express that when the hosts you want tunnelled
and the ones you do not sit behind the same CDN — the addresses are shared, the
names are not, and sing-box reads the SNI. Reach for it when a provider refuses
the tunnel's exit address while the same credentials work from a direct route.
Pair it with `wan_interface` so the direct outbound binds to the node's real
egress NIC; without that, `host` mode's default-route swap sends "direct" traffic
back through the tun and the exception loops instead of leaving.

## Tasks

- `install` (default via `main`) — install the pinned binary, render per-instance
  config + routing env, install helper scripts and systemd template units, then
  enable/start each instance (and its pod watcher for `k3s-pods`).
- `uninstall` — stop/disable every instance, remove its config/env and the shared
  scripts/units/binary. Stopping an instance tears down its routing via
  `ExecStopPost`.

## Example

```yaml
singbox_instances:
  - name: "apps"
    routing_mode: "k3s-pods"
    scope_namespaces: ["apps"]
    vless:
      server: "vpn.example.com"
      port: 443
      sni: "vpn.example.com"
      reality_public_key: "<pubkey>"
      short_id: "e2"
      uuid: !vault |
        ...
  - name: "telegram"
    routing_mode: "dests"
    route_dests: ["149.154.160.0/20", "91.108.4.0/22"]
    vless:
      server: "vpn.example.com"
      port: 443
      uuid: "..."
  - name: "office"
    routing_mode: "host"
    host_exclude_cidrs: ["203.0.113.0/24"]
    vless:
      server: "gw.example.net"
      port: 443
      uuid: "..."
```

Per-instance `tun_name` / `tun_address` / `route_table` / `fwmark` / `ipset`
default off the instance index, so multiple tunnels never collide. See
`defaults/main.yml` for the full schema.

The fwmark defaults to `0x1000 << index`. Keep any override out of bits 16-31:
Cilium puts the endpoint identity there, so a mark that overlaps matches roughly
half of the identities and pulls their traffic — node-to-node VXLAN included —
into the tunnel. `0x4000` and `0x8000` belong to kube-proxy.
