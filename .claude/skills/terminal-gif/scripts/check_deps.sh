#!/usr/bin/env bash
# Check for VHS and its dependencies, and print OS-appropriate install commands
# for anything missing. Does NOT install anything — the caller must ask the user
# for permission first.

set -u

os="$(uname -s)"
missing=()

check() {
  if command -v "$1" >/dev/null 2>&1; then
    printf '  ok   %-8s %s\n' "$1" "$(command -v "$1")"
  else
    printf '  MISS %-8s not found on PATH\n' "$1"
    missing+=("$1")
  fi
}

echo "Checking VHS dependencies (os: $os)"
check vhs
check ttyd
check ffmpeg

if [ ${#missing[@]} -eq 0 ]; then
  echo
  echo "All dependencies present. Ready to render."
  exit 0
fi

echo
echo "Missing: ${missing[*]}"
echo "Suggested install command(s) for this OS — ASK THE USER before running:"
echo

case "$os" in
  Darwin)
    echo "  brew install ${missing[*]}"
    ;;
  Linux)
    echo "  # VHS (Charm apt repo):"
    echo "  sudo mkdir -p /etc/apt/keyrings"
    echo "  curl -fsSL https://repo.charm.sh/apt/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/charm.gpg"
    echo "  echo \"deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *\" | sudo tee /etc/apt/sources.list.d/charm.list"
    echo "  sudo apt update && sudo apt install ${missing[*]}"
    echo
    echo "  # Or, if Homebrew is available on Linux:"
    echo "  brew install ${missing[*]}"
    ;;
  *)
    echo "  Unknown OS. See https://github.com/charmbracelet/vhs#installation"
    ;;
esac

exit 1
