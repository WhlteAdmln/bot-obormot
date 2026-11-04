#!/bin/sh
# bot-obormot installer
# Usage: curl -fsSL https://YOUR_HOST/install.sh | sh -s -- --latest [--systemd]
# Set BOT_GITHUB_REPOSITORY to the public GitHub owner/repository before publishing.

set -eu

APP_NAME="bot-obormot"
SERVICE_NAME="bot-obormot.service"
BOT_GITHUB_REPOSITORY="${BOT_GITHUB_REPOSITORY:-OWNER/REPOSITORY}"
INSTALL_DIR="${BOT_INSTALL_DIR:-${HOME:-}/bot-obormot}"
CHANNEL="latest"
CHANNEL_WAS_SET=0
CREATE_SYSTEMD=0
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

log() {
    printf '%s\n' "[${APP_NAME}] $*"
}

warn() {
    printf '%s\n' "[${APP_NAME}] WARNING: $*" >&2
}

die() {
    printf '%s\n' "[${APP_NAME}] ERROR: $*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: install.sh [--latest | --nightly] [--systemd] [--help]

Options:
  --latest    Install the newest stable GitHub Release (default).
  --nightly   Install the newest GitHub prerelease.
  --systemd   Create a per-user systemd service in ~/.config/systemd/user/.
  --help      Show this help.

Optional environment variables:
  BOT_GITHUB_REPOSITORY  GitHub repository in owner/name format.
  BOT_INSTALL_DIR        Installation directory (default: ~/bot-obormot).
  GITHUB_TOKEN           Optional GitHub token for API rate limits/private repos.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --latest)
            if [ "$CHANNEL_WAS_SET" -eq 1 ] && [ "$CHANNEL" != "latest" ]; then
                die "Use only one of --latest or --nightly."
            fi
            CHANNEL="latest"
            CHANNEL_WAS_SET=1
            ;;
        --nightly)
            if [ "$CHANNEL_WAS_SET" -eq 1 ] && [ "$CHANNEL" != "nightly" ]; then
                die "Use only one of --latest or --nightly."
            fi
            CHANNEL="nightly"
            CHANNEL_WAS_SET=1
            ;;
        --systemd)
            CREATE_SYSTEMD=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "Unknown argument: $1. Use --help for usage."
            ;;
    esac
    shift
done

if [ "$(id -u)" -eq 0 ]; then
    die "Run this installer as the regular bot user, not as root. It uses sudo only when OS packages need installation."
fi

if [ -z "${HOME:-}" ] || [ ! -d "$HOME" ]; then
    die "HOME is not set to an existing directory."
fi
RUNNING_USER=$(id -un)

case "$BOT_GITHUB_REPOSITORY" in
    OWNER/REPOSITORY|owner/repository|/*|*/|*/*/*)
        die "Set BOT_GITHUB_REPOSITORY to the real GitHub repository, e.g. myaccount/bot-obormot."
        ;;
    *[!A-Za-z0-9._/-]*)
        die "Invalid GitHub repository name: $BOT_GITHUB_REPOSITORY"
        ;;
    */*) ;;
    *) die "BOT_GITHUB_REPOSITORY must have owner/name format." ;;
esac

if [ "$CREATE_SYSTEMD" -eq 1 ]; then
    command -v systemctl >/dev/null 2>&1 || die "--systemd was requested, but systemctl is not installed."
    systemctl --user show-environment >/dev/null 2>&1 || die "--systemd was requested, but the user systemd manager is unavailable. Log in through a systemd user session and retry."
    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
    SYSTEMD_UNIT_FILE="$SYSTEMD_USER_DIR/$SERVICE_NAME"
    if [ -e "$SYSTEMD_UNIT_FILE" ]; then
        die "The systemd unit already exists: $SYSTEMD_UNIT_FILE. Remove or rename it before reinstalling."
    fi
fi

have() {
    command -v "$1" >/dev/null 2>&1
}

find_python() {
    PYTHON_BIN=""
    for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
        if have "$candidate"; then
            candidate_path=$(command -v "$candidate")
            if "$candidate_path" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
                PYTHON_BIN="$candidate_path"
                return 0
            fi
        fi
    done
    return 1
}

venv_works() {
    if [ -z "$PYTHON_BIN" ]; then
        return 1
    fi
    probe_dir=$(mktemp -d "${TMPDIR:-/tmp}/bot-obormot-venv-check.XXXXXX") || return 1
    if "$PYTHON_BIN" -m venv "$probe_dir/venv" >/dev/null 2>&1 \
        && "$probe_dir/venv/bin/python" -m pip --version >/dev/null 2>&1; then
        venv_result=0
    else
        venv_result=1
    fi
    rm -rf "$probe_dir"
    return "$venv_result"
}

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif have sudo; then
        sudo "$@"
    else
        die "Missing OS packages and sudo is unavailable. Install dependencies manually or run with an administrative package manager."
    fi
}

install_os_packages() {
    if have apt-get; then
        log "Installing OS packages with apt-get (Python, venv, unzip and build tools)."
        run_privileged apt-get update
        run_privileged apt-get install -y \
            ca-certificates curl unzip \
            python3 python3-venv python3-pip \
            build-essential cmake pkg-config
        run_privileged apt-get install -y ffmpeg || warn "Could not install ffmpeg from configured apt repositories. Video support will remain unavailable."
    elif have dnf; then
        log "Installing OS packages with dnf."
        run_privileged dnf install -y \
            ca-certificates curl unzip \
            python3 python3-pip \
            gcc gcc-c++ make cmake pkgconf-pkg-config
        run_privileged dnf install -y ffmpeg-free || warn "Could not install ffmpeg-free from configured dnf repositories. Video support will remain unavailable."
    elif have yum; then
        log "Installing OS packages with yum."
        run_privileged yum install -y \
            ca-certificates curl unzip \
            python3 python3-pip \
            gcc gcc-c++ make cmake pkgconfig
        run_privileged yum install -y ffmpeg || warn "Could not install ffmpeg from configured yum repositories. Video support will remain unavailable."
    elif have pacman; then
        log "Installing OS packages with pacman."
        run_privileged pacman -Sy --needed --noconfirm \
            ca-certificates curl unzip ffmpeg \
            python python-pip base-devel cmake pkgconf
    elif have zypper; then
        log "Installing OS packages with zypper."
        run_privileged zypper --non-interactive install \
            ca-certificates curl unzip \
            python3 python3-pip \
            gcc gcc-c++ make cmake pkg-config
        run_privileged zypper --non-interactive install ffmpeg || warn "Could not install ffmpeg from configured zypper repositories. Video support will remain unavailable."
    elif have apk; then
        log "Installing OS packages with apk."
        run_privileged apk add --no-cache \
            ca-certificates curl unzip \
            python3 py3-pip py3-virtualenv \
            build-base cmake pkgconf
        run_privileged apk add --no-cache ffmpeg || warn "Could not install ffmpeg from configured apk repositories. Video support will remain unavailable."
    else
        die "Unsupported package manager. Install Python 3.11+, venv, pip, unzip, curl and C/C++ build tools/CMake manually. ffmpeg/ffprobe are also needed for video support."
    fi
}

# Check and install base operating-system tools before using Python to parse the
# GitHub API response. The invoking curl command already requires curl, but it
# is checked here as well for local/scripted execution.
NEED_OS_PACKAGES=0
have curl || NEED_OS_PACKAGES=1
have unzip || NEED_OS_PACKAGES=1
find_python || NEED_OS_PACKAGES=1
if [ -n "$PYTHON_BIN" ] && ! venv_works; then
    NEED_OS_PACKAGES=1
fi
have cmake || NEED_OS_PACKAGES=1
have make || NEED_OS_PACKAGES=1
if ! have cc && ! have gcc; then
    NEED_OS_PACKAGES=1
fi
if ! have pkg-config && ! have pkgconf; then
    NEED_OS_PACKAGES=1
fi
have ffmpeg || NEED_OS_PACKAGES=1
have ffprobe || NEED_OS_PACKAGES=1

if [ "$NEED_OS_PACKAGES" -eq 1 ]; then
    install_os_packages
fi

have curl || die "curl is still missing after package installation."
have unzip || die "unzip is still missing after package installation."
find_python || die "Python 3.11 or newer is required. Install it and rerun the installer."
venv_works || die "Python venv/ensurepip is unavailable. Install the matching venv package for $PYTHON_BIN."

PYTHON_VERSION=$("$PYTHON_BIN" -c 'import sys; print("{}.{}.{}".format(*sys.version_info[:3]))')
log "Using $PYTHON_BIN (Python $PYTHON_VERSION)."
if ! have ffmpeg || ! have ffprobe; then
    warn "ffmpeg/ffprobe are not available. Video and video-sticker processing will not work until they are installed."
fi

if [ -e "$INSTALL_DIR" ]; then
    die "Installation directory already exists: $INSTALL_DIR. Move it aside or set BOT_INSTALL_DIR to a new path. Existing data will not be overwritten."
fi

case "$INSTALL_DIR" in
    /*) ;;
    *) INSTALL_DIR="$PWD/$INSTALL_DIR" ;;
esac

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/bot-obormot-install.XXXXXX") || die "Could not create temporary directory."
INSTALL_CREATED=0
INSTALL_SUCCEEDED=0
SYSTEMD_UNIT_CREATED=0

cleanup() {
    if [ -n "${TMP_DIR:-}" ] && [ -d "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
    if [ "${INSTALL_SUCCEEDED:-0}" -ne 1 ]; then
        if [ "${SYSTEMD_UNIT_CREATED:-0}" -eq 1 ]; then
            rm -f "$SYSTEMD_UNIT_FILE"
            systemctl --user daemon-reload >/dev/null 2>&1 || true
        fi
        if [ "${INSTALL_CREATED:-0}" -eq 1 ]; then
            warn "Installation did not complete. Removing the incomplete directory: $INSTALL_DIR"
            rm -rf "$INSTALL_DIR"
        fi
    fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

API_BASE="https://api.github.com/repos/$BOT_GITHUB_REPOSITORY"
if [ "$CHANNEL" = "latest" ]; then
    API_URL="$API_BASE/releases/latest"
    log "Looking up the latest stable release of $BOT_GITHUB_REPOSITORY."
else
    API_URL="$API_BASE/releases?per_page=100"
    log "Looking up the latest prerelease of $BOT_GITHUB_REPOSITORY."
fi

API_JSON="$TMP_DIR/release.json"
if [ -n "$GITHUB_TOKEN" ]; then
    curl -fLsS --retry 3 --retry-delay 2 \
        -H 'Accept: application/vnd.github+json' \
        -H 'X-GitHub-Api-Version: 2026-03-10' \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H 'User-Agent: bot-obormot-installer' \
        "$API_URL" -o "$API_JSON" || die "Could not query GitHub Releases API. Check repository access and GITHUB_TOKEN."
else
    curl -fLsS --retry 3 --retry-delay 2 \
        -H 'Accept: application/vnd.github+json' \
        -H 'X-GitHub-Api-Version: 2026-03-10' \
        -H 'User-Agent: bot-obormot-installer' \
        "$API_URL" -o "$API_JSON" || die "Could not query GitHub Releases API. Check the repository name and its public visibility."
fi

RELEASE_TAG=$("$PYTHON_BIN" -c '
import json, sys
channel, filename = sys.argv[1], sys.argv[2]
with open(filename, encoding="utf-8") as stream:
    data = json.load(stream)
release = None
if channel == "latest":
    if isinstance(data, dict) and not data.get("draft") and not data.get("prerelease"):
        release = data
else:
    if isinstance(data, list):
        release = next((item for item in data if not item.get("draft") and item.get("prerelease")), None)
if not release:
    raise SystemExit("No matching release was found")
print(release.get("tag_name") or "")
' "$CHANNEL" "$API_JSON") || die "No $CHANNEL release was found for $BOT_GITHUB_REPOSITORY."

ARCHIVE_URL=$("$PYTHON_BIN" -c '
import json, sys
channel, filename = sys.argv[1], sys.argv[2]
with open(filename, encoding="utf-8") as stream:
    data = json.load(stream)
if channel == "latest":
    release = data
else:
    release = next((item for item in data if not item.get("draft") and item.get("prerelease")), None)
print((release or {}).get("zipball_url") or "")
' "$CHANNEL" "$API_JSON") || die "Could not read release archive URL."
case "$ARCHIVE_URL" in
    https://api.github.com/*|https://codeload.github.com/*) ;;
    *) die "GitHub returned an unexpected archive URL. Refusing to download: $ARCHIVE_URL" ;;
esac
[ -n "$RELEASE_TAG" ] || die "Release has an empty tag name."
[ -n "$ARCHIVE_URL" ] || die "Release does not provide a source ZIP archive."

log "Selected $CHANNEL release: $RELEASE_TAG."
ZIP_FILE="$TMP_DIR/release.zip"
if [ -n "$GITHUB_TOKEN" ]; then
    curl -fLsS --retry 3 --retry-delay 2 \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H 'Accept: application/vnd.github+json' \
        -H 'User-Agent: bot-obormot-installer' \
        -o "$ZIP_FILE" "$ARCHIVE_URL" || die "Could not download release ZIP."
else
    curl -fLsS --retry 3 --retry-delay 2 \
        -H 'Accept: application/vnd.github+json' \
        -H 'User-Agent: bot-obormot-installer' \
        -o "$ZIP_FILE" "$ARCHIVE_URL" || die "Could not download release ZIP."
fi

# Verify ZIP paths before extraction to reject absolute paths and ../ traversal.
"$PYTHON_BIN" - "$ZIP_FILE" <<'PY'
import sys
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

try:
    with ZipFile(sys.argv[1]) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit("Unsafe path in release archive: {}".format(item.filename))
except BadZipFile:
    raise SystemExit("Downloaded file is not a valid ZIP archive")
PY

EXTRACT_DIR="$TMP_DIR/extracted"
mkdir -p "$EXTRACT_DIR"
unzip -q "$ZIP_FILE" -d "$EXTRACT_DIR" || die "Could not extract release ZIP."

SOURCE_DIR=$("$PYTHON_BIN" - "$EXTRACT_DIR" <<'PY'
import sys
from pathlib import Path

base = Path(sys.argv[1])
matches = set()
for main_file in base.rglob("bot/main.py"):
    root = main_file.parent.parent
    if (root / ".env.example").is_file() and (root / "requirements-lock.txt").is_file():
        matches.add(root)
if len(matches) != 1:
    raise SystemExit("Expected exactly one project root containing bot/main.py, .env.example and requirements-lock.txt; found {}".format(len(matches)))
print(next(iter(matches)))
PY
) || die "Release ZIP does not contain the expected bot-obormot project layout."

log "Installing into $INSTALL_DIR."
mkdir -p "$INSTALL_DIR"
INSTALL_CREATED=1
cp -R "$SOURCE_DIR/." "$INSTALL_DIR/"

if [ ! -f "$INSTALL_DIR/.env.example" ]; then
    die "Release archive is missing .env.example."
fi
mv "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"

log "Creating Python virtual environment."
"$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check -r "$INSTALL_DIR/requirements-lock.txt"

if [ "$CREATE_SYSTEMD" -eq 1 ]; then
    mkdir -p "$SYSTEMD_USER_DIR"

    # Quote systemd values safely, including spaces, quotes, backslashes and '%'.
    SYSTEMD_WORKDIR=$(printf '%s' "$INSTALL_DIR" | sed 's/\\/\\\\/g; s/"/\\"/g; s/%/%%/g')
    SYSTEMD_PYTHON=$(printf '%s' "$INSTALL_DIR/.venv/bin/python" | sed 's/\\/\\\\/g; s/"/\\"/g; s/%/%%/g')

    cat > "$SYSTEMD_UNIT_FILE" <<EOF
[Unit]
Description=bot-obormot Telegram bot
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory="$SYSTEMD_WORKDIR"
ExecStart="$SYSTEMD_PYTHON" -m bot.main
Restart=on-failure
RestartSec=5
UMask=0077
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
    chmod 600 "$SYSTEMD_UNIT_FILE"
    SYSTEMD_UNIT_CREATED=1
    systemctl --user daemon-reload || die "Could not reload the user systemd manager."
    log "Created user systemd unit: $SYSTEMD_UNIT_FILE"
fi

INSTALL_SUCCEEDED=1

cat <<EOF

Installation completed successfully.

Project directory:
  $INSTALL_DIR

Next step — configure the bot:
  1. Edit $INSTALL_DIR/.env
  2. Set BOT_TOKEN (from @BotFather) and SUPERVISOR_ID (your numeric Telegram ID).
  3. Check LLM_BASE_URL and make sure llama-server is running.
  4. Keep ALLOW_ALL_USERS=false unless you intentionally want an open bot.

Open the configuration file:
  nano "$INSTALL_DIR/.env"

Run manually:
  cd "$INSTALL_DIR"
  .venv/bin/python -m bot.main
EOF

if [ "$CREATE_SYSTEMD" -eq 1 ]; then
    cat <<EOF

A per-user systemd unit was created and systemd has reloaded its unit files.
It was NOT started or enabled yet, so the unconfigured sample .env cannot
cause a restart loop. After editing .env, run:
  systemctl --user enable --now $SERVICE_NAME

Check status and logs:
  systemctl --user status $SERVICE_NAME
  journalctl --user -u $SERVICE_NAME -f

The service runs as the current user. To let it start at boot without an
interactive login, an administrator may enable lingering once:
  sudo loginctl enable-linger "$RUNNING_USER"
EOF
fi

log "Installed release $RELEASE_TAG ($CHANNEL)."
