#!/bin/sh
# pdfcraft-zh launcher -- macOS / Linux
#
# Finds a Python 3.8+ (or explains how to install one), then hands over to
# pdfcraft-zh.py. The main script uses the standard library only, so any
# Python 3 on the system will do: no pip, no virtualenv.

set -e

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MAIN="$HERE/pdfcraft-zh.py"

# Terminal colours (empty when not writing to a terminal)
if [ -t 1 ]; then
    B=$(printf '\033[1m'); G=$(printf '\033[32m'); R=$(printf '\033[31m'); Y=$(printf '\033[33m'); N=$(printf '\033[0m')
else
    B=; G=; R=; Y=; N=
fi

say()  { printf '%s\n' "$1"; }
ok()   { printf '%s\n' "${G}$1${N}"; }
warn() { printf '%s\n' "${Y}$1${N}"; }
die()  { printf '\n%s\n' "${R}error: $1${N}" >&2; exit 1; }

find_python() {
    for c in python3 python; do
        if command -v "$c" >/dev/null 2>&1; then
            if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
                command -v "$c"
                return 0
            fi
        fi
    done
    return 1
}

install_hint_macos() {
    say ""
    warn "Python 3.8 or newer was not found."
    say ""
    say "On macOS there are two ways to install it:"
    say ""
    say "  1) Install the Xcode command line tools (small; they include python3):"
    say "     ${B}xcode-select --install${N}"
    say "     Click Install in the window that appears, then run this script again."
    say ""
    say "  2) With Homebrew:"
    say "     ${B}brew install python3${N}"
    say ""
    say "You can also download an installer from https://www.python.org/downloads/"
    say ""
}

install_hint_linux() {
    say ""
    warn "Python 3.8 or newer was not found."
    say ""
    say "Install it with your distribution's package manager:"
    say ""
    say "  Debian / Ubuntu:   ${B}sudo apt install python3${N}"
    say "  Fedora / RHEL:     ${B}sudo dnf install python3${N}"
    say "  Arch:              ${B}sudo pacman -S python${N}"
    say "  openSUSE:          ${B}sudo zypper install python3${N}"
    say ""
    say "Then run this script again."
    say ""
}

main() {
    say ""
    say "${B}pdfcraft-zh${N}"
    say "  Adds to PdfCraft: system CJK fonts / four UI languages / Chinese OCR"
    say ""

    PY=$(find_python || true)
    if [ -z "$PY" ]; then
        case "$(uname -s)" in
            Darwin) install_hint_macos ;;
            Linux)  install_hint_linux ;;
            *)      warn "Python 3.8+ not found. Install it from https://www.python.org/downloads/" ;;
        esac
        exit 1
    fi

    ok "  ✓ Using Python: $PY ($("$PY" --version 2>&1))"
    exec "$PY" "$MAIN" "$@"
}

main "$@"
