# Basic environment setup
export PATH="/usr/local/opt/libpq/bin:$PATH"
export PATH=~/miniconda3/bin:$PATH
export PATH="$PATH:/home/zufall/.zig/zig-linux-x86_64-0.14.0-dev.349+e82f7d380"
export PATH="$HOME/.cargo/bin:$PATH"
export PATH="/opt/local/bin:$PATH"
export PATH=$PATH:$(go env GOPATH)/bin

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
__conda_setup="$('/Users/mylius/miniconda3/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/Users/mylius/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/Users/mylius/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/Users/mylius/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup

# Deno configuration
. "/Users/mylius/.deno/env"

# Initialize zoxide
eval "$(zoxide init zsh)"

# Initialize starship (this must be at the end of the file)
eval "$(starship init zsh)"
