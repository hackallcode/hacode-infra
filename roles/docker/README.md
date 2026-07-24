# hacode.infra.docker

Install Docker Engine, CLI, containerd and the compose plugin. Configures
kernel modules and sysctls required for container networking.

## Tasks

- `install` (default): repository setup, packages, kernel modules, sysctl, service start, python `docker` module.
- `compose`: ensure project dir exists and run `docker compose up` against the already-staged tree.

The `compose` entrypoint does NOT render templates or sync files — it expects the project directory to be fully
populated before being called. In practice you drive deployment through `hacode.infra.app`, which handles source sync,
templates, certificate copy and permissions, then includes `compose` for the final `up`.

## Variables (compose mode)

| Variable | Default | Purpose |
| --- | --- | --- |
| `docker_remote_dir` | `/opt` | base dir on the remote |
| `docker_dest` | `{{ inventory_hostname }}` | project directory name |
| `docker_compose_owner` | `root` | project dir owner |
| `docker_compose_group` | `root` | project dir group |
| `app_disabled` | `false` | skip `compose up` when true |
| `sources_changed` | `false` | hint to force `build: always` |

## Variables (install mode)

| Variable | Default | Purpose |
| --- | --- | --- |
| `docker_repo_baseurl` | `""` | override docker-ce.repo with a custom mirror baseurl on RHEL family |
| `docker_repo_gpgcheck` | `false` | enable GPG check on packages from the custom mirror |
| `docker_daemon_config` | `{}` | rendered verbatim to `/etc/docker/daemon.json` when non-empty (a `Restart docker` handler applies changes). Empty means the role writes no `daemon.json`. Typical use: opt out of the containerd image store on Docker 28+/29 (`features.containerd-snapshotter: false`) so pulls through registries without the referrers API (GitLab dep proxy) keep working. |
| `docker_install_user` | `""` | when non-empty, create a system user with that name in the `docker` group (no-login shell, home `/var/lib/<name>`). Useful for compose isolation. |

## Examples

Install only:

```yaml
- hosts: "all"
  become: true
  roles:
    - role: "hacode.infra.docker"
```

Compose deployment (typically via `hacode.infra.app`, not directly):

```yaml
- hosts: "app"
  become: true
  tasks:
    - ansible.builtin.include_role:
        name: "hacode.infra.docker"
        tasks_from: "compose"
      vars:
        docker_dest: "my-app"
```
