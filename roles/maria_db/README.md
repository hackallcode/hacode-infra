# hacode.infra.maria_db

Run MariaDB in Docker compose; manage databases and users.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `maria_db_dest_name` | derived from inventory | compose project dir name |
| `maria_db_version` | `latest` | MariaDB image tag |
| `maria_db_port` | `3306` | host port |
| `maria_db_root_password` | `null` | root password (required to install) |
| `maria_db_databases` | `null` | list of databases to create |
| `maria_db_users` | `null` | list of `{name, password, privileges}` |
| `maria_db_database`, `maria_db_user` | `null` | shortcuts for single-db setups |

## Tasks

- `install` (default): bring up MariaDB compose stack with root password.
- `add-db` / `delete-db`, `add-user` / `delete-user`: lifecycle.
- `backup` / `backup-db`: mysqldump archive.
- `restore` / `restore-db`: restore from a dump.

## Example

```yaml
- hosts: "db"
  become: true
  roles:
    - role: "hacode.infra.maria_db"
      vars:
        maria_db_root_password: "{{ vault_maria_root }}"
        maria_db_databases: ["app"]
        maria_db_users:
          - name: "app"
            password: "{{ vault_app_db_pass }}"
            privileges: "app.*:ALL"
```
