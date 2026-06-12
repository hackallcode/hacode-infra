# Changelog

All notable changes to this collection will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this collection adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `k8s_addons` role: Cilium CNI addon
  ([cilium/cilium](https://github.com/cilium/cilium)). Replacement CNI for
  clusters that disable k3s's built-in flannel + kube-router
  (`--flannel-backend=none --disable-network-policy`), bringing the
  cluster closer to DOKS / GKE Dataplane V2 / EKS defaults. Toggle with
  `k8s_addons_cilium_enabled`; pod CIDR auto-tracks `k3s_cluster_cidr`
  when in scope. Default `operator.replicas: 1` prevents `helm --wait`
  hangs on single-node clusters (upstream default 2 leaves one operator
  `Pending`). `_kube_proxy_replacement` is a string (`"false"` / `"true"`)
  to match Cilium 1.16+ chart schema; switching to `"true"` requires
  `_k8s_service_host` and `--disable-kube-proxy` in `k3s_server_args`.
  Cilium installs first and uninstalls last so the CNI stays up while
  other addons talk to the apiserver during teardown. Installing Cilium
  into the molecule cluster is out of scope (eBPF + per-node CNI state
  are fragile in privileged docker), but value-rendering is covered by
  an offline `helm template` smoke-test in the molecule scenario that
  validates the role's defaults against the chart's `values.schema.json`
  — catches stringified-scalar / wrong-key / wrong-nesting regressions
  independent of Ansible's jinja2-native default.

### Changed

- `k8s_addons_kubeconfig` default now respects the k3s role's
  `k3s_kubeconfig_local_dir` / `k3s_kubeconfig_local_file` overrides
  (previously assumed `<hacode_kube_configs_dir>/<cluster>.yml`), so a
  custom kubeconfig filename pinned in inventory composes correctly with
  `hacode.infra.k3s`.

## [0.1.0] - 2026-06-09

### Added

- Initial public release. Targets `ansible-core >= 2.16` (CI matrix:
  stable-2.16 through stable-2.20). Supported platforms: RHEL / AlmaLinux /
  Rocky 9-10, Debian 11/12, Ubuntu 22.04/24.04; Raspberry Pi auto-detected.
  EL 8 unsupported (`dnf` module needs Python 3.7+, EL 8 ships 3.6). Galaxy
  deps carry lower bounds only so consumers pulling newer majors of
  `ansible.posix` / `community.*` don't hit resolver conflicts.

- `common` role: collection-wide conventions. Ships no tasks; carries shared
  variables consumed by other roles — `hacode_output_dir` (controller-side
  artifact root), `hacode_kube_configs_dir` (`<output>/kube-configs`, shared
  by `k3s` and `k8s_addons`), `hacode_sync_rsh` (custom `--rsh` for
  `synchronize` re-enabling ControlMaster), `force` (collection-wide
  idempotence override).

- `machine` role: baseline host setup — users, ssh, firewall (firewalld),
  dns (dnsmasq), journald, fail2ban, selinux, swap, packages, oh-my-zsh with
  bundled theme, plus opt-in Docker / Cockpit / NVIDIA-CUDA / tmux / Raspberry
  Pi tweaks / AI-CLI installers (`machine_*_enabled` toggles). Locale is
  generated before being set as the system default (avoids C-fallback
  mojibake on minimal Debian / Raspbian). dnsmasq splits config
  (`machine_dns_enabled`) from external exposure (`machine_dns_public`,
  hashlimit-rate-limited). Legacy `/dev/dm-1` swap migration is opt-in and
  destructive (`swap_migrate_legacy_dm1`).

- `app` role: rsync sources, dispatch to docker compose / Node.js build /
  static; lifecycle entrypoints (upload / start / stop / restart / delete /
  backup). Per-app UID / GID isolation when `app_owner` is non-root. Compose
  runs with `--wait`, so crashlooping containers fail the deploy instead of
  "succeeded but down". `app_post_deploy_services` runs one-shot containers
  via `compose run --rm` after the main `up` — tag them with
  `profiles: [post-deploy]` in `compose.yaml` so they stay out of the main
  bring-up; pre-deploy hooks belong in compose's native
  `depends_on: { condition: service_completed_successfully }`.

- `docker` role: Docker Engine + compose plugin (Debian / Ubuntu / RHEL).
  `docker_repo_baseurl` for an internal mirror. `docker_install_user`
  optionally creates a no-login system account in the `docker` group for
  compose isolation.

- `k3s` role: single-node or HA k3s server / agent with kubeconfig fetch.
  `k3s_node_ip` (default `ansible_host`) feeds kubelet's `--node-ip` so the
  cluster doesn't mis-route on multi-NIC hosts. Labels / taints apply via
  `k3s kubectl` post-registration (kubelet refuses `kubernetes.io/*`
  prefixes via NodeRestriction).

- `nginx` role: install + per-app vhost (TLS via certbot, redirects, basic
  auth, static aliases). OS-family `nginx_user` / `nginx_group` resolved via
  `vars/<family>.yml`.

- `maria_db` role: MariaDB in Docker with database / user lifecycle and
  `mysqldump` backup / restore. Default entrypoint installs the server,
  waits for mysqld to authenticate, then creates databases / users from
  `maria_db_databases` and `maria_db_users` when those lists are
  non-empty. Install asserts `maria_db_root_password` is set. Compose
  binds the port to `maria_db_docker_bridge_ip` for sibling host-side
  containers; empty string drops the bind.

- `php` role: PHP-FPM install + pool config.

- `node_js` role: build helper for Node.js projects. Molecule scenario is
  syntax-only — the build task operates on a pre-existing remote source
  tree, nothing to converge against on a fresh CI host.

- `prometheus` role: Prometheus + Alertmanager + node_exporter with bundled
  rule files (covering host CPU / RAM / disk / network / systemd / clock /
  reboot / liveness, and prometheus itself).

- `wireguard` role: server + clients with config export. `wg_role`
  (`server` / `client`) selects the entrypoint. Private-key reads use
  `slurp`; key-rendering / fetch tasks set `no_log: true`. Optional internal
  DNS for VPN clients (`wg_dns_enabled`) reuses
  `hacode.infra.machine.tasks.dns`.

- `certbot` role: Let's Encrypt issuance and renewal. Default entrypoint
  installs certbot + the right plugin package, registers the ACME account,
  installs the renew cron, and — when `app_domains` is non-empty — issues
  the cert. Supports the full plugin matrix (nginx / apache / webroot /
  standalone / dns-cloudflare / route53 / google / rfc2136 / digitalocean),
  LE staging via `certbot_staging`, custom ACME servers via `certbot_server`
  (ZeroSSL, Buypass, internal Boulder), `--dry-run`, pre/post/deploy hooks
  stored per-cert so renewals reuse them, and wildcards through
  `certbot_add_www: false`. Asserts `certbot_email` before registering.

- `certificate` role: internal self-signed CA + per-host certificates.
  `cert_dir` and `cert_ca_key_path` anchor on `{{ playbook_dir }}` so issued
  certs and CA private keys land in inventory-local paths.

- `gitlab_runner` role: Docker-based runner — install / register /
  unregister / uninstall. The `register` task is `no_log: true` so the
  registration token doesn't leak into stdout / log collectors.

- `gost` role: N gost daemons via `gost_instances`. Each instance is its own
  systemd unit with its own firewall REDIRECT rules; selective vs. catch-all
  is a per-instance flag.

- `ssh_tunnel` role: persistent SSH `-D` / `-R` tunnels as systemd units.
  ExecStart pins `BatchMode=yes`, `StrictHostKeyChecking=accept-new`, and a
  server-known-hosts file so a fresh unit doesn't hang on an interactive
  host-key prompt on first start.

- `k8s_addons` role: opinionated Helm-based addons against an existing
  cluster — [Headlamp](https://headlamp.dev/) (web UI, with a
  cluster-admin bearer token saved next to the kubeconfig) and
  [ingress-nginx](https://kubernetes.github.io/ingress-nginx/) (NodePort
  service type since the chart default `LoadBalancer` stalls on
  baremetal). Each addon is gated by its own `_enabled` flag. All tasks
  `delegate_to: localhost` + `run_once: true` so the role can be
  included in any play without firing N times against managed hosts.
  `k8s_addons_kubeconfig` auto-derives from `k3s_cluster_name` for
  zero-config composition with `hacode.infra.k3s`. Requires the `helm`
  CLI on the controller.

- `k8s_addons` role: ingress-nginx addon
  ([kubernetes/ingress-nginx](https://github.com/kubernetes/ingress-nginx)).
  Service type is forced to `NodePort` (chart default `LoadBalancer` hangs
  in `<pending>` on baremetal). Toggle with
  `k8s_addons_ingress_nginx_enabled`; pin
  `k8s_addons_ingress_nginx_http_node_port` /
  `_https_node_port` when an upstream proxy needs deterministic targets.
