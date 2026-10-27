# Basic environment setup. ~/.config/env detects the machine profile and
# workspace root and exports WORKSPACE_ROOT, DOTFILES_PROFILE, and the XDG dirs.
source "$HOME/.zsh_profile"
if [[ "$OSTYPE" == darwin* ]]; then
    export PATH="/usr/local/opt/libpq/bin:/opt/local/bin:$PATH"
fi
export PATH="$HOME/.cargo/bin:$PATH"
export PATH="$HOME/go/bin:$PATH"  # Static GOPATH instead of $(go env GOPATH)

for conda_root in "$HOME/miniforge3" "$HOME/miniconda3"; do
    if [ -d "$conda_root/bin" ]; then
        export PATH="$conda_root/bin:$PATH"
        export CONDA_ROOT="$conda_root"
        break
    fi
done

# pnpm configuration
if [[ "$OSTYPE" == darwin* ]]; then
    export PNPM_HOME="$HOME/Library/pnpm"
    case ":$PATH:" in
      *":$PNPM_HOME:"*) ;;
      *) export PATH="$PNPM_HOME:$PATH" ;;
    esac
fi

# Cache directory for shell init scripts
ZSH_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/zsh"
ZSH_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/zsh"
mkdir -p "$ZSH_CACHE_DIR" "$ZSH_STATE_DIR"
export ZSH_COMPDUMP="$ZSH_CACHE_DIR/zcompdump-$HOST-$ZSH_VERSION"

# Helper: cache and source init scripts (regenerate if binary is newer than cache)
_cache_init() {
    local name="$1"
    local cmd="$2"
    local cache="$ZSH_CACHE_DIR/$name.zsh"
    local bin_path="$(command -v "${cmd%% *}" 2>/dev/null)"
    if [[ -n "$bin_path" ]]; then
        if [[ ! -f "$cache" || "$bin_path" -nt "$cache" ]]; then
            eval "$cmd" > "$cache" 2>/dev/null
        fi
        source "$cache"
    fi
}

# Lazy load conda (only init when 'conda' is first called)
conda() {
    unfunction conda 2>/dev/null
    if [[ -n "$CONDA_ROOT" ]]; then
        __conda_setup="$("$CONDA_ROOT/bin/conda" 'shell.zsh' 'hook' 2>/dev/null)"
        if [[ $? -eq 0 ]]; then
            eval "$__conda_setup"
        elif [[ -f "$CONDA_ROOT/etc/profile.d/conda.sh" ]]; then
            . "$CONDA_ROOT/etc/profile.d/conda.sh"
        fi
        unset __conda_setup
    fi
    conda "$@"
}

# Lazy load NVM. node/npm/npx come from PATH (~/.zshenv), so agent shell
# snapshots never capture wrappers that depend on an uncaptured helper.
export NVM_DIR="$HOME/.nvm"
if ! command -v node >/dev/null 2>&1; then
    _nvm_bins=("$NVM_DIR"/versions/node/v*/bin(N/nOn))
    (( $#_nvm_bins )) && export PATH="$_nvm_bins[1]:$PATH"
    unset _nvm_bins
fi
nvm() {
    unfunction nvm 2>/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    nvm "$@"
}

# Deno configuration
if [ -f "$HOME/.deno/env" ]; then
    . "$HOME/.deno/env"
fi

# Initialize tools with caching
export _ZO_EXCLUDE_DIRS="$WORKSPACE_ROOT/wt:$WORKSPACE_ROOT/wt/*:$WORKSPACE_ROOT/wt/*/*"
_cache_init "zoxide" "zoxide init zsh"
_cache_init "wt" "wt config shell --shell zsh"
_cache_init "sesh" "sesh completion zsh"
_cache_init "atuin" "atuin init zsh"
_cache_init "starship" "starship init zsh"

# Source atuin env if exists
[[ -f "$HOME/.atuin/bin/env" ]] && . "$HOME/.atuin/bin/env"

# Plugins (direct source is fast)
[[ -f "$HOME/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh" ]] && \
    source "$HOME/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh"
[[ -f "$HOME/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]] && \
    source "$HOME/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"

# Aliases
alias lg='lazygit'

# Custom functions
function git_clean_up(){
    git fetch -p
    for branch in $(git branch -vv | grep ': gone]' | awk '{print $1}'); do
        git branch -D $branch
    done
}

figlet() {
    echo; echo
    command figlet -w $(tput cols) -c "$@"
    echo; echo
}

retro() {
    (echo;echo;echo; echo "HARIvederci"; echo; echo "See ✌️you!"; echo;) | figlet -f 3D | dotacat
}

killport() {
    if [ -z "$1" ]; then
        echo "Usage: killport <port>"
        return 1
    fi
    local pids=$(lsof -ti :"$1" 2>/dev/null)
    if [ -z "$pids" ]; then
        echo "No processes found on port $1"
        return 0
    fi
    echo "$pids" | xargs kill -9
    echo "Killed processes on port $1: $pids"
}

# History configuration
export HISTSIZE=1000000
export SAVEHIST=1000000
export HISTFILE="$ZSH_STATE_DIR/history"
setopt APPEND_HISTORY INC_APPEND_HISTORY HIST_IGNORE_ALL_DUPS HIST_REDUCE_BLANKS

if command -v wt >/dev/null 2>&1; then eval "$(command wt config shell init zsh)"; fi

# bun completions
[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

if [[ $WORKSPACE_ROOT == $HOME ]]; then
    # Directories the tskr daemon may run sandboxed tasks in.
    export TSKR_ROOTS="$HOME/.t3/worktrees:$HOME/projects:/tmp"
fi

# OpenClaw completion
[ -s "$HOME/.openclaw/completions/openclaw.zsh" ] && source "$HOME/.openclaw/completions/openclaw.zsh"

# herdr session switch supervisor
herdr() {
    "$HOME/.local/bin/herdr-switch" "$@"
}
