# hacode.infra.prometheus

Install Prometheus server, Alertmanager and node_exporter using the upstream `prometheus.prometheus` collection as a
backend. Ships a curated set of alert rules under `files/rules/`.

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
| `prometheus_bundled_rules_enabled` | `true` | ship the curated rules under `files/rules/`; `false` keeps only `prometheus_extra_rule_dirs` |
| `node_exporter_allowed_sources` | `[]` | CIDRs allowed to reach node_exporter (RHEL family); `[]` opens the port to everyone |
| `prometheus_unit_overrides` | `{}` | per-unit systemd `[Service]` settings written as a drop-in, e.g. `OOMScoreAdjust`, `MemoryMax` |

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
