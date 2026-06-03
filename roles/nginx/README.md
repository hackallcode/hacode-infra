# hacode.infra.nginx

Install nginx and render per-app vhost configs.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `domain` | `null` (required) | primary domain for the app |
| `aliases` | `[]` | extra domain names; result is alias-to-primary redirects |
| `basic_users` | `{}` | mapping `{user: password}` for basic auth |

## Tasks

- `install` (default): install nginx, deploy `nginx.conf` and shared snippets.
- `configure`: deploy a per-app vhost.
- `app-configure` / `app-delete` / `app-prepare`: app-scoped operations.
- `reload`: graceful reload.

## Example

```yaml
- hosts: "web"
  become: true
  roles:
    - role: "hacode.infra.nginx"
      vars:
        domain: "example.com"
        aliases: ["www.example.com"]
```
