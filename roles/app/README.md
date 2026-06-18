# hacode.infra.app

Deploy and manage an application on a remote host. Wraps three concerns:

1. **Sync** the project source tree from the controller to a content directory on the remote (rsync via
   `ansible.posix.synchronize`), with a curated exclude list and explicit "data" paths that survive between deploys.
2. **Dispatch** to a deployment backend depending on `app_type`:
   - `docker`  - call `hacode.infra.docker` `tasks_from: compose` against the synced tree.
   - `node_js` - call `hacode.infra.node_js` `tasks_from: build` against the synced tree.
   - `static`  - sync only; no service supervision.
3. **Lifecycle** entrypoints: `start`, `stop`, `restart`, `delete`, `backup`.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `app_project` | `null` (required) | identifier, e.g. `my-api` |
| `app_src_name` | `app_project` | basename of the source directory under the source root; override when several hosts share the same source tree but get different compose project names |
| `app_source_dir` | `{{ playbook_dir }}/sources/{{ app_src_name }}` | local source directory; if missing, sync is skipped |
| `app_content_dir` | `/opt/{{ app_project }}` | remote content directory |
| `app_type` | `docker` | one of `docker`, `node_js`, `static` |
| `app_domains` | `[]` | FQDNs served by an nginx vhost; controls firewall behavior |
| `app_ports` | `[]` | `["8080/tcp"]`; opened in firewalld if no domains, closed otherwise. Firewall manipulation is a no-op when firewalld isn't installed / active, so Debian or RHEL hosts that don't run firewalld are unaffected |
| `app_disabled` | `false` | leave the service stopped after deploy |
| `app_post_deploy_services` | `[]` | compose service names run as one-shot containers after the main `compose up --wait` succeeds. Each is invoked via `docker compose run --rm <name>`; tag the services with `profiles: [post-deploy]` in `compose.yaml` so they stay out of the main `up`. Gated on `sources_changed \| force` so it doesn't fire on every play. Use for smoke tests, cache warm-up, post-migration verifications |
| `app_data_paths` | `[]` | paths under `app_content_dir` excluded from rsync, included in backup |
| `app_exclude_paths` | `[]` | paths under `app_content_dir` excluded from rsync, NOT backed up |
| `app_global_exclude_common` | `["log", ".git", "__pycache__", ".DS_Store", ".idea"]` | always-excluded baseline |
| `app_global_exclude_by_type` | `{node_js: [node_modules, build], ...}` | extra excludes per `app_type` |
| `app_owner` | `root` | service user that owns `app_content_dir`; non-`root` values are auto-provisioned as a no-login system user |
| `app_dir_owner` / `app_dir_group` | `app_owner` / `app_owner` | override individually if owner and group should differ |
| `app_content_dir_mode` | `u=rwX,g=rX,o=` (0750) | mode applied to `app_content_dir` after rsync |
| `app_cleanup` | `false` | tear down the stack and wipe `app_content_dir` before deploying |
| `app_overlay_source_dir` | `{{ playbook_dir }}/files/{{ app_project }}/{{ inventory_hostname }}` | per-host file overlay copied on top of the synced tree; skipped if the dir doesn't exist |
| `app_certificates` | `[]` | basenames (relative to `app_cert_src_dir`) copied to `{{ app_content_dir }}/certs/<basename>` with mode `0600` |
| `app_cert_src_dir` | `cert_dir` or `{{ playbook_dir }}/output/certs` | controller-side dir holding the certs referenced by `app_certificates` |
| `app_data_permissions` | `[]` | post-sync chmod/chown of specific paths inside the project tree (`{path, state?, owner?, group?, mode?, recurse?}`) |
| `app_templates` | `[]` | Jinja templates rendered into `app_content_dir`. Entries are either `"<basename>"` or `{path, mode}` |
| `app_templates_src_dir` | `app_source_dir` | controller-side dir holding `<name>.j2` source files |
| `app_backup_local_dir` | `{{ playbook_dir }}/backups/app` | fetch destination on controller |
| `app_backup_remote_dir` | `/opt/backups/app` | scratch dir on the remote |

## Entrypoints

| `tasks_from` | What it does |
| --- | --- |
| (default) | `prepare` + `upload` + `restart` |
| `prepare` | create remote content dir |
| `upload` | rsync sources, dispatch to docker/node_js, set firewall ports |
| `restart` | restart compose stack (or stop it when `app_disabled`) |
| `start` | start compose stack |
| `stop` | stop compose stack |
| `delete` | down compose stack (volumes+orphans), remove content dir, close ports |
| `backup` | archive `app_data_paths` on the remote, fetch to `app_backup_local_dir` |

## Examples

Docker app behind nginx:

```yaml
# inventory/host_vars/web1.yml
app_project: "my-api"
app_domains: ["api.example.com"]
app_ports: ["8080/tcp"]     # closed in firewall; nginx proxies via localhost:8080
app_data_paths: ["data", "uploads"]

# playbook.yml
- hosts: "web1"
  become: true
  roles:
    - role: "hacode.infra.app"
```

Direct-exposure node app:

```yaml
- hosts: "node1"
  become: true
  roles:
    - role: "hacode.infra.app"
      vars:
        app_project: "edge-worker"
        app_type: "node_js"
        app_ports: ["3000/tcp"]   # opened; no domain set
```

Backup data dirs:

```yaml
- hosts: "web1"
  become: true
  tasks:
    - ansible.builtin.include_role:
        name: "hacode.infra.app"
        tasks_from: "backup"
      vars:
        app_project: "my-api"
        app_data_paths: ["data", "uploads"]
```

Tear down:

```yaml
- hosts: "web1"
  become: true
  tasks:
    - ansible.builtin.include_role:
        name: "hacode.infra.app"
        tasks_from: "delete"
      vars:
        app_project: "my-api"
```

## Per-app isolation

The role always runs `docker compose` under `become: true` (root). Isolation
between apps comes from **file ownership + restrictive mode + the container
running under a non-root UID/GID**, not from the user that invokes compose.

The Docker daemon itself is rootful and shared, and any member of the `docker`
group is effectively root-equivalent through the socket (bind-mount `/` → root
shell). So this collection deliberately does NOT give human accounts docker
group membership. Each app instead gets a dedicated host UID/GID that owns its
project tree and is referenced by the container.

Three layers:

1. **Host user per app.** Each app gets a no-login system account whose UID/GID
   is the file-ownership anchor. Setting `app_owner` to a non-root value
   provisions this user automatically (`/var/lib/<name>`, `/usr/sbin/nologin`,
   no `docker` group, no sudo, no shell). Alternatively, create the user
   explicitly via `machine_users`.

2. **File ownership on the host.** `app_dir_owner` / `app_dir_group` (default
   to `app_owner`) chown the project tree to the app's host user. Combined
   with `app_content_dir_mode: "u=rwX,g=,o="` (0700), other apps' UIDs cannot
   read the tree. The default mode is 0750 (group-readable, convenient on
   single-tenant hosts); switch to 0700 for hard multi-tenant isolation.

3. **UID inside the container.** Declare `user: "<uid>:<gid>"` in the app's
   `compose.yaml` so the container process runs under the app's host UID/GID.
   The bind-mounted tree is then readable inside the container, but the
   container process cannot read another app's tree (different UID, mode 0700).

Example — two apps `api` and `worker`:

```yaml
# machine_users (provisioned via hacode.infra.machine)
machine_extra_users:
  - name: "api"      # no `groups:` -> not in docker, not in wheel
  - name: "worker"

# api host inventory
app_project: "api"
app_owner: "api"
app_content_dir_mode: "u=rwX,g=,o="   # 0700

# worker host inventory
app_project: "worker"
app_owner: "worker"
app_content_dir_mode: "u=rwX,g=,o="

# api's compose.yaml (lives in app_source_dir)
services:
  api:
    image: "registry/internal/api:1.2.3"
    user: "{{ ansible_lookup('passwd', 'api').uid }}:{{ ansible_lookup('passwd', 'api').gid }}"
    volumes:
      - "./data:/var/lib/api"
```

What this buys: a process inside `api`'s container can read `api`'s files,
not `worker`'s. The rootful daemon can still do anything, but no human or
non-admin process can reach the daemon — only Ansible runs under root.

What this does NOT buy: protection from a compromised container against
the host (rootful Docker; a container with a bind mount can still pivot
via daemon if it can talk to the socket). For that, see `rootless` Docker
(not implemented by this role; would require a per-user dockerd setup).

## Notes

- `app_data_paths` items are **relative to `app_content_dir`** and are excluded from the rsync `--delete` (so they survive
  redeploy) and included in the backup task. `app_exclude_paths` is excluded from both.
- The role assumes `community.docker.docker_compose_v2`. Make sure Docker is installed first via `hacode.infra.docker`
  (or `machine_docker_enabled: true` in `hacode.infra.machine`).
- When `app_type == 'docker'`, the compose project name is set to `app_project`. Compose files (`compose.yaml`, etc.)
  must live inside `app_source_dir` and will land in `app_content_dir` after sync.
