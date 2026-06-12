# hacode.infra

[![Ansible Galaxy](https://img.shields.io/badge/galaxy-hacode.infra-660198?logo=ansible)](https://galaxy.ansible.com/ui/repo/published/hacode/infra/)

Reusable Ansible roles for bootstrapping bare-metal and VM hosts.

## Contents

| Role                         | Purpose                                                                                                                                                                                                      |
|------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `hacode.infra.common`        | Collection-wide variable carrier (no tasks). Other roles depend on it to inherit shared vars: `hacode_output_dir`, `hacode_kube_configs_dir`, `hacode_sync_rsh`, `force`.                                    |
| `hacode.infra.machine`       | Baseline host setup: users, ssh, firewall (firewalld), dns (dnsmasq), journald, fail2ban, selinux, swap, packages, oh-my-zsh, optional Docker, Cockpit, NVIDIA/CUDA, Raspberry Pi tweaks.                    |
| `hacode.infra.app`           | Deploy and manage an application: rsync sources, dispatch to Docker compose / Node.js build / static, lifecycle entrypoints (start/stop/restart/delete/backup), firewall port mgmt based on domain presence. |
| `hacode.infra.docker`        | Install Docker Engine + containerd + compose plugin (Debian/Ubuntu/RHEL), with kernel modules and sysctls. Compose entrypoint for app deployment.                                                            |
| `hacode.infra.k3s`           | Install k3s server (single or HA via `--cluster-init`) and agents; rewrite and fetch kubeconfig to the controller.                                                                                           |
| `hacode.infra.k8s_addons`    | Opinionated k8s addons (Cilium CNI, Longhorn block storage, Headlamp web UI, Ingress-NGINX) installed from the controller against an existing cluster via Helm. Long-lived Headlamp admin token exported to disk; each addon gated by its own `_enabled` flag. Longhorn additionally exposes a `host-prep` entrypoint for per-node iscsid setup. |
| `hacode.infra.nginx`         | nginx install + per-app vhost configuration (TLS via certbot, redirects, basic auth, static aliases).                                                                                                        |
| `hacode.infra.maria_db`      | MariaDB in Docker compose; database/user lifecycle and `mysqldump` backup/restore.                                                                                                                           |
| `hacode.infra.php`           | PHP-FPM install and pool configuration paired with nginx.                                                                                                                                                    |
| `hacode.infra.node_js`       | Install Node.js via NodeSource and run a configurable build command.                                                                                                                                         |
| `hacode.infra.prometheus`    | Prometheus + Alertmanager + node_exporter with bundled rule files (delegates to `prometheus.prometheus.prometheus`).                                                                                         |
| `hacode.infra.wireguard`     | WireGuard server + clients with config generation and export.                                                                                                                                                |
| `hacode.infra.certbot`       | Let's Encrypt certificate issuance and renewal.                                                                                                                                                              |
| `hacode.infra.certificate`   | Internal self-signed CA and per-host certificate generation.                                                                                                                                                 |
| `hacode.infra.gitlab_runner` | Docker-based GitLab Runner install / register / unregister / uninstall.                                                                                                                                      |
| `hacode.infra.gost`          | go-gost tunnel as a systemd service.                                                                                                                                                                         |
| `hacode.infra.ssh_tunnel`    | Persistent SSH tunnels (`ssh -N -D / -R`) managed as systemd units.                                                                                                                                          |

## Requirements

- Ansible >= 2.16
- Collections (pulled automatically via this collection's `dependencies`):
  - `ansible.posix`, `community.general`, `community.docker`, `community.mysql`, `community.crypto`
  - `kubernetes.core` (only if you use the `k8s_addons` role; also needs `helm` CLI on the controller)
  - `prometheus.prometheus` (only if you use the `prometheus` role)

Supported host platforms: RHEL/AlmaLinux/Rocky 9 and 10, Debian 11/12,
Ubuntu 22.04/24.04. Raspberry Pi OS is auto-detected in the `machine` role.

EL 8 is intentionally not supported — ansible-core 2.17+ requires
Python ≥ 3.7 on managed nodes, but EL 8's `dnf` module only ships bindings
for the 3.6 platform-python, making the combination unusable.

## Install

From Ansible Galaxy:

```sh
ansible-galaxy collection install hacode.infra
```

From source (git):

```yaml
# requirements.yml
collections:
  - name: "git+https://github.com/hackallcode/hacode-infra.git"
    type: "git"
    version: "main"
```

```sh
ansible-galaxy collection install -r requirements.yml
```

## Quick start

```yaml
# inventory/hosts.yml
all:
  hosts:
    server1:
      ansible_host: "10.0.0.10"
      setup_user_name: "ubuntu"   # cloud-image bootstrap user for the first ssh
```

```yaml
# playbook.yml
- hosts: "all"
  become: true
  roles:
    - role: "hacode.infra.machine"
      vars:
        machine_users:
          - name: "admin"
            ssh_authorized_keys: "ssh-ed25519 AAAA... you@laptop"
        firewall_ports: ["80/tcp", "443/tcp"]
        machine_docker_enabled: true

    - role: "hacode.infra.nginx"
      vars:
        domain: "example.com"
```

## Per-role docs

Each role has its own `README.md` under `roles/<name>/README.md` with variables and examples.

## Versioning

This collection follows [Semantic Versioning](https://semver.org/).
The current version is in `galaxy.yml`. Releases are tagged in git as `vX.Y.Z`.

## License

Apache-2.0 - see [LICENSE](LICENSE).
