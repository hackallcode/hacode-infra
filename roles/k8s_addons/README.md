# hacode.infra.k8s_addons

Install opinionated Kubernetes addons (currently: Headlamp) into an existing
cluster via Helm and raw manifests. Each addon is gated by its own
`k8s_addons_<name>_enabled` flag and lives in its own
`tasks/<addon>-install.yml` / `tasks/<addon>-uninstall.yml` pair.

The role talks to the cluster from the controller via the supplied
kubeconfig - every task is `delegate_to: localhost` + `run_once: true` -
so it can be included in any play (including `hosts: cluster_nodes`) without
firing N times against unrelated managed hosts. The `helm` CLI must be
installed on the controller (the `kubernetes.core.helm` module shells out
to it).

## Variables

### Cluster target

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_kubeconfig` | `{{ hacode_kube_configs_dir }}/{{ k3s_cluster_name }}.yml` when `k3s_cluster_name` is in scope, otherwise `""` | path to a kubeconfig on the controller. The default works zero-config when the role is included alongside `hacode.infra.k3s` in the same inventory group (both roles share `hacode_kube_configs_dir`). For clusters provisioned by anything other than the k3s role, set this explicitly in inventory (e.g. group_vars of a dedicated `k8s` group) |

### Headlamp

[Headlamp](https://headlamp.dev/) is the actively-maintained
CNCF/kubernetes-sigs successor to the now-archived `kubernetes-dashboard`.
The chart pulls a single web-UI deployment that accepts a bearer token
on login.

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_headlamp_enabled` | `false` | opt-in flag; main entrypoint is a no-op until set |
| `k8s_addons_headlamp_chart_version` | `0.42.0` | pinned Helm chart version from `https://kubernetes-sigs.github.io/headlamp/` |
| `k8s_addons_headlamp_chart_timeout` | `5m0s` | helm `--timeout` for chart install. Raise it on constrained clusters where pods can't become Ready within 5 minutes |
| `k8s_addons_headlamp_namespace` | `headlamp` | release namespace (created on install) |
| `k8s_addons_headlamp_node_port` | `""` | NodePort exposing Headlamp on every node. Empty (default) → chart keeps `ClusterIP`, so users route via an Ingress (`extra_values.ingress`) — typical setup if you've enabled `ingress_nginx`. Set a port (e.g. `30080`) for direct NodePort access. Headlamp serves **plain HTTP** on container port 4466; the role maps NodePort → service port 80 → 4466. Terminate TLS upstream if you need https |
| `k8s_addons_headlamp_ingress_enabled` | `false` | opt-in shortcut that wires the chart's built-in Ingress resource. When `true`, requires `..._ingress_host`. Reach for `..._extra_values.ingress` directly if you need multiple hosts, TLS secrets, annotations, or non-`Prefix` paths |
| `k8s_addons_headlamp_ingress_class_name` | `nginx` | `ingressClassName` on the generated Ingress (matches the `ingress_nginx` addon's default class) |
| `k8s_addons_headlamp_ingress_host` | `""` | FQDN the Ingress serves; required when `..._ingress_enabled: true` |
| `k8s_addons_headlamp_ingress_path` | `/` | path on the Ingress; `pathType: Prefix` |
| `k8s_addons_headlamp_admin_sa` | `headlamp-admin` | name of the admin `ServiceAccount` + `ClusterRoleBinding` + token `Secret` (all three share this name) |
| `k8s_addons_headlamp_token_file` | `<kubeconfig_dir>/<kubeconfig_basename>-headlamp-token.txt` | controller-side path where the decoded admin bearer token is saved. The default derives from the kubeconfig basename, so `<dir>/prod.yml` → `<dir>/prod-headlamp-token.txt` |
| `k8s_addons_headlamp_extra_values` | `{}` | extra Helm values deep-merged on top of the role's NodePort defaults (user wins on conflicts). Use this to enable OIDC, add plugins, set resource limits, etc. |

The role creates a long-lived `kubernetes.io/service-account-token` Secret
bound to `cluster-admin` and saves the decoded bearer token to
`k8s_addons_headlamp_token_file` (mode `0600`). The Wait and Save tasks
have `no_log: true` so the token never lands in CI logs. The role pins
`clusterRoleBinding.create: false` in the helm values so the chart
doesn't try to create its own (name-colliding) CRB — RBAC is managed
explicitly via the SA+CRB+Secret block above.

### Ingress-NGINX

The [ingress-nginx](https://kubernetes.github.io/ingress-nginx/) controller
deployed via its official Helm chart. Service type is forced to `NodePort`
(chart default is `LoadBalancer`, which silently stays `<pending>` on
baremetal / on-prem clusters with no cloud LB controller).

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_ingress_nginx_enabled` | `false` | opt-in flag |
| `k8s_addons_ingress_nginx_chart_version` | `4.15.1` | pinned chart version; chart `4.x.y` ships controller `1.x.y` |
| `k8s_addons_ingress_nginx_chart_timeout` | `5m0s` | helm `--timeout` for chart install |
| `k8s_addons_ingress_nginx_namespace` | `ingress-nginx` | release namespace (created on install) |
| `k8s_addons_ingress_nginx_http_node_port` | `""` | fixed NodePort for the controller's external HTTP listener. Empty = auto-assign from cluster's NodePort range (default `30000-32767`). Set when an upstream proxy / external nginx needs a deterministic target |
| `k8s_addons_ingress_nginx_https_node_port` | `""` | same for HTTPS |
| `k8s_addons_ingress_nginx_extra_values` | `{}` | extra Helm values deep-merged on top of the role's NodePort defaults (user wins on conflicts). Use to tune resources, enable metrics, switch IngressClass name, etc. |

## Security warning

The default admin ServiceAccount is bound to the built-in **`cluster-admin`**
ClusterRole. That is appropriate for a dev/PoC cluster but **not for
production**. For prod:

1. Provision your own least-privilege ClusterRole (or namespaced Role) before
   running this role.
2. Either pre-create the ServiceAccount + RoleBinding and skip the role's
   admin-RBAC task (open an issue if you need a flag for this), or set
   `k8s_addons_headlamp_admin_sa` to a name the role isn't otherwise
   binding to `cluster-admin`.
3. Treat the token file like a secret. Rotate the Secret to invalidate
   the bearer token; the file on disk is the only copy outside the cluster.
4. Don't expose Headlamp's NodePort directly to the internet. Terminate
   TLS at an ingress/proxy and gate access with auth (OIDC via
   `k8s_addons_headlamp_extra_values`, or an upstream identity-aware
   proxy).

## Inventory patterns

### Pattern 1 — colocated with `hacode.infra.k3s` (zero-config)

Drop `k8s_addons` into the same inventory group as `k3s`. The kubeconfig
path is auto-derived from `k3s_cluster_name`:

```yaml
# inventory/hosts.yml
k3s_server:
  hosts:
    node1: { ansible_host: "10.0.0.10" }
  vars:
    k3s_cluster_name: "prod"
```

```yaml
# playbook.yml
- hosts: "k3s_server"
  become: true
  roles:
    - role: "hacode.infra.k3s"
    - role: "hacode.infra.k8s_addons"
      vars:
        k8s_addons_headlamp_enabled: true
```

`k3s` writes `<hacode_output_dir>/kube-configs/prod.yml`;
`k8s_addons_kubeconfig` resolves to the same path; token lands at
`<hacode_output_dir>/kube-configs/prod-headlamp-token.txt`.

### Pattern 2 — external clusters with explicit kubeconfig paths

Put each cluster's controller-side kubeconfig path in inventory and
include the role from any play that has those vars in scope:

```yaml
# inventory/hosts.yml
k8s:
  hosts:
    prod-cluster:
      ansible_host: "127.0.0.1"   # placeholder; role is delegate_to: localhost
      k8s_addons_kubeconfig: "/etc/kubernetes/prod.yml"
    staging-cluster:
      ansible_host: "127.0.0.1"
      k8s_addons_kubeconfig: "/etc/kubernetes/staging.yml"
```

```yaml
# playbook.yml
- hosts: "k8s"
  gather_facts: false
  roles:
    - role: "hacode.infra.k8s_addons"
      vars:
        k8s_addons_headlamp_enabled: true
```

Token files land next to each kubeconfig
(`/etc/kubernetes/prod-headlamp-token.txt`, etc.).

## Uninstall

```yaml
- hosts: "k3s_server"
  tasks:
    - ansible.builtin.include_role:
        name: "hacode.infra.k8s_addons"
        tasks_from: "uninstall"
```

The uninstall path runs unconditionally (regardless of the `_enabled`
flag) so you can tear an addon down without flipping the flag back on.
Use `--tags headlamp` to scope to a specific addon. The Headlamp
uninstall removes the Helm release, the cluster-scoped `ClusterRoleBinding`,
the namespace, and the saved token file on the controller.
