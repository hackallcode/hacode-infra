# hacode.infra.headscale

Run [headscale](https://github.com/juanfont/headscale) - a self-hosted Tailscale control server - with its embedded
DERP relay and STUN, in docker compose with host networking. TLS is terminated in front of it (e.g. nginx proxying
`headscale_server_url` to `headscale_listen_addr` with connection upgrade).

## Tasks

- `install` (default): render config, policy and DERP map under `headscale_dir`, start the stack, wait for `/health`, pin
  `headscale_node_ips`, open the STUN port in firewalld (when active), create `headscale_users`. With
  `headscale_guard_addresses` the stack starts only on the host the `headscale_server_url` name resolves to and is
  stopped elsewhere (a standby keeps config and images).
- `active`: set `_headscale_active` - whether headscale should run on this host, by the guard above.
- `api-key`: keep a working API key in `headscale_api_key_file` on the target host - checked against the API and,
  when missing or rejected, created on `headscale_api_key_control_host`; sets `headscale_api_key_changed`. The key
  lives in the database, so it moves with the database and is replaced after a fresh one.
- `preauth-key`: create a preauth key and set it as the `headscale_preauth_key` fact - nothing is stored.
- `uninstall`: stop the stack, close the STUN port, delete `headscale_dir` with its database.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `headscale_version` | `0.29.7` | image tag (`headscale/headscale:v<version>`) |
| `headscale_image` | `headscale/headscale:v<version>` | full image reference; overrides the version tag |
| `headscale_dir` | `/opt/headscale` | compose project; `config/` and `data/` (SQLite, DERP key) under it |
| `headscale_server_url` | `""` (required) | public URL clients log in to; under the `failover` role its hostname is in the service's `dns_names` |
| `headscale_listen_addr` | `127.0.0.1:8090` | HTTP listener for the TLS proxy |
| `headscale_metrics_listen_addr` | `127.0.0.1:9098` | Prometheus metrics |
| `headscale_noise_private_key` | `""` | 64 hex chars; empty - generated in `data/`. Set it to keep the server identity across hosts |
| `headscale_base_domain` | `""` | MagicDNS domain; empty - MagicDNS off. Local DNS of nodes is never overridden |
| `headscale_derp_server_enabled` | `true` | embedded DERP + STUN |
| `headscale_derp_region_id` / `_code` / `_name` | `999` / `headscale` / `Headscale Embedded DERP` | embedded region |
| `headscale_derp_stun_port` | `3478` | STUN UDP port, opened in firewalld |
| `headscale_derp_ipv4` | `""` | public IPv4 announced for the embedded region |
| `headscale_derp_regions` | `{}` | extra regions in Tailscale `DERPMap.Regions` shape, keyed by id |
| `headscale_derp_urls` | `[]` | remote DERP maps; Tailscale's public one is off |
| `headscale_policy` | `{}` | ACL policy as a dict, rewritten on every deploy; `{}` - allow all |
| `headscale_initial_policy` | `{}` | instead of `headscale_policy`: the policy lives in headscale's database (editable over the API), this one goes only into an empty database |
| `headscale_oidc` | `{}` | OIDC login for user devices: `issuer`, `client_id`, `client_secret` and any other `oidc` keys; PKCE on; headscale starts without the provider, with CLI login only until restarted |
| `headscale_oidc_wait` | `0` | seconds headscale's start waits for the provider's discovery document, e.g. while a provider failing over together with headscale comes up; under `failover`, keep the service's `start_timeout` above it |
| `headscale_oidc_wait_image` | `curlimages/curl:8.23.0` | image of that wait |
| `headscale_users` | `[]` | user names to create |
| `headscale_node_ips` | `{}` | fixed addresses by given name or, failing that, the hostname a node reports (a rename does not touch it), `{"<name>": ["<ipv4>", "<ipv6>"]}`; the database is edited with headscale stopped, nodes not registered yet are skipped |
| `headscale_hold_file` | `""` | under the `failover` role: `<failover_state_dir>/<service>/hold`, the agent leaves headscale alone while it exists |
| `headscale_config_extra` | `{}` | deep-merged over the generated config; `noise.private_key_path`, `policy.path`, `derp.paths` and `database.sqlite.path` are locked to the files the role writes |
| `headscale_guard_addresses` | `[]` | this host's public addresses; non-empty - run only while `headscale_server_url` resolves to one of them |
| `headscale_api_key_file` | `""` | `api-key`: key file on the target host (root, `0600`) |
| `headscale_api_key_control_host` | `""` | `api-key`: inventory host running headscale, where a new key is created |
| `headscale_api_key_expiration` | `3650d` | `api-key`: lifetime of a new key |
| `headscale_preauth_user` | `""` | `preauth-key`: owner of a personal device; empty for tagged keys |
| `headscale_preauth_tags` | `[]` | `preauth-key`: tags for the node |
| `headscale_preauth_expiration` | `1h` | `preauth-key`: key lifetime |
| `headscale_preauth_reusable` | `false` | `preauth-key`: allow several registrations |

## Example

```yaml
- hosts: "control"
  become: true
  roles:
    - role: "hacode.infra.headscale"
      vars:
        headscale_server_url: "https://hs.example.com"
        headscale_noise_private_key: "{{ vault_headscale_noise_private_key }}"
        headscale_base_domain: "ts.example.com"
        headscale_derp_region_id: 900
        headscale_derp_ipv4: "{{ ansible_host }}"
        headscale_users: ["alice"]
        headscale_policy:
          tagOwners: {"tag:server": ["alice@"]}
          acls:
            - {action: "accept", src: ["alice@"], dst: ["*:*"]}
```

Register a server node with a one-off key:

```yaml
- hosts: "control"
  become: true
  tasks:
    - ansible.builtin.include_role:
        name: "hacode.infra.headscale"
        tasks_from: "preauth-key"
      vars:
        headscale_preauth_tags: ["tag:server"]
```
