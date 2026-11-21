#!/usr/bin/env bash
# Per-user install (no sudo): copies the app to ~/.local and registers the launcher.
#   ./install.sh            install / update
#   ./install.sh --uninstall
set -euo pipefail
APP_ID=io.github.jamieharwood.MoonPhase
SRC="$(cd "$(dirname "$0")" && pwd)"
SHARE="${XDG_DATA_HOME:-$HOME/.local/share}"
LIB="$SHARE/moonphase-ubuntu"
BIN="$HOME/.local/bin"

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -rf "$LIB" "$BIN/moonphase-ubuntu" "$SHARE/applications/$APP_ID.desktop" \
         "$SHARE/icons/hicolor/scalable/apps/$APP_ID.svg"
  update-desktop-database "$SHARE/applications" 2>/dev/null || true
  echo "MoonPhase removed. Settings and history remain in ~/.config/moonphase and ~/.local/share/moonphase."
  exit 0
fi

missing=()
for pkg in python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-cairo; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if ((${#missing[@]})); then
  echo "Missing packages: ${missing[*]}"
  echo "Install them with:  sudo apt install ${missing[*]}"
  exit 1
fi

mkdir -p "$LIB" "$BIN" "$SHARE/applications" "$SHARE/icons/hicolor/scalable/apps"
rm -rf "$LIB/moonphase"
cp -r "$SRC/moonphase" "$LIB/"
find "$LIB" -name __pycache__ -prune -exec rm -rf {} +
install -m755 "$SRC/moonphase-ubuntu" "$BIN/moonphase-ubuntu"
install -m644 "$SRC/data/$APP_ID.svg" "$SHARE/icons/hicolor/scalable/apps/$APP_ID.svg"
sed "s|^Exec=.*|Exec=$BIN/moonphase-ubuntu|" "$SRC/data/$APP_ID.desktop" > "$SHARE/applications/$APP_ID.desktop"
update-desktop-database "$SHARE/applications" 2>/dev/null || true
gtk-update-icon-cache -q -t "$SHARE/icons/hicolor" 2>/dev/null || true
echo "Installed. Launch 'MoonPhase' from the app grid, or run: $BIN/moonphase-ubuntu"
