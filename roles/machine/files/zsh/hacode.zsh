# Hacode theme plugin - aliases & functions paired with the theme.
# Installed as $ZSH_CUSTOM/hacode.zsh (auto-loaded by oh-my-zsh).
# Framework-owned: re-running the installer overwrites this file.
# Put personal aliases in ~/.aliases and exports in ~/.exports.

# Fallback defaults - kept in sync with the exports template.
: "${SOURCES_DIR:=$HOME/sources}"
: "${VENV_DIR:=$HOME/.venv}"

# --- Help ---

# Print summary of all theme commands.
hacode-help() {
    cat <<'EOF'
Hackallcode shell helpers:

Misc:
  hacode-help           print this help
  ssh-add-apple [key]   ssh-add --apple-use-keychain (macOS)
  g-rm [args]           git rebase master: fetch + rebase onto origin's default branch (args go to `git rebase`)
  g-bc                  git branch cleanup: delete locals whose upstream is gone
  g-aliases             install handy git aliases (co, ci, st, br, hist, type, dump, wdiff) into global git config

Python environments:
  mkv <name>            make venv: create venv at $VENV_DIR/<name> and activate it
  swv <name>            switch venv: activate $VENV_DIR/<name>
  rmv <name>            remove venv: delete $VENV_DIR/<name> (deactivates first if active)

Projects:
  mks <name>            make sources: mkdir $SOURCES_DIR/<name>
  sws <name>            switch sources: cd $SOURCES_DIR/<name> + swv <name>

Kubernetes:
  swk <name>            switch k8s: switch KUBECONFIG to ~/.kube/<name>

Multi-workspace:
  sw-make <prefix> <SOURCES_DIR> <VENV_DIR>
                        generate <prefix>{mks,sws,mkv,swv,rmv} commands bound to those dirs
EOF
}

# --- Utilities ---

if [[ "$OSTYPE" == darwin* ]]; then
    # Add SSH key to Apple's keychain so passphrase is remembered across reboots.
    ssh-add-apple() {
        ssh-add --apple-use-keychain "${1:-${HOME}/.ssh/id_rsa}"
    }
fi

# Rebase current branch onto origin's default branch (main/master/...).
# Extra args are forwarded to `git rebase` (e.g. `g-rm -i`).
g-rm() {
    local branch
    git fetch || return $?
    branch="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')"
    if [ -z "$branch" ]; then
        # origin/HEAD not set locally - ask the remote and retry.
        git remote set-head origin --auto >/dev/null 2>&1
        branch="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')"
    fi
    if [ -z "$branch" ]; then
        echo "g-rm: could not determine origin's default branch" >&2
        return 1
    fi
    git rebase "origin/${branch}" "$@"
}

# Prune remote-tracking branches, then delete local branches whose upstream is gone.
alias g-bc='git fetch -p && git branch -vv | awk "/: gone]/ {print \$1}" | xargs -r git branch -D'

# Install handy git aliases into the global git config.
g-aliases() {
    git config --global alias.co checkout
    git config --global alias.ci commit
    git config --global alias.st status
    git config --global alias.br branch
    git config --global alias.hist "log --pretty=format:'%h %ad | %s%d [%an]' --graph --date=short"
    git config --global alias.type 'cat-file -t'
    git config --global alias.dump 'cat-file -p'
    git config --global alias.wdiff 'diff --word-diff=color --unified=1'
    echo "Git aliases installed: co, ci, st, br, hist, type, dump, wdiff"
}

# Docker CLI completions (Docker Desktop installs them here).
if [ -d "${HOME}/.docker/completions" ]; then
    fpath=("${HOME}/.docker/completions" $fpath)
    autoload -Uz compinit && compinit
fi

# --- Projects & venvs ---

# Generate prefix variants of sws/swv/mks/mkv/rmv bound to a specific workspace.
# Each wrapper exports SOURCES_DIR/VENV_DIR (persists after the call) and runs
# the base command. Completion is reused from the unprefixed versions.
#   sw-make w "$HOME/Workspace/sources" "$HOME/Workspace/venv"  ->  wsws / wswv / wmks / wmkv / wrmv
sw-make() {
    if [ $# -lt 3 ]; then
        echo "usage: sw-make <prefix> <sources_dir> <venv_dir>" >&2
        echo "  generates <prefix>{sws,swv,mks,mkv,rmv} wrappers" >&2
        return 1
    fi
    local prefix="$1" src="$2" venv="$3" cmd
    for cmd in sws swv mks mkv rmv; do
        eval "${prefix}${cmd}() { export SOURCES_DIR='${src}' VENV_DIR='${venv}'; ${cmd} \"\$@\"; }"
    done
    # Per-prefix completion functions with hardcoded dirs (so tab-suggestions
    # don't depend on the current SOURCES_DIR/VENV_DIR).
    eval "_${prefix}sws() { _path_files -W '${src}' -/ }"
    eval "_${prefix}swv() {
        if [[ -n \"\${VIRTUAL_ENV-}\" && \"\${VIRTUAL_ENV}/\" == '${venv%/}/'*/ ]]; then
            compadd -- \"\${VIRTUAL_ENV#${venv%/}/}\"
        fi
        _path_files -W '${venv}' -/
    }"
    compdef "_${prefix}sws" "${prefix}sws"
    compdef "_${prefix}sws" "${prefix}mkv"
    compdef "_${prefix}swv" "${prefix}swv"
    compdef "_${prefix}swv" "${prefix}rmv"
}

# Create a new project directory.
mks() {
    if [ $# -eq 0 ]; then
        echo "usage: mks <name>   - mkdir \$SOURCES_DIR/<name>" >&2
        return 1
    fi
    mkdir -p "${SOURCES_DIR}/${1}"
}

# Create a new venv, upgrade pip inside it, and activate it.
# Completion suggests project paths under $SOURCES_DIR so you can mkv test/sub/myproj.
mkv() {
    if [ $# -eq 0 ]; then
        echo "usage: mkv <name>   - create venv at \$VENV_DIR/<name> and activate it" >&2
        return 1
    fi
    mkdir -p "$(dirname "${VENV_DIR}/${1}")" && \
        python -m venv "${VENV_DIR}/${1}" && \
        "${VENV_DIR}/${1}/bin/python" -m pip install --upgrade pip && \
        swv "$1"
}
_mkv() {
    if [[ "$PWD/" == "${SOURCES_DIR%/}/"*/ ]]; then
        compadd -- "${PWD#${SOURCES_DIR%/}/}"
    fi
    _path_files -W "${SOURCES_DIR}" -/
}
compdef _mkv mkv

# Remove a venv by name. Deactivates first if the venv being removed is active.
rmv() {
    if [ $# -eq 0 ]; then
        echo "usage: rmv <name>   - delete \$VENV_DIR/<name>" >&2
        return 1
    fi
    local target="${VENV_DIR}/${1}"
    if [ ! -d "${target}" ]; then
        echo "rmv: no venv at ${target}" >&2
        return 1
    fi
    if [ -n "${VIRTUAL_ENV-}" ] && [ "${VIRTUAL_ENV}" = "${target}" ]; then
        deactivate
    fi
    rm -rf "${target}"
}

# Activate a venv by name.
swv() {
    if [ $# -eq 0 ]; then
        echo "usage: swv <name>   - activate \$VENV_DIR/<name>" >&2
        return 1
    fi
    [ -n "${VIRTUAL_ENV-}" ] && deactivate
    [ -f "${VENV_DIR}/${1}/bin/activate" ] && source "${VENV_DIR}/${1}/bin/activate"
}
_swv() {
    if [[ -n "${VIRTUAL_ENV-}" && "${VIRTUAL_ENV}/" == "${VENV_DIR%/}/"*/ ]]; then
        compadd -- "${VIRTUAL_ENV#${VENV_DIR%/}/}"
    fi
    _path_files -W "${VENV_DIR}" -/
}
compdef _swv swv
compdef _swv rmv

# Switch to project <name>: deactivate current venv, cd, activate matching venv if present.
sws() {
    if [ $# -eq 0 ]; then
        echo "usage: sws <name>   - cd \$SOURCES_DIR/<name> and activate matching venv" >&2
        return 1
    fi
    cd "${SOURCES_DIR}/${1}" || return $?
    [ -f "${VENV_DIR}/${1}/bin/activate" ] && swv "$1"
    return 0
}
_sws() {
    _path_files -W "${SOURCES_DIR}" -/
}
compdef _sws sws

# Switch kubectl context by selecting a kubeconfig file from ~/.kube/.
# Usage: swk <name> - switch KUBECONFIG to ~/.kube/<name>[.yml|.yaml|.kubeconfig]
swk() {
    if [ $# -eq 0 ]; then
        echo "usage: swk <name>   - switch KUBECONFIG to ~/.kube/<name>" >&2
        return 1
    fi

    local kube_dir="${HOME}/.kube"
    local candidates=(
        "${kube_dir}/${1}.yml"
        "${kube_dir}/${1}.yaml"
        "${kube_dir}/${1}.kubeconfig"
        "${kube_dir}/${1}"
    )
    local c
    for c in "${candidates[@]}"; do
        if [ -f "$c" ]; then
            export KUBECONFIG="$c"
            return 0
        fi
    done

    echo "swk: no kubeconfig for '${1}' in ${kube_dir}" >&2
    return 1
}
_swk() {
    setopt local_options null_glob
    local -a names
    local f
    for f in "${HOME}/.kube"/*.yml "${HOME}/.kube"/*.yaml "${HOME}/.kube"/*.kubeconfig; do
        names+=("${${f##*/}%.*}")
    done
    compadd "${names[@]}"
}
compdef _swk swk
