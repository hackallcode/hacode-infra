### Params

ONE_LINE=false
SHOW_VENV=true
SHOW_KUBE=true

### Segment drawing
# A few utility functions to make it easy and re-usable to draw segmented prompts

FIRST_SEGMENT=true
JOBS_COUNT=0
TIMER_START=''
ELAPSED=''

# Begin a segment
# Takes two arguments, background and foreground. Both can be omitted,
# rendering default background/foreground.
prompt_segment() {
  if [[ -z $4 ]] && [[ "$FIRST_SEGMENT" != "true" ]]; then
    echo -n " "
  fi
  FIRST_SEGMENT=false

  local bg fg
  [[ -n $1 ]] && bg="%K{$1}" || bg="%k"
  [[ -n $2 ]] && fg="%F{$2}" || fg="%f"
  echo -n "%{$bg%}%{$fg%}"

  [[ -n $3 ]] && echo -n $3
}

# End the prompt, closing any open segments
prompt_end() {
  echo -n "%{%k%}%{%f%} "
}

prompt_bold() {
    echo -n "%{%B%}"
}

prompt_unbold() {
    echo -n "%{%b%}"
}

### Prompt components
# Each component will draw itself, and hide itself if no information needs to be shown

# Context: user@hostname (who am I and where am I)
prompt_context() {
  local is_remote=0
  if [[ -n "$SSH_CLIENT" ]] || (who am i | grep -q '([0-9]'); then
    is_remote=1
  fi

  if [[ "$USERNAME" != "$DEFAULT_USER" ]] || (( is_remote )); then
    [[ $UID -eq 0 ]] && uc='red' || uc=''
    (( is_remote )) && hc='magenta' || hc=''
    prompt_segment '' "$uc" "%n"
    prompt_segment '' "$hc" "@%m" true
  fi
}

# Git: branch/detached head, dirty status
prompt_git() {
  (( $+commands[git] )) || return
  if [[ "$(command git config --get oh-my-zsh.hide-status 2>/dev/null)" = 1 ]]; then
    return
  fi

  local PL_BRANCH_CHAR='\u2022'

  local ahead behind
  ahead=$(command git log --oneline @{upstream}.. 2>/dev/null)
  behind=$(command git log --oneline ..@{upstream} 2>/dev/null)
  if [[ -n "$ahead" ]] && [[ -n "$behind" ]]; then
    PL_BRANCH_CHAR='\u21c5'
  elif [[ -n "$ahead" ]]; then
    PL_BRANCH_CHAR='\u2191'
  elif [[ -n "$behind" ]]; then
    PL_BRANCH_CHAR='\u2193'
  fi

  local ref dirty mode repo_path

   if [[ "$(command git rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ]]; then
    repo_path=$(command git rev-parse --git-dir 2>/dev/null)
    dirty=$(parse_git_dirty)
    ref=$(command git symbolic-ref HEAD 2> /dev/null) || \
    ref=$(command git describe --exact-match --tags HEAD 2> /dev/null) || \
    ref=$(command git rev-parse --short HEAD 2> /dev/null)
    if [[ -n $dirty ]]; then
      prompt_segment '' yellow
    else
      prompt_segment '' green
    fi

    if [[ -e "${repo_path}/BISECT_LOG" ]]; then
      mode='\u21C4'
    elif [[ -e "${repo_path}/MERGE_HEAD" ]]; then
      mode='\u21B0'
    elif [[ -e "${repo_path}/rebase" || -e "${repo_path}/rebase-apply" || -e "${repo_path}/rebase-merge" || -e "${repo_path}/../.dotest" ]]; then
      mode='\u21B6'
    fi

    setopt promptsubst
    autoload -Uz vcs_info

    zstyle ':vcs_info:*' enable git
    zstyle ':vcs_info:*' get-revision true
    zstyle ':vcs_info:*' check-for-changes true
    zstyle ':vcs_info:*' stagedstr '+'
    zstyle ':vcs_info:*' unstagedstr '±'
    zstyle ':vcs_info:*' formats ' %c%u'
    zstyle ':vcs_info:*' actionformats ' %c%u'
    vcs_info
    echo -n "${mode:-${PL_BRANCH_CHAR}} ${${ref:gs/%/%%}/refs\/heads\//}${vcs_info_msg_0_%% }"
  fi
}

prompt_bzr() {
  (( $+commands[bzr] )) || return

  # Test if bzr repository in directory hierarchy
  local dir="$PWD"
  while [[ ! -d "$dir/.bzr" ]]; do
    [[ "$dir" = "/" ]] && return
    dir="${dir:h}"
  done

  local bzr_status status_mod status_all revision
  if bzr_status=$(command bzr status 2>&1); then
    status_mod=$(echo -n "$bzr_status" | head -n1 | grep "modified" | wc -m)
    status_all=$(echo -n "$bzr_status" | head -n1 | wc -m)
    revision=${$(command bzr log -r-1 --log-format line | cut -d: -f1):gs/%/%%}
    if [[ $status_mod -gt 0 ]] ; then
      prompt_segment '' yellow "bzr@$revision ✚"
    else
      if [[ $status_all -gt 0 ]] ; then
        prompt_segment '' yellow "bzr@$revision"
      else
        prompt_segment '' green "bzr@$revision"
      fi
    fi
  fi
}

prompt_hg() {
  (( $+commands[hg] )) || return
  local rev st branch
  if $(command hg id >/dev/null 2>&1); then
    if $(command hg prompt >/dev/null 2>&1); then
      if [[ $(command hg prompt "{status|unknown}") = "?" ]]; then
        # if files are not added
        prompt_segment '' red
        st='±'
      elif [[ -n $(command hg prompt "{status|modified}") ]]; then
        # if any modification
        prompt_segment '' yellow
        st='±'
      else
        # if working copy is clean
        prompt_segment '' green
      fi
      echo -n ${$(command hg prompt "☿ {rev}@{branch}"):gs/%/%%} $st
    else
      st=""
      rev=$(command hg id -n 2>/dev/null | sed 's/[^-0-9]//g')
      branch=$(command hg id -b 2>/dev/null)
      if command hg st | command grep -q "^\?"; then
        prompt_segment '' red
        st='±'
      elif command hg st | command grep -q "^[MA]"; then
        prompt_segment '' yellow
        st='±'
      else
        prompt_segment '' green
      fi
      echo -n "☿ ${rev:gs/%/%%}@${branch:gs/%/%%}" $st
    fi
  fi
}

# Dir: current working directory
prompt_dir() {
  prompt_segment '' blue '%~'
}

# Virtualenv: current working virtualenv
prompt_virtualenv() {
  if [[ -n "$VIRTUAL_ENV" && -n "$VIRTUAL_ENV_DISABLE_PROMPT" ]]; then
    prompt_segment '' '' "(${VIRTUAL_ENV:t:gs/%/%%})"
  fi
}

# Status:
# - was there an error
# - am I root
# - are there background jobs?
prompt_status() {
  local -a symbols

  [[ $RETVAL -eq 0 ]] && symbols+="%{%F{green}%}✔%{%f%}"
  [[ $RETVAL -ne 0 ]] && symbols+="%{%F{red}%}✘ $RETVAL%{%f%}"

  [[ -n "$symbols" ]] && prompt_segment '' '' "$symbols"
}

#AWS Profile:
# - display current AWS_PROFILE name
# - displays yellow on red if profile name contains 'production' or
#   ends in '-prod'
# - displays black on green otherwise
prompt_aws() {
  [[ -z "$AWS_PROFILE" || "$SHOW_AWS_PROMPT" = false ]] && return
  case "$AWS_PROFILE" in
    *-prod|*production*) prompt_segment '' red  "λ ${AWS_PROFILE:gs/%/%%}" ;;
    *) prompt_segment '' cyan "λ ${AWS_PROFILE:gs/%/%%}" ;;
  esac
}

# Kubernetes:
# - reads current-context directly from KUBECONFIG (or ~/.kube/config) without
#   shelling out to kubectl, so prompt stays fast
# - red for *-prod / *production*, cyan otherwise
prompt_kube() {
  [[ "$SHOW_KUBE" == false ]] && return

  local cfgs cfg ctx
  cfgs="${KUBECONFIG:-$HOME/.kube/config}"
  for cfg in ${(s.:.)cfgs}; do
    [[ -f "$cfg" ]] || continue
    ctx=$(awk -F': *' '/^current-context:/ {gsub(/[\"\047]/,"",$2); print $2; exit}' "$cfg" 2>/dev/null)
    [[ -n "$ctx" ]] && break
  done
  [[ -z "$ctx" ]] && return

  case "$ctx" in
    *-prod|*production*) prompt_segment '' red  "⎈ ${ctx:gs/%/%%}" ;;
    *) prompt_segment '' cyan "⎈ ${ctx:gs/%/%%}" ;;
  esac
}

timer_start() {
  TIMER_START=${EPOCHREALTIME%.*}
  ELAPSED=''
}

timer_stop() {
  local elapsed
  if [[ -n $TIMER_START ]]; then
    local end_time=${EPOCHREALTIME%.*}
    elapsed=$((end_time - TIMER_START))
  else
    elapsed=0
  fi

  local hours=$((elapsed / 3600))
  local minutes=$(((elapsed % 3600) / 60))
  local seconds=$((elapsed % 60))

  TIMER_START=''
  ELAPSED=""
  (( hours > 0 )) && ELAPSED+="${hours}h "
  (( minutes > 0 )) && ELAPSED+="${minutes}m "
  ELAPSED+="${seconds}s"
}

prompt_time() {
  [[ -n "$ELAPSED" ]] && prompt_segment '' '' "$ELAPSED"
}

### Main

build_extra_prompt() {
  RETVAL=$?
  prompt_status
  prompt_time
  if [[ "${SHOW_VENV}" == true ]]; then
    prompt_virtualenv
  fi
  prompt_aws
  prompt_kube
  prompt_git
  prompt_bzr
  prompt_hg
  prompt_end
}

build_main_prompt() {
  RETVAL=$?
  prompt_bold
  prompt_context
  prompt_dir
  prompt_unbold
  prompt_end
  echo -n '$ '
}

preexec_functions+=(timer_start)
precmd_functions+=(timer_stop)

if [[ "${ONE_LINE}" == true ]]; then
  PROMPT='%{%f%b%k%}$(build_extra_prompt)$(build_main_prompt)'
else
  PROMPT='%{%f%b%k%}$(build_extra_prompt)
$(build_main_prompt)'
fi
