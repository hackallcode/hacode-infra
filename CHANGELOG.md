# Changelog

All notable changes to this collection will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this collection adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `nginx` role: `nginx_config_template` renders the vhost config through
  Jinja, so it can use vault values.
- `certbot` role: `certbot_deploy_hook` is also installed into
  `renewal-hooks/deploy`, so it reaches certificates issued before it was set.
- `headscale_failover` role: `headscale_failover_headplane_dir` runs Headplane
  on the leader only and moves its database through etcd with Headscale's, so
  users, roles, links and sessions survive a handover. Independent panels need
  merging first, as the role README describes.
- `headscale_failover` role: the serving agent moves etcd's Raft leadership to
  its own member, named by `headscale_failover_etcd_member` (`""` turns it
  off), so its renewals and snapshots commit without a round trip to another
  server.
- `tailscale` role: `tailscale_metrics_enabled` has tailscaled serve its client
  metrics, including traffic by path (direct, peer relay or DERP), for
  Prometheus at `<tailnet IP>:5252/metrics`.

### Changed

- `nginx` role: the `app-prepare` scaffold enables HTTP/2 with `http2 on;`, as
  the `http2` parameter of `listen` is deprecated since nginx 1.25.1. The
  directive needs that version or newer; on an older nginx, move `http2` back
  to the `listen` lines of a newly scaffolded config.
- `headscale_failover` role: the agent starts Headscale without waiting for its
  Docker healthcheck, as readiness can outlast the election lease, and gives a
  stopping container one second before Docker kills it.
- `headscale_failover` role: the election lease renews in its own thread, so a
  slow tick (Docker, Cloudflare, etcd reads through a distant Raft leader) no
  longer fences a healthy leader; a tick stuck for over a minute still lets
  another server take over. `headscale_failover_etcd_timeout` (2 s) replaces
  the fixed 1 s etcd request timeout.
- `prometheus` role: `InstanceDown` skips a `headscale` scrape job target on a
  server whose `headscale_failover_serving` is 0, as a standby keeps Headscale
  stopped.

### Fixed

- `prometheus` role: the built-in self-scrape goes to `prometheus_web_listen_ip`
  (loopback for `0.0.0.0`), so Prometheus bound to another address still
  scrapes itself.
- `prometheus` role: the built-in Alertmanager target follows
  `alertmanager_web_listen_ip` the same way, so alerts still reach an
  Alertmanager bound to another address.
- `prometheus` role: the stale rule cleanup also removes `*.rules` files from
  `/etc/prometheus/rules`, which Prometheus loads next to `*.yml`; a leftover
  copy kept an older version of a rule firing.

## [0.5.0] - 2026-11-08

### Breaking changes

- `certbot`: `certbot_add_www` defaults to `false` — set `true` where a `www.`
  name is still served, or certificates issued from now on come without it
  ([9d503cc](https://github.com/hackallcode/hacode-infra/commit/9d503cc))
- `maria_db`: `backup` / `restore` run inside the container with
  `--single-transaction`; dumps are `<YYYYMMDDTHHMMSSZ>_<host>_<db>.sql.gz`
  under `maria_db_backup_local_dir` (set it or `hacode_backups_dir` to keep
  `playbook_dir/../../backups/maria-db`), `restore` takes the newest per database
  ([9ebb049](https://github.com/hackallcode/hacode-infra/commit/9ebb049))
- `machine`: sshd settings move to `sshd_config.d/00-hacode.conf`, ahead of
  image fragments, and the run fails if `sshd -T` shows root or password logins
  on (a `machine_ssh_dropins` entry sorting earlier skips the check). A host
  whose image re-enabled them loses them — make sure a non-root user with a
  key can reach it first
  ([7f5ccab](https://github.com/hackallcode/hacode-infra/commit/7f5ccab))
- `prometheus`: the bundled rules and Alertmanager template now reach the
  host, so existing hosts start evaluating the CPU / RAM / filesystem /
  instance alerts on the next run; opt out with
  `prometheus_bundled_rules_enabled: false`
  ([1d306b1](https://github.com/hackallcode/hacode-infra/commit/1d306b1))

### Added

- self-hosted Tailscale mesh: `headscale` (control server with embedded DERP
  and STUN, OIDC), `derper` (standalone DERP relay), `etcd` (TLS member),
  `headscale_failover` (etcd-elected leader restores the newest snapshot and
  moves the Cloudflare A record) and `tailscale` (pinned client, firewalld
  zone, one-shot `up`; `tailscale_firewalld_rich_rules` keeps exit-node
  clients off the host's closed public ports)
  ([c945b4f](https://github.com/hackallcode/hacode-infra/commit/c945b4f),
  [525af60](https://github.com/hackallcode/hacode-infra/commit/525af60))
- `singbox`: multi-instance VLESS (+REALITY) egress client with `k3s-pods`,
  `host` and `dests` modes (`dests` works under Cilium's BPF datapath) and
  `direct_domains` SNI bypass
  ([7a8ad36](https://github.com/hackallcode/hacode-infra/commit/7a8ad36),
  [ab42980](https://github.com/hackallcode/hacode-infra/commit/ab42980),
  [51631e1](https://github.com/hackallcode/hacode-infra/commit/51631e1),
  [688966d](https://github.com/hackallcode/hacode-infra/commit/688966d),
  [eb23020](https://github.com/hackallcode/hacode-infra/commit/eb23020))
- backup / restore for state the roles can't regenerate: `wireguard` keys,
  `certbot` `/etc/letsencrypt`, `ssh_tunnel` `~/.ssh`, `app` data —
  timestamped uid-preserving archives under `hacode_backups_dir`
  ([9ebb049](https://github.com/hackallcode/hacode-infra/commit/9ebb049))
- `k8s_addons`: CloudNativePG addon; cert-manager `ClusterIssuers` and CoreDNS
  `<name>.override` snippets reconciled both ways (only issuers labelled
  `managed-by: hacode.infra` get deleted); external Prometheus scrapes pods
  through the API-server proxy
  ([0dbd1f1](https://github.com/hackallcode/hacode-infra/commit/0dbd1f1),
  [58ef129](https://github.com/hackallcode/hacode-infra/commit/58ef129))
- `k8s_addons`: Kyverno addon and a transparent egress-proxy sidecar (skips
  gvisor, opt-out-label and `runAsNonRoot` pods)
  ([bc77d18](https://github.com/hackallcode/hacode-infra/commit/bc77d18),
  [53187ff](https://github.com/hackallcode/hacode-infra/commit/53187ff),
  [a5a65fc](https://github.com/hackallcode/hacode-infra/commit/a5a65fc))
- `prometheus`: extra rule and Alertmanager template files, optional bundled
  ones, `node_exporter_allowed_sources` reconciled both ways,
  `prometheus_unit_overrides`, `keep_firing_for: 3m` on the resource alerts
  ([f3d3720](https://github.com/hackallcode/hacode-infra/commit/f3d3720),
  [1d306b1](https://github.com/hackallcode/hacode-infra/commit/1d306b1))
- `ssh_tunnel`, `machine`: per-tunnel `-L` / `-R` / `-D` forwards with a bind
  address, `user` + `identity_file`, forwarding-only accounts,
  `machine_ssh_dropins`, `machine_tmux_users`
  ([71a8a1a](https://github.com/hackallcode/hacode-infra/commit/71a8a1a))
- `machine`: `machine_yum_repos` entries take `gpgkey` and `file:` (overwrites
  a stock repo file in place), `machine_yum_remove_repo_files`,
  `machine_dnf_excludes` reconciled both ways
  ([b9295f0](https://github.com/hackallcode/hacode-infra/commit/b9295f0),
  [33bb7c0](https://github.com/hackallcode/hacode-infra/commit/33bb7c0),
  [4a934ec](https://github.com/hackallcode/hacode-infra/commit/4a934ec))
- `machine`: `machine_netplan_files` (idempotent on NetworkManager hosts),
  `machine_raspberry_cmdline_params`, `machine_pip_packages` (PEP 668-aware),
  `/etc/pip.conf` internal-index settings
  ([4ea7a7e](https://github.com/hackallcode/hacode-infra/commit/4ea7a7e),
  [4aef69d](https://github.com/hackallcode/hacode-infra/commit/4aef69d),
  [6acf0ad](https://github.com/hackallcode/hacode-infra/commit/6acf0ad),
  [dde21ec](https://github.com/hackallcode/hacode-infra/commit/dde21ec))
- `k3s`: `cordon` / `uncordon` / `drain` / `reboot` / `delete` entrypoints,
  `k3s_resolv_conf` kubelet upstream, upgrade on `k3s_version` drift
  ([ded63ef](https://github.com/hackallcode/hacode-infra/commit/ded63ef),
  [f095ce8](https://github.com/hackallcode/hacode-infra/commit/f095ce8),
  [3d31445](https://github.com/hackallcode/hacode-infra/commit/3d31445),
  [47dfe52](https://github.com/hackallcode/hacode-infra/commit/47dfe52))
- `docker`: `docker_daemon_config` rendered to `daemon.json`
  ([b166189](https://github.com/hackallcode/hacode-infra/commit/b166189))
- `wireguard`: `wg_firewall_public` (keeps `wg_port` closed), `wg_firewalld_zone`,
  `wg_endpoint` / `wg_client_dns` / `wg_mtu`
  ([42d6589](https://github.com/hackallcode/hacode-infra/commit/42d6589))
- `certbot`: `certbot_credentials_content` written 0600 to
  `certbot_credentials_file` for `dns-*` plugins
  ([9d503cc](https://github.com/hackallcode/hacode-infra/commit/9d503cc))

### Fixed

- `machine`: a fresh host bootstraps in one pass (the play must set
  `gather_facts: false`) and reboots into the upgraded kernel before Docker
  setup, even with `machine_reboot_enabled: false` (opt out with
  `machine_bootstrap_reboot_enabled: false`)
  ([3d5e59a](https://github.com/hackallcode/hacode-infra/commit/3d5e59a),
  [aaf819b](https://github.com/hackallcode/hacode-infra/commit/aaf819b),
  [76692de](https://github.com/hackallcode/hacode-infra/commit/76692de),
  [0b12856](https://github.com/hackallcode/hacode-infra/commit/0b12856))
- `machine`: `firewall_default_zone` now covers ingress, not only forwarding
  and masquerade — `firewall_zone_interfaces` (default: the primary-route NIC)
  move to it, runtime and permanent reconciled independently
  ([195195a](https://github.com/hackallcode/hacode-infra/commit/195195a),
  [9d6cfc0](https://github.com/hackallcode/hacode-infra/commit/9d6cfc0))
- `machine`: NVIDIA DKMS module is built for the running kernel and the GPU
  container modules are loaded
  ([720adf9](https://github.com/hackallcode/hacode-infra/commit/720adf9))
- `machine`: journald settings survive Pi OS's volatile-storage drop-in (its
  own drop-in filename is configurable), connections without a resolver get
  fallback upstreams, `nodejs:20` is skipped on EL10
  ([eb9c419](https://github.com/hackallcode/hacode-infra/commit/eb9c419),
  [6f800cb](https://github.com/hackallcode/hacode-infra/commit/6f800cb),
  [d9c4dfd](https://github.com/hackallcode/hacode-infra/commit/d9c4dfd),
  [f25a9ef](https://github.com/hackallcode/hacode-infra/commit/f25a9ef))
- `app`: backup excludes work, so archives shrink — check `app_exclude_paths`
  if you relied on the old contents; uploads keep source dirs named like a
  data path, `restart` applies a changed `env_file`, archives stream over rsync
  ([43f62a7](https://github.com/hackallcode/hacode-infra/commit/43f62a7),
  [87eed1c](https://github.com/hackallcode/hacode-infra/commit/87eed1c))
- `k8s_addons`: stale `OLD_CILIUM_*` cleanup no longer fails the play; the
  `kubernetes` Python package is probed with the controller's interpreter
  ([e807bfd](https://github.com/hackallcode/hacode-infra/commit/e807bfd),
  [23301b8](https://github.com/hackallcode/hacode-infra/commit/23301b8),
  [5e252b5](https://github.com/hackallcode/hacode-infra/commit/5e252b5))
- `k8s_addons`: Envoy Gateway on k3s v1.37 needs `--disable=gateway-api-crd`
  ([ac6b8cd](https://github.com/hackallcode/hacode-infra/commit/ac6b8cd))
- `wireguard`: a non-default `wg_port` reaches the firewall rule and client
  `Endpoint`; adding a peer works while `wg0` is down
  ([42d6589](https://github.com/hackallcode/hacode-infra/commit/42d6589))
- `docker`: `kernel-modules-extra` covers every installed kernel, and a host
  that cannot load the modules fails there, naming the cause
  ([b166189](https://github.com/hackallcode/hacode-infra/commit/b166189),
  [f25a9ef](https://github.com/hackallcode/hacode-infra/commit/f25a9ef))
- `gitlab_runner`: re-runs no longer register a duplicate runner, `unregister`
  finds it
  ([9c79e16](https://github.com/hackallcode/hacode-infra/commit/9c79e16),
  [b31fca6](https://github.com/hackallcode/hacode-infra/commit/b31fca6))
- `prometheus`: a partial fact cache no longer fails installs
  ([2582053](https://github.com/hackallcode/hacode-infra/commit/2582053))
- `certbot`: `openssl` is installed; an expiry check that cannot run fails
  instead of re-issuing
  ([2427920](https://github.com/hackallcode/hacode-infra/commit/2427920))
- `gost`: firewalld changes no longer flush other tools' direct rules
  (Cilium's masquerade)
  ([60dfe27](https://github.com/hackallcode/hacode-infra/commit/60dfe27))
- `app`, `prometheus`: `--diff` no longer prints rendered secrets
  ([381f6a4](https://github.com/hackallcode/hacode-infra/commit/381f6a4))

## [0.4.0] - 2026-07-03

### Added

- `k8s_addons`: kube-state-metrics addon with scoped external Prometheus API-server proxy credentials
  ([15740e3](https://github.com/hackallcode/hacode-infra/commit/15740e3))

## [0.3.0] - 2026-07-02

### Added

- `k8s_addons`: Envoy Gateway addon — upstream Envoy Gateway controller,
  Gateway API + Envoy Gateway CRDs, `GatewayClass` + shared `Gateway`
  reconciled by the role, NodePort data-plane exposure with
  `externalTrafficPolicy: Cluster`
  ([da2d7fb](https://github.com/hackallcode/hacode-infra/commit/da2d7fb))

## [0.2.2] - 2026-06-29

### Fixed

- `machine`: tmux wheel scroll forwards the wheel to mouse-reporting apps (Claude Code, vim, htop) instead of arrow keys
  ([9aeb48f](https://github.com/hackallcode/hacode-infra/commit/9aeb48f))

## [0.2.1] - 2026-06-23

### Fixed

- `machine`: enable nvidia-driver dnf module stream so cuda driver installs on RHEL9 ([2191c85](https://github.com/hackallcode/hacode-infra/commit/2191c85))

## [0.2.0] - 2026-06-23

One line per commit; click through for full rationale and code.

### Breaking changes

- `k8s_addons`: split `<addon>-install` / `<addon>-uninstall` tags; append the lifecycle suffix to any `--tags <addon>`
  invocation ([c7d859a](https://github.com/hackallcode/hacode-infra/commit/c7d859a))
- Kebab-case user-visible paths: `maria_db` backups + `wg-configs`; `mv` the old dirs on each host ([11d638a](https://github.com/hackallcode/hacode-infra/commit/11d638a))

### Added

- `k3s`: preflight auto-enables XFS `rootflags=pquota` on xfs roots ([3b0e2a7](https://github.com/hackallcode/hacode-infra/commit/3b0e2a7))
- `k8s_addons`: Cilium CNI addon ([fd20dcb](https://github.com/hackallcode/hacode-infra/commit/fd20dcb))
- `k8s_addons`: Longhorn block-storage addon ([824366b](https://github.com/hackallcode/hacode-infra/commit/824366b))
- `k8s_addons`: coredns-custom, cert-manager and trust-manager addons ([3576132](https://github.com/hackallcode/hacode-infra/commit/3576132))
- `machine`: scripts subrole + optional shell completion ([9181103](https://github.com/hackallcode/hacode-infra/commit/9181103))
- `machine`: `machine_sudoers` extra drop-ins + per-script `dest` override ([f58c0cb](https://github.com/hackallcode/hacode-infra/commit/f58c0cb))
- `machine`: `firewall_routes` `proto` opt-in + nullable `to_ip` ([f4df193](https://github.com/hackallcode/hacode-infra/commit/f4df193))
- `machine`: tmux.conf via Jinja template + customization knobs ([49b448a](https://github.com/hackallcode/hacode-infra/commit/49b448a))
- `machine`: disks subrole for fstab-managed mounts ([fcacba7](https://github.com/hackallcode/hacode-infra/commit/fcacba7))
- `machine`: raspberry config.txt via template + LightDM autologin ([45a112c](https://github.com/hackallcode/hacode-infra/commit/45a112c))
- `machine`: cron + systemd_dropins subroles, scripts gain `template: true` ([81270a7](https://github.com/hackallcode/hacode-infra/commit/81270a7))
- `machine`: zsh `sw-make` suffix-style wrappers + `hacode-update` helper ([cc98b78](https://github.com/hackallcode/hacode-infra/commit/cc98b78))
- `machine`: zsh `mkv`/`swv`/`rmv`/`sws` default to the project from PWD ([15e3d77](https://github.com/hackallcode/hacode-infra/commit/15e3d77))
- `wireguard` + `app`: smarter firewalld handling (per-server zone; live-state gate) ([b910598](https://github.com/hackallcode/hacode-infra/commit/b910598))

### Changed

- `k8s_addons`: document controller-side deps + preflight assert ([03f5ab7](https://github.com/hackallcode/hacode-infra/commit/03f5ab7))
- `k8s_addons`: document Longhorn CSI `replicaCount` install-time-only caveat ([dbeed70](https://github.com/hackallcode/hacode-infra/commit/dbeed70))

### Fixed

- `k3s`: preflight probes local NICs for `k3s_node_ip` and falls back to k3s auto-detect; reinstall on `*_args` drift ([0e8043e](https://github.com/hackallcode/hacode-infra/commit/0e8043e))
- `k8s_addons`: harden helm release lifecycle (atomic installs, recover `pending-*`) ([2e7b321](https://github.com/hackallcode/hacode-infra/commit/2e7b321))
- `k8s_addons`: recover stuck `uninstalling` helm release via `helm rollback` ([0894164](https://github.com/hackallcode/hacode-infra/commit/0894164))
- `machine`: zsh init creates `~/.ssh/control` for ControlPath multiplexing ([40784cb](https://github.com/hackallcode/hacode-infra/commit/40784cb))

## [0.1.0] - 2026-06-09

### Added

- Initial public release. Targets `ansible-core >= 2.16` (CI matrix:
  stable-2.16, stable-2.17, stable-2.18, stable-2.19, stable-2.20).
- Roles:
  - **machine**: baseline host setup. Component subroles for users +
    SSH keys, sshd hardening, hostname/locale/motd/PATH, swap (file +
    optional legacy LVM swap migration), packages, oh-my-zsh with the
    bundled hacode theme, firewalld services / ports / route
    forwarding / masquerade, SELinux, Raspberry Pi config, persistent
    journald, fail2ban, dnsmasq (per-source-IP hashlimit when public),
    Docker (via `hacode.infra.docker`), Cockpit (with optional custom
    certs), NVIDIA CUDA + container toolkit (RHEL 9/10), tmux built
    from source, `@anthropic-ai/claude-code` and `@openai/codex` npm
    globals, post-deploy reboot. Each component is opt-in/out via a
    `machine_<component>_enabled` boolean.
  - **docker**: install Docker CE on RHEL/Rocky/AlmaLinux + Debian/Ubuntu
    with the official repo, plus kernel modules (`overlay`,
    `br_netfilter`) and the bridge-netfilter sysctls.
  - **k3s**: install k3s server + agent nodes from `get.k3s.io`, manage
    server / agent flags via `k3s_server_args` / `k3s_agent_args` and
    detect drift on re-run, post-install labels and taints via
    `kubectl`, kubeconfig fetch + rewrite to the controller, firewall
    ports + trusted pod / service CIDRs in firewalld.
  - **k8s_addons**: Helm-driven addons. Initial set is **Headlamp**
    (NodePort / Ingress wiring + cluster-admin token written next to
    the kubeconfig) and **Ingress-NGINX** (NodePort by default,
    `LoadBalancer` left to the chart user). The `helm` CLI and the
    Python `kubernetes` package are required on the controller.
  - **maria_db**: install MariaDB Server + Client (RHEL via dnf module
    stream, Debian via apt). Root password rotation. `python3-mariadb`
    (RHEL) / `python3-pymysql` (Debian) installed for the
    `community.mysql` modules. Server-side replication (master/replica
    roles), per-replica privileges. Optional `mariadb-backup`-based
    timestamped backup script + cron, optional rsync mirror to the
    controller, optional restore-from-backup flow (skipped when
    `/var/lib/mysql` already has data).
  - **maria_db_user**: per-user database + grant management via
    `community.mysql.mysql_db` / `mysql_user`, controller-side flow
    (delegates to the DB host through `ansible_host`).
  - **nginx**: install nginx, default ports, render vhosts from
    `nginx_sites`. Optional cert ingestion from `hacode.infra.certificate`
    via `cert_dir` (auto-resolves SSL `crt` / `key` per site when
    `vault_certs_password` and `server_names` are in scope).
  - **certbot**: certbot install + per-domain cert request (HTTP-01,
    standalone or webroot via nginx integration), renewal via systemd
    timer, post-renew hook to reload nginx.
  - **certificate**: generate an internal CA (rotate by bumping
    `cert_ca_version`), per-host signed certs, optional ingest of
    certs from an external CA. Renders into `cert_dir`
    (defaults to a sibling of the playbook).
  - **app**: deploy arbitrary apps: docker compose, Node.js builds
    (npm/yarn/pnpm with optional `pnpm` install via corepack), static
    sites. Rsync sources, run pre-/post-deploy hooks, manage env file,
    open firewall when no domain (direct exposure), close when
    fronted by nginx.
  - **node_js**: install Node.js via `n` (version pinned).
  - **php**: install PHP-FPM + curated extensions per inventory; pool
    config + fpm tuning.
  - **prometheus**: install node-exporter, alertmanager and Prometheus
    via the upstream `prometheus.prometheus` collection. Roll-up role
    that delegates to the sub-roles with sensible defaults.
  - **wireguard**: server flow (install + configure + per-peer keys +
    download config bundle for the client), client flow (install +
    add server config + bring `wg-quick@<name>` up). Optional dnsmasq
    for VPN clients with direct-rule firewalld ACCEPT for the VPN
    subnets at priority `-10`.
  - **ssh_tunnel**: persistent SSH tunnel managed via systemd template
    units, autossh-style reconnect, key auth.
  - **gost**: install GOST (HTTPS/SOCKS5 multiplexing proxy), per-host
    listener and forwarder configuration.
  - **gitlab_runner**: install gitlab-runner via the official RPM/DEB
    repo, register with a token, manage executors (shell / docker).
- Galaxy-namespaced collection (`hacode.infra`). Roles tagged so a
  single role's tasks can be re-run with `--tags <role>` from
  inventory-wide plays.
- CI: per-PR matrix of 5 `ansible-core` versions × every molecule
  scenario in `extensions/molecule/`. `ansible-lint` (production
  profile) + `yamllint` + `markdownlint-cli2` on every push.
- Make targets: `make lint` (ansible-lint + yamllint + markdownlint),
  `make test/molecule/<scenario>` per-scenario, `make build` (Galaxy
  tarball), `make clean`.
- README + per-role READMEs + onboarding doc, plus a `CHANGELOG.md`
  using the Keep-a-Changelog format.
