# hacode.infra.telegram_relay

Deploy a Cloudflare Worker that relays the Telegram Bot API for listed bots, for hosts that reach Cloudflare but not
`api.telegram.org`. A client takes `https://<telegram_relay_hostname>` as its API base, e.g. Alertmanager's
`telegram_configs[].api_url`. The role talks to the Cloudflare API only, so run it on the controller.

The Worker passes `/bot<id>:<token>/<method>` and `/file/bot<id>:<token>/<path>` of the listed bots with any method,
query and body, and answers everything else with 404.

## Tasks

- `install` (default): upload the Worker and attach it to `telegram_relay_hostname`; an unchanged script and an
  attached hostname change nothing.
- `uninstall`: detach the hostname and delete the Worker.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `telegram_relay_cloudflare_token` | `""` (required) | API token: account Workers Scripts:Edit (legacy), zone Workers Routes:Edit |
| `telegram_relay_account_id` | `""` (required) | Cloudflare account of the Worker |
| `telegram_relay_zone_id` | `""` (required) | zone of `telegram_relay_hostname` |
| `telegram_relay_hostname` | `""` (required) | name the Worker answers on; Cloudflare creates its DNS record and certificate |
| `telegram_relay_name` | `telegram-relay` | Worker script name |
| `telegram_relay_bot_ids` | `[]` (required) | numeric bot ids, the part of a token before `:` |
| `telegram_relay_compatibility_date` | `2026-11-01` | Workers runtime compatibility date |

## Example

```yaml
- name: "Telegram relay"
  hosts: "localhost"
  gather_facts: false
  roles:
    - role: "hacode.infra.telegram_relay"
      vars:
        telegram_relay_cloudflare_token: "{{ vault_cloudflare_workers_token }}"
        telegram_relay_account_id: "<account id>"
        telegram_relay_zone_id: "<zone id>"
        telegram_relay_hostname: "tg.example.com"
        telegram_relay_bot_ids: ["{{ bot_token.split(':')[0] }}"]
```

## Testing

`make test/telegram-relay` runs the Worker's unit tests under `node --test` with a stubbed `fetch`. There is no molecule
scenario: the tasks only call the Cloudflare API, which CI does not have.
