# hacode.infra.etcd

Run one member of an [etcd](https://etcd.io) cluster from the upstream release (checked against its `SHA256SUMS`) as a
systemd service, with TLS and client certificates for both clients and peers.

## Tasks

- `main` (default): install etcd, make this member's key on the host, sign its certificate on the controller with the
  CA from variables, render the config, start the member and wait until it is healthy. A weekly defrag and a daily
  `snapshot save` run from timers. `/usr/local/sbin/etcdctl-local` is etcdctl pointed at this member with its
  certificate.

- `step-down`: if this member leads Raft, pass the lead on, so that its address can change without an election.
- `peer-url`: run on another member, before a member changes its address: `etcd_move_name` gets peer URL
  `etcd_move_address`. The role itself only configures a member, it never changes the cluster's membership.

A new cluster starts when all of `etcd_members` run the role in the same play: members wait for each other.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `etcd_version` | `3.7.3` | upstream release |
| `etcd_name` | `inventory_hostname` | this member's name, one of `etcd_members` |
| `etcd_address` | `""` (required) | address the member listens and advertises on, e.g. its tailnet address |
| `etcd_members` | `[]` | every member: `[{name, address}]`, the same list everywhere |
| `etcd_client_port` / `etcd_peer_port` | `2379` / `2380` | client and peer ports |
| `etcd_cluster_token` | `etcd` | initial cluster token |
| `etcd_data_dir` | `/var/lib/etcd` | data, owned by the `etcd` user |
| `etcd_ca_key` / `etcd_ca_cert` | `""` (required) | CA that signs member certificates (PEM); the key is used on the controller only |
| `etcd_cert_days` | `3650` | member certificate lifetime |
| `etcd_heartbeat_interval` / `etcd_election_timeout` | `100` / `1000` | Raft timing in ms; raise both on high-latency links |
| `etcd_snapshot_count` | `10000` | Raft entries kept in memory before a snapshot; lower it for large values |
| `etcd_quota_backend_bytes` | `2147483648` | backend size limit |
| `etcd_auto_compaction_retention` | `1h` | history kept by periodic compaction |
| `etcd_defrag_on_calendar` | `Sun *-*-* 04:00:00` | weekly defrag (with up to an hour of random delay) |
| `etcd_backup_dir` / `etcd_backup_keep` | `/var/backups/etcd` / `7` | daily snapshots and how many days to keep |
