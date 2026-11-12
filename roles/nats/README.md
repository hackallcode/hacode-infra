# hacode.infra.nats

Run one server of a [NATS](https://nats.io) cluster with JetStream from the upstream release (checked against its
`SHA256SUMS`) as a systemd service, with TLS and client certificates for both clients and routes.

## Tasks

- `main` (default): install nats-server, make this server's key on the host, sign its certificate on the controller
  with the CA from variables, render the config and start the server. Monitoring answers on localhost.

A cluster forms once a majority of `nats_peers` run; JetStream needs that majority to elect its leaders. With one
address in `nats_peers` the server runs JetStream on its own, without a cluster.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `nats_version` | `2.15.2` | upstream release |
| `nats_name` | `inventory_hostname` | this server's name |
| `nats_address` | `""` (required) | address for clients and routes, e.g. its tailnet address; the unit orders after `tailscaled.service` |
| `nats_peers` | `[]` | addresses of every server, this one included, the same list everywhere |
| `nats_cluster_name` | `nats` | cluster name |
| `nats_client_port` / `nats_cluster_port` / `nats_monitor_port` | `4222` / `6222` / `8222` | client, route and localhost monitoring ports |
| `nats_data_dir` | `/var/lib/nats` | JetStream store, owned by the `nats` user |
| `nats_config_dir` | `/etc/nats` | config and the `pki/` certificates |
| `nats_ping_interval` / `nats_ping_max` | `2s` / `3` | a server that died without closing connections is dropped after their product; the NATS default leaves requests routed to it hanging for minutes |
| `nats_max_file_store` / `nats_max_memory_store` | `2147483648` / `67108864` | JetStream limits of this server, bytes |
| `nats_config_extra` | `{}` | deep-merged over the rendered config; the server's identity, listeners, store and TLS are locked |
| `nats_ca_key` / `nats_ca_cert` | `""` (required) | CA that signs server certificates (PEM); the key is used on the controller only |
| `nats_cert_days` | `3650` | server certificate lifetime |

Server certificates carry `clientAuth` too: clients on the same host (`pki/server.crt`, `pki/server.key`, readable
by the `nats` group and root) can use them.

## Example

```yaml
- hosts: "nats"  # nats-1, nats-2, nats-3
  become: true
  roles:
    - role: "hacode.infra.nats"
      vars:
        nats_address: "{{ tailscale_ips[0] }}"
        nats_peers: "{{ groups['nats'] | map('extract', hostvars, 'tailscale_ips') | map('first') | list }}"
        nats_ca_key: "{{ vault_nats_ca_key }}"
        nats_ca_cert: "{{ vault_nats_ca_cert }}"
```
