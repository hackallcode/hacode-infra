#!/bin/bash
# Maintain the routing ipset in real time by watching the scoped namespaces, so
# short-lived pods are captured before their first egress (a periodic poll can
# miss a pod that starts, egresses and exits inside one interval). `kubectl get
# --watch` emits ADDED for every existing pod first (initial sync), then streams
# ADDED / MODIFIED / DELETED. Runs as singbox-podwatch@<instance>.
set -u
INSTANCE="${1:-}"
[ -n "$INSTANCE" ] || { echo "usage: $0 <instance>" >&2; exit 1; }
ENV_FILE="/etc/sing-box/${INSTANCE}.route.env"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
SET="${SINGBOX_SET:-sbx_${INSTANCE}}"
NS_LIST="${SINGBOX_SCOPE_NS:-}"
KUBECTL="${SINGBOX_KUBECTL:-/usr/local/bin/k3s kubectl}"

[ -n "$NS_LIST" ] || { echo "podwatch: SINGBOX_SCOPE_NS empty" >&2; exit 1; }
ipset create -exist "$SET" hash:ip family inet

watch_ns() {
  # shellcheck disable=SC2086
  $KUBECTL -n "$1" get pods --watch --output-watch-events \
    -o "custom-columns=T:.type,IP:.object.status.podIP" --no-headers 2>/dev/null \
  | while read -r evt ip; do
      if [ -z "$ip" ] || [ "$ip" = "<none>" ]; then continue; fi
      case "$evt" in
        ADDED|MODIFIED) ipset add -exist "$SET" "$ip" ;;
        DELETED) ipset del "$SET" "$ip" 2>/dev/null || true ;;
      esac
    done
}

for ns in $NS_LIST; do watch_ns "$ns" & done
# Any watcher exiting (API connection drop) fails the unit so systemd restarts
# the whole set; on restart the initial list re-syncs the ipset.
wait -n
echo "podwatch: a namespace watcher exited; restarting" >&2
exit 1
