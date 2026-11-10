# hacode.infra.headscale_failover

One headscale for a set of candidate servers, elected through etcd. An agent on each candidate:

- holds an etcd lease and queues in an election; the first live entry leads (its create revision is the term);
- as the leader, restores the newest database snapshot from etcd, points the server name's A record at itself and
  starts headscale; then puts the database back into etcd after every meaningful change (a consistent SQLite copy,
  compressed, written only while its election entry is still the leader's);
- stops headscale when it cannot renew the lease (out of the quorum) before another candidate can take over;
- as a standby, keeps headscale stopped;
- as the leader, while `<state_dir>/hold` exists (younger than 5 minutes), keeps the lease but neither restarts
  headscale nor writes a snapshot, for a deploy that edits the stopped database.

A manual switch writes a request naming the server that should lead: the leader writes its last snapshot and leaves the
queue, the requested server takes over, the request is cleared. Columns that change on every reconnect (`last_seen`,
`endpoints`, `host_info`, `updated_at`, `disco_key`) do not trigger a snapshot.

## Tasks

- `main` (default): install and run the agent with `headscale_failover_state: present`; remove it with `absent`.
- `seed`: put this server's database into etcd as the first snapshot - once, on the server that serves when the agents
  are introduced. A leader without a snapshot does not start headscale.
- `hand-over`: if headscale runs here, switch it to `headscale_failover_to` and wait for that server and DNS.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `headscale_failover_state` | `present` | `present` or `absent` |
| `headscale_failover_name` | `inventory_hostname` | name in the election and the panel |
| `headscale_failover_self_ip` | `""` | public address the server name points at while this server leads |
| `headscale_failover_candidate` | `true` | whether this server may lead |
| `headscale_failover_server_name` / `_zone` | `""` | name clients reach headscale at, and its Cloudflare zone |
| `headscale_failover_cloudflare_token` | `""` | Cloudflare API token with DNS edit on the zone |
| `headscale_failover_etcd_endpoints` | `[]` | etcd client URLs |
| `headscale_failover_etcd_ca` / `_cert` / `_key` | the etcd member's files under `/etc/etcd/pki` | client TLS |
| `headscale_failover_etcd_timeout` | `2` | seconds per etcd request and endpoint |
| `headscale_failover_prefix` | `/headscale` | etcd key prefix |
| `headscale_failover_lease_ttl` | `10` | lease TTL in seconds; renewed every fifth of it in a thread apart from the loop; a leader stops headscale at 70% of it without a renewal |
| `headscale_failover_tick` | `1` | seconds between agent loops; keep well under the lease TTL |
| `headscale_failover_snapshot_debounce` | `10` | seconds after the last change before a snapshot |
| `headscale_failover_snapshot_limit` | `524288` | largest compressed snapshot, bytes |
| `headscale_failover_desired_fresh` / `_desired_wait` | `120` / `15` | how long a manual request stays valid; how long the leader that handed over stays out of the queue |
| `headscale_failover_headscale_dir` | `/opt/headscale` | the headscale role's `headscale_dir`; the agent runs compose in it and reads its database |
| `headscale_failover_headplane_dir` | `""` | Headplane's compose directory; `""` leaves Headplane out of failover |
| `headscale_failover_textfile_dir` | `/var/lib/node_exporter` | node_exporter textfile directory the metrics land in |
| `headscale_failover_api_listen` / `_api_token` | `""` | HTTP API: `GET /state`, `POST /takeover` (a request to lead), bearer token |

Metrics (node-exporter textfile `headscale_failover.prom`): `leader`, `has_leader`, `serving`, `lease_ok`, `etcd_ok`,
`error`, `snapshot_timestamp_seconds`, `snapshot_bytes`, `last_tick_timestamp_seconds`; alert rules are in the
`prometheus` role.

## Optional Headplane state

With `headscale_failover_headplane_dir` set, the agent runs Headplane only on the Headscale leader. Standby nginx
must proxy `/panel` to the serving peer on 502. Keep `cookie_secret` identical on both panels. Keep each server's
`headscale_api_key` file local; only `data/hp_persist.db` travels (users, roles, links, sessions and host information).

Disable independent panel startup: use compose `restart: "no"` and deploy its files without starting it.
With the `app` role, `app_disabled: true` stops the old container during deploy; the leader's agent starts the
updated project on its next tick. Deploy Headplane before the failover role on a fresh server.

Both SQLite snapshots and their metadata commit in a single leader-fenced etcd transaction. Headplane-only
changes also trigger a snapshot. The existing snapshot debounce and combined compressed size limit apply.
A graceful handover stops writes before the final snapshot; loss of quorum fences both services.

To upgrade existing independent panels, back up both databases, merge missing user records by OIDC subject
into the current leader (preserving its user IDs and sessions), then enable this option on the current leader
first. Wait for `panel_hash` in `/headscale/db-meta` before enabling it on the standby. Restarting the leader's
agent adopts its running Headscale and publishes the merged local panel state. A takeover refuses to overwrite
an existing panel if the shared panel snapshot is missing. Standbys restore the shared snapshot before starting.
Authentication sessions from the former standby are not merged; those browsers sign in again once.

Service starts do not wait for Docker healthchecks: readiness can take longer than the election lease,
so waiting would block lease renewals and fencing. Docker healthchecks continue to report readiness separately.

Stops allow one second for graceful shutdown
before Docker kills a slow container; SQLite WAL recovery preserves committed transactions. DNS requests run
outside the fencing lock. After DNS preparation the agent renews and verifies its election entry before starting
services, so an expired lease cannot start a stale leader.

Docker startup commands renew the election lease while they run, even when container creation itself exceeds
the TTL. A renewal failure cancels the Docker CLI process group and stops both services before retrying.

The lease renews in its own thread, so a slow loop (Docker, Cloudflare, etcd reads through a distant Raft leader)
does not eat the fencing margin. A loop stuck for over a minute stops the renewals, and another server takes over.
