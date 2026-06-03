# hacode.infra.certificate

Generate an internal self-signed CA and issue per-host certificates.
Useful for internal services (Cockpit, dashboards, internal nginx vhosts).

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `cert_dir` | `../../output/certs` | controller-side output directory |
| `cert_issued_dir` | `{{ cert_dir }}/issued` | per-host certs subdirectory |
| `force` | `false` | force regeneration |
| `server_names` | inventory-specific | list of `{name, ...}` items for which certs are issued |

## Tasks

- `main` / `ca` / `ca_create`: ensure CA exists.
- `hostnames` / `hostname` / `hostname_create`: issue per-host certs.

## Example

```yaml
- hosts: "localhost"
  connection: "local"
  roles:
    - role: "hacode.infra.certificate"
      vars:
        cert_dir: "{{ playbook_dir }}/output/certs"
        server_names:
          - {name: "cockpit.lan"}
```
