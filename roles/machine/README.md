# hacode.infra.machine

Baseline host setup. Each component is a separate sub-task file and can be turned on/off individually with a boolean
toggle. Defaults are conservative: things that need explicit input (DNS server, Docker, Cockpit, NVIDIA, AI CLIs) are
off by default.

## Toggles

| Variable                      | Default | Component                                                                  |
|-------------------------------|---------|----------------------------------------------------------------------------|
| `machine_users_enabled`       | `true`  | create users from `machine_users`, install SSH keys, remove bootstrap user |
| `machine_ssh_enabled`         | `true`  | harden `sshd_config`: disable root login, password auth, keepalives        |
| `machine_system_enabled`      | `true`  | hostname + aliases in /etc/hosts, locale, motd, /usr/local/bin in PATH     |
| `machine_swap_enabled`        | `true`  | swap file at `/swapfile` (size configurable)                               |
| `machine_disks_enabled`       | `true`  | mount extra block devices listed in `machine_disks` via fstab (no-op when `machine_disks` is empty) |
| `machine_packages_enabled`    | `true`  | upgrade + install curated package set                                      |
| `machine_zsh_enabled`         | `false` | install oh-my-zsh and (optionally) copy theme/aliases                      |
| `machine_firewall_enabled`    | `true`  | firewalld services/ports + port forwarding + masquerade                    |
| `machine_selinux_enabled`     | `true`  | set SELinux mode (default: permissive)                                     |
| `machine_raspberry_enabled`   | `true`  | Raspberry-only knobs; auto-skipped on non-RPi                              |
| `machine_journald_enabled`    | `true`  | persistent journald with size cap                                          |
| `machine_fail2ban_enabled`    | `true`  | install fail2ban with SSH jail                                             |
| `machine_dns_enabled`         | `false` | install + configure dnsmasq (firewall untouched)                           |
| `machine_dns_public`          | `false` | expose dnsmasq publicly with per-source-IP hashlimit (requires `machine_dns_enabled`) |
| `machine_docker_enabled`      | `false` | install Docker via `hacode.infra.docker`                                   |
| `machine_cockpit_enabled`     | `false` | install Cockpit with optional custom certs                                 |
| `machine_nvidia_enabled`      | `false` | install NVIDIA CUDA + container toolkit (RHEL only)                        |
| `machine_tmux_enabled`        | `false` | build tmux `tmux_version` from source, drop `~/.tmux.conf` per user        |
| `machine_claude_code_enabled` | `false` | install `@anthropic-ai/claude-code` globally via npm (installs nodejs+npm) |
| `machine_codex_enabled`       | `false` | install `@openai/codex` globally via npm (installs nodejs+npm)             |
| `machine_scripts_enabled`     | `false` | copy entries in `machine_scripts` into `/usr/local/bin`                    |
| `machine_reboot_enabled`      | `true`  | reboot at the end if required                                              |

## Key variables

```yaml
# Users
setup_user_name: "root"        # bootstrap user used for the first connection
root_password: ""              # optional root password rotation
machine_admin_group: "wheel"   # members get sudo via 90-<group>
machine_admin_nopasswd: true   # false -> password-prompted sudo for the admin group
machine_sudoers: []            # extra sudoers drop-ins (community.general.sudoers schema)
machine_users: []              # base user roster (see below)
machine_extra_users: []        # per-host append; final list = users + extras

# Password update policy. "on_create" (default for machine_users) seeds the
# inventory password once at user creation and leaves it alone on subsequent
# deploys, so an operator who changes their password on the host isn't reset.
# Set to "always" to enforce the inventory password every run.
machine_password_update: "on_create"
root_password_update: "always"  # root pre-exists, so on_create would never apply

# System
hostname: "{{ inventory_hostname }}"
hostname_aliases: []           # extra /etc/hosts aliases; auto-derived from `server_names`
# when that var is defined (shared with hacode.infra.certificate)
locale_lang: "en_US.UTF-8"
locale_ctype: "en_US.UTF-8"
machine_localbin_in_path: true # /etc/profile.d/localbin.sh

# Swap
swap_file_path: "/swapfile"
swap_file_size: "2G"

# Disks (only mounted when `machine_disks_enabled: true`; the role never
# formats the device). Each entry maps to `ansible.posix.mount` params.
machine_disks: []
# e.g.:
# machine_disks:
#   - {src: "UUID=<uuid>", path: "/var/lib/longhorn", fstype: "xfs", opts: "defaults,pquota"}
#   - {src: "/dev/nvme1n1p1", path: "/data",          fstype: "ext4"}

# Packages
machine_extra_packages: []

# Firewall (firewalld)
firewall_services: ["ssh", "dhcpv6-client"]
firewall_ports: []                 # ["80/tcp", "443/tcp"]
firewall_routes: []                # [{from_port, to_port, proto?: "tcp"|"udp", to_ip?, state?}]
firewall_masquerade: false
firewall_default_zone: "public"
firewall_dns_rate_limit: "600/minute"  # per-source-IP cap (hashlimit) when machine_dns_public
firewall_dns_rate_burst: 60            # short-burst tolerance per source IP

# DNS (dnsmasq via NetworkManager)
machine_dns_public: false          # open `dns` in zone + hashlimit; off-by-default
dns_server_interfaces: []          # listen by interface NAME; falls back to listen-address by IP when empty
dns_server_custom_addresses: []    # [{domain: "host.example.com", ip: "10.0.0.1"}]
dns_server_custom_servers: []      # ["1.1.1.1"]  OR  [{domain: "x.tld", dns_ip: "10.0.0.1"}]

# SELinux
selinux_mode: "permissive"         # enforcing | permissive | disabled

# Cockpit
cockpit_cert_path: ""              # paths on controller; empty -> use Cockpit's self-signed
cockpit_ca_cert_path: ""
cockpit_key_path: ""

# Tmux (source build)
tmux_version: "3.5a"
# Template rendered into each user's ~/.tmux.conf. Default resolves to the
# bundled `roles/machine/templates/tmux.conf.j2` via Ansible's template
# search path; override (e.g. "{{ playbook_dir }}/templates/tmux.conf.j2")
# for a fully custom config without forking the collection.
machine_tmux_conf_template: "tmux.conf.j2"
# Whether the bundled template emits its default options. Flip to `false`
# to keep the delivery wiring but drop the role's opinions — the rendered
# ~/.tmux.conf then contains only `machine_tmux_extra_conf` (if set).
machine_tmux_use_defaults: true
# Raw extras appended to the bundled template — use when you only want to
# add lines instead of replacing the whole file.
machine_tmux_extra_conf: ""

# Scripts dropped onto the host. Each entry:
# {name (required), src?, dest?, mode?, owner?, group?, completion?}.
# Default src is "{{ machine_scripts_src_dir }}/{{ name }}"; default dest
# is "/usr/local/bin" (PATH-wide for login shells via
# `machine_localbin_in_path`). Set `dest: "/usr/local/sbin"` for root-only
# helpers. When `completion` is set the role evals its output (e.g.
# "kubectl completion bash", "ovpn init") on login: for bash via
# /etc/profile.d/<name>-completion.sh, and for zsh (when
# `machine_zsh_enabled`) via each user's
# ~/.oh-my-zsh/custom/<name>-completion.zsh so it loads after compinit.
machine_scripts_src_dir: "{{ playbook_dir }}/sources/scripts"
machine_scripts: []                # e.g. [{name: "ovpn", completion: "ovpn init"}]

# NVIDIA / CUDA
cuda_version: "12.5"
nvidia_container_toolkit_version: "1.17.8"

# Raspberry Pi config.txt block (rendered between BEGIN/END ANSIBLE-MANAGED
# markers at the bottom of /boot/firmware/config.txt; auto-skipped on
# non-Pi hosts).
machine_raspberry_config_template: "raspberry/config.txt.j2"
machine_raspberry_use_defaults: true   # false -> drop bundled opinions
machine_raspberry_extra_config: ""     # raw lines appended to the block

# Raspberry Pi OS Desktop LightDM autologin (no-op on Pi OS Lite / non-Pi).
# Set to a username to boot straight to a desktop session without a prompt.
raspberry_autologin_user: ""
```

## `machine_users` schema

`machine_users` and `machine_extra_users` are concatenated to produce the final user roster. Use `machine_users` at
the group level for the base list and `machine_extra_users` per-host to append (Ansible's default `replace` hash
behavior would otherwise force you to redeclare the whole list when extending). Each entry:

| Field                  | Required | Description                                                                                                      |
|------------------------|----------|------------------------------------------------------------------------------------------------------------------|
| `name`                 | yes      | login name                                                                                                       |
| `ssh_authorized_keys`  | no       | single key string, or several keys joined with `\n`. Acts as a complete dump of `~/.ssh/authorized_keys` — any key not in the list is removed. Omit (or empty) to leave the file untouched. |
| `password`             | no       | plaintext; hashed with sha512 + a per-host seed before being applied                                             |
| `password_update`      | no       | `"on_create"` (default, via `machine_password_update`) or `"always"`. Overrides the global setting per-user.     |
| `groups`               | no       | extra groups (membership is appended). Include `machine_admin_group` (default `wheel`) to grant sudo (password-less when `machine_admin_nopasswd: true`, default). |

The `90-{{ machine_admin_group }}` sudoers entry is created by the role; you don't need a separate `sudoers:` step.
Distro-provided `90-cloud-init-users` and (when `machine_admin_group != "wheel"`) `90-wheel` are removed.

## Example

```yaml
- hosts: "vps"
  become: true
  roles:
    - role: "hacode.infra.machine"
      vars:
        machine_users:
          - name: "admin"
            ssh_authorized_keys: "ssh-ed25519 AAAA... you@laptop"
            groups: ["wheel"]
          - name: "deploy"
            ssh_authorized_keys: "ssh-ed25519 BBBB... ci@runner"
            groups: ["docker"]
        firewall_ports: ["80/tcp", "443/tcp"]
        machine_extra_packages: ["jq", "fd-find"]
        machine_zsh_enabled: true
        machine_zsh_files:
          - {from: "zshrc", to: ".zshrc"}
        machine_docker_enabled: true
        machine_tmux_enabled: true
```

## Tags

Each sub-task is tagged; you can re-run a single component:

```sh
ansible-playbook site.yml --tags "firewall"
ansible-playbook site.yml --tags "users,ssh"
```

Available tags: `always`, `root_user`, `users`, `setup_user_cleanup`, `ssh`, `locale`, `hostname`, `motd`,
`path`, `swap`, `disks`, `package`, `zsh`, `firewall`, `selinux`, `raspberry`, `journald`, `fail2ban`, `dns`,
`docker`, `cockpit`, `nvidia`, `tmux`, `tmux_conf`, `claude_code`, `codex`, `scripts`, `reboot`.

`tmux_conf` is a subtag that runs only the `~/.tmux.conf` rewrite — handy for pushing config tweaks
without re-checking / rebuilding tmux itself.

## Convenience entrypoint

`tasks_from: host` runs `users` → `ssh` → `system` in one call - handy when an inventory wants the combined identity
bootstrap without the rest of the role.

## Notes

- ZSH files (`hacode.zsh-theme`, `hacode.zsh`, `zshrc`, `aliases`, `exports`) are shipped in `files/zsh/` as a sample.
  Override or extend via `machine_zsh_files`. By default `machine_zsh_users` is `[root] + machine_users[*].name`.
- The NVIDIA task currently supports RHEL 9/10 only. Debian/Ubuntu paths need a separate implementation.
- The role detects Raspberry Pi OS automatically by the presence of `/etc/apt/sources.list.d/raspi.list`
  (pre-Bookworm one-line format) or `/etc/apt/sources.list.d/raspi.sources` (Bookworm+ DEB822 format).
- `tmux` is built from source pinned to `tmux_version`; the distro's package is skipped because it lags by years.
- `claude_code` / `codex` install nodejs + npm on first run (idempotent thereafter).
