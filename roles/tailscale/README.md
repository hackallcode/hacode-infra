# hacode.infra.tailscale

Install [tailscale](https://tailscale.com) from pkgs.tailscale.com at a pinned version and join a tailnet - usually
one run by `hacode.infra.headscale` - with a one-off preauth key.

## Tasks

- `install` (default): repository, pinned package, `tailscaled` port and MTU, IP forwarding (opt-in), firewalld (UDP
  port open, `tailscale0` in `tailscale_firewalld_zone`); sets the `tailscale_backend_state` fact (`Running`,
  `NeedsLogin`, ...).
- `up`: `tailscale up --reset` with `tailscale_login_server`, `tailscale_authkey` and `tailscale_up_args`. Run it for
  nodes whose `tailscale_backend_state` isn't `Running`, or to re-apply the flags.
- `uninstall`: log out, remove the package, repository, firewalld rules and state.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `tailscale_version` | `1.104.5` | package version |
| `tailscale_port` | `41641` | tailscaled UDP port, opened in firewalld |
| `tailscale_mtu` | `1200` | `tailscale0` MTU (`TS_DEBUG_MTU`); `0` keeps tailscale's 1280 |
| `tailscale_firewalld_zone` | `trusted` | zone for `tailscale0`; the tailnet policy filters traffic |
| `tailscale_exit_node` | `false` | `up`: `--advertise-exit-node`, forwarding on |
| `tailscale_ip_forward` | `tailscale_exit_node` | enable IPv4/IPv6 forwarding (exit node, subnet routes) |
| `tailscale_login_server` | `""` | `up`: control server URL |
| `tailscale_authkey` | `""` | `up`: one-off preauth key, never stored; a tagged key tags the node |
| `tailscale_hostname` | `inventory_hostname` | `up`: node name |
| `tailscale_up_args` | `[]` | `up`: extra flags, e.g. `--accept-dns=false`; not `--advertise-tags`, and not `--advertise-exit-node`/`--advertise-routes` - `tailscale_exit_node` / `tailscale_ip_forward` own those and the forwarding behind them |

## Example

```yaml
- hosts: "servers"
  become: true
  vars:
    tailscale_login_server: "https://hs.example.com"
    tailscale_up_args: ["--accept-dns=false"]
  roles:
    - role: "hacode.infra.tailscale"
  tasks:
    - name: "Get a key from the control server"
      ansible.builtin.include_role:
        name: "hacode.infra.headscale"
        tasks_from: "preauth-key"
        apply:
          delegate_to: "control"
      vars:
        headscale_preauth_tags: ["tag:server"]
      when: "tailscale_backend_state != 'Running'"

    - name: "Join the tailnet"
      ansible.builtin.include_role:
        name: "hacode.infra.tailscale"
        tasks_from: "up"
      vars:
        tailscale_authkey: "{{ headscale_preauth_key }}"
      when: "tailscale_backend_state != 'Running'"
```
