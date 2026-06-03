# hacode.infra.k3s

Install k3s server and agent nodes; fetch and rewrite kubeconfig to the controller.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `k3s_channel` | `stable` | release channel when `k3s_version` is empty |
| `k3s_version` | `""` | pin specific version like `v1.32.0+k3s1` |
| `k3s_token` | `""` | shared cluster token; must be set per inventory |
| `k3s_server_args` | `[]` | extra flags for `k3s server` |
| `k3s_agent_args` | `[]` | extra flags for `k3s agent` |
| `k3s_tls_san_extra` | `[]` | extra SANs on top of `ansible_host` |
| `k3s_node_ip` | `{{ ansible_host }}` | kubelet `--node-ip` (+ apiserver `--advertise-address` on servers); `""` falls back to k3s default-route detection |
| `k3s_control_plane_taint` | `""` | taint effect on servers as `node-role.kubernetes.io/control-plane=true:<effect>` (`NoSchedule` / `PreferNoSchedule` / `NoExecute`); empty = no taint. Applied via `kubectl taint` |
| `k3s_node_labels` | `{}` | dict of labels applied via `kubectl label` post-install (server applies its own; agent labels are applied from primary via `delegate_to`) |
| `k3s_node_taints` | `[]` | list of raw taint specs (`key=value:effect`) applied via `kubectl taint` post-install |
| `k3s_kubeconfig_local_dir` | `{{ hacode_kube_configs_dir }}` (defaults to `{{ hacode_output_dir }}/kube-configs`) | where to save kubeconfig on controller; shared with `hacode.infra.k8s_addons` so the addons role auto-discovers it |
| `k3s_kubeconfig_local_file` | `{{ hostname }}.yml` | kubeconfig filename |
| `k3s_cluster_name`, `k3s_user_name`, `k3s_context_name` | derived from `hostname` | names written into the saved kubeconfig |
| `k3s_namespace` | `""` | optional context namespace |
| `k3s_server_ports` | `[6443/tcp, 2379/tcp, 2380/tcp, 8472/udp, 10250/tcp]` | firewall ports |
| `k3s_agent_ports` | `[8472/udp, 10250/tcp]` | firewall ports |
| `k3s_cluster_cidr` | `10.42.0.0/16` | pod CIDR (k3s default); used for firewalld trust |
| `k3s_service_cidr` | `10.43.0.0/16` | service CIDR (k3s default); used for firewalld trust |
| `k3s_trusted_cidrs` | `[k3s_cluster_cidr, k3s_service_cidr]` | CIDRs added as `source` to firewalld `trusted` zone so pod traffic isn't dropped; empty to skip |
| `k3s_kernel_modules` | `[overlay, br_netfilter]` | modules loaded via `modprobe` and persisted in `k3s_modules_load_file` |
| `k3s_modules_load_file` | `/etc/modules-load.d/k3s.conf` | drop-in for systemd-modules-load |
| `k3s_sysctls` | `{net.ipv4.ip_forward:1, net.bridge.bridge-nf-call-iptables:1, net.bridge.bridge-nf-call-ip6tables:1}` | sysctls applied via `ansible.posix.sysctl`; empty to skip |

### Notes on labels and taints

k3s already labels server nodes as `node-role.kubernetes.io/control-plane=true`
on its own (via the embedded cloud-controller-manager) — the role doesn't
duplicate that. Labels and taints go through `k3s kubectl` after node
registration rather than through `kubelet --node-labels` / `--node-taint`
because kubelet refuses to self-assign labels/taints in the `kubernetes.io` /
`k8s.io` namespaces (it would crash-loop the service). Apply non-restricted
labels via kubectl too, for consistency.

## Example

```yaml
- hosts: "k3s_servers"
  become: true
  roles:
    - role: "hacode.infra.k3s"
      vars:
        k3s_token: "{{ vault_k3s_token }}"
```

For HA, run on multiple servers with the same `k3s_token`; the role uses `--cluster-init` on the first node and
`--server https://<first>:6443` on the rest.
