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
| `etcd_address` | `""` (required) | address the member listens and advertises on, e.g. its tailnet address; the unit orders after `tailscaled.service` |
| `etcd_members` | `[]` | every member: `[{name, address}]`, the same list everywhere |
| `etcd_client_port` / `etcd_peer_port` | `2379` / `2380` | client and peer ports |
| `etcd_cluster_token` | `etcd` | initial cluster token |
| `etcd_data_dir` | `/var/lib/etcd` | data, owned by the `etcd` user |
| `etcd_config_dir` | `/etc/etcd` | config, `etcdctl-local` and the `pki/` certificates |
| `etcd_config_extra` | `{}` | deep-merged over the rendered config; the member's identity, URLs and TLS blocks are locked to it |
| `etcd_ca_key` / `etcd_ca_cert` | `""` (required) | CA that signs member certificates (PEM); the key is used on the controller only |
| `etcd_cert_days` | `3650` | member certificate lifetime |
| `etcd_heartbeat_interval` / `etcd_election_timeout` | `100` / `1000` | Raft timing in ms; raise both on high-latency links |
| `etcd_snapshot_count` | `10000` | Raft entries kept in memory before a snapshot; lower it for large values |
| `etcd_quota_backend_bytes` | `2147483648` | backend size limit |
| `etcd_auto_compaction_retention` | `1h` | history kept by periodic compaction |
| `etcd_defrag_on_calendar` | `Sun *-*-* 04:00:00` | weekly defrag (with up to an hour of random delay) |
| `etcd_backup_dir` / `etcd_backup_keep` | `/var/backups/etcd` / `7` | daily snapshots and how many days to keep; `""` removes the backup timer |
| `etcd_move_name` / `etcd_move_address` | `""` | `peer-url`: the member whose address changes, and its new peer address |

## Example

A three-member cluster on a tailnet, then moving a member to a new address:

```yaml
- hosts: "etcd"  # etcd-1, etcd-2, etcd-3
  become: true
  roles:
    - role: "hacode.infra.etcd"
      vars:
        etcd_address: >-
          {{ etcd_members | selectattr('name', 'equalto', inventory_hostname)
             | map(attribute='address') | first }}
        etcd_members:
          - {name: "etcd-1", address: "100.64.0.11"}
          - {name: "etcd-2", address: "100.64.0.12"}
          - {name: "etcd-3", address: "100.64.0.13"}
        etcd_ca_key: "{{ vault_etcd_ca_key }}"
        etcd_ca_cert: "{{ vault_etcd_ca_cert }}"
```

```yaml
# etcd-1 changes its address: let someone else lead, teach the cluster the new
# peer URL from another member, then redeploy etcd-1 with etcd_address set to it.
- hosts: "etcd-1"
  become: true
  tasks:
    - ansible.builtin.include_role: {name: "hacode.infra.etcd", tasks_from: "step-down"}
- hosts: "etcd-2"
  become: true
  tasks:
    - ansible.builtin.include_role: {name: "hacode.infra.etcd", tasks_from: "peer-url"}
      vars: {etcd_move_name: "etcd-1", etcd_move_address: "100.64.0.21"}
```
