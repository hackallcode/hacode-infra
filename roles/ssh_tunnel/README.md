# hacode.infra.ssh_tunnel

Manage persistent SSH tunnels as systemd units. Each entry in `ssh_tunnels`
produces a `<name>.service` unit that runs `ssh -N` with optional `-D`
(forward) and `-R` (reverse) port bindings, restarted on failure.

## Tasks

- `install` (default): render service units and (re)start them.
- `uninstall`: stop, disable and remove service units.

## Variables

| Variable      | Default | Description                                                                                                                   |
| ------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `ssh_tunnels` | `[]`    | List of tunnels. Each entry: `name`, `remote_user`, `remote_host`, optional `forward_port` (`-D`), optional `reverse_port` (`-R`). |
| `force`       | `false` | When `true`, restart services even if the unit file did not change.                                                           |

## Example

```yaml
- hosts: "runners"
  become: true
  roles:
    - role: "hacode.infra.ssh_tunnel"
      vars:
        ssh_tunnels:
          - name: "cute-tunnel"
            remote_user: "runner"
            remote_host: "203.0.113.10"
            forward_port: 61173
            reverse_port: 61173
```

## Notes

- The unit runs as `root` so it can bind low ports remotely if needed.
- Authentication relies on `root`'s existing SSH key/agent. Provision keys
  out of band (the role does not manage SSH credentials).
- The `ssh` binary is provided by the base OS; the role does not install it.
