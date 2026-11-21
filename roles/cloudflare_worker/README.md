# hacode.infra.cloudflare_worker

Deploy a Cloudflare Worker that relays calls to one upstream, for hosts that reach Cloudflare but not the upstream. A
client takes `https://<cloudflare_worker_hostname>` in place of the upstream's origin, e.g. Alertmanager's
`telegram_configs[].api_url` in `telegram` mode. The role talks to the Cloudflare API only, so run it on the controller.

The Worker passes a call with its method, headers, query and body, and answers a path outside the mode's list with
404, so it is no open proxy:

| Mode | Relays |
| --- | --- |
| `relay` (default) | paths starting with one of `cloudflare_worker_paths` to `cloudflare_worker_upstream` |
| `telegram` | `/bot<id>:<token>/<method>` and `/file/bot<id>:<token>/<path>` of `cloudflare_worker_telegram_bot_ids` to `api.telegram.org` |

## Tasks

- `install` (default): upload the Worker when its code, upstream, paths or compatibility date differ from the
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
| `cloudflare_worker_upstream` | `""` (required for `relay`) | upstream origin, scheme and host without a path |
| `cloudflare_worker_paths` | `[]` (required for `relay`) | path prefixes passed to the upstream, `/` for all |
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

    - name: "A vendor API"
      ansible.builtin.include_role:
        name: "hacode.infra.cloudflare_worker"
      vars:
        cloudflare_worker_name: "vendor-relay"
        cloudflare_worker_hostname: "vendor.example.com"
        cloudflare_worker_upstream: "https://api.vendor.example"
        cloudflare_worker_paths: ["/v1/"]
```

## Testing

`make test/cloudflare-worker` runs the Worker's unit tests under `node --test` with a stubbed `fetch`. There is no
molecule scenario: the tasks only call the Cloudflare API, which CI does not have.
