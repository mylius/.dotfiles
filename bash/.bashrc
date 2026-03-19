export VIM="nvim"

if [ -f "$HOME/.config/env" ]; then
  # shellcheck disable=SC1090
  source "$HOME/.config/env"
fi

addToPathFront "$HOME/.local/bin"
export PATH="$HOME/.cargo/bin:$PATH"

alias lg='lazygit'

if [ -f "$HOME/.bash-preexec.sh" ]; then
  # shellcheck disable=SC1090
  source "$HOME/.bash-preexec.sh"
fi

if command -v atuin >/dev/null 2>&1; then
  eval "$(atuin init bash)"
fi

if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init bash)"
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

if command -v starship >/dev/null 2>&1; then
  eval "$(starship init bash)"
fi

case $- in
  *i*) bind -x '"\C-f":"tmux-sessionizer"' ;;
esac
