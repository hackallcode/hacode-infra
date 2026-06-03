# hacode.infra.wireguard

Install WireGuard server and clients; generate peers and download/export their configs.

## Tasks

- `server-install` / `server-configure` (default sequence)
- `server-clients-add` / `server-client-add`
- `server-clients-delete` / `server-client-delete`
- `server-clients-download` / `server-client-download`
- `client-install`
- `client-servers-add` / `client-server-add`

## Example

```yaml
- hosts: "wg_servers"
  become: true
  roles:
    - role: "hacode.infra.wireguard"
```

See the templates and per-task variables; this role expects a `wg_*` set of variables defined per-inventory (peer key
material, IP allocations, listen port).

## DNS for VPN clients

Enable `wg_dns_enabled: true` to make the VPN endpoint also serve DNS to its clients. Wireguard-side traffic is
allowed **without any rate limit** (trusted VPN sources). dnsmasq config is delegated to `hacode.infra.machine`
(`tasks_from: dns`) so the setup matches a stand-alone DNS host 1:1.

```yaml
wg_dns_enabled: true                # add direct ACCEPT for wg subnets, install dnsmasq
machine_dns_enabled: true           # dnsmasq is installed/configured by the machine role
dns_server_interfaces: ["wg0"]      # listen on the VPN interface (plus any LAN you want)
```

DNS is **not** exposed to the public internet by default. To also serve external clients (with per-source-IP
rate limit), set `machine_dns_public: true` on the host — wg clients still bypass the limit because the wireguard
role places their ACCEPT in `filter/INPUT` at priority **-10**, ahead of the `machine_dns_public` hashlimit DROPs
at priority **0**.

What gets configured under the hood (with `wg_dns_enabled: true`):

- `dnsmasq` is installed and pointed at `dns_server_interfaces` (`hacode.infra.machine` `tasks_from: dns`).
- Four direct rules — `ipv4|ipv6 × udp|tcp` — at INPUT priority **-10** ACCEPT port 53 from
  `wg_ipv4_prefix.0/24` and `wg_ipv6_prefix::/64`.
