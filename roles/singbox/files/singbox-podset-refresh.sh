#!/bin/bash
# Refresh the ipset of scoped pod IPs (pods in $SINGBOX_SCOPE_NS namespaces)
# consumed by singbox-podroute. Built into a temp set and swapped in atomically
# so routing never sees a half-populated set. Run once at sing-box start and
# then periodically by singbox-podset-refresh.timer.
set -u
INSTANCE="${1:-}"
[ -n "$INSTANCE" ] || { echo "usage: $0 <instance>" >&2; exit 1; }
ENV_FILE="/etc/sing-box/${INSTANCE}.route.env"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
SET="${SINGBOX_SET:-sbx_${INSTANCE}}"
NS_LIST="${SINGBOX_SCOPE_NS:-}"
KUBECTL="${SINGBOX_KUBECTL:-/usr/local/bin/k3s kubectl}"

ipset create -exist "$SET" hash:ip family inet
TMP="${SET}_tmp"
ipset create -exist "$TMP" hash:ip family inet
ipset flush "$TMP"

for ns in $NS_LIST; do
  $KUBECTL -n "$ns" get pods -o jsonpath='{range .items[*]}{.status.podIP}{"\n"}{end}' 2>/dev/null \
    | grep -E '^[0-9]+\.' \
    | while read -r ip; do ipset add -exist "$TMP" "$ip"; done
done

ipset swap "$TMP" "$SET"
ipset destroy "$TMP"
