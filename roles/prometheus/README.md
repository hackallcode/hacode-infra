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
