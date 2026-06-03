# hacode.infra.certbot

Install certbot and issue / revoke Let's Encrypt certificates.

The default entrypoint runs the full setup-and-issue flow: install
certbot + plugin packages, register the ACME account, set up the
renewal cron, then — if `app_domains` is non-empty — issue the
certificate. With empty `app_domains` it stops after install, which is
the right behaviour for hosts that only need the binary or that issue
many certs via per-cert calls.

| Entrypoint | What it does |
| --- | --- |
| default (= `main`) | full flow: install + ACME register + renewal cron + (if `app_domains`) issue cert |
| `install` | install certbot, register the ACME account, install renewal cron — no cert issuance |
| `certificate-get` | issue or renew a single certificate (`certbot certonly`); call repeatedly for multi-cert hosts |
| `certificate-delete` | revoke a single certificate (`certbot revoke`) |

## Variables

### Setup (always honoured by the default entrypoint)

| Variable | Default | Purpose |
| --- | --- | --- |
| `certbot_email` | `""` (required) | ACME account email |
| `app_cert` | `true` | master switch — set false on a host that shares the install but doesn't issue |
| `certbot_renew_cron` | `true` | install the daily renewal cron job |
| `certbot_authenticator` | `nginx` | plugin used by `certonly`; also selects the plugin package installed by `install.yml` |
| `certbot_extra_authenticators` | `[]` | install extra plugin packages so one machine can issue under multiple plugins |

### Mode (per `certificate-get` call)

| Variable | Default | Purpose |
| --- | --- | --- |
| `certbot_authenticator` | `nginx` | plugin — `nginx`, `apache`, `webroot`, `standalone`, `dns-cloudflare`, `dns-route53`, `dns-google`, `dns-rfc2136`, `dns-digitalocean` |
| `certbot_staging` | `false` | use LE staging (`--test-cert` + staging server) instead of production |
| `certbot_dry_run` | `false` | run `certonly --dry-run` — full ACME flow, cert discarded |
| `certbot_webroot_path` | `/var/www/html` | used when `certbot_authenticator: webroot` |
| `certbot_credentials_file` | `""` | passed via `--<plugin>-credentials`, required by most `dns-*` plugins |
| `certbot_pre_hook` | `""` | `--pre-hook` shell command — runs before every issue/renewal |
| `certbot_post_hook` | `""` | `--post-hook` shell command — runs after every issue/renewal |
| `certbot_deploy_hook` | `""` | `--deploy-hook` shell command — runs only when a cert was actually issued/renewed |
| `certbot_extra_args` | `[]` | raw flags appended to every `certonly` invocation |

### Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `certbot_server` | `""` | override the ACME server URL (ZeroSSL, Buypass, internal Boulder); wins over `certbot_staging` |
| `certbot_le_production_url` | LE prod directory URL | exposed for intranet proxies |
| `certbot_le_staging_url` | LE staging directory URL | exposed for intranet proxies |
| `certbot_authenticator_packages` | dict | plugin → package list; override to teach the role about new plugins or rename distro packages |

### Per-cert (`certificate-get` / `certificate-delete`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `app_domains` | `[]` | list of domains; first entry is also `--cert-name`. Empty list → default entrypoint stops after install |
| `certbot_add_www` | `true` | duplicate each non-wildcard entry with a `www.` SAN |

## Examples

### One-shot: install + issue an nginx-validated cert

```yaml
- hosts: "web"
  become: true
  roles:
    - role: "hacode.infra.certbot"
      vars:
        certbot_email: "ops@example.com"
        app_domains: ["example.com"]
```

### Install only (no domains yet, certs issued elsewhere)

```yaml
- ansible.builtin.import_role:
    name: "hacode.infra.certbot"
  vars:
    certbot_email: "ops@example.com"
```

### Staging cert via webroot (dev box, no rate-limit risk)

```yaml
- hosts: "dev"
  become: true
  roles:
    - role: "hacode.infra.certbot"
      vars:
        certbot_email: "ops@example.com"
        app_domains: ["dev.example.com"]
        certbot_authenticator: "webroot"
        certbot_webroot_path: "/srv/dev.example.com/htdocs"
        certbot_staging: true
```

### Wildcard cert via Cloudflare DNS-01

```yaml
- hosts: "web"
  become: true
  roles:
    - role: "hacode.infra.certbot"
      vars:
        certbot_email: "ops@example.com"
        app_domains: ["example.com", "*.example.com"]
        certbot_add_www: false
        certbot_authenticator: "dns-cloudflare"
        certbot_credentials_file: "/etc/letsencrypt/cloudflare.ini"
```

### Many certs on one machine, mixed plugins

Set up the install (with extra plugin packages) once via the default
entrypoint, then loop `certificate-get` per cert:

```yaml
- ansible.builtin.import_role:
    name: "hacode.infra.certbot"
  vars:
    certbot_email: "ops@example.com"
    certbot_extra_authenticators: ["dns-cloudflare"]

- ansible.builtin.include_role:
    name: "hacode.infra.certbot"
    tasks_from: "certificate-get"
  loop:
    - { domains: ["a.example.com"], auth: "nginx" }
    - { domains: ["*.b.example.com", "b.example.com"], auth: "dns-cloudflare", add_www: false }
  vars:
    app_domains: "{{ item.domains }}"
    certbot_authenticator: "{{ item.auth }}"
    certbot_add_www: "{{ item.add_www | default(true) }}"
    certbot_credentials_file: "{{ '/etc/letsencrypt/cloudflare.ini' if item.auth == 'dns-cloudflare' else '' }}"
```

### Revoke

```yaml
- ansible.builtin.include_role:
    name: "hacode.infra.certbot"
    tasks_from: "certificate-delete"
  vars:
    app_domains: ["example.com"]
```
