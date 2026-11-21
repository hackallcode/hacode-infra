# hacode.infra.cloudflare_worker

Deploy a Cloudflare Worker that relays calls to listed upstreams, for hosts that reach Cloudflare but not the
upstreams. The role talks to the Cloudflare API only, so run it on the controller.

A client takes `https://<cloudflare_worker_hostname>/<upstream host>` as the upstream's base URL. The Worker passes
`/<host>/<path>` to `https://<host>/<path>` with its method, headers, query and body when the host is a key of
`cloudflare_worker_upstreams` and the path starts with one of its prefixes, and answers anything else with 404, so it
is no open proxy. All upstreams sit behind the one hostname, so no DNS record or certificate names them.

## Tasks

- `install` (default): upload the Worker when its code, upstreams or compatibility date differ from the
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
| `cloudflare_worker_upstreams` | `{}` (required for `install`) | `{upstream host: [path prefixes]}`, lowercase host names, `/` for all of a host's paths |
| `cloudflare_worker_compatibility_date` | `2026-11-01` | Workers runtime compatibility date |

## Example

The Telegram Bot API for one bot and a vendor API, at `https://relay.example.com/api.telegram.org` (e.g. Alertmanager's
`telegram_configs[].api_url`) and `https://relay.example.com/api.vendor.example`:

```yaml
- name: "API relay"
  hosts: "localhost"
  gather_facts: false
  roles:
    - role: "hacode.infra.cloudflare_worker"
      vars:
        cloudflare_worker_token: "{{ vault_cloudflare_workers_token }}"
        cloudflare_worker_account_id: "<account id>"
        cloudflare_worker_zone_id: "<zone id>"
        cloudflare_worker_hostname: "relay.example.com"
        cloudflare_worker_name: "api-relay"
        cloudflare_worker_upstreams:
          # Bot API calls and file downloads of this bot only.
          api.telegram.org: ["/bot{{ bot_id }}:", "/file/bot{{ bot_id }}:"]
          api.vendor.example: ["/v1/"]
```

## Testing

`make test/cloudflare-worker` runs the Worker's unit tests under `node --test` with a stubbed `fetch`. There is no
molecule scenario: the tasks only call the Cloudflare API, which CI does not have.
