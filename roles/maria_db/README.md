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
| `maria_db_backup_local_dir` | `{{ hacode_backups_dir }}/maria-db` | controller dir `backup` pulls dumps into and `restore` reads them from |
| `maria_db_backup_remote_dir` | `{{ hacode_backups_remote_dir }}/maria-db` | scratch dir on the remote |

## Tasks

- `install` (default): bring up MariaDB compose stack with root password.
- `add-db` / `delete-db`, `add-user` / `delete-user`: lifecycle.
- `backup` / `backup-db`: dump each database as `<YYYYMMDDTHHMMSSZ>_<inventory_hostname>_<db>.sql.gz` into
  `maria_db_backup_local_dir`.
- `restore` / `restore-db`: import the newest dump per database (an undated
  `<db>.sql[.gz|.bz2]` as a fallback) into the existing database; run `add-db`
  first on a fresh server.

Dumps and imports run inside the container (`mariadb-dump` / `mariadb`, or the
`mysql*` names on older images) with the root password from its secret file,
so nothing depends on the client packages installed on the host.

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
