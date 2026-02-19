#!/usr/bin/env bash
set -euo pipefail

bin_dir="$HOME/.local/bin"
mkdir -p "$bin_dir"

wrapper="$bin_dir/p_man"
cat > "$wrapper" <<'EOF'
#!/usr/bin/env bash
powershell.exe -NoProfile -Command "p_man @args" "$@"
EOF
chmod +x "$wrapper"

profile="$HOME/.profile"
if ! grep -Fqs "$bin_dir" "$profile"; then
  {
    echo ""
    echo "# Photo Manager (p_man) WSL shim"
    echo "export PATH=\"$bin_dir:\$PATH\""
  } >> "$profile"
  echo "Added $bin_dir to PATH in $profile."
fi

echo "WSL shim installed. Ensure Windows p_man is installed and on PATH."
echo "Restart your shell to use p_man from WSL."
