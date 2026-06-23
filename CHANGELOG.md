# Changelog

All notable changes to this collection will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this collection adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `machine` role: `hacode-update` zsh helper that refreshes the
  bundled theme files (hacode.zsh, hacode.zsh-theme, zshrc) from
  `$HACODE_ZSH_URL` (default `https://hacode.ru/zsh`). The same
  install script the role uses on first deploy, so the user-owned
  `aliases.zsh` / `exports.zsh` seeds aren't touched. Restart the
  shell after running to pick up the new helpers.

- `machine` role: three new subroles for inventory-driven host
  hygiene, all auto-skipped when their list is empty.
  - `cron` (`machine_cron_jobs`) maps each entry 1:1 to
    `ansible.builtin.cron` (`name`, `user`, `job`, schedule fields,
    `state`, `disabled`, `env`) for inventory-driven crontab
    management — replacing the `cron_d` files operators were dropping
    by hand via the scripts subrole.
  - `systemd_dropins` (`machine_systemd_dropins`) drops
    `/etc/systemd/system/<unit>.d/<name>.conf` fragments
    (`unit`, optional `name`, `content`, `state`), reloads systemd
    once, and restarts only the units whose drop-ins actually
    changed (computed from the rendered task's `results`).
  - `scripts` (existing) now accepts `template: true` per entry to
    render the source through Jinja before dropping it on the host
    — for helpers that need to embed inventory values. Default src
    becomes `<name>.j2` in template mode, `<name>` otherwise. The
    `cron` and `systemd_dropins` subroles default to enabled
    (`machine_cron_enabled`, `machine_systemd_dropins_enabled`) but
    no-op until their respective lists are populated, mirroring the
    `disks` pattern from earlier.

- `k8s_addons` role: three new opt-in addons.
  - `coredns-custom` writes a `coredns-custom` ConfigMap in
    `kube-system` from `k8s_addons_coredns_custom_servers`, so k3s's
    bundled CoreDNS `import` plugin picks up extra server blocks
    without a restart. Each list entry maps to a `<name>.server`
    ConfigMap key with `zone` / `forward` / optional `cache`.
  - `cert-manager` installs the upstream Jetstack chart with CRDs
    bundled (`crds.enabled: true`, `crds.keep: true`) so an
    uninstall doesn't nuke `Certificate` / `Issuer` /
    `ClusterIssuer` objects other workloads still rely on. Standalone
    useful, and a hard prerequisite for trust-manager (whose webhook
    serving cert is a cert-manager `Certificate` + `Issuer`).
  - `trust-manager` installs the Jetstack OCI chart, seeds a source
    ConfigMap with a controller-side CA cert (PEM), waits for the
    `Bundle` CRD to be `Established` (not just registered — a
    freshly-registered CRD is missing from the apiserver's discovery
    doc until the controller flips the `Established` condition), and
    creates a `Bundle` that fans the CA out as a ConfigMap into every
    namespace carrying the configured label. The Bundle's
    `matchLabels` are templated via a dict expression because Jinja
    doesn't render mapping *keys* (only values), and the apply itself
    retries to ride out the python kubernetes client's discovery-
    cache lag right after CRD registration. Check-mode-safe: tasks
    that depend on the freshly-installed namespace / CRD skip when
    `ansible_check_mode`.
    All three opt-in via `_enabled` flags; install order is
    cert-manager → trust-manager, uninstall is the reverse. The
    kubeconfig validator picks them all up so the friendly assert
    message fires when the kubeconfig isn't in scope.

- `wireguard` role: each entry in `wg_servers` accepts an optional
  `firewall_zone` field. When set, the client-side
  `client-server-add` task binds the resulting WireGuard interface to
  that firewalld zone via `firewall-cmd --add-interface` (permanent +
  immediate) — so tunnel traffic isn't dropped by a `public` / `drop`
  default policy on a hardened host. Empty (default) leaves the
  interface in whatever zone firewalld picks for it.

- `machine` role: opt-in LightDM autologin for Raspberry Pi OS Desktop
  hosts. Set `raspberry_autologin_user` to a username and the role
  writes `autologin-user=<name>` + `autologin-user-timeout=0` into
  `[Seat:*]` in `/etc/lightdm/lightdm.conf`, so the host boots
  straight to a desktop session without a prompt (kiosk-style Pi-as-
  display setups). Empty (default) leaves the file untouched. Gated
  on `is_raspberry_os`, so non-Pi hosts are a no-op even if set at
  the group level.

- `machine` role: optional `disks` subrole mounts extra block devices
  (extra SSD/NVMe/HDD, network shares) listed in `machine_disks` via
  `/etc/fstab`. Each entry maps to `ansible.posix.mount` params
  (`src`, `path`, `fstype`, `opts`, `state`, `dump`, `passno` plus
  mount point dir `owner` / `group` / `mode`). The role only manages
  fstab + mount state; it never runs mkfs (formatting an already-
  populated FS would be destructive). `machine_disks_enabled` (default
  `true`) is a no-op until `machine_disks` is populated, so existing
  inventories are unaffected. `disks` tag for targeted re-runs.

- `k3s` role: preflight auto-enables XFS project quotas on the root
  filesystem (`rootflags=pquota`) when it's xfs, so kubelet's
  `LocalStorageCapacityIsolation` and Longhorn replicas have
  `prjquota` available without manual `grubby` + reboot. Cross-distro:
  `grubby --update-kernel=ALL --args=rootflags=pquota` on RHEL family,
  regex-edit of `GRUB_CMDLINE_LINUX` in `/etc/default/grub` +
  `update-grub` on Debian family. If the running mount doesn't yet
  reflect the new cmdline the role reboots the host — gated by
  `machine_reboot_enabled` (from `hacode.infra.machine`, default
  `true`) so a "no reboots please" inventory is respected. Toggle the
  whole flow off with `k3s_xfs_prjquota_enabled: false`. No-op on
  non-xfs roots and inside docker containers.

- `machine` role: optional `scripts` subrole copies arbitrary
  executables into `/usr/local/bin` (already on PATH for login shells
  via `machine_localbin_in_path`). Toggle with
  `machine_scripts_enabled`; populate `machine_scripts` with
  `[{name: <basename>}]` entries. Source defaults to
  `{{ machine_scripts_src_dir }}/<name>` (with
  `machine_scripts_src_dir` defaulting to
  `{{ playbook_dir }}/sources/scripts`); per-entry `src` / `mode` /
  `owner` / `group` overrides supported. An optional `completion`
  field — the command that prints a bash-style `complete ...` snippet
  (`kubectl completion bash`, `ovpn init`, ...) — wires shell completion
  on login: bash via `/etc/profile.d/<name>-completion.sh`, and zsh
  (when `machine_zsh_enabled`) via each `machine_zsh_users` user's
  `~/.oh-my-zsh/custom/<name>-completion.zsh`. The zsh shim runs after
  compinit so `bashcompinit` can register bash's `complete` builtin
  under zsh — `/etc/profile.d/*.sh` is too early for that under zsh's
  default startup order.

- `k8s_addons` role: Longhorn distributed block-storage addon
  ([longhorn/longhorn](https://github.com/longhorn/longhorn)). Provides a
  default `StorageClass` for clusters installed with
  `--disable=local-storage` (DOKS-style) so PVCs without an explicit
  `storageClassName` bind via Longhorn. Toggle with
  `k8s_addons_longhorn_enabled`; default `replicaCount: 1` keeps PVCs
  binding on single-node clusters (upstream chart default `3` leaves
  them `Pending` waiting for distinct nodes). Per-node prep (iscsid,
  optional NFS support) lives behind a new `host-prep` role entrypoint
  invoked from a play whose `hosts:` covers every k3s server + agent —
  the cluster-level `helm` work stays on `delegate_to: localhost`.
  Value rendering shared between the install task and an offline
  `helm template` smoke-test in the molecule scenario; the Longhorn
  1.7.x chart doesn't ship a values.schema.json, so the test catches
  wrong-key / wrong-nesting / missing-manifest regressions rather than
  pure type coercion (a separate type-assert in `longhorn-values.yml`
  guards the latter on Ansible <2.18).

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

- `machine` role: `mkv` / `swv` / `rmv` / `sws` now default
  `<name>` to the current project when invoked without arguments
  from inside `$SOURCES_DIR/<project>/...`. The fallback uses a
  small `_hacode_project_from_pwd` helper that returns the first
  path segment below `$SOURCES_DIR`; the usage message is still
  printed when PWD is outside (or `$SOURCES_DIR` is unset). Plays
  nicely with `sw-make`-generated suffix variants since they
  export their own `$SOURCES_DIR` before delegating.

- `machine` role: the zsh `sw-make` workspace helper now generates
  suffix-style command names (`sw-make w …` → `swsw / swvw / mksw
  / mkvw / rmvw`) instead of the old prefix-style (`wsws / wswv /
  wmks / wmkv / wrmv`). Tab-completion follows. **Migration**: any
  inventory or local user dotfile calling `sw-make` keeps the same
  three positional args; only the *generated* command names need
  to be updated wherever they're referenced from muscle memory or
  scripts.

- `app` role: the firewall port-open tasks now gate on the live
  firewalld state (`systemctl is-active firewalld`) instead of
  `ansible_os_family == 'RedHat'`. That fixes RHEL hosts where
  firewalld is intentionally disabled / masked (previously the role
  tried `firewall-cmd` and failed); it also lets Debian hosts that
  explicitly install and run firewalld opt into the port-open
  behavior, which was a hard-coded "RHEL only" before.

- `machine` role: the Raspberry Pi `config.txt` block is now rendered
  from a Jinja template (`templates/raspberry/config.txt.j2`) instead
  of a static file, with the same customization knobs as the tmux
  subrole — `machine_raspberry_config_template` to swap in a fully
  custom config without forking the collection,
  `machine_raspberry_use_defaults` (default `true`) to keep the
  delivery wiring but drop the bundled opinions, and
  `machine_raspberry_extra_config` for raw lines appended to the
  block. The default block (watchdog, USB max current, PCIe gen2,
  Pi 5 cooling-fan thresholds) is unchanged, so existing inventories
  see identical output.

- `maria_db` role: backup directory renamed from `maria_db` to `maria-db`
  (remote `/opt/backups/maria-db/`, controller-side
  `../../backups/maria-db/`). Matches the `kube-configs` / `wg-configs`
  kebab-case convention for output subdirs. **Migration**: existing
  hosts need `mv /opt/backups/maria_db /opt/backups/maria-db` (and the
  same on the controller for any local backups already taken).

- `wireguard` role: client config filenames switched from snake_case to
  kebab-case separators. Remote: `/etc/wireguard/configs/wg0_<name>.conf`
  → `wg0-<name>.conf`; the local-net-only variant goes from
  `<name>_local.conf` → `<name>-local.conf`. Controller-side downloads
  land at `<wg-configs>/<host>-<wg-file>` instead of
  `<wg-configs>/<host>_<wg-file>`. **Migration**: rename existing files
  (`mv /etc/wireguard/configs/wg0_*.conf …/wg0-*.conf` on each server;
  same for the local downloads).

- `k8s_addons_kubeconfig` default now respects the k3s role's
  `k3s_kubeconfig_local_dir` / `k3s_kubeconfig_local_file` overrides
  (previously assumed `<hacode_kube_configs_dir>/<cluster>.yml`), so a
  custom kubeconfig filename pinned in inventory composes correctly with
  `hacode.infra.k3s`.

- `wireguard` role: default `wg_client_configs_local_dir` renamed from
  `<output>/wg_configs` to `<output>/wg-configs` for consistency with
  the `kube-configs` and `certs` siblings (kebab-case for output
  subdirs). Inventories pinning the var explicitly are unaffected; any
  existing on-disk dir needs a manual rename.

- `k8s_addons` role: per-addon tags are now split into
  `<addon>-install` / `<addon>-uninstall` lifecycle pairs. The bare
  `<addon>` tag (e.g. `cilium`) no longer matches anything, so
  `--tags cilium` can't accidentally fire install AND uninstall in the
  same run — a real-world incident sparked the change. Migrate any
  `--tags <addon>` invocations to the appropriate `-install` /
  `-uninstall` lifecycle suffix.

- `k8s_addons` role: README now explicitly documents controller-side
  requirements (`helm` CLI + Python `kubernetes` package).
  `_validate.yml` asserts both up-front with clear fail-messages,
  replacing a deep stack trace from the first helm/k8s task with an
  immediate fix-message.

- `k8s_addons` role: README documents that Longhorn's csi sidecar
  replica-count values (`csi.attacherReplicaCount` and friends) are
  read by `longhorn-driver-deployer` only at *create* time and never
  reconciled afterwards — setting them via `_extra_values` on an
  already-deployed cluster updates the Helm release values but the
  running Deployments stay at the original replica count. Workaround
  (`kubectl scale deploy csi-* --replicas=1`) is documented inline.

- `machine` role: `machine_sudoers` accepts a list of extra sudoers
  drop-ins rendered via `community.general.sudoers` (the same module
  the admin-group entry uses; built-in `visudo -c` validation). Each
  entry mirrors the module's parameters (`name` + `users`/`group` +
  `commands` + `nopassword` + `state`/`host`/`runas`/`setenv`/`noexec`).
  Typical use: grant `NOPASSWD` on a helper installed via
  `machine_scripts` without piling everyone into the admin group.

- `machine` role: scripts subrole now accepts a per-entry `dest`
  override (default `/usr/local/bin`). Set `dest: /usr/local/sbin` for
  root-only helpers, etc.

- `machine` role: `firewall_routes` entries accept a `proto` field
  (default `"tcp"`, set to `"udp"` for QUIC / Hysteria2-style
  port-hopping — e.g. `20000-50000/udp → 443/udp`). `to_ip` is now
  optional: omit it when only a port rewrite is needed and the forward
  should stay on the host without DNAT.

- `machine` role: user-management tasks in `tasks/users.yml` migrated
  from the `custom_user` tag to `users` for consistency with the
  filename (admin-group sudoers, custom-user creation, key authorisation,
  stock-sudoers cleanup, `machine_sudoers` drop-ins). The
  `setup_user_cleanup` tag is unchanged. Migrate any
  `--tags custom_user` invocations to `--tags users`.

- `machine` role: tmux conf-drop task picks up an extra `tmux_conf`
  subtag so operators can push config tweaks via `--tags tmux_conf`
  without re-running the version probe / build-from-source pipeline.
  The umbrella `tmux` tag still covers everything.

- `machine` role: `~/.tmux.conf` is now rendered via
  `ansible.builtin.template` (was `copy`) from
  `roles/machine/templates/tmux.conf.j2`. Three customization knobs:
  `machine_tmux_conf_template` swaps the entire template
  (e.g. `"{{ playbook_dir }}/templates/tmux.conf.j2"` — picks up
  playbook-side templates via the search path);
  `machine_tmux_use_defaults` (default `true`) toggles whether the
  bundled template emits its default options at all — flip to `false`
  to keep the delivery wiring but drop the role's opinions; and
  `machine_tmux_extra_conf` is a raw string appended to the rendered
  output for inventories that want to add a few lines (or, with
  `_use_defaults: false`, supply the whole content) without forking
  the template file.

### Fixed

- `machine` role: Raspberry Pi OS auto-detection (`is_raspberry_os`)
  now also recognises Pi OS Bookworm and later, which moved the apt
  source from `/etc/apt/sources.list.d/raspi.list` (legacy one-line
  format) to `/etc/apt/sources.list.d/raspi.sources` (DEB822). The
  detect-stat task `loop`s over both paths and sets `is_raspberry_os`
  true if either exists. Without this, the `raspberry` subrole and
  the `is_raspberry_os` gate elsewhere in the role silently no-op'd
  on a Bookworm Pi.

- `machine` role: `files/tmux.conf` no longer pipes mouse-drag selections
  through `pbcopy` — that binary only exists on macOS, so on the Linux
  hosts this role actually deploys to the binding silently failed and
  also dragged `copy-pipe-and-cancel`'s side effect of exiting copy-mode
  on release. Replaced with `set -g set-clipboard on` so the default
  `MouseDragEnd1Pane` → `copy-selection-no-clear` keeps the selection
  active *and* tmux propagates it to the system clipboard via OSC 52
  (handled by every modern terminal — iTerm2, WezTerm, Kitty, Ghostty).

- `machine` role: `hacode.zsh` now ensures `~/.ssh/control` exists at
  shell startup so SSH ControlPath multiplexing works out of the box
  on a fresh account — openssh refuses to create the parent directory
  itself, so the first multiplexed connection used to fail with
  `mux_client_open_session: muxserver_open_session: socket: No such
  file or directory` until the operator created the dir by hand.

- `k3s` role: preflight now probes local interfaces for `k3s_node_ip` and
  silently falls back to k3s auto-detect when the address isn't bound to
  a local NIC. Without this, the default `k3s_node_ip: {{ ansible_host }}`
  would propagate to etcd's `--listen-peer-urls=https://<ip>:2380` and
  systemd-start the unit into `bind: cannot assign requested address` on
  cloud droplets where `ansible_host` is a floating / NAT'd public IP
  (DO floating IPs, AWS EIPs, GCP external IPs) routed externally to a
  host whose local NIC has a private address. The probe makes the default
  work zero-config for both bare metal and cloud. Pin `k3s_node_ip: ""`
  to skip the probe entirely. Regression-guarded by removing the molecule
  workaround that previously pinned `k3s_node_ip: ""` — both `k3s` and
  `k8s_addons` scenarios now rely on the fallback.

- `k8s_addons` role: harden the helm release lifecycle. A SIGTERM /
  Ctrl-C during `helm install --wait` previously left releases in
  `pending-install`, wedging the next run with `another operation in
  progress`. The role now probes `helm status` before install and
  uninstalls any `pending-*` release. All chart installs additionally
  set `atomic: true` so partial failures roll back instead of leaving
  a half-baked release behind. The uninstall path gates every
  cluster-touching task on `helm_info.status is defined`, making it
  tolerant of both missing-release and unreachable-cluster cases.

- `k8s_addons` role: helm preflight now also recovers from the
  `uninstalling` state — left over when a `helm uninstall` is killed
  mid-flight (e.g. operator killed a stuck pre-delete Job). Recovery
  is now split by state: `pending-install` (no prior deployed
  revision) is reaped via `helm uninstall`, while `pending-upgrade` /
  `pending-rollback` / `uninstalling` (all of which have a prior
  deployed revision to fall back to) are recovered via `helm rollback`.
  NEVER uninstalling charts with pre-delete hooks (Longhorn,
  cert-manager, postgres-operator, ...) — the hooks run cluster-wide
  cleanup logic and would destroy the data the release was managing.

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
