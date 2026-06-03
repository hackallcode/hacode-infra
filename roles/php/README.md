# hacode.infra.php

Install PHP-FPM and configure pools / unix sockets for nginx.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `php_user` | `php` | PHP-FPM run-as user |
| `php_group` | `www` | PHP-FPM run-as group (shared with nginx) |

## Tasks

- `install` (default): packages, user/group, default pool.
- `configure`: render PHP-FPM pool config.
- `restart`: restart php-fpm.

## Example

```yaml
- hosts: "web"
  become: true
  roles:
    - role: "hacode.infra.php"
```
