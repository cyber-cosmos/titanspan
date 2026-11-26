#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
VERSION="$(cat "$ROOT/.vale-version")"
INSTALL_DIR="$ROOT/.cache/tools/vale/$VERSION"

case "$(uname -s)/$(uname -m)" in
  Linux/x86_64)
    ARCHIVE="vale_${VERSION}_Linux_64-bit.tar.gz"
    SHA256="068954ad869ebec24b8dec6ebcd1cbb1fd5f5a83e966a35baedfae8b2cdc093a"
    ;;
  Linux/aarch64|Linux/arm64)
    ARCHIVE="vale_${VERSION}_Linux_arm64.tar.gz"
    SHA256="af0ca36ec6133ba20093295591e43ed2823b2632520d1f3811293aa4cbe758f2"
    ;;
  Darwin/x86_64)
    ARCHIVE="vale_${VERSION}_macOS_64-bit.tar.gz"
    SHA256="4a59f52678b4e6bd55846fb6c22371ed531a274a614ea8e4d51a365c365b563e"
    ;;
  Darwin/arm64)
    ARCHIVE="vale_${VERSION}_macOS_arm64.tar.gz"
    SHA256="b5362c16d2c95db9d773078b957f5bd59cef27d05dac34c5248a93fed130e9f1"
    ;;
  *)
    echo "Vale installation does not support this operating system or CPU." >&2
    exit 1
    ;;
esac

case "$VERSION" in
  3.28.1) ;;
  *)
    echo "Add an official release checksum before changing .vale-version." >&2
    exit 1
    ;;
esac

if [ -x "$INSTALL_DIR/vale" ] &&
  [ "$("$INSTALL_DIR/vale" --version)" = "vale version $VERSION" ]; then
  echo "Vale $VERSION is already installed at $INSTALL_DIR/vale"
  exit 0
fi

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT HUP INT TERM
curl --fail --silent --show-error --location --retry 3 \
  --retry-all-errors \
  --output "$TEMP_DIR/$ARCHIVE" \
  "https://github.com/vale-cli/vale/releases/download/v$VERSION/$ARCHIVE"

if [ "$(uname -s)" = "Darwin" ]; then
  printf '%s  %s\n' "$SHA256" "$TEMP_DIR/$ARCHIVE" |
    shasum -a 256 --check
else
  printf '%s  %s\n' "$SHA256" "$TEMP_DIR/$ARCHIVE" |
    sha256sum --check
fi

mkdir -p "$INSTALL_DIR"
tar -xzf "$TEMP_DIR/$ARCHIVE" -C "$TEMP_DIR"
install -m 0755 "$TEMP_DIR/vale" "$INSTALL_DIR/vale"

if [ "$("$INSTALL_DIR/vale" --version)" != "vale version $VERSION" ]; then
  echo "The installed Vale binary does not match .vale-version." >&2
  exit 1
fi

echo "Installed Vale $VERSION at $INSTALL_DIR/vale"
