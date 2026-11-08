# hacode.infra.derper

Run a standalone Tailscale [DERP](https://tailscale.com/kb/1232/derp-servers) relay with STUN in docker compose with host
networking. There is no upstream derper binary or image, so the image is built from `tailscale.com/cmd/derper` at
`derper_version`. derper serves plain HTTP on `derper_port`; terminate TLS in front of it with connection upgrade.

## Tasks

- `install` (default): build and start derper, wait for `/derp/probe`, open the STUN port in firewalld (when active).
- `uninstall`: stop derper, drop its image, close the STUN port, delete `derper_dir`.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `derper_version` | `1.104.5` | tailscale release to build derper from |
| `derper_go_version` | `1.27` | Go toolchain image; must satisfy tailscale's `go.mod` |
| `derper_dir` | `/opt/derper` | compose project and `data/` (node key) |
| `derper_hostname` | `""` (required) | DERP host name as listed in the DERP map |
| `derper_port` | `8445` | HTTP port on all interfaces (STUN shares the bind address) - keep it closed in the firewall |
| `derper_stun_port` | `3478` | STUN UDP port, opened in firewalld |
| `derper_verify_clients` | `true` | admit only nodes known to the local tailscaled (it must run on the host); adds a tailscaled drop-in that keeps `/run/tailscale` across restarts |
| `derper_extra_args` | `[]` | extra derper flags |

## Example

```yaml
- hosts: "relay"
  become: true
  roles:
    - role: "hacode.infra.tailscale"
    - role: "hacode.infra.derper"
      vars:
        derper_hostname: "derp.example.com"
```

Add the relay to the control server's DERP map, e.g. `headscale_derp_regions` of `hacode.infra.headscale`.
