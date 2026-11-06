#!/bin/sh
# bot-obormot installer
# Usage:
# curl -fsSL https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh | sh -s -- --latest
# curl -fsSL https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh | sh -s -- --nightly --systemd

set -eu

APP_NAME="bot-obormot"
SERVICE_NAME="bot-obormot.service"
DEFAULT_BOT_GITHUB_REPOSITORY="WhlteAdmln/bot-obormot"
BOT_GITHUB_REPOSITORY="${BOT_GITHUB_REPOSITORY:-$DEFAULT_BOT_GITHUB_REPOSITORY}"
INSTALL_DIR="${BOT_INSTALL_DIR:-${HOME:-}/bot-obormot}"
CHANNEL="latest"
CHANNEL_WAS_SET=0
CREATE_SYSTEMD=0
UPGRADE=0
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
Usage: install.sh [--latest | --nightly] [--systemd] [--upgrade] [--help]

Options:
  --latest    Install the newest stable GitHub Release (default).
  --nightly   Install the newest GitHub prerelease.
  --systemd   Create a per-user systemd service in ~/.config/systemd/user/.
  --upgrade   Update an existing installation and preserve its configuration.
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
	--upgrade)
		UPGRADE=1
		;;
	--help | -h)
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

case "$INSTALL_DIR" in
/*) ;;
*) INSTALL_DIR="$PWD/$INSTALL_DIR" ;;
esac

if [ "$UPGRADE" -eq 1 ]; then
	[ -d "$INSTALL_DIR" ] || die "Cannot upgrade: installation directory does not exist: $INSTALL_DIR."
	[ -f "$INSTALL_DIR/bot/main.py" ] || die "Cannot upgrade: bot/main.py was not found in $INSTALL_DIR."
	[ -f "$INSTALL_DIR/.env" ] || die "Cannot upgrade: .env was not found in $INSTALL_DIR."
	[ -f "$INSTALL_DIR/requirements-lock.txt" ] || die "Cannot upgrade: requirements-lock.txt was not found in $INSTALL_DIR."
	[ -x "$INSTALL_DIR/.venv/bin/python" ] || die "Cannot upgrade: Python virtual environment was not found in $INSTALL_DIR/.venv."
elif [ -e "$INSTALL_DIR" ]; then
	die "Installation directory already exists: $INSTALL_DIR. Use --upgrade to update it or choose another path."
fi



# Do not replace application files while the systemd service is running.
if [ "$UPGRADE" -eq 1 ] && command -v systemctl >/dev/null 2>&1; then
    if systemctl --user is-active --quiet "$SERVICE_NAME"; then
        die "The bot service is running. Stop it before upgrading: systemctl --user stop $SERVICE_NAME"
    fi
fi

# Ignore old documentation placeholders.
case "$BOT_GITHUB_REPOSITORY" in
OWNER/REPOSITORY | owner/repository)
	warn "Ignoring placeholder BOT_GITHUB_REPOSITORY; using $DEFAULT_BOT_GITHUB_REPOSITORY."
	BOT_GITHUB_REPOSITORY="$DEFAULT_BOT_GITHUB_REPOSITORY"
	;;
esac

case "$BOT_GITHUB_REPOSITORY" in
/* | */ | */*/*)
	die "Invalid GitHub repository path: $BOT_GITHUB_REPOSITORY"
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

	if [ -e "$SYSTEMD_UNIT_FILE" ] && [ "$UPGRADE" -ne 1 ]; then
		die "The systemd unit already exists: $SYSTEMD_UNIT_FILE. Use --upgrade to preserve the existing unit."
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

	if "$PYTHON_BIN" -m venv "$probe_dir/venv" >/dev/null 2>&1 &&
		"$probe_dir/venv/bin/python" -m pip --version >/dev/null 2>&1; then
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
		log "Installing OS packages with apt-get."

		run_privileged apt-get update
		run_privileged apt-get install -y \
			ca-certificates curl unzip \
			python3 python3-venv python3-pip \
			build-essential cmake pkg-config

		run_privileged apt-get install -y ffmpeg ||
			warn "Could not install ffmpeg. Video support will remain unavailable."

	elif have dnf; then
		log "Installing OS packages with dnf."

		run_privileged dnf install -y \
			ca-certificates curl unzip \
			python3 python3-pip \
			gcc gcc-c++ make cmake pkgconf-pkg-config

		run_privileged dnf install -y ffmpeg-free ||
			warn "Could not install ffmpeg-free. Video support will remain unavailable."

	elif have yum; then
		log "Installing OS packages with yum."

		run_privileged yum install -y \
			ca-certificates curl unzip \
			python3 python3-pip \
			gcc gcc-c++ make cmake pkgconfig

		run_privileged yum install -y ffmpeg ||
			warn "Could not install ffmpeg. Video support will remain unavailable."

	elif have pacman; then
		log "Installing OS packages with pacman."

		run_privileged pacman -S --needed --noconfirm \
			ca-certificates curl unzip ffmpeg \
			python python-pip base-devel cmake pkgconf

	elif have zypper; then
		log "Installing OS packages with zypper."

		run_privileged zypper --non-interactive install \
			ca-certificates curl unzip \
			python3 python3-pip \
			gcc gcc-c++ make cmake pkg-config

		run_privileged zypper --non-interactive install ffmpeg ||
			warn "Could not install ffmpeg. Video support will remain unavailable."

	elif have apk; then
		log "Installing OS packages with apk."

		run_privileged apk add --no-cache \
			ca-certificates curl unzip \
			python3 py3-pip py3-virtualenv \
			build-base cmake pkgconf

		run_privileged apk add --no-cache ffmpeg ||
			warn "Could not install ffmpeg. Video support will remain unavailable."

	else
		die "Unsupported package manager. Install Python 3.11+, venv, pip, unzip, curl and C/C++ build tools/CMake manually. ffmpeg/ffprobe are also needed for video support."
	fi
}

# Check required operating-system tools.
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

find_python || die "Python 3.11 or newer is required."
venv_works || die "Python venv/ensurepip is unavailable."

PYTHON_VERSION=$("$PYTHON_BIN" -c 'import sys; print("{}.{}.{}".format(*sys.version_info[:3]))')

log "Using $PYTHON_BIN (Python $PYTHON_VERSION)."

if ! have ffmpeg || ! have ffprobe; then
	warn "ffmpeg/ffprobe are not available. Video processing will not work."
fi



TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/bot-obormot-install.XXXXXX") ||
	die "Could not create temporary directory."

INSTALL_CREATED=0
INSTALL_SUCCEEDED=0
SYSTEMD_UNIT_CREATED=0
UPGRADE_BACKUP_DIR=""
UPGRADE_BACKUP_READY=0

cleanup() {
	if [ -n "${TMP_DIR:-}" ] && [ -d "$TMP_DIR" ]; then
		rm -rf "$TMP_DIR" ||
			warn "Could not remove temporary directory: $TMP_DIR"
	fi

	if [ "${INSTALL_SUCCEEDED:-0}" -ne 1 ]; then
		if [ "${SYSTEMD_UNIT_CREATED:-0}" -eq 1 ]; then
			rm -f "$SYSTEMD_UNIT_FILE"
			systemctl --user daemon-reload >/dev/null 2>&1 || true
		fi

		if [ "${UPGRADE_BACKUP_READY:-0}" -eq 1 ]; then
			warn "Upgrade failed. Restoring the previous installation."

			if rm -rf "$INSTALL_DIR" &&
				mkdir -p "$INSTALL_DIR" &&
				cp -R "$UPGRADE_BACKUP_DIR/." "$INSTALL_DIR/"; then
				log "Previous installation restored."
				rm -rf "$UPGRADE_BACKUP_DIR" ||
					warn "Could not remove backup directory: $UPGRADE_BACKUP_DIR"
				UPGRADE_BACKUP_DIR=""
				UPGRADE_BACKUP_READY=0
			else
				warn "Automatic rollback failed. Your backup has been retained at: $UPGRADE_BACKUP_DIR"
			fi
		elif [ "${INSTALL_CREATED:-0}" -eq 1 ]; then
			warn "Installation did not complete. Removing incomplete directory: $INSTALL_DIR"
			rm -rf "$INSTALL_DIR"
		elif [ -n "${UPGRADE_BACKUP_DIR:-}" ] && [ -d "$UPGRADE_BACKUP_DIR" ]; then
			# Remove an incomplete backup created before the update began.
			rm -rf "$UPGRADE_BACKUP_DIR"
		fi
	elif [ -n "${UPGRADE_BACKUP_DIR:-}" ] && [ -d "$UPGRADE_BACKUP_DIR" ]; then
		rm -rf "$UPGRADE_BACKUP_DIR" ||
			warn "Could not remove backup directory: $UPGRADE_BACKUP_DIR"
	fi
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Resolve GitHub release.
API_BASE="https://api.github.com/repos/$BOT_GITHUB_REPOSITORY"

if [ "$CHANNEL" = "latest" ]; then
	API_URL="$API_BASE/releases/latest"
	log "Looking up the latest stable release."
else
	API_URL="$API_BASE/releases?per_page=100"
	log "Looking up the latest prerelease."
fi

API_JSON="$TMP_DIR/release.json"

if [ -n "$GITHUB_TOKEN" ]; then
	HTTP_STATUS=$(curl -sSL --retry 3 --retry-delay 2 \
		-H 'Accept: application/vnd.github+json' \
		-H 'X-GitHub-Api-Version: 2026-03-10' \
		-H "Authorization: Bearer $GITHUB_TOKEN" \
		-H 'User-Agent: bot-obormot-installer' \
		-o "$API_JSON" -w '%{http_code}' "$API_URL") ||
		die "Could not connect to GitHub Releases API."
else
	HTTP_STATUS=$(curl -sSL --retry 3 --retry-delay 2 \
		-H 'Accept: application/vnd.github+json' \
		-H 'X-GitHub-Api-Version: 2026-03-10' \
		-H 'User-Agent: bot-obormot-installer' \
		-o "$API_JSON" -w '%{http_code}' "$API_URL") ||
		die "Could not connect to GitHub Releases API."
fi

case "$HTTP_STATUS" in
200)
	;;
404)
	if [ "$CHANNEL" = "latest" ]; then
		die "No stable release is published yet. Use --nightly or wait for a stable release."
	fi
	die "GitHub Releases endpoint was not found."
	;;
403)
	die "GitHub API rate limit or access restriction. Set GITHUB_TOKEN and try again."
	;;
*)
	die "GitHub Releases API returned HTTP $HTTP_STATUS."
	;;
esac

# Select one release and extract its asset URLs.
RELEASE_INFO="$TMP_DIR/release-info.txt"

"$PYTHON_BIN" - "$CHANNEL" "$API_JSON" "$RELEASE_INFO" <<'PY' ||
    die "Could not select a matching GitHub release."
import json
import re
import sys

channel, filename, output = sys.argv[1:]

with open(filename, encoding="utf-8") as stream:
    data = json.load(stream)

if channel == "latest":
    candidates = [data] if isinstance(data, dict) else []
else:
    candidates = data if isinstance(data, list) else []

release = next(
    (
        item
        for item in candidates
        if isinstance(item, dict)
        and not item.get("draft")
        and (
            not item.get("prerelease")
            if channel == "latest"
            else item.get("prerelease")
        )
    ),
    None,
)

if release is None:
    raise SystemExit("No matching release was found.")

tag = release.get("tag_name") or ""
if not tag or any(char in tag for char in "\r\n\t"):
    raise SystemExit("Release has an invalid tag name.")

version = tag[1:] if tag.startswith("v") else tag

archive_url = ""
checksums_url = ""

# Only use our own archive when both expected assets exist.
if re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]*", version):
    archive_name = f"bot-obormot-{version}.zip"
    assets = release.get("assets") or []

    archive_assets = [
        item
        for item in assets
        if isinstance(item, dict)
        and item.get("name") == archive_name
        and item.get("state") == "uploaded"
    ]
    checksum_assets = [
        item
        for item in assets
        if isinstance(item, dict)
        and item.get("name") == "SHA256SUMS"
        and item.get("state") == "uploaded"
    ]

    if len(archive_assets) == 1 and len(checksum_assets) == 1:
        archive_url = archive_assets[0].get("url") or ""
        checksums_url = checksum_assets[0].get("url") or ""

zipball_url = release.get("zipball_url") or ""

with open(output, "w", encoding="utf-8") as stream:
    for value in (tag, archive_url, checksums_url, zipball_url):
        if "\n" in value or "\r" in value:
            raise SystemExit("Invalid newline in release metadata.")
        stream.write(value + "\n")
PY
	RELEASE_TAG=$(sed -n '1p' "$RELEASE_INFO")
ASSET_ARCHIVE_URL=$(sed -n '2p' "$RELEASE_INFO")
CHECKSUMS_URL=$(sed -n '3p' "$RELEASE_INFO")
ZIPBALL_URL=$(sed -n '4p' "$RELEASE_INFO")

[ -n "$RELEASE_TAG" ] || die "Release has an empty tag name."

log "Selected release: $RELEASE_TAG."

# Download a GitHub release asset or source archive.
download_file() {
	DOWNLOAD_URL=$1
	DOWNLOAD_PATH=$2
	DOWNLOAD_ACCEPT=$3

	if [ -n "$GITHUB_TOKEN" ]; then
		curl -fLsS --retry 3 --retry-delay 2 \
			-H "Authorization: Bearer $GITHUB_TOKEN" \
			-H "Accept: $DOWNLOAD_ACCEPT" \
			-H 'X-GitHub-Api-Version: 2026-03-10' \
			-H 'User-Agent: bot-obormot-installer' \
			-o "$DOWNLOAD_PATH" "$DOWNLOAD_URL" ||
			die "Could not download a file from the selected GitHub release."
	else
		curl -fLsS --retry 3 --retry-delay 2 \
			-H "Accept: $DOWNLOAD_ACCEPT" \
			-H 'X-GitHub-Api-Version: 2026-03-10' \
			-H 'User-Agent: bot-obormot-installer' \
			-o "$DOWNLOAD_PATH" "$DOWNLOAD_URL" ||
			die "Could not download a file from the selected GitHub release."
	fi
}

if [ -n "$ASSET_ARCHIVE_URL" ] && [ -n "$CHECKSUMS_URL" ]; then
	# Release assets must come from this repository's GitHub API.
	ASSET_PREFIX="https://api.github.com/repos/${BOT_GITHUB_REPOSITORY}/releases/assets/"

	case "$ASSET_ARCHIVE_URL" in
	"${ASSET_PREFIX}"*) ;;
	*) die "GitHub returned an unexpected release archive URL." ;;
	esac

	case "$CHECKSUMS_URL" in
	"${ASSET_PREFIX}"*) ;;
	*) die "GitHub returned an unexpected checksum URL." ;;
	esac

	RELEASE_VERSION=${RELEASE_TAG#v}
	ARCHIVE_NAME="bot-obormot-${RELEASE_VERSION}.zip"
	ZIP_FILE="$TMP_DIR/$ARCHIVE_NAME"
	CHECKSUM_FILE="$TMP_DIR/SHA256SUMS"

	log "Downloading the project's release archive."
	download_file "$ASSET_ARCHIVE_URL" "$ZIP_FILE" "application/octet-stream"
	download_file "$CHECKSUMS_URL" "$CHECKSUM_FILE" "application/octet-stream"

	# Accept exactly one checksum entry, for the expected archive only.
	EXPECTED_SHA=$(
		"$PYTHON_BIN" - "$CHECKSUM_FILE" "$ARCHIVE_NAME" <<'PY'
import re
import sys
from pathlib import Path

checksum_file, expected_name = sys.argv[1:]
entries = []

for line in Path(checksum_file).read_text(encoding="utf-8").splitlines():
    if not line:
        continue

    match = re.fullmatch(r"([0-9a-fA-F]{64})[ \t]+[*]?(.+)", line)
    if match is None:
        raise SystemExit("Invalid entry in SHA256SUMS.")

    entries.append((match.group(1).lower(), match.group(2)))

if len(entries) != 1 or entries[0][1] != expected_name:
    raise SystemExit("SHA256SUMS does not contain exactly the expected archive.")

print(entries[0][0])
PY
	) || die "Could not read the release checksum."

	if command -v sha256sum >/dev/null 2>&1; then
		ACTUAL_SHA=$(sha256sum "$ZIP_FILE" | awk '{print $1}')
	elif command -v shasum >/dev/null 2>&1; then
		ACTUAL_SHA=$(shasum -a 256 "$ZIP_FILE" | awk '{print $1}')
	else
		die "Cannot verify SHA-256: install sha256sum or shasum."
	fi

	[ "$EXPECTED_SHA" = "$ACTUAL_SHA" ] ||
		die "Release archive SHA-256 verification failed. Refusing to install."

	log "Release archive SHA-256 verified."

else
	# Older releases may only provide GitHub's automatically generated zipball.
	case "$ZIPBALL_URL" in
	https://api.github.com/* | https://codeload.github.com/*) ;;
	*) die "GitHub returned an unexpected source archive URL." ;;
	esac

	warn "Release has no project ZIP with SHA256SUMS. Falling back to GitHub source archive; checksum verification is unavailable."

	ZIP_FILE="$TMP_DIR/release.zip"
	download_file "$ZIPBALL_URL" "$ZIP_FILE" "application/vnd.github+json"
fi

# Verify ZIP paths before extraction.
"$PYTHON_BIN" - "$ZIP_FILE" <<'PY'
import sys
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

try:
    with ZipFile(sys.argv[1]) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)

            if path.is_absolute() or ".." in path.parts:
                raise SystemExit(
                    "Unsafe path in release archive: {}".format(item.filename)
                )

except BadZipFile:
    raise SystemExit("Downloaded file is not a valid ZIP archive")
PY

EXTRACT_DIR="$TMP_DIR/extracted"
mkdir -p "$EXTRACT_DIR"

unzip -q "$ZIP_FILE" -d "$EXTRACT_DIR" ||
	die "Could not extract release ZIP."

SOURCE_DIR=$(
	"$PYTHON_BIN" - "$EXTRACT_DIR" <<'PY'
import sys
from pathlib import Path

base = Path(sys.argv[1])
matches = set()

for main_file in base.rglob("bot/main.py"):
    root = main_file.parent.parent

    if (
        (root / ".env.example").is_file()
        and (root / "requirements-lock.txt").is_file()
    ):
        matches.add(root)

if len(matches) != 1:
    raise SystemExit(
        "Expected exactly one project root containing bot/main.py, "
        ".env.example and requirements-lock.txt; found {}".format(len(matches))
    )

print(next(iter(matches)))
PY
) || die "Release ZIP does not contain the expected project layout."

# Install the project.
log "Installing into $INSTALL_DIR."

if [ "$UPGRADE" -eq 1 ]; then
	[ -f "$SOURCE_DIR/bot/main.py" ] ||
		die "New release is missing bot/main.py."

	[ -f "$SOURCE_DIR/prompts/systemPrompt.md" ] ||
		die "New release is missing prompts/systemPrompt.md."

	BACKUP_PARENT=$(dirname "$INSTALL_DIR")

	UPGRADE_BACKUP_DIR=$(
		mktemp -d "$BACKUP_PARENT/.${APP_NAME}-backup.XXXXXX"
	) || die "Could not create an upgrade backup directory."

	cp -R "$INSTALL_DIR/." "$UPGRADE_BACKUP_DIR/" ||
		die "Could not back up the existing installation."

	UPGRADE_BACKUP_READY=1
	log "Created upgrade backup: $UPGRADE_BACKUP_DIR"
else
	mkdir -p "$INSTALL_DIR"
	INSTALL_CREATED=1
fi

if [ "$UPGRADE" -eq 1 ]; then
	# Replace packaged application code and prompts, removing obsolete files.
	rm -rf "$INSTALL_DIR/bot" "$INSTALL_DIR/prompts" ||
		die "Could not remove the previous application files."
fi

cp -R "$SOURCE_DIR/." "$INSTALL_DIR/"

if [ "$UPGRADE" -eq 1 ]; then
	[ -f "$INSTALL_DIR/.env" ] ||
		die "Existing configuration file disappeared during upgrade."

	# Keep the user's configuration unchanged.
	chmod 600 "$INSTALL_DIR/.env"
	log "Preserved existing .env configuration."
else
	if [ ! -f "$INSTALL_DIR/.env.example" ]; then
		die "Release archive is missing .env.example."
	fi

	mv "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
	chmod 600 "$INSTALL_DIR/.env"
fi

# Create or reuse Python virtual environment.
if [ "$UPGRADE" -eq 1 ]; then
	log "Reusing existing Python virtual environment."
else
	log "Creating Python virtual environment."
	"$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"
fi

log "Installing locked Python dependencies."

"$INSTALL_DIR/.venv/bin/python" -m pip install \
	--disable-pip-version-check \
	-r "$INSTALL_DIR/requirements-lock.txt"

# Create per-user systemd unit if requested.
if [ "$CREATE_SYSTEMD" -eq 1 ]; then
	if [ -e "$SYSTEMD_UNIT_FILE" ]; then
		log "Preserving existing systemd unit: $SYSTEMD_UNIT_FILE"
	else
		mkdir -p "$SYSTEMD_USER_DIR"

		SYSTEMD_WORKDIR=$(printf '%s' "$INSTALL_DIR" |
			sed 's/\\/\\\\/g; s/"/\\"/g; s/%/%%/g')

		SYSTEMD_PYTHON=$(printf '%s' "$INSTALL_DIR/.venv/bin/python" |
			sed 's/\\/\\\\/g; s/"/\\"/g; s/%/%%/g')

		SYSTEMD_UNIT_CREATED=1

		cat >"$SYSTEMD_UNIT_FILE" <<EOF
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

		systemctl --user daemon-reload ||
			die "Could not reload the user systemd manager."

		log "Created user systemd unit: $SYSTEMD_UNIT_FILE"
	fi
fi

INSTALL_SUCCEEDED=1

# Print final instructions.
if [ "$UPGRADE" -eq 1 ]; then
	cat <<EOF

Upgrade completed successfully.

Updated release:
  $RELEASE_TAG

Project directory:
  $INSTALL_DIR

The existing .env configuration and Python virtual environment were preserved.

Run manually:
  cd "$INSTALL_DIR"
  .venv/bin/python -m bot.main

If managed by systemd, restart the service to apply the update:
  systemctl --user restart $SERVICE_NAME
EOF
else
	cat <<EOF

Installation completed successfully.

Project directory:
  $INSTALL_DIR

Next step — configure the bot:
  1. Edit $INSTALL_DIR/.env
  2. Set BOT_TOKEN (from @BotFather).
  3. Set SUPERVISOR_ID (your numeric Telegram ID).
  4. Check LLM_BASE_URL and make sure your OpenAI-compatible LLM server is running.
  5. Keep ALLOW_ALL_USERS=false unless you intentionally want an open bot.

Open the configuration file:
  nano "$INSTALL_DIR/.env"

Run manually:
  cd "$INSTALL_DIR"
  .venv/bin/python -m bot.main
EOF
fi

if [ "$CREATE_SYSTEMD" -eq 1 ] && [ "$SYSTEMD_UNIT_CREATED" -eq 1 ]; then
	cat <<EOF

A per-user systemd unit was created and systemd has reloaded its unit files.

The service was NOT started or enabled yet.
Configure .env first, then run:

  systemctl --user enable --now $SERVICE_NAME

Check status and logs:

  systemctl --user status $SERVICE_NAME
  journalctl --user -u $SERVICE_NAME -f

The service runs as the current user.
To start it at boot without an interactive login, an administrator may enable lingering:

  sudo loginctl enable-linger "$RUNNING_USER"
EOF
elif [ "$CREATE_SYSTEMD" -eq 1 ]; then
	cat <<EOF

The existing per-user systemd unit was preserved:
  $SYSTEMD_UNIT_FILE

The installer did not restart or enable the service.
EOF
fi

if [ "$UPGRADE" -eq 1 ]; then
	log "Updated to release $RELEASE_TAG ($CHANNEL)."
else
	log "Installed release $RELEASE_TAG ($CHANNEL)."
fi
