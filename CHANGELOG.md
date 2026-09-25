# Changelog

All notable changes to this collection will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this collection adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `prometheus` role: knobs for a project that brings its own alerting on
  a host shared with a workload. `prometheus_bundled_rules_enabled:
  false` leaves out the curated rules (and removes them from the host)
  so the project's thresholds are the only ones;
  `node_exporter_allowed_sources` opens node_exporter to the given
  IPv4 CIDRs only instead of to everyone, reconciled both ways — the
  role owns the rich rules on that port, so a source dropped from the
  list has its accept rule removed on the next run instead of staying
  open forever; `prometheus_unit_overrides` writes
  systemd `[Service]` settings per unit, e.g. `OOMScoreAdjust` and
  `MemoryMax`, so the kernel kills the workload before the alerter and
  the alerter cannot press the host.

- `ssh_tunnel` role: per-tunnel `forwards` list for explicit `-L`,
  `-R` and `-D` forwards with a bind address and, for `-L` / `-R`, a
  destination (`{type, bind_address, bind_port, host, port}`). The
  old `forward_port` / `reverse_port` shorthands could only open a
  SOCKS proxy on `0.0.0.0`, so publishing one port of the host on a
  jump box's private address (ssh or RDP back into a laptop) or
  reaching one service behind it was out of reach. The shorthands
  still render first and unchanged, so existing units are not
  restarted.

- `machine` role: forwarding-only accounts. User entries take an
  optional `shell` (e.g. `/usr/sbin/nologin`), the new
  `machine_ssh_dropins` list writes `/etc/ssh/sshd_config.d/<name>.conf`
  fragments verbatim (typically a `Match User` block: no tty,
  `AllowTcpForwarding remote`), and `machine_tmux_users` picks who
  gets `~/.tmux.conf` the way `machine_zsh_users` already does for
  oh-my-zsh. Together they let an inventory describe a hand-made
  tunnel account exactly, so adopting it is a no-op run instead of a
  chsh, a new dotfile and a lost sshd restriction.

- `machine` role: `machine_yum_repos` entries take an optional `file`
  key (default `<name>.repo`). Point it at the distro's own repo
  filename (`almalinux-baseos.repo`, ...) to overwrite the stock repo
  file in place. Since `.repo` files are marked `%config(noreplace)`
  by the packaging, the in-house definition then survives an
  `almalinux-repos` upgrade instead of colliding with the stock one —
  no `machine_dnf_excludes` on `almalinux-release` (which breaks
  depsolve on the version-locked `almalinux-release` / `-repos` /
  `-gpg-keys` set), no rm-and-recreate ordering games. Also reconciles
  `machine_dnf_excludes` both ways: emptying the list now removes the
  `exclude=` line from `/etc/dnf/dnf.conf` again.

- `singbox` role: per-instance `direct_domains` — hosts named there
  go past the tunnel and leave the node on its own address instead of
  via VLESS. Routes can't do this when the hosts to tunnel and the
  ones to skip sit behind the same CDN (addresses are shared, names
  are not); a sing-box `sniff` rule reads the TLS SNI and sends the
  listed names to the direct outbound. Motivating case: a provider
  refuses the tunnel's exit address while the same credentials work
  from a direct route. Pair with the new per-instance `wan_interface`
  so the direct outbound binds to the node's egress NIC — in `host`
  mode the default route points at the tun, so an unbound direct
  outbound loops the exception back through the tunnel instead of
  leaving.

- `singbox` role: `dests` routing mode. Sends `route_dests` CIDRs
  through the tun in the main routing table — no marks, no ipsets,
  no policy rules — so it works under Cilium's BPF datapath, where
  `k3s-pods` mode is a no-op (the BPF forwarding path skips `ip rule`
  lookups so the fwmark never routes the packet). Every other
  destination keeps its route, including the ssh you are holding.

- `machine` role: `machine_netplan_files` (list, default `[]`) — netplan
  configs dropped into `/etc/netplan/` (root:root, 0600) and applied via
  `netplan apply` on notify. Each item takes `name` plus one of `content`
  (inline YAML) or `template` (Jinja path rendered on the controller).
  Gated by `machine_netplan_enabled` (default `true`) and
  `ansible_os_family == 'Debian'` — the whole block is skipped on RHEL
  where netplan isn't installed. Empty list = no-op. The rendered config
  is tracked in a shadow copy under `machine_netplan_state_dir` (default
  `/var/lib/hacode/netplan`); `/etc/netplan` is rewritten and `netplan
  apply` fired only when it changes, so runs stay idempotent even on
  NetworkManager-backed hosts where `netplan apply` consumes the source
  file (rewriting it as `90-NM-<uuid>.yaml`). `force=true` re-applies.

- `machine` role: `machine_raspberry_cmdline_params` (list, default `[]`)
  — kernel command-line parameters ensured in
  `/boot/firmware/cmdline.txt` on Raspberry Pi OS. Params are matched by
  key (the part before `=`): present with any value → left untouched,
  absent → appended. Nothing is ever removed, so it composes with the
  firmware-injected params. A change flags `/var/run/reboot-required`
  inline (not via handler — the marker has to exist before `reboot.yml`
  checks it at the end of the run). `machine_raspberry_cmdline_file`
  overrides the path (Pi OS Bookworm default is `/boot/firmware/cmdline.txt`).

- `k3s` role: `cordon`, `uncordon`, `drain`, `reboot` and `delete`
  entrypoints (`tasks_from`) for taking a node out of scheduling and
  putting it back — a machine being replaced, rebooted for maintenance,
  or retired. All five delegate `k3s kubectl` to the cluster's primary
  server, so they work against agents just as well as against a server. `k3s_drain_args` carries
  `--ignore-daemonsets --delete-emptydir-data` by default, without
  which drain refuses to evict on any cluster with a CNI or a CSI
  driver; `k3s_drain_timeout` (default `600s`) bounds the wait;
  `k3s_reboot_timeout` and `k3s_reboot_ready_timeout` bound the
  reboot flow's host-back and node-Ready waits; `k3s_node_name` pins
  the registered name when the inventory does not set `hostname`.
  Peer-resolution (`k3s_cluster_peers`, `k3s_primary_url`,
  `k3s_is_primary`) is factored into `_peers.yml` and imported by all
  entrypoints and by `install-server` / `install-agent`, so the two
  duplicated blocks are gone.

- `machine` role: `machine_pip_packages` (list, default `[]`) — Python
  packages to `pip install` system-wide. On PEP 668 distros
  (Ubuntu 24.04+, Debian 12+, RHEL 10) the role detects the
  `EXTERNALLY-MANAGED` marker and passes `--break-system-packages`
  automatically; older pip that doesn't understand the flag stays
  untouched. Runs after the `machine_pip_index_url` block so installs
  hit the configured mirror when one is set.

- `machine` role: `machine_pip_index_url`, `machine_pip_extra_index_url`
  and `machine_pip_trusted_host` — point pip at an internal PyPI mirror
  by merging into `/etc/pip.conf`'s `[global]` section via
  `community.general.ini_file` (other keys already in `[global]` are
  preserved). `machine_pip_index_url` gates the whole block; the extra
  and trusted-host keys are reconciled to inventory each run — set the
  value and the line is written, clear it and the previously-written
  line is removed.

- `k3s` role (server): `k3s_resolv_conf` (list, default `[]`) — upstream
  nameservers to write into a curated resolv.conf and pass to kubelet
  via `resolv-conf:` in `/etc/rancher/k3s/config.yaml`. CoreDNS forwards
  cluster egress to this file (`forward . /etc/resolv.conf`) so it
  becomes the effective cluster upstream. Set this on nodes that run a
  local stub resolver (systemd-resolved / NetworkManager dnsmasq →
  `127.0.0.1`), where k3s otherwise falls back to a hardcoded
  `8.8.8.8` + IPv6 resolver that dead-ends on IPv4-only hosts. A
  change re-renders the file and restarts k3s. Path is configurable
  via `k3s_resolv_conf_path` (default `/etc/rancher/k3s/resolv.conf`).

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

### Changed

- `prometheus` role: the RAM, CPU and filesystem-space rules keep firing
  for 3 minutes through missing samples. A host that goes away used to
  resolve its open alerts first and only then fire InstanceDown, so the
  chat read as if the disk or memory had recovered.

### Fixed

- `prometheus` role: the bundled CPU, filesystem and RAM alerts carry
  `keep_firing_for: 3m`, so a host that stops answering is reported as
  down rather than first resolving its resource alerts. Without it the
  alerts lose their samples the moment the host goes away and clear
  immediately, while `InstanceDown` (`up == 0`, `for: 1m`) has not
  fired yet — the operator sees a burst of "resolved" a minute before
  the real problem lands. Covered by a `promtool` case that goes stale
  mid-series and asserts the alert holds at 5m and is gone at 8m.

- `machine` role: `machine_yum_remove_repo_files` and
  `machine_dnf_excludes` for closed-network hosts pointing the stock
  repo ids at an in-house mirror. When `machine_yum_repos` re-uses
  `baseos` / `appstream` / `extras`, the distro-shipped `almalinux-*.repo`
  files still carry an internet `mirrorlist=` for the same ids —
  duplicating them and, behind a closed network, timing out every
  `dnf` metadata refresh. `machine_yum_remove_repo_files` lists
  filename globs to delete from `/etc/yum.repos.d/` (e.g.
  `almalinux*.repo`), applied once in `repos.yml` before any dnf op.
  `machine_dnf_excludes` writes an `exclude=` line into
  `/etc/dnf/dnf.conf`'s `[main]`, so a package upgrade of
  `almalinux-release` (or similar) can't lay the stock files back
  down. Both default to `[]`, so the change is a no-op for
  inventories that don't run behind a closed network.

- `machine` role: package repositories are now configured **before**
  any dnf/apt operation. The role's first package action is the glibc
  langpack install in `system.yml`, which refreshes every enabled repo;
  a stale repo baked into the base image (a decommissioned mirror, say)
  timed out there and aborted the whole run before `packages.yml` ever
  got to drop the managed `.repo` files. Repo drops (custom yum repos +
  AlmaLinux GPG key) and the initial apt cache refresh live in a new
  `repos.yml` imported first in both `main.yml` and the `host`
  entrypoint, so `machine` converges in a single pass on freshly-imaged
  and already-provisioned hosts alike.

- `machine` role: the `dns` subrole now gives the ethernet connection
  profiles a resolver of their own when no device carries one, via the new
  `dns_server_fallback_upstreams`. A cloud image can ship a profile with an
  empty DNS list and no DHCP option behind it (netcup's does); with nothing
  to hand its dnsmasq, NetworkManager never starts it, and the role stopped
  on the wait for `127.0.0.1:53` after every task before it had reported
  success on a host that resolved nothing. Hosts whose devices already carry
  a resolver are left alone.

- `k3s` role: `delete` now runs from a peer that survives the removal.
  It delegated to the first peer, which is usually the node being deleted
  (it comes first in the inventory), so `kubectl delete node` talked to the
  apiserver it was deleting: the node object went, that k3s stopped serving,
  and the command never returned - the playbook hung long after the cluster
  was fine without the node. With no other server left, the role now says so
  instead of hanging.

- `machine` role: journald settings are now written as an
  `/etc/systemd/journald.conf.d/95-hacode.conf` drop-in instead of edited
  into the main `journald.conf`. On Raspberry Pi OS the shipped
  `40-rpi-volatile-storage.conf` drop-in forces `Storage=volatile`, which
  silently overrode the main file, so `journald_storage: persistent` was a
  no-op and every boot's logs were lost on reboot. The task also creates
  `/var/log/journal` when persistent.

- `k8s_addons` role: cilium-prep now unfeeds `OLD_CILIUM_*` chains from
  PREROUTING / POSTROUTING before flushing and deleting them. Cilium
  leaves the feeder rules pointing at the renamed chains, so
  `iptables -X` returned `CHAIN_DEL failed (Device or resource busy)`
  and the task died on it. Cilium meanwhile looped on "iptables rules
  full reconciliation failed" every 10s and never installed
  `CILIUM_POST_nat` — every pod outside a tunnelled namespace lost its
  way out, including CoreDNS, so the whole node started answering
  "Temporary failure in name resolution". Unfeed / flush / delete now
  run as one retried shell block so a re-added feeder from the live
  agent doesn't derail the cleanup, and the feeder rules travel back
  through `xargs` instead of a shell loop (one carries
  `--comment "cilium-feeder: CILIUM_OUTPUT"`, which an unquoted
  expansion splits in two).

- `singbox` role (`k3s-pods` mode): default fwmark now stays out of the
  bits Cilium writes the endpoint identity into. The old default
  (`0x80000 << index`) landed in bits 16-31; about half of the
  cluster's identities collided and had their traffic (node-to-node
  VXLAN on port 8472 included) pulled into the tunnel — one live
  reproducer had Longhorn CSI restarting 300 times on a 10s timeout
  because its cross-node calls to `longhorn-backend` were being
  re-routed into VLESS. The default becomes `0x1000 << index`, below
  the identity bits and clear of the `0x4000` / `0x8000` that
  kube-proxy owns. The route.sh header now also spells out that the
  mode itself is a no-op under Cilium's BPF datapath (the mark is
  set but `ip rule` is never consulted) — use the new `dests` mode
  there.

- `k8s_addons` role: host prep no longer dies on the stale-`OLD_CILIUM_*`
  cleanup. The chains were found with `iptables-save`, which walks every
  table, but flushed and deleted against `filter` only, so a `nat` / `raw`
  / `mangle` chain failed with "No chain/target/match by that name" and
  took the play with it - including the Longhorn host packages that run
  after, leaving a fresh node without `iscsi-initiator-utils` and unable
  to attach a volume. The table now travels with the chain name, and a
  chain the agent has already cleaned up is no longer an error.

- `singbox` role: `singbox-podwatch@<name>` now follows the lifecycle of
  its `sing-box@<name>` parent — `PartOf=` propagates restart (a
  `systemctl restart sing-box@<name>` now re-establishes the watch too
  instead of leaving the previous `kubectl --watch` running against a
  torn-down TUN), and `WantedBy=sing-box@%i.service` (instead of
  `multi-user.target`) attaches enablement to the parent so it can't
  start against a stopped sing-box. Install also removes the stale
  `multi-user.target.wants/singbox-podwatch@<name>.service` symlink on
  upgrade, so `systemctl enable` installs the new one (it is a no-op
  while any prior enablement symlink exists).

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

- `machine` role: `claude_code` / `codex` no longer try to enable the
  `nodejs:20` dnf module stream on EL10. Modularity is gone in RHEL 10 and
  its rebuilds, where `dnf module enable -y nodejs:20` fails outright with
  "missing groups or modules: nodejs:20" and takes the whole play with it;
  the plain `nodejs` + `npm` packages there are already new enough. EL8/EL9
  still get the stream.

- `docker` role: a host that cannot load Docker's kernel modules now fails
  at the modules, not later at the daemon. The `modprobe` loop used to run
  with `failed_when: false`, so a missing `br_netfilter` / `xt_addrtype`
  passed silently and the run died at "Start and enable Docker" with
  dockerd's own `Extension addrtype revision 0 not supported, missing
  kernel module?` -- a message that names neither the module nor the
  kernel. The loop still attempts every module, but an assert afterwards
  names the ones that failed and the running kernel, and points at the
  common cause (host still booted into an old kernel whose
  `kernel-modules-extra` has aged out of the repositories while a newer
  kernel waits for a reboot). Missing packages for other, non-running
  kernels stay tolerated as before, and the assert is skipped in
  containers, which have no modules of their own to load.

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
