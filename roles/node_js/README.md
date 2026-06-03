# hacode.infra.node_js

Install Node.js via NodeSource and run a build command in a project directory.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `node_js_version` | `"12"` | major version installed via NodeSource setup script |
| `node_js_build_command` | `["npm", "run", "build"]` | command executed in the project dir |

## Example

```yaml
- hosts: "build"
  become: true
  roles:
    - role: "hacode.infra.node_js"
      vars:
        node_js_version: "20"
        node_js_build_command: ["pnpm", "build"]
```
