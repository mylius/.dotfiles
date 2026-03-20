# Basic environment setup
export PATH="/usr/local/opt/libpq/bin:$PATH"
export PATH="$PATH:/home/zufall/.zig/zig-linux-x86_64-0.14.0-dev.349+e82f7d380"
export PATH="$HOME/.cargo/bin:$PATH"
export PATH="$HOME/.local/bin:$PATH"
export PATH="/opt/local/bin:$PATH"
if command -v go >/dev/null 2>&1; then
    export PATH="$PATH:$(go env GOPATH)/bin"
fi

for conda_root in "$HOME/miniforge3" "$HOME/miniconda3"; do
    if [ -d "$conda_root/bin" ]; then
        export PATH="$conda_root/bin:$PATH"
        break
    fi
done

# pnpm configuration
export PNPM_HOME="/Users/mylius/Library/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME:"*) ;;
  *) export PATH="$PNPM_HOME:$PATH" ;;
esac

# Your custom functions
function git_clean_up(){
    git fetch -p
    for branch in $(git branch -vv | grep ': gone]' | awk '{print $1}');
    do 
        git branch -D $branch;
    done
}

figlet() {
    echo
    echo
    command figlet -w $(tput cols) -c "$@"
    echo
    echo
}

retro() {
    (echo;echo;echo; echo "HARIvederci"; echo; echo "See ✌️you!"; echo; echo;) | figlet -f 3D | dotacat
}

# Conda initialization
CONDA_ROOT=""
for candidate in "$HOME/miniforge3" "$HOME/miniconda3"; do
    if [ -x "$candidate/bin/conda" ]; then
        CONDA_ROOT="$candidate"
        break
    fi
done

if [ -n "$CONDA_ROOT" ]; then
    __conda_setup="$("$CONDA_ROOT/bin/conda" 'shell.zsh' 'hook' 2> /dev/null)"
    if [ $? -eq 0 ]; then
        eval "$__conda_setup"
    else
        if [ -f "$CONDA_ROOT/etc/profile.d/conda.sh" ]; then
            . "$CONDA_ROOT/etc/profile.d/conda.sh"
        else
            export PATH="$CONDA_ROOT/bin:$PATH"
        fi
    fi
fi
unset __conda_setup CONDA_ROOT

# Deno configuration
if [ -f "$HOME/.deno/env" ]; then
    . "$HOME/.deno/env"
fi

# Initialize zoxide
if command -v zoxide >/dev/null 2>&1; then
    eval "$(zoxide init zsh)"
fi

alias lg='lazygit'

if command -v atuin >/dev/null 2>&1; then
    eval "$(atuin init zsh)"
fi

if [ -f "$HOME/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh" ]; then
    source "$HOME/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh"
fi

if [ -f "$HOME/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]; then
    source "$HOME/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
fi

killport() {
    if [ -z "$1" ]; then
        echo "Usage: killport <port>"
        return 1
    fi
    local pids
    pids=$(lsof -ti :"$1" 2>/dev/null)
    if [ -z "$pids" ]; then
        echo "No processes found on port $1"
        return 0
    fi
    echo "$pids" | xargs kill -9
    echo "Killed processes on port $1: $pids"
}

# Initialize starship (this must be at the end of the file)
if command -v starship >/dev/null 2>&1; then
    eval "$(starship init zsh)"
fi

# Infinite and timestamped zsh history configuration
export HISTSIZE=1000000
export SAVEHIST=1000000
export HISTFILE=$HOME/.config/zsh/history
setopt APPEND_HISTORY
setopt INC_APPEND_HISTORY
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_REDUCE_BLANKS

. "$HOME/.atuin/bin/env"
