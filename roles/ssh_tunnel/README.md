# hacode.infra.ssh_tunnel

Manage persistent SSH tunnels as systemd units. Each entry in `ssh_tunnels`
produces a `<name>.service` unit that runs `ssh -N` with the requested local
(`-L`), remote (`-R`) and dynamic (`-D`) port forwards, restarted on failure.

## Tasks

- `install` (default): render service units and (re)start them.
- `uninstall`: stop, disable and remove service units.

## Variables

| Variable      | Default | Description                                                                                                   |
| ------------- | ------- | ------------------------------------------------------------------------------------------------------------- |
| `ssh_tunnels` | `[]`    | List of tunnels. Each entry: `name`, `remote_user`, `remote_host`, optionally `user` and `identity_file` (below), and any of `forward_port`, `reverse_port`, `forwards` (below). |
| `force`       | `false` | When `true`, restart services even if the unit file did not change.                                           |

Tunnel entry keys that pick who runs ssh:

| Key             | Default         | Description                                                                                                  |
| --------------- | --------------- | ------------------------------------------------------------------------------------------------------------ |
| `user`          | `root`          | Local account in the unit's `User=`. Its home (looked up with getent, so the account must exist) holds `.ssh/known_hosts`. |
| `identity_file` | ssh's defaults  | Private key to use: absolute, or relative to the user's home (`.ssh/id_ed25519`). Adds `IdentitiesOnly=yes`. |

Tunnel entry keys that pick the forwards:

| Key            | Renders as                        | Description                                                                         |
| -------------- | --------------------------------- | ----------------------------------------------------------------------------------- |
| `forward_port` | `-D 0.0.0.0:<port>`               | SOCKS proxy on all local addresses.                                                 |
| `reverse_port` | `-R 0.0.0.0:<port>`               | SOCKS proxy on all remote addresses (subject to the server's `GatewayPorts`).       |
| `forwards`     | one `-L` / `-R` / `-D` per item   | Explicit forwards with bind address and destination, see the item schema below.   |

`forwards` item schema:

| Field          | Required                        | Description                                                                                         |
| -------------- | ------------------------------- | --------------------------------------------------------------------------------------------------- |
| `type`         | yes                             | `local` (`-L`), `remote` (`-R`) or `dynamic` (`-D`).                                                |
| `bind_address` | no                              | Address the listening side binds. Omitted: ssh's default (loopback; for `remote` the server's `GatewayPorts` decides). IPv6 in brackets, `*` for all. |
| `bind_port`    | yes                             | Port the listening side binds.                                                                      |
| `host`, `port` | `local`: yes; `remote`: no; `dynamic`: not allowed | Where connections go, as seen from the other side. A `remote` item without them is a SOCKS proxy on the remote. |

`forward_port` / `reverse_port` render first and keep their `0.0.0.0` bind, so
entries written before `forwards` existed produce the same unit file and are
not restarted.

## Example

```yaml
- hosts: "runners"
  become: true
  roles:
    - role: "hacode.infra.ssh_tunnel"
      vars:
        ssh_tunnels:
          # SOCKS both ways on all addresses.
          - name: "cute-tunnel"
            remote_user: "runner"
            remote_host: "203.0.113.10"
            forward_port: 61173
            reverse_port: 61173
          # Publish this host's ssh and RDP on the jump host's private
          # address, and reach a dashboard behind it on local 3000. Runs
          # as the workstation's own user, with that user's key.
          - name: "office-link"
            user: "alice"
            identity_file: ".ssh/id_ed25519"
            remote_user: "tunnel"
            remote_host: "203.0.113.10"
            forwards:
              - {type: "remote", bind_address: "10.0.0.10", bind_port: 7722, host: "127.0.0.1", port: 22}
              - {type: "remote", bind_address: "10.0.0.10", bind_port: 7789, host: "127.0.0.1", port: 3389}
              - {type: "local", bind_port: 3000, host: "grafana.internal", port: 3000}
```

## Notes

- The unit runs as `root` unless the entry sets `user`. A root tunnel keeps
  exactly the unit it had before `user` existed, so it is not restarted.
- Authentication relies on the running user's existing SSH key (`BatchMode`,
  no agent, so the key must not need a passphrase). Provision keys out of
  band: the role does not manage SSH credentials or create the user.
- A non-root user's `~/.ssh/config` still applies to the connection; the
  unit's `-o` options win over it, other settings (`ControlMaster`,
  `ProxyJump`, ...) do not, so keep the `remote_host` out of such blocks.
- The `ssh` binary is provided by the base OS; the role does not install it.
- A remote bind on a specific address needs `GatewayPorts clientspecified` on
  the server; `permitlisten` / `PermitListen` there can pin what the key may
  bind.
