#!/bin/bash
# Wire host/pod egress into the sing-box VLESS tun. Mode-driven so the client
# is not k3s-specific. Wired to the sing-box unit as ExecStartPost (up) /
# ExecStopPost (down). Config comes from route.env.
#
#   SINGBOX_MODE=k3s-pods  route egress of scoped k3s pods (IPs in ipset
#                          $SINGBOX_SET, refreshed by singbox-podset-refresh)
#                          via fwmark policy-routing. Host untouched.
#   SINGBOX_MODE=host      route the whole host's egress through the tun
#                          (default route in a side table), excluding the VLESS
#                          server, local nets and $SINGBOX_HOST_EXCLUDES.
#   SINGBOX_MODE=none      bring the tun up only; caller does its own routing.
set -u
ACTION="${1:-}"
INSTANCE="${2:-}"
[ -n "$INSTANCE" ] || { echo "usage: $0 up|down <instance>" >&2; exit 1; }
ENV_FILE="/etc/sing-box/${INSTANCE}.route.env"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
MODE="${SINGBOX_MODE:-none}"
DEV="${SINGBOX_DEV:-singbox0}"
TABLE="${SINGBOX_TABLE:-100}"
MARK="${SINGBOX_MARK:-0x80000}"
SET="${SINGBOX_SET:-singbox_pods}"
PREF_EXCLUDE=1000
PREF_MAIN_POD=1005
PREF_TABLE=1010
read -r -a LOCAL_DESTS <<< "${SINGBOX_LOCAL_DESTS:-10.42.0.0/16 10.43.0.0/16}"
read -r -a HOST_EXCLUDES <<< "${SINGBOX_HOST_EXCLUDES:-}"

wait_tun() {
  for _ in $(seq 1 40); do ip link show "$DEV" >/dev/null 2>&1 && return 0; sleep 0.5; done
  echo "singbox-route: $DEV never appeared" >&2; return 1
}

# --- k3s-pods mode: mark scoped pods' external traffic -> side table ---
# Cluster/node dests are excluded via a second ipset (nf_tables iptables
# rejects multiple "! -d" in one rule), matched on the packet destination.
LOCALSET="${SET}_local"
POD_MATCH=(-m set --match-set "$SET" src -m set ! --match-set "$LOCALSET" dst -j MARK --set-xmark "$MARK/$MARK")

k3s_up() {
  ipset create -exist "$SET" hash:ip family inet
  ipset create -exist "$LOCALSET" hash:net family inet
  ipset flush "$LOCALSET"
  for d in "${LOCAL_DESTS[@]}"; do ipset add -exist "$LOCALSET" "$d"; done
  ip route replace default dev "$DEV" table "$TABLE"
  iptables -t mangle -C PREROUTING "${POD_MATCH[@]}" 2>/dev/null || iptables -t mangle -A PREROUTING "${POD_MATCH[@]}"
  ip rule del pref "$PREF_TABLE" 2>/dev/null || true
  ip rule add pref "$PREF_TABLE" fwmark "$MARK/$MARK" lookup "$TABLE"
  [ -x /usr/local/bin/singbox-podset-refresh.sh ] && /usr/local/bin/singbox-podset-refresh.sh "$INSTANCE" || true
  echo "singbox-route: up mode=k3s-pods (@$SET mark $MARK -> table $TABLE via $DEV)"
}
k3s_down() {
  ip rule del pref "$PREF_TABLE" 2>/dev/null || true
  while iptables -t mangle -D PREROUTING "${POD_MATCH[@]}" 2>/dev/null; do :; done
  ip route flush table "$TABLE" 2>/dev/null || true
}

# --- host mode: whole-host egress via tun, with excludes to stay reachable ---
server_ips() { getent ahostsv4 "${SINGBOX_SERVER:-}" 2>/dev/null | awk '{print $1}' | sort -u; }

host_up() {
  ip route replace default dev "$DEV" table "$TABLE"
  # exclude the VLESS server (else loop), local nets and operator excludes -> main
  { server_ips; printf '%s\n' "${LOCAL_DESTS[@]}" "${HOST_EXCLUDES[@]}"; } | sed '/^$/d' | sort -u | while read -r cidr; do
    ip rule add pref "$PREF_EXCLUDE" to "$cidr" lookup main 2>/dev/null || true
  done
  ip rule del pref "$PREF_TABLE" 2>/dev/null || true
  ip rule add pref "$PREF_TABLE" from all lookup "$TABLE"
  echo "singbox-route: up mode=host (default via $DEV table $TABLE, excludes to main)"
}
host_down() {
  while ip rule del pref "$PREF_EXCLUDE" 2>/dev/null; do :; done
  ip rule del pref "$PREF_TABLE" 2>/dev/null || true
  ip route flush table "$TABLE" 2>/dev/null || true
}

up() {
  wait_tun || exit 1
  sysctl -qw "net.ipv4.conf.$DEV.rp_filter=0"
  case "$MODE" in
    k3s-pods) k3s_up ;;
    host) host_up ;;
    none) echo "singbox-route: up mode=none (tun only)" ;;
    *) echo "singbox-route: unknown SINGBOX_MODE=$MODE" >&2; exit 1 ;;
  esac
}
down() {
  case "$MODE" in
    k3s-pods) k3s_down ;;
    host) host_down ;;
    none) : ;;
  esac
  echo "singbox-route: down mode=$MODE"
}

case "$ACTION" in
  up) up ;;
  down) down ;;
  *) echo "usage: $0 up|down <instance>" >&2; exit 1 ;;
esac
