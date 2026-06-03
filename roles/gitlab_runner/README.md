# hacode.infra.gitlab_runner

Install, register and manage a Docker-based GitLab Runner.

## Tasks

- `install` (default): install gitlab-runner package and start service.
- `register` / `unregister`: register with a GitLab instance.
- `start` / `stop` / `restart`: service control.
- `uninstall`: remove the runner.

## Variables

See `defaults/main.yml` - typically `gitlab_runner_url`, `gitlab_runner_token`, `gitlab_runner_image`, `gitlab_runner_executor`.

## Example

```yaml
- hosts: "runners"
  become: true
  roles:
    - role: "hacode.infra.gitlab_runner"
      vars:
        gitlab_runner_url: "https://gitlab.example.com/"
        gitlab_runner_token: "{{ vault_runner_token }}"
```
