#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  tools/resign_ipa_recursive.sh --ipa INPUT.ipa --identity "Apple Development: ..." --out OUTPUT.ipa [--provision embedded.mobileprovision] [--entitlements entitlements.plist]

Purpose:
  Rebuild an IPA with a consistent signing identity across the main executable,
  embedded frameworks, app extensions, dylibs, and the .app bundle. This fixes
  dyld / Library Validation failures caused by mixed or stripped signatures.

Requirements:
  macOS with Xcode command-line tools, /usr/bin/codesign, /usr/bin/security,
  /usr/bin/plutil, /usr/bin/zip, /usr/bin/unzip.

Examples:
  security find-identity -v -p codesigning
  tools/resign_ipa_recursive.sh \
    --ipa "F:/测试/cookingGO/Cooking Go_1.26.02.ipa" \
    --identity "Apple Development: Your Name (TEAMID)" \
    --provision ./embedded.mobileprovision \
    --out ./CookingGo_1.26.02.resigned.ipa
USAGE
}

IPA=""
IDENTITY=""
OUT=""
PROVISION=""
ENTITLEMENTS=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ipa) IPA="${2:-}"; shift 2 ;;
    --identity) IDENTITY="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    --provision) PROVISION="${2:-}"; shift 2 ;;
    --entitlements) ENTITLEMENTS="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$IPA" ] || { echo "--ipa is required" >&2; exit 2; }
[ -n "$IDENTITY" ] || { echo "--identity is required" >&2; exit 2; }
[ -n "$OUT" ] || { echo "--out is required" >&2; exit 2; }
[ -f "$IPA" ] || { echo "IPA not found: $IPA" >&2; exit 2; }
[ -z "$PROVISION" ] || [ -f "$PROVISION" ] || { echo "provision not found: $PROVISION" >&2; exit 2; }
[ -z "$ENTITLEMENTS" ] || [ -f "$ENTITLEMENTS" ] || { echo "entitlements not found: $ENTITLEMENTS" >&2; exit 2; }

for tool in unzip zip codesign security plutil; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 2; }
done

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cookinggo-resign.XXXXXX")"
cleanup() { rm -rf "$TMP_ROOT"; }
trap cleanup EXIT

WORK="$TMP_ROOT/work"
mkdir -p "$WORK"
unzip -q "$IPA" -d "$WORK"

APP="$(find "$WORK/Payload" -maxdepth 1 -type d -name '*.app' | head -n 1)"
[ -n "$APP" ] || { echo "Payload/*.app not found" >&2; exit 1; }
INFO="$APP/Info.plist"
EXEC_NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$INFO")"
MAIN_EXEC="$APP/$EXEC_NAME"
[ -f "$MAIN_EXEC" ] || { echo "main executable not found: $MAIN_EXEC" >&2; exit 1; }

if [ -n "$PROVISION" ]; then
  cp "$PROVISION" "$APP/embedded.mobileprovision"
fi

DERIVED_ENT="$TMP_ROOT/entitlements.plist"
if [ -n "$ENTITLEMENTS" ]; then
  DERIVED_ENT="$ENTITLEMENTS"
elif [ -n "$PROVISION" ]; then
  security cms -D -i "$PROVISION" > "$TMP_ROOT/provision.plist"
  /usr/libexec/PlistBuddy -x -c 'Print :Entitlements' "$TMP_ROOT/provision.plist" > "$DERIVED_ENT"
else
  # Fallback minimal entitlements for ad-hoc/lab signing. Prefer --provision on real devices.
  cat > "$DERIVED_ENT" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
</dict>
</plist>
PLIST
fi

# Remove archive-level signatures so CodeResources are regenerated consistently.
find "$APP" -name _CodeSignature -type d -prune -exec rm -rf {} +

SIGN_BASE_ARGS=(--force --sign "$IDENTITY" --timestamp=none)
SIGN_APP_ARGS=("${SIGN_BASE_ARGS[@]}")
if [ -f "$DERIVED_ENT" ]; then
  SIGN_APP_ARGS+=(--entitlements "$DERIVED_ENT")
fi

sign_path_base() {
  local p="$1"
  echo "[sign] $p"
  codesign "${SIGN_BASE_ARGS[@]}" "$p"
}

sign_path_app() {
  local p="$1"
  echo "[sign-app] $p"
  codesign "${SIGN_APP_ARGS[@]}" "$p"
}

# Sign nested code before the containing .app. The sort puts deeper paths first.
mapfile -t NESTED < <(
  find "$APP" \( \
    -name '*.framework' -o \
    -name '*.dylib' -o \
    -name '*.appex' -o \
    -name '*.app' -o \
    -name '*.xpc' \
  \) -print | awk '{ print length, $0 }' | sort -rn | cut -d' ' -f2-
)

for item in "${NESTED[@]}"; do
  [ "$item" = "$APP" ] && continue
  case "$item" in
    *.appex|*.app) sign_path_app "$item" ;;
    *) sign_path_base "$item" ;;
  esac
done

sign_path_app "$APP"

codesign --verify --deep --strict --verbose=2 "$APP"

mkdir -p "$(dirname "$OUT")"
(
  cd "$WORK"
  rm -f "$OUT"
  zip -qry "$OUT" Payload
)

printf '\nResigned IPA: %s\n' "$OUT"
shasum -a 256 "$OUT" || true
