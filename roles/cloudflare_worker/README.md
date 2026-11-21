# hacode.infra.cloudflare_worker

Deploy a Cloudflare Worker that relays calls to listed upstreams, for hosts that reach Cloudflare but not the
upstreams. The role talks to the Cloudflare API only, so run it on the controller.

The Worker passes a call with its method, headers, query and body over HTTPS, and answers anything outside the mode's
list with 404, so it is no open proxy:

| Mode | Client's base URL | Relays |
| --- | --- | --- |
| `relay` (default) | `https://<cloudflare_worker_hostname>/<upstream host>` | `/<host>/<path>` to `https://<host>/<path>` when `<path>` starts with one of the host's prefixes in `cloudflare_worker_upstreams` |
| `telegram` | `https://<cloudflare_worker_hostname>`, e.g. Alertmanager's `telegram_configs[].api_url` | `/bot<id>:<token>/<method>` and `/file/bot<id>:<token>/<path>` of `cloudflare_worker_telegram_bot_ids` to `api.telegram.org` |

In `relay` mode every upstream sits behind the one hostname, so no DNS record or certificate names it.

## Tasks

- `install` (default): upload the Worker when its code, routes or compatibility date differ from the
  `deploy-<hash>` tag of the deployed one, attach it to `cloudflare_worker_hostname` and detach the other hostnames it
  serves. A rerun with nothing changed makes no call that writes; `--check` reports the writes it would make.
- `uninstall`: detach every hostname the Worker serves and delete it.

A refused call fails with Cloudflare's status and errors; the token stays out of the output.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `cloudflare_worker_token` | `""` (required) | API token: account Workers Scripts:Edit (legacy), zone Workers Routes:Edit |
| `cloudflare_worker_account_id` | `""` (required) | Cloudflare account of the Worker |
| `cloudflare_worker_zone_id` | `""` (required for `install`) | zone of `cloudflare_worker_hostname` |
| `cloudflare_worker_hostname` | `""` (required for `install`) | name the Worker answers on; Cloudflare creates its DNS record and certificate |
| `cloudflare_worker_name` | `""` (required) | Worker script name |
| `cloudflare_worker_mode` | `relay` | `relay` or `telegram` |
| `cloudflare_worker_upstreams` | `{}` (required for `relay`) | `{upstream host: [path prefixes]}`, lowercase host names, `/` for all of a host's paths |
| `cloudflare_worker_telegram_bot_ids` | `[]` (required for `telegram`) | numeric bot ids, the part of a token before `:` |
| `cloudflare_worker_compatibility_date` | `2026-11-01` | Workers runtime compatibility date |

## Example

```yaml
- name: "Relays on Cloudflare"
  hosts: "localhost"
  gather_facts: false
  vars:
    cloudflare_worker_token: "{{ vault_cloudflare_workers_token }}"
    cloudflare_worker_account_id: "<account id>"
    cloudflare_worker_zone_id: "<zone id>"
  tasks:
    - name: "Telegram Bot API"
      ansible.builtin.include_role:
        name: "hacode.infra.cloudflare_worker"
      vars:
        cloudflare_worker_name: "telegram-relay"
        cloudflare_worker_hostname: "tg.example.com"
        cloudflare_worker_mode: "telegram"
        cloudflare_worker_telegram_bot_ids: ["{{ bot_token.split(':')[0] }}"]

    - name: "Vendor APIs, at https://relay.example.com/<host>/..."
      ansible.builtin.include_role:
        name: "hacode.infra.cloudflare_worker"
      vars:
        cloudflare_worker_name: "api-relay"
        cloudflare_worker_hostname: "relay.example.com"
        cloudflare_worker_upstreams:
          api.vendor.example: ["/v1/"]
          files.vendor.example: ["/"]
```

## Testing

`make test/cloudflare-worker` runs the Worker's unit tests under `node --test` with a stubbed `fetch`. There is no
molecule scenario: the tasks only call the Cloudflare API, which CI does not have.
