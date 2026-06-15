# Changelog

All notable changes to this collection will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this collection adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- `machine` role: user-management tasks in `tasks/users.yml` migrated
  from the `custom_user` tag to `users` for consistency with the
  filename (admin-group sudoers, custom-user creation, key authorisation,
  stock-sudoers cleanup, `machine_sudoers` drop-ins). The
  `setup_user_cleanup` tag is unchanged. Migrate any
  `--tags custom_user` invocations to `--tags users`.

### Fixed

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
