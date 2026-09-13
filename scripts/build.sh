#!/usr/bin/env bash
# Build the rootless DEB for Cooking GO 1.25.03 (must run on macOS with Xcode).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(awk '/^Version:/ {print $2}' "$ROOT/packaging/control")"
PKGID="$(awk '/^Package:/ {print $2}' "$ROOT/packaging/control")"
ARCH="$(awk '/^Architecture:/ {print $2}' "$ROOT/packaging/control")"
[[ -z "$VERSION" || -z "$PKGID" ]] && { echo "control file incomplete"; exit 1; }

BUILD="$ROOT/build"
PKG="$BUILD/pkg"
OUT="$ROOT/outputs"
DEB="$OUT/${PKGID}_${VERSION}_${ARCH}.deb"

echo "== version $VERSION / package $PKGID / arch $ARCH"

python3 "$ROOT/tools/embed_js.py"

SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
echo "== iOS SDK $SDK"

rm -rf "$BUILD"
mkdir -p "$PKG/DEBIAN" "$PKG/var/jb/usr/lib/TweakInject" "$OUT"

# Compile the tweak (arm64, rootless install name, no substrate link dependency).
xcrun --sdk iphoneos clang \
  -arch arm64 \
  -miphoneos-version-min=14.0 \
  -fobjc-arc \
  -fmodules \
  -O2 \
  -dynamiclib \
  -isysroot "$SDK" \
  -I"$ROOT/src" \
  -DCGM_VERSION=@"\"$VERSION\"" \
  -framework Foundation -framework UIKit -framework QuartzCore -framework CoreGraphics \
  -Wl,-undefined,dynamic_lookup \
  -Wl,-install_name,/var/jb/usr/lib/TweakInject/CookingGoMod.dylib \
  "$ROOT/src/CookingGoMod.m" \
  -o "$BUILD/CookingGoMod.dylib"

file "$BUILD/CookingGoMod.dylib"

# Sign so the dylib loads cleanly under ElleKit.
if command -v ldid >/dev/null 2>&1; then
  ldid -S "$BUILD/CookingGoMod.dylib"
  echo "== signed with ldid"
else
  echo "!! ldid not found (dylib left unsigned)"
fi

cp "$BUILD/CookingGoMod.dylib" "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.dylib"
cp "$ROOT/packaging/CookingGoMod.plist" "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.plist"
cp "$ROOT/packaging/CookingGoMod.cfg" "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.cfg"
if [[ -f "$ROOT/packaging/CookingGoMod.index12602.jsc" ]]; then
  cp "$ROOT/packaging/CookingGoMod.index12602.jsc" "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc"
fi
# control must end with a newline and use LF, or dpkg-deb refuses the package
{
  printf '%s' "$(cat "$ROOT/packaging/control")"
  printf '\n'
} > "$PKG/DEBIAN/control"
cp "$ROOT/packaging/postinst" "$PKG/DEBIAN/postinst"
cp "$ROOT/packaging/postrm" "$PKG/DEBIAN/postrm"
cp "$ROOT/src/CGMBootstrap.js" "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.bootstrap.js"
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
chmod 644 "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.bootstrap.js"
[[ -f "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc" ]] && chmod 644 "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc"
chmod 644 "$PKG/DEBIAN/control" "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.plist"
chmod 755 "$PKG/var/jb/usr/lib/TweakInject/CookingGoMod.dylib"

# Strip anything that would break install on a read-only root filesystem.
find "$PKG" \( -name '.DS_Store' -o -name '._*' -o -name '__MACOSX' -o -name '*.dSYM' \) -exec rm -rf {} + 2>/dev/null || true

dpkg-deb --root-owner-group -Zgzip -b "$PKG" "$DEB"
echo "== built $DEB"

bash "$ROOT/tools/verify_deb.sh" "$DEB"