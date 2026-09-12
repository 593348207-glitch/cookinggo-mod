#!/usr/bin/env bash
# Structural self-check for the rootless DEB (read-only root filesystem safety).
set -euo pipefail
DEB="${1:?usage: verify_deb.sh <deb>}"
fail=0

echo "== control fields"
dpkg-deb -f "$DEB"

ARCH="$(dpkg-deb -f "$DEB" Architecture)"
[[ "$ARCH" == "iphoneos-arm64" ]] || { echo "!! bad Architecture: $ARCH"; fail=1; }

echo "== top level entries"
TOPS="$(dpkg-deb -c "$DEB" | awk '{print $6}' | sed 's|^\./||' | cut -d/ -f1 | sort -u | tr '\n' ' ')"
echo "   $TOPS"
for t in $TOPS; do
  case "$t" in
    var|DEBIAN|.) ;;
    *) echo "!! unexpected top level entry: $t"; fail=1 ;;
  esac
done

echo "== payload files"
dpkg-deb -c "$DEB" | awk '{print $6}' | sed 's|^\./||' | grep -v '^\.$' || true

echo "== junk scan"
if dpkg-deb -c "$DEB" | grep -E '\.DS_Store|__MACOSX|/\._|\.dSYM' ; then
  echo "!! junk files present"; fail=1
else
  echo "   clean"
fi

echo "== required payload"
for want in var/jb/usr/lib/TweakInject/CookingGoMod.dylib var/jb/usr/lib/TweakInject/CookingGoMod.plist DEBIAN/control; do
  if ! dpkg-deb -c "$DEB" | awk '{print $6}' | sed 's|^\./||' | grep -qx "$want"; then
    echo "!! missing $want"; fail=1
  fi
done

if [[ $fail -ne 0 ]]; then echo "VERIFY FAILED"; exit 1; fi
echo "VERIFY OK"