# hacode.infra.gost

Install [go-gost](https://github.com/go-gost/gost) as one-or-more systemd services with transparent firewalld REDIRECT
rules into SOCKS5 upstreams.

## Tasks

- `install` (default): download binary, render `<name>.service` per instance, start units, install firewalld rules
  (RHEL only).
- `uninstall`: stop + remove units, strip firewall rules, delete the binary.

## Instance model

Each entry in `gost_instances` produces a separate gost daemon. There's no built-in distinction between "selective"
and "default-route" - that's just a function of *how* you attach traffic to a given instance:

| Capture mode | How you set it | Where it lands |
| --- | --- | --- |
| Selective | `redirects: [{ip: ...}, ...]` on the instance | REDIRECT rules at firewalld priority `0`, OUTPUT + PREROUTING |
| Default route | `default: true` on the instance | RETURN excludes at priority `1`, catch-all REDIRECT at priority `100` |

An instance can use either mode or both. You can have N selective instances pointing at different SOCKS upstreams.
At most one instance per host may set `default: true` (multiple catch-alls would collide).

## Variables

```yaml
gost_version: "3.2.4"          # upstream release
gost_arch: "{{ ... }}"         # auto-mapped from ansible_architecture
gost_bin_path: "/usr/local/bin/gost"

gost_docker_cidr: "172.16.0.0/12"   # source CIDR for PREROUTING-chain rules

# CIDRs RETURNed past any `default: true` catch-all. Override per-instance
# with `exclude_cidrs`.
gost_default_exclude_cidrs:
  - "10.0.0.0/8"
  - "127.0.0.0/8"
  - "169.254.0.0/16"
  - "172.16.0.0/12"
  - "192.168.0.0/16"

gost_instances: []
```

### `gost_instances[*]` schema

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | systemd unit basename (no `.service` suffix) |
| `listen_port` | yes | local TCP port for transparent REDIRECT capture |
| `socks_ip` | yes | upstream SOCKS5 host |
| `socks_port` | yes | upstream SOCKS5 port |
| `socks_user` | no | SOCKS5 username (auth via `user:pass@host:port`) |
| `socks_pass` | no | SOCKS5 password |
| `redirects` | no | list of `{ip, state?}` for selective REDIRECT. `state: disabled` removes a previously installed rule |
| `default` | no | when `true`, install a catch-all REDIRECT for all remaining TCP |
| `exclude_cidrs` | no | per-instance override of `gost_default_exclude_cidrs` (only meaningful with `default: true`) |

## Example

Three independent gosts on the same host:

```yaml
- hosts: "edge"
  become: true
  roles:
    - role: "hacode.infra.gost"
      vars:
        gost_instances:
          # 1) Route corporate IPs through a no-auth internal SOCKS.
          - name: "gost-corp"
            listen_port: 23104
            socks_ip: "10.0.0.5"
            socks_port: 1080
            redirects:
              - { ip: "203.0.113.10" }
              - { ip: "203.0.113.11" }
              - { ip: "10.42.0.0/16" }
          # 2) Route a second set of IPs through a separate SOCKS upstream.
          - name: "gost-vendor"
            listen_port: 23105
            socks_ip: "10.0.0.6"
            socks_port: 1080
            redirects:
              - { ip: "198.51.100.20" }
          # 3) Default route: everything else (except gost_default_exclude_cidrs)
          #    goes through an authenticated external SOCKS.
          - name: "gost-default"
            listen_port: 23106
            socks_ip: "10.0.0.7"
            socks_port: 1080
            socks_user: "alice"
            socks_pass: "secret"
            default: true
```

## Notes

- Firewalld is RHEL-only - on Debian/Ubuntu the role installs the binary and units but leaves firewall
  configuration to the operator (ufw / nftables / iptables).
- The `default: true` instance excludes RFC 1918 + loopback + link-local by default. Adjust `exclude_cidrs` per
  instance, or `gost_default_exclude_cidrs` globally.
- Rule priorities are: selective REDIRECT at `0`, default excludes at `1`, default catch-all at `100`. The role
  hard-codes these because firewalld direct rules apply in priority order.
