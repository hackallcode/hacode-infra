# Changelog

All notable changes to this collection will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this collection adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `singbox` role — installs [sing-box](https://sing-box.sagernet.org/) as a
  systemd-managed VLESS (+REALITY) egress client. Multi-instance: each
  entry in `singbox_instances` becomes its own `sing-box@<name>.service`
  with a dedicated TUN, routing table, fwmark and ipset, so several
  independent tunnels to different servers can coexist on one host.
  Three per-instance routing modes: `k3s-pods` (tunnel egress of pods in
  `scope_namespaces` only, via an ipset of their pod IPs + fwmark
  policy-routing — CNI-agnostic and gVisor-compatible), `host` (whole-host
  egress through the TUN with excludes to stay reachable), and `none`
  (bring the TUN up only). Routing is torn down via the unit's
  `ExecStopPost`, so stopping an instance cleanly reverts the host.

- `docker` role: `docker_daemon_config` (dict, default `{}`) — rendered to
  `/etc/docker/daemon.json` when non-empty, with a `Restart docker` handler
  applying changes. Enables e.g. opting out of the containerd image store on
  Docker 28+/29 (`features.containerd-snapshotter: false`), whose referrers
  API breaks pulls through registries that don't implement it (GitLab's
  dependency proxy).

- `k3s` role: version upgrades. When `k3s_version` is pinned and differs
  from what `k3s --version` reports on the host, the role re-runs the
  installer (which performs an in-place upgrade + service restart).
  Previously the installer was guarded on unit presence + ExecStart drift
  only, so bumping `k3s_version` on already-installed nodes was a no-op.
  Detection runs on both servers and agents.

- `k8s_addons`: Kyverno addon (Helm chart) — generic admission policy
  engine, opt-in via `k8s_addons_kyverno_enabled`.
- `k8s_addons`: egress proxy addon. A Kyverno `ClusterPolicy` injects an
  init container (iptables REDIRECT of outbound TCP inside the pod
  netns, minus `_exclude_cidrs` and the sidecar's own uid) plus a
  gost sidecar forwarding captured traffic to `_forwarder`. Interception
  in the pod netns is CNI-agnostic (works where host-level REDIRECT can't,
  e.g. a Cilium node that owns pod egress). Requires
  `k8s_addons_kyverno_enabled: true`. Three opt-out knobs skip pods that
  can't take the injection: `_exclude_runtime_classes` (default
  `["gvisor"]` — runsc can't do iptables/nft, the init would fail), the
  `_optout_label` label (`egress-proxy-inject: "false"` on a pod
  bypasses injection — for e.g. runAsNonRoot pods or workloads with
  their own egress policy), and a native check on
  `spec.securityContext.runAsNonRoot: true` (the init needs root for
  iptables, so kubelet would reject it — skip up-front). Kyverno
  controller autogen is disabled on the policy so pod-level labels /
  runtimeClassName are read at the Pod path, not from
  `spec.template.*`.

### Fixed

- `gitlab_runner` role: registration idempotency. `gitlab-runner list`
  writes its inventory to stderr (not stdout); the "already-registered"
  check only looked at stdout and treated every host as unregistered,
  registering the runner again on each play (duplicate entries in
  GitLab). Match against `stdout ~ stderr` so the check keys off
  whichever stream carries the name.

- `docker` role (RHEL family): `kernel-modules-extra` is now installed for
  **every** installed kernel (via `rpm -q kernel-core`), not only the
  running one (`uname -r`). A `dnf upgrade` stages a newer kernel that a
  later reboot boots into; without the matching
  `kernel-modules-extra-<VERSION>` already present, `br_netfilter` /
  `xt_addrtype` are missing on that first post-reboot boot and Docker's
  bridge setup fails.

- `gost`: manage firewalld direct rules through the runtime config +
  `firewall-cmd --runtime-to-permanent` instead of `--permanent` +
  `--reload`. `--reload` rebuilds the whole iptables ruleset from
  firewalld's permanent config and flushes direct rules other tools
  own outside firewalld (Cilium's pod-egress masquerade on a k8s
  node); runtime mutations leave those chains untouched.

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

- `k8s_addons`: split `<addon>-install` / `<addon>-uninstall` tags
  ([c7d859a](https://github.com/hackallcode/hacode-infra/commit/c7d859a)).
  **Migration**: append the lifecycle suffix to any `--tags <addon>` invocation.
- `k8s_addons`: document controller-side deps + preflight assert ([03f5ab7](https://github.com/hackallcode/hacode-infra/commit/03f5ab7))
- `k8s_addons`: document Longhorn CSI `replicaCount` install-time-only caveat ([dbeed70](https://github.com/hackallcode/hacode-infra/commit/dbeed70))
- Kebab-case user-visible paths: `maria_db` backups + `wg-configs` (**migration**: `mv` the old dirs on each host) ([11d638a](https://github.com/hackallcode/hacode-infra/commit/11d638a))

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
