#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

bin_path="$repo_root/.venv/bin"
profile="$HOME/.profile"

if ! grep -Fqs "$bin_path" "$profile"; then
  {
    echo ""
    echo "# Photo Manager (p_man)"
    echo "export PATH=\"$bin_path:\$PATH\""
  } >> "$profile"
  echo "Added $bin_path to PATH in $profile."
fi

echo "Installation complete. Restart your shell to use p_man."
