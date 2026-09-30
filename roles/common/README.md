# hacode.infra.common

Collection-wide defaults shared across roles, plus the backup / restore
helpers other roles' `backup` and `restore` entrypoints are built on. It has
no default entrypoint: other roles in the collection list `common` in their
`meta/main.yml` dependencies so the variables become available without the
consumer having to define them.

## Variables

| Variable            | Default                                                              | Purpose                                                                                                                                                                                                                                                                          |
|---------------------|----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `hacode_sync_rsh`   | `ssh -o ControlMaster=auto -o ControlPersist=600 …` (see defaults)   | Custom `--rsh` for `ansible.posix.synchronize`. The module hard-codes `ssh -S none`, which disables ControlMaster for rsync; passing our own `--rsh` (rsync uses the last one it sees) re-enables socket reuse so N host aliases on one IP share one ssh connection. Inventory-supplied bits (`ansible_port`, `ansible_ssh_private_key_file`, `ansible_ssh_common_args`, `ansible_ssh_extra_args`) are appended after our baseline so they win on conflicts. |
| `force`             | `false`                                                              | Collection-wide force switch, read as `force \| default(false) \| bool`. When `true`, idempotence guards (`is changed`, `sources_changed`, …) are short-circuited so services restart, firewalld reloads, and compose redeploys happen unconditionally.                          |
| `hacode_output_dir` | `{{ playbook_dir }}/output`                                          | Controller-side root for artifacts written by roles (issued certs, kubeconfigs, generated wg-client configs, …). Set once in inventory to relocate everything in one go.                                                                                                         |
| `hacode_kube_configs_dir` | `{{ hacode_output_dir }}/kube-configs`                         | Shared kubeconfig drop-off. `hacode.infra.k3s` writes here by default, `hacode.infra.k8s_addons` reads from here by default — both roles share this single convention so adding `k8s_addons` to the same inventory group as `k3s` Just Works without per-role path plumbing.    |
| `hacode_backups_dir` | `{{ playbook_dir }}/backups` | Controller-side root for backups, one subdirectory per role (`app`, `wireguard`, `certbot`, `ssh-tunnel`, `maria-db`). Kept apart from `hacode_output_dir`: backups are data you keep, output is regenerated. |
| `hacode_backups_remote_dir` | `/opt/backups` | Remote scratch root where archives are built before they are pulled to the controller and deleted. On disk rather than `/tmp`, which is a tmpfs on some distros. |

## Backup helpers

Called via `include_role` (`tasks_from:`) by the roles' own `backup` /
`restore` entrypoints; reach for them directly only when adding one.

| `tasks_from` | What it does |
| --- | --- |
| `backup` | archive `hacode_backup_paths` (optionally less `hacode_backup_exclude_paths` / `hacode_backup_exclusion_patterns`) in `hacode_backup_remote_dir` and pull it to `hacode_backup_local_dir/<YYYYMMDD>_<hacode_backup_name>.tar.gz` |
| `restore` | unpack the newest `<YYYYMMDD>_<hacode_backup_name>.tar.gz` from `hacode_backup_local_dir` over the same `hacode_backup_paths`, keeping numeric uids / gids; fails when there is none |
| `pull` | move the remote file `hacode_pull_src` into `hacode_pull_dest_dir` on the controller |

Archives store entries relative to the paths' common parent directory, and
`restore` derives that directory from the same list, so both sides only need
the paths. Transfers go through rsync (`synchronize`), not `fetch`: under
become `fetch` reads the file through `slurp`, which holds it whole in the
remote's memory.

## Usage

You typically don't include this role directly. It is pulled in automatically
via `dependencies` from other roles in the collection. Override any of the
variables above in inventory or playbook `vars:`.

```yaml
# inventory/group_vars/all.yml
hacode_output_dir: "/var/lib/hacode/artifacts"
force: false
```
