# hacode.infra.k8s_addons

Install opinionated Kubernetes addons (Cilium CNI, Longhorn block
storage, Headlamp, Ingress-NGINX, Envoy Gateway, CoreDNS custom server
blocks, cert-manager, trust-manager) into an existing cluster via Helm
and raw manifests.
Each addon is gated by its own `k8s_addons_<name>_enabled` flag and
lives in its own `tasks/<addon>-install.yml` /
`tasks/<addon>-uninstall.yml` pair.

Cluster-level tasks (helm, k8s) delegate to localhost + `run_once`, so
the role can be included in any play (including `hosts: cluster_nodes`)
without firing N times against unrelated managed hosts.

## Controller requirements

The role's helm / k8s tasks run on the controller and need:

- **`helm` CLI on `PATH`** — `kubernetes.core.helm` and
  `kubernetes.core.helm_info` shell out to it. Install via
  [get.helm.sh](https://helm.sh/docs/intro/install/) or your package
  manager. Tested with helm v3.x and v4.x.
- **Python `kubernetes` package** in the same interpreter Ansible uses on
  the controller. `kubernetes.core.k8s` / `helm_info` import it
  directly; without it the role fails with `ModuleNotFoundError:
  kubernetes`. Install with `pip install kubernetes`.

A preflight assert in `_validate.yml` checks both are present before any
addon-touching task runs, so the failure message is clear when a
dependency is missing.

Addons that need per-node OS setup expose their host-level tasks via
`tasks_from: host-prep`. Currently: Longhorn installs the iscsid stack;
Cilium flushes orphan `OLD_CILIUM_*` iptables chains left over from an
unclean shutdown. Invoke the entrypoint from a play whose `hosts:`
covers every cluster node:

```yaml
- hosts: "k3s_server:k3s_agent"
  become: true
  tasks:
    - ansible.builtin.import_role:
        name: "hacode.infra.k8s_addons"
        tasks_from: "host-prep"
```

## Variables

### Cluster target

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_kubeconfig` | derived from `k3s_kubeconfig_local_dir` / `_local_file` / `k3s_cluster_name` when in scope, else `""` | path to a kubeconfig on the controller. The default works zero-config when the role is included alongside `hacode.infra.k3s` in the same inventory group - including the case where the operator pinned a custom kubeconfig filename via `k3s_kubeconfig_local_file`. For clusters provisioned by anything other than the k3s role, set this explicitly in inventory (e.g. group_vars of a dedicated `k8s` group) |

### Cilium

[Cilium](https://cilium.io/) is the CNI / NetworkPolicy implementation
used by DOKS, GKE Dataplane V2, EKS Anywhere, etc. Use it to replace
k3s's bundled flannel + kube-router; the cluster ends up much closer to
upstream / managed-Kubernetes defaults.

**Prerequisite**: install k3s with the flannel and kube-router disable
flags so Cilium can take over the datapath. Until Cilium lands, the node
will sit `NotReady` and CoreDNS will stay `Pending`. That's expected.

```yaml
k3s_server_args:
  - "--flannel-backend=none"
  - "--disable-network-policy"
  - "--disable=traefik"     # optional but typical (use ingress-nginx)
  - "--disable=servicelb"   # optional but typical (no Klipper LB)
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_cilium_enabled` | `false` | opt-in flag |
| `k8s_addons_cilium_chart_version` | `1.16.5` | pinned chart version from `https://helm.cilium.io` |
| `k8s_addons_cilium_chart_timeout` | `10m0s` | helm `--timeout`; Cilium DaemonSet needs cluster-wide rollout before `--wait` returns |
| `k8s_addons_cilium_namespace` | `kube-system` | release namespace |
| `k8s_addons_cilium_operator_replicas` | `1` | upstream chart default is `2` (HA) which leaves one operator `Pending` on single-node clusters and hangs `--wait`. Bump to 2+ when running HA control planes |
| `k8s_addons_cilium_pod_cidr` | `{{ k3s_cluster_cidr \| default('10.42.0.0/16') }}` | pod CIDR Cilium allocates from. Default tracks `k3s_cluster_cidr` when in scope, otherwise falls back to k3s's own default - so colocating with `hacode.infra.k3s` needs no extra config |
| `k8s_addons_cilium_pod_cidr_mask_size` | `24` | per-node block size carved out of the pod CIDR |
| `k8s_addons_cilium_kube_proxy_replacement` | `"false"` | string `"false"` keeps kube-proxy (DOKS-style). Set to `"true"` + `--disable-kube-proxy` in `k3s_server_args` for Cilium's kube-proxy-free datapath |
| `k8s_addons_cilium_k8s_service_host` | `""` | apiserver IP/FQDN; required only when `_kube_proxy_replacement: "true"` |
| `k8s_addons_cilium_k8s_service_port` | `6443` | apiserver port; paired with `_k8s_service_host` |
| `k8s_addons_cilium_cni_exclusive` | `false` | leave non-Cilium CNI configs in `/etc/cni/net.d` alone (e.g. flannel leftovers from a previous install). Set `true` for strict single-CNI |
| `k8s_addons_cilium_devices` | `""` | interfaces Cilium attaches BPF programs to (e.g. `eth0`, `eth+`). Empty = auto-detect via default route. Pin when the node has multiple public NICs and Cilium picks the wrong one |
| `k8s_addons_cilium_egress_masquerade_interfaces` | `""` | SNAT source interface for pod→external traffic. Empty = derive from `_devices` / default route. Pin to the egress NIC (e.g. `eth0`) when pod-to-internet times out because pod IPs leak out unmasqueraded |
| `k8s_addons_cilium_extra_values` | `{}` | extra Helm values deep-merged on top of the role's defaults (user wins). Use to enable Hubble, BGP, ClusterMesh, etc. |

See [Uninstall](#uninstall) for teardown notes (Cilium leaves per-node
CNI state on disk; the `kube-system` namespace is shared).

**Note on k3s restarts and masquerade.** On self-hosted k3s, a
`systemctl restart k3s` rewrites iptables on startup and can transiently
flush Cilium's pod-egress masquerade chain. Cilium reinstalls it on the
next agent reconcile loop, but the symptom in the gap is `pod →
external` timing out while `hostNetwork pod → external` works. Manual
recovery: `kubectl -n kube-system rollout restart ds/cilium`. To make
sure Cilium masquerades through the right interface on multi-NIC nodes,
pin `k8s_addons_cilium_egress_masquerade_interfaces`.

An unclean shutdown also leaves orphan `OLD_CILIUM_*` iptables chains
that the next agent appends to, producing the same symptom. The role's
`host-prep` entrypoint includes a Cilium-specific iptables cleanup
(`cilium-prep.yml`) that flushes and deletes any `OLD_CILIUM_*` chains
before the agent starts — invoke it from a play whose `hosts:` covers
every cluster node (see the host-prep example near the top of this
file).

The molecule scenario doesn't *install* Cilium (eBPF datapath + per-node
CNI state are fragile in privileged docker), but the rendered helm
values are validated offline against the chart's `values.schema.json`
via a `helm template` smoke-test in `extensions/molecule/k8s_addons/`.
That catches stringified-scalar / wrong-key / wrong-nesting regressions
regardless of which Ansible version is in use.

### Longhorn

[Longhorn](https://longhorn.io/) is a distributed block-storage CSI for
k8s. Use it as the cluster's default `StorageClass` when k3s is
installed with `--disable=local-storage` (DOKS-style) - PVCs without an
explicit `storageClassName` then bind through Longhorn instead of staying
`Pending`.

Longhorn's CSI driver needs `iscsid` on every node. The role installs
the relevant host packages (`iscsi-initiator-utils` on RHEL/Rocky,
`open-iscsi` on Debian/Ubuntu) and starts the service via the
`host-prep` entrypoint. NFS support (for ReadWriteMany volumes) is
opt-in via `_install_nfs: true`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_longhorn_enabled` | `false` | opt-in flag |
| `k8s_addons_longhorn_chart_version` | `1.7.2` | pinned chart version from `https://charts.longhorn.io` |
| `k8s_addons_longhorn_chart_timeout` | `10m0s` | helm `--timeout`; the Longhorn manager/CSI rollout takes a while on cold installs |
| `k8s_addons_longhorn_namespace` | `longhorn-system` | release namespace |
| `k8s_addons_longhorn_replica_count` | `1` | default replica count for the StorageClass + global default. Upstream chart default is `3` (HA) which leaves PVCs `Pending` on single-node clusters waiting for distinct hosts. Bump to `3` for HA |
| `k8s_addons_longhorn_default_storage_class` | `true` | mark Longhorn's StorageClass as the cluster default. Needed when k3s ships without local-storage and PVCs don't pin a `storageClassName` |
| `k8s_addons_longhorn_install_nfs` | `false` | install `nfs-utils` / `nfs-common` on every node so Longhorn can serve RWX volumes via its internal NFS provisioner |
| `k8s_addons_longhorn_extra_values` | `{}` | extra Helm values deep-merged on top of the role's defaults (user wins). Use to tune resource limits, change `defaultDataPath`, enable backup target, etc. |

The uninstall path removes only the Helm release and the namespace.
Host packages and replica data on disk (`/var/lib/longhorn/` by default)
are left in place.

**csi sidecar replicas are install-time only.** The chart's
`csi.attacherReplicaCount` / `provisionerReplicaCount` / `resizerReplicaCount`
/ `snapshotterReplicaCount` keys are read by `longhorn-driver-deployer`
when it *creates* the csi-* Deployments and never reconciled afterwards.
Setting them via `_extra_values` on an already-deployed cluster updates
the Helm release values (visible in `helm get values`) but the running
Deployments stay at their original replica count. To scale down on a
live cluster, `kubectl scale deploy csi-attacher csi-provisioner
csi-resizer csi-snapshotter -n longhorn-system --replicas=1` and the
deployer won't reconcile them back.

The molecule scenario doesn't *install* Longhorn (it needs iscsid +
privileged host access that's unreliable in nested docker, and PVC
binding only makes sense against a long-lived host), but a `helm
template` smoke-test in `extensions/molecule/k8s_addons/` renders the
chart offline against the role's defaults and sanity-checks that
`defaultClass: true` propagates to the StorageClass annotation and
`defaultClassReplicaCount` to `numberOfReplicas`. The Longhorn 1.7.x
chart doesn't ship a `values.schema.json`, so pure type-coercion bugs
aren't caught by this — the type-assert in `longhorn-values.yml` is
the regression guard for those.

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

### Envoy Gateway

Installs the upstream Envoy Gateway product (`gateway.envoyproxy.io`): a
dynamic Gateway API controller. The chart ships the control plane plus the
Gateway API and Envoy Gateway CRDs; the role then reconciles a
`GatewayClass` and a `Gateway`, at which point the controller provisions
the Envoy data-plane (Deployment + Service) itself and starts watching
`HTTPRoute`s. Unlike a static Envoy, routing is dynamic: new HTTPRoutes are
picked up from the API without redeploying anything.

Routing policy is deliberately not owned by this role. The role stands up
the controller and one shared Gateway with an all-namespaces listener;
workload charts attach their own `HTTPRoute`s (and `BackendTrafficPolicy` /
filters) by `parentRef`, keeping environment-specific policy out of the
collection.

The data-plane Service defaults to `NodePort` (a baremetal cluster has no
cloud LoadBalancer) with `externalTrafficPolicy: Cluster`, applied through an
`EnvoyProxy` resource attached to the GatewayClass `parametersRef`. `Cluster`
lets any node route to the Envoy pod, which is what a single upstream proxy
targeting one NodePort needs; `Local` would only answer on nodes running an
Envoy pod.

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_envoy_gateway_enabled` | `false` | opt-in flag |
| `k8s_addons_envoy_gateway_chart_ref` | `oci://docker.io/envoyproxy/gateway-helm` | official OCI Helm chart (control plane + CRDs) |
| `k8s_addons_envoy_gateway_chart_version` | `v1.8.2` | pinned chart/app version; bump intentionally |
| `k8s_addons_envoy_gateway_chart_timeout` | `5m0s` | helm `--timeout` for chart install |
| `k8s_addons_envoy_gateway_namespace` | `envoy-gateway-system` | control-plane release namespace |
| `k8s_addons_envoy_gateway_class_name` | `envoy-gateway` | GatewayClass name (also names the EnvoyProxy the class references) |
| `k8s_addons_envoy_gateway_controller_name` | `gateway.envoyproxy.io/gatewayclass-controller` | fixed controllerName the chart's controller reconciles; do not change |
| `k8s_addons_envoy_gateway_gateway_name` | `eg` | name of the shared Gateway the role reconciles |
| `k8s_addons_envoy_gateway_gateway_namespace` | `envoy-gateway-system` | namespace of the Gateway; where the data-plane is provisioned |
| `k8s_addons_envoy_gateway_listeners` | one HTTP `:80` listener, `allowedRoutes.namespaces.from: All` | Gateway listener list; override to add HTTPS/TLS or restrict route namespaces |
| `k8s_addons_envoy_gateway_service_type` | `NodePort` | data-plane Service type; `NodePort` avoids a pending LoadBalancer on baremetal |
| `k8s_addons_envoy_gateway_node_ports` | `{}` | map of listener-name to fixed nodePort; empty = auto-assign. Applied via a StrategicMerge patch on the data-plane Service |
| `k8s_addons_envoy_gateway_service_external_traffic_policy` | `Cluster` | data-plane Service `externalTrafficPolicy`. `Cluster` lets any node forward to the Envoy pod (right for a single upstream proxy hitting one NodePort target); `Local` only answers on nodes running an Envoy pod |
| `k8s_addons_envoy_gateway_extra_values` | `{}` | extra Helm values deep-merged over defaults (user wins). Tune control-plane resources, metrics, log level |
| `k8s_addons_envoy_gateway_proxy_extra_spec` | `{}` | deep-merged into the EnvoyProxy `spec.provider.kubernetes` (user wins). Pin data-plane replicas/resources/tolerations; the role seeds `envoyService` (`type`/`externalTrafficPolicy`/nodePorts) from the variables above and a matching key here wins |

```yaml
k8s_addons_envoy_gateway_enabled: true
k8s_addons_envoy_gateway_node_ports:
  http: 30080
  https: 30443
k8s_addons_envoy_gateway_listeners:
  - name: "http"
    port: 80
    protocol: "HTTP"
    allowedRoutes:
      namespaces:
        from: "All"
  - name: "https"
    port: 443
    protocol: "HTTPS"
    tls:
      mode: "Terminate"
      certificateRefs:
        - kind: "Secret"
          name: "wildcard-tls"
    allowedRoutes:
      namespaces:
        from: "All"
```

### CoreDNS custom server blocks

k3s ships CoreDNS with the `import` plugin pre-wired against a
`coredns-custom` ConfigMap in `kube-system`. Drop extra server blocks
into that ConfigMap and CoreDNS picks them up without a restart —
useful for resolving internal zones (e.g. `*.k.int-net`) that aren't
served by the cluster's default upstreams. Each entry in
`k8s_addons_coredns_custom_servers` becomes a `<name>.server` key in
the ConfigMap.

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_coredns_custom_enabled` | `false` | opt-in flag |
| `k8s_addons_coredns_custom_servers` | `[]` | list of server blocks (see schema below); empty = no-op |

Each entry:

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | ConfigMap data key prefix; final key becomes `<name>.server` |
| `zone` | yes | CoreDNS zone the block serves (e.g. `k.int-net:53`) |
| `forward` | yes | upstream resolver(s); string `"10.0.1.10"` or list `["10.0.1.10", "10.0.1.11"]` |
| `cache` | no | cache TTL in seconds; default `30` |

```yaml
k8s_addons_coredns_custom_enabled: true
k8s_addons_coredns_custom_servers:
  - name: "k-int-net"
    zone: "k.int-net:53"
    forward: ["10.0.1.10", "10.0.1.11"]
```

Uninstall removes the `coredns-custom` ConfigMap; CoreDNS reverts to
the stock cluster zones.

### cert-manager

[cert-manager](https://cert-manager.io/) is the de-facto PKI
controller for Kubernetes. It's a hard prerequisite for
trust-manager (which serves its webhook via a `cert-manager`
`Certificate` + `Issuer`), but you may also want it for its own
sake (`Certificate` resources, ACME issuers, etc.).

The role installs the upstream Jetstack chart with CRDs bundled
(`crds.enabled: true`, `crds.keep: true` so an uninstall doesn't
nuke `Certificate` / `Issuer` objects other workloads still rely
on).

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_cert_manager_enabled` | `false` | opt-in flag |
| `k8s_addons_cert_manager_chart_version` | `""` | empty = track latest; pin once you've validated a version |
| `k8s_addons_cert_manager_chart_timeout` | `5m0s` | helm `--timeout` |
| `k8s_addons_cert_manager_namespace` | `cert-manager` | release namespace |
| `k8s_addons_cert_manager_extra_values` | `{}` | deep-merged over `{crds: {enabled: true, keep: true}}` (user wins on conflicts) |

When both cert-manager and trust-manager are enabled in the same
play, the role installs cert-manager first and uninstalls it last
(reverse-order), so trust-manager's webhook serving cert always
sees the cert-manager controller during both lifecycles.

### trust-manager

[trust-manager](https://cert-manager.io/docs/trust/trust-manager/) is
the Jetstack project that publishes a CA bundle into namespaces as a
`ConfigMap` workloads can mount or pass to their HTTP clients. Use
this addon to fan a corporate / internal CA out to selected
namespaces without manually maintaining a per-namespace ConfigMap.

**Prerequisite**: cert-manager (above) must be installed first —
trust-manager's webhook serving cert is a cert-manager
`Certificate` / `Issuer`. The role's install order honors this when
both addons are enabled in the same play.

The role installs the OCI chart, seeds a source ConfigMap with the CA
cert read from the controller, waits for the `Bundle` CRD to be
`Established` (not just registered — a freshly-registered CRD is
missing from the apiserver's discovery doc until the controller
flips the `Established` condition), and creates a `Bundle` whose
`namespaceSelector` matches on a label. The Bundle apply itself
retries with backoff to ride out the python kubernetes client's
discovery-cache lag right after CRD registration.

| Variable | Default | Purpose |
| --- | --- | --- |
| `k8s_addons_trust_manager_enabled` | `false` | opt-in flag |
| `k8s_addons_trust_manager_chart_ref` | `oci://quay.io/jetstack/charts/trust-manager` | OCI chart reference |
| `k8s_addons_trust_manager_chart_version` | `""` | empty = track latest; pin once you've validated a version |
| `k8s_addons_trust_manager_chart_timeout` | `5m0s` | helm `--timeout` |
| `k8s_addons_trust_manager_namespace` | `cert-manager` | release namespace; co-located with cert-manager because trust-manager's webhook serving cert is issued by it |
| `k8s_addons_trust_manager_ca_source_file` | `""` | **required when enabled.** Controller-side path to the CA cert (PEM) to publish |
| `k8s_addons_trust_manager_ca_source_name` | `cute-ca-source` | name of the source ConfigMap (in `_namespace`) seeded with the CA cert |
| `k8s_addons_trust_manager_bundle_name` | `cute-ca` | name of the `Bundle` resource |
| `k8s_addons_trust_manager_target_label_key` | `cute-ca` | namespace label key that opts a namespace into the CA |
| `k8s_addons_trust_manager_target_label_value` | `enabled` | label value paired with `_target_label_key` |
| `k8s_addons_trust_manager_target_configmap_key` | `ca.crt` | data key under which the CA lands in the target ConfigMap |

```yaml
k8s_addons_trust_manager_enabled: true
k8s_addons_trust_manager_ca_source_file: "{{ playbook_dir }}/configs/ca/corp-ca.crt"
# Label any namespace that should receive the CA bundle:
#   kubectl label namespace my-app cute-ca=enabled
```

Workloads then mount the ConfigMap (named after `_bundle_name`,
default `cute-ca`) or read `data["ca.crt"]` directly. Uninstall
removes the Bundle, the source ConfigMap, and the trust-manager Helm
release; the target ConfigMaps in labeled namespaces are garbage-
collected by trust-manager itself before the chart is removed.

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
Use `--tags <addon>-uninstall` (`trust-manager-uninstall`,
`cert-manager-uninstall`, `coredns-custom-uninstall`,
`headlamp-uninstall`, `ingress-nginx-uninstall`,
`envoy-gateway-uninstall`, `longhorn-uninstall`, `cilium-uninstall`)
to scope to a specific addon. Install and uninstall lifecycles use **separate tags**
(`<addon>-install` vs `<addon>-uninstall`) on purpose — the bare
`<addon>` tag matches nothing, so `--tags cilium` will never
accidentally fire both install and uninstall in the same run.
Removal order is the reverse of install (trust-manager,
cert-manager, CoreDNS-custom, Headlamp, Envoy Gateway, Ingress-NGINX,
Longhorn, then Cilium last), so the CNI stays up while the others talk
to the apiserver during teardown — and cert-manager stays up while
trust-manager hands its CRs back to the apiserver.

Per-addon teardown details:

- **trust-manager** — removes the `Bundle`, the source ConfigMap, and
  the Helm release. trust-manager garbage-collects the target
  ConfigMaps in labeled namespaces during the Bundle's own teardown
  hook, so they vanish before the chart is removed.
- **cert-manager** — removes the Helm release. The chart installed
  CRDs with `keep: true`, so `Certificate` / `Issuer` /
  `ClusterIssuer` objects other workloads may still rely on are
  preserved across the uninstall.
- **CoreDNS custom** — removes the `coredns-custom` ConfigMap;
  CoreDNS picks up the absence and stops serving the custom zones
  without needing a restart.
- **Headlamp** — removes the Helm release, the cluster-scoped
  `ClusterRoleBinding`, the namespace, and the saved token file on the
  controller.
- **Envoy Gateway** — removes the `Gateway`, `GatewayClass`, and
  `EnvoyProxy` the role created (which deprovisions the Envoy data-plane),
  then the Helm release. The control-plane namespace is left in place.
- **Ingress-NGINX** — removes the Helm release and the namespace.
- **Longhorn** — removes the Helm release and the namespace. Host
  packages (`iscsi-initiator-utils` / `open-iscsi`, optional NFS) and
  replica data on disk (`/var/lib/longhorn/` by default) are kept in
  place; both are cheap and may still be wanted by the operator.
- **Cilium** — removes only the Helm release. The `kube-system`
  namespace is shared and per-node CNI state on disk
  (`/etc/cni/net.d/05-cilium.conflist`, pinned BPF maps under
  `/sys/fs/bpf`) is left in place; to migrate to another CNI, run
  `cilium-cli uninstall` on each node or wipe `/etc/cni/net.d`
  manually.
