#!/bin/sh
# Install Yamaha's Windows "AG Controller" (for AG06MK2/AG03MK2) into its own Wine prefix
# and add a launcher + menu entry. The installer is NOT included: download
# Install_AG_Controller.exe from Yamaha yourself and pass its path.
#
#   ./install-ag-controller.sh ~/Downloads/Install_AG_Controller.exe
#
# Nothing is installed system-wide; everything goes under ~/.local.
set -eu

INSTALLER=${1:-}
if [ -z "$INSTALLER" ] || [ ! -f "$INSTALLER" ]; then
  echo "usage: $0 /path/to/Install_AG_Controller.exe" >&2
  exit 2
fi
command -v wine >/dev/null || { echo "wine is not installed (sudo apt install wine wine64)" >&2; exit 1; }

PREFIX="$HOME/.local/share/yamaha-ag-controller/wine"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
HERE=$(cd "$(dirname "$0")" && pwd)

mkdir -p "$(dirname "$PREFIX")" "$BIN" "$APPS"
export WINEPREFIX="$PREFIX" WINEDEBUG=-all
export WINEDLLOVERRIDES="winemenubuilder.exe=d;mscoree=d;mshtml=d"

echo "Creating Wine prefix in $PREFIX ..."
wineboot -i >/dev/null 2>&1
echo "Running the Yamaha installer silently ..."
wine "$INSTALLER" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- >/dev/null 2>&1 || true

if [ ! -f "$PREFIX/drive_c/Program Files/Yamaha/AGController/AGController.exe" ]; then
  echo "Installation failed: AGController.exe not found in the prefix." >&2
  exit 1
fi

install -m 755 "$HERE/ag-controller" "$BIN/ag-controller"
sed "s|@BIN@|$BIN|" "$HERE/ag-controller.desktop.in" > "$APPS/yamaha-ag-controller.desktop"
update-desktop-database "$APPS" 2>/dev/null || true
echo "Done. Start it from the menu (\"AG Controller\") or run: ag-controller"
