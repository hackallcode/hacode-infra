# hacode.infra.prometheus

Install Prometheus server, Alertmanager and node_exporter using the upstream `prometheus.prometheus` collection as a
backend. Ships a curated set of alert rules under `files/rules/`.

## Tasks

- `main` (default): node_exporter, Alertmanager and Prometheus.
- `uninstall`: stop Prometheus, Alertmanager and blackbox_exporter and delete their units, binaries, configs, data and
  users. node_exporter stays for the Prometheus servers left.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `prometheus_web_listen_ip` | `127.0.0.1` | bind address for prometheus |
| `prometheus_web_listen_port` | `9090` | bind port |
| `prometheus_metrics_path` | `/metrics` | self-scrape path |
| `alertmanager_web_listen_ip` | `127.0.0.1` | bind address for AM |
| `alertmanager_web_listen_port` | `9093` | bind port |
| `node_exporter_web_listen_ip` | `0.0.0.0` | bind address for node_exporter |
| `node_exporter_web_listen_port` | `9100` | bind port |
| `prometheus_scrape_custom_configs` | `[]` | extra scrape configs merged with defaults |
| `prometheus_am_custom_configs` | `[]` | extra AM target configs |
| `prometheus_extra_rule_dirs` | `[]` | controller-side directories with extra `*.yml` rule files |
| `prometheus_extra_target_dirs` | `[]` | controller-side directories with extra `*.yml` static target files |
| `alertmanager_bundled_templates_enabled` | `true` | ship the bundled `templates/*.tmpl`; `false` keeps only `alertmanager_extra_template_files` |
| `alertmanager_extra_template_files` | `[]` | controller-side globs of extra Alertmanager `*.tmpl` files |
| `alertmanager_instance_emojis` | `{}` | emoji of a host in the Telegram header, by the `instance_name` label |
| `alertmanager_severity_inhibit_enabled` | `true` | a `critical` alert mutes its `warning` twin of the same name, host and mountpoint; `alertmanager_inhibit_rules` are kept after it |
| `prometheus_bundled_rules_enabled` | `true` | ship the curated rules under `files/rules/`; `false` keeps only `prometheus_extra_rule_dirs` |
| `node_exporter_allowed_sources` | `[]` | CIDRs allowed to reach node_exporter (RHEL family); `[]` opens the port to everyone |
| `prometheus_unit_overrides` | `{}` | per-unit systemd `[Service]` settings written as a drop-in, e.g. `OOMScoreAdjust`, `MemoryMax` |

## Telegram message

The bundled `telegram.default.message` template turns a notification into a header and an item per alert:

```text
🚨⚠️🌍🍓 • 2 firing

14:02 • ✅🌍🧠 • 👀🍓
host-1 has 7% of its memory available, not counting swap

14:10 • ⚠️🍓🧠 • 👀🌍🍓
host-2 has 18% of its memory available, not counting swap

14:14 • 🚨🌍🧠 • 👀🍓 🆕
host-1 has 6% of its memory available, not counting swap
```

The header carries the emoji of each severity among the firing alerts and the emoji `alertmanager_instance_emojis` gives
each of their hosts, then the count of those not `info`, which are events rather than state; with none firing it is ✅
and the hosts. Items run oldest first, each with when the alert fired, or resolved, in the Alertmanager host's time
zone, the emoji of its severity (✅ once resolved), of its host and of its `category` label, and below them its
`description` annotation, or `summary` without one, less a final period. 🆕 marks an alert other than `info` fired under
a minute ago: that is the one the message is about, as a group is notified within `group_interval` of a change.

Prometheus servers that watch the same hosts each send their own copy of an alert. An `observer` label naming the
server's host, set through `prometheus_alert_relabel_configs`, keeps the copies apart, so one that sees a host down and
one that sees it up do not flip a shared alert between firing and resolved; the item then shows 👀 and the emoji of each
observer that sees it. Without the label, the copies are one alert and the item shows no observers.

A project rule reads well with a `category` label (`memory`, `cpu`, `disk`, `network`, `host`, `clock`, `services`,
`mesh`, `monitoring`) and a `description` that names the host and the value. A route with `group_by: []` puts all it
routes into one group, so each message shows everything that fires.

## Example

```yaml
- hosts: "monitoring"
  become: true
  roles:
    - role: "hacode.infra.prometheus"
      vars:
        prometheus_extra_rule_dirs:
          - "{{ playbook_dir }}/prometheus/{{ inventory_hostname }}/rules"
        prometheus_scrape_custom_configs:
          - job_name: "node"
            static_configs:
              - targets: ["host1:9100", "host2:9100"]
```

## Dependencies

- `prometheus.prometheus` collection (already listed in the parent collection's `dependencies`).
