# hacode.infra.common

Collection-wide defaults shared across roles. **This role ships no tasks** —
it exists purely as a variable carrier. Other roles in the collection list
`common` in their `meta/main.yml` dependencies so the variables become
available without the consumer having to define them.

## Variables

| Variable            | Default                                                              | Purpose                                                                                                                                                                                                                                                                          |
|---------------------|----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `hacode_sync_rsh`   | `ssh -o ControlMaster=auto -o ControlPersist=600 …` (see defaults)   | Custom `--rsh` for `ansible.posix.synchronize`. The module hard-codes `ssh -S none`, which disables ControlMaster for rsync; passing our own `--rsh` (rsync uses the last one it sees) re-enables socket reuse so N host aliases on one IP share one ssh connection. Inventory-supplied bits (`ansible_port`, `ansible_ssh_private_key_file`, `ansible_ssh_common_args`, `ansible_ssh_extra_args`) are appended after our baseline so they win on conflicts. |
| `force`             | `false`                                                              | Collection-wide force switch, read as `force \| default(false) \| bool`. When `true`, idempotence guards (`is changed`, `sources_changed`, …) are short-circuited so services restart, firewalld reloads, and compose redeploys happen unconditionally.                          |
| `hacode_output_dir` | `{{ playbook_dir }}/output`                                          | Controller-side root for artifacts written by roles (issued certs, kubeconfigs, generated wg-client configs, …). Set once in inventory to relocate everything in one go.                                                                                                         |
| `hacode_kube_configs_dir` | `{{ hacode_output_dir }}/kube-configs`                         | Shared kubeconfig drop-off. `hacode.infra.k3s` writes here by default, `hacode.infra.k8s_addons` reads from here by default — both roles share this single convention so adding `k8s_addons` to the same inventory group as `k3s` Just Works without per-role path plumbing.    |

## Usage

You typically don't include this role directly. It is pulled in automatically
via `dependencies` from other roles in the collection. Override any of the
variables above in inventory or playbook `vars:`.

```yaml
# inventory/group_vars/all.yml
hacode_output_dir: "/var/lib/hacode/artifacts"
force: false
```
