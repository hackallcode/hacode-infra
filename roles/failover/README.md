# hacode.infra.failover

Run the [failover](https://github.com/hackallcode/failover) agent: for each service, one node of several runs it,
elected in NATS JetStream KV, while the others keep a standby copy of its SQLite databases, replicated by
Litestream into JetStream object stores. The leader points the service's Cloudflare records at itself. How the
agent decides, and what it guarantees, is in its README.

## Tasks

- `main` (default): install the agent into a virtualenv and Litestream next to it, write one config per service and
  run `failover@<service>.service` for each. A service with `state: absent` loses its agent, config and state; its
  containers stop with the agent.
- `backup`: on the node that leads a service, copy its databases online with SQLite's backup API, check each copy
  and pull them to `failover_backup_local_dir` as `<stamp>_<service>.tar.gz`, with each database's path and owner.
  A standby has nothing to back up; a service without a leader fails the run.
- `restore`: put the latest copies in place on a fresh host before the agents start; with no position in NATS yet,
  the first leader starts from them and replicates them. It refuses while a service's agent runs.

The unit is `Type=notify` with `WatchdogSec=30`, `KillMode=mixed` (a stopping leader hands the lease on) and
`ExecStopPost=failover stop`: the service's containers outlive
the agent, so a dead or hung agent stops them.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `failover_version` | `0.1.0` | agent release |
| `failover_package` | `git+https://github.com/hackallcode/failover@v<version>` | what pip installs |
| `failover_package_file` | `""` | a wheel or source tree on the controller, installed instead |
| `failover_release` | the agent's GitHub release download URL | where Litestream comes from |
| `failover_litestream_url` / `failover_litestream_checksum` | `<release>/litestream-linux-<arch>` | Litestream built with the nats.go object store fix |
| `failover_litestream_file` | `""` | a Litestream binary on the controller, uploaded instead |
| `failover_python` | `""` | Python 3.11+; `""` picks `python3.12` on EL 9, `python3` elsewhere |
| `failover_dir` / `failover_config_dir` / `failover_state_dir` | `/opt/failover` / `/etc/failover` / `/var/lib/failover` | virtualenv and Litestream, configs and secrets, per-service state (`<service>/hold` is the deploy hold file) |
| `failover_backup_local_dir` / `failover_backup_remote_dir` | `<hacode_backups_dir>/failover` / `<hacode_backups_remote_dir>/failover` | where `backup` pulls the archives to and builds them |
| `failover_textfile_dir` | `/var/lib/node_exporter` | `failover_<service>.prom` for node_exporter; `""` turns it off |
| `failover_node` | `inventory_hostname` | this node's name |
| `failover_nats_servers` / `failover_nats_litestream_url` | `[]` / `""` (required) | NATS URLs, the local server first, and the one Litestream uses |
| `failover_nats_server_name` | `failover_node` | the local NATS server's name (`nats_name` of the nats role), where the leader pulls its streams |
| `failover_nats_replicas` | `3` | replicas of the KV and object store buckets the agent creates |
| `failover_place_streams` | `true` | while leading, move the leaders of the service's streams to this node's NATS server; `false` on a node too loaded to host them |
| `failover_nats_tls` | the `nats` role's server certificate | client certificate for NATS: `{ca, cert, key}` |
| `failover_services` | `[]` | services, see below |
| `failover_lease_ttl` | `15` | lease TTL in seconds; keep it well above the time NATS needs to re-elect a stream leader after losing a server |
| `failover_cloudflare_token` | `""` | Cloudflare API token with DNS edit on the services' zones |
| `failover_api_token` | `""` | bearer token of the agents' HTTP API |

A service in `failover_services`:

| Key | Purpose |
| --- | --- |
| `name` | the service, stable across nodes |
| `projects` | docker compose project dirs, started in order and stopped in reverse |
| `databases` | `{name: path}` of its SQLite files |
| `dns_zone` / `dns_names` / `dns_ip` | Cloudflare A records pointed at `dns_ip` while this node leads |
| `candidate` | `false`: follow and report, never lead (default `true`) |
| `lease_ttl` | overrides `failover_lease_ttl` |
| `api_listen` | `host:port` of the agent's API (`GET /state`, `POST /takeover`); unset for none |
| `state` | `absent` removes the agent |

Deploy the service's compose projects with `restart: "no"` and without starting them: the leader's agent starts them.

## Example

```yaml
- hosts: "candidates"
  become: true
  roles:
    - role: "hacode.infra.failover"
      vars:
        failover_nats_servers: >-
          {{ ["nats://" ~ tailscale_ips[0] ~ ":4222"] + groups['nats'] | map('extract', hostvars, 'tailscale_ips')
             | map('first') | reject('equalto', tailscale_ips[0]) | map('regex_replace', '^', 'nats://')
             | map('regex_replace', '$', ':4222') | list }}
        failover_nats_litestream_url: "nats://{{ tailscale_ips[0] }}:4222"
        failover_cloudflare_token: "{{ vault_cloudflare_dns_token }}"
        failover_services:
          - name: "app"
            projects: ["/opt/app"]
            databases: {main: "/opt/app/data/db.sqlite"}
            dns_zone: "example.com"
            dns_names: ["app.example.com"]
            dns_ip: "{{ public_ip }}"
```
