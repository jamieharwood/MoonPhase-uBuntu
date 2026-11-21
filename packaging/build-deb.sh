#!/usr/bin/env bash
# Builds dist/moonphase-ubuntu_<version>_all.deb with dpkg-deb (no root needed).
# Install with:  sudo apt install ./dist/moonphase-ubuntu_<version>_all.deb
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ID=io.github.jamieharwood.MoonPhase
VERSION="$(python3 -c "import re,sys;print(re.search(r'__version__ = \"(.+?)\"', open('$ROOT/moonphase/__init__.py').read()).group(1))")"
PKG=moonphase-ubuntu
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

install -d "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/$PKG" \
  "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/scalable/apps" \
  "$STAGE/usr/share/metainfo" "$STAGE/usr/share/doc/$PKG"
cp -r "$ROOT/moonphase" "$STAGE/usr/share/$PKG/"
find "$STAGE" -name __pycache__ -prune -exec rm -rf {} +
install -m755 "$ROOT/moonphase-ubuntu" "$STAGE/usr/bin/$PKG"
install -m644 "$ROOT/data/$APP_ID.desktop" "$STAGE/usr/share/applications/"
install -m644 "$ROOT/data/$APP_ID.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/"
install -m644 "$ROOT/data/$APP_ID.metainfo.xml" "$STAGE/usr/share/metainfo/"
install -m644 "$ROOT/README.md" "$STAGE/usr/share/doc/$PKG/"

cat > "$STAGE/DEBIAN/control" <<CTRL
Package: $PKG
Version: $VERSION
Section: science
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, python3-cairo, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.4), gir1.2-graphene-1.0
Suggests: python3-pymongo
Maintainer: Jamie Harwood <noreply@github.com>
Homepage: https://github.com/jamieharwood/MoonPhase-uBuntu
Description: Moon phase and solar system dashboard for the GNOME desktop
 Native GTK4/libadwaita port of the MoonPhase web dashboard: moon phase,
 planet and deep-space probe distances, light travel times, Earth data,
 aurora Kp index, ISS/LEO data, people in space and a history chart
 (local SQLite or MongoDB).
CTRL
cat > "$STAGE/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
POST
cp "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/${PKG}_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT"
echo "Built $OUT"
