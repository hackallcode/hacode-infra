# hacode.infra.singbox

Install [sing-box](https://sing-box.sagernet.org/) as a systemd-managed VLESS
egress client. Multi-instance: each entry in `singbox_instances` becomes its own
`sing-box@<name>.service` with a dedicated tun, routing table, fwmark and ipset,
so you can run several independent tunnels to different servers on one host.

## Routing modes (`routing_mode` per instance)

- **`k3s-pods`** — tunnel the egress of pods in `scope_namespaces`. Pod IPs are
  kept in an ipset refreshed every 20s (`singbox-podset-refresh@<name>.timer`)
  and marked with an fwmark that policy-routes them into the tun. Host traffic
  and other namespaces are untouched. Works for gVisor (`runsc`) pods too — the
  capture is at the node's kernel forwarding path, not inside the pod.
- **`host`** — tunnel the whole host's egress (default route in a side table).
  The VLESS server, `local_dests` and `host_exclude_cidrs` stay on the direct
  route so the box remains reachable.
- **`none`** — bring the tun up only; route into it yourself.

## Tasks

- `install` (default via `main`) — install the pinned binary, render per-instance
  config + routing env, install helper scripts and systemd template units, then
  enable/start each instance (and its refresh timer for `k3s-pods`).
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
