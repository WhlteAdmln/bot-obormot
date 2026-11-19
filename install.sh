#!/bin/sh
# bot-obormot installer. Installs a verified GitHub Release wheel.

set -eu
umask 077

APP_NAME="bot-obormot"
GITHUB_REPOSITORY="${BOT_OBORMOT_GITHUB_REPOSITORY:-WhlteAdmln/bot-obormot}"
CHANNEL="latest"
VERSION=""
WITH_TGS=0
CREATE_SYSTEMD=0
UPGRADE=0
PYTHON_BIN=""
UPGRADE_BACKUP=0
INSTALL_CREATED=0
INSTALL_SUCCEEDED=0

log() {
	printf '%s\n' "[$APP_NAME] $*"
}

die() {
	printf '%s\n' "[$APP_NAME] ERROR: $*" >&2
	exit 1
}

usage() {
	cat <<'EOF'
Usage: install.sh [options]

  --version X    Install release X (for example 0.2.0).
  --nightly      Install the newest GitHub prerelease.
  --systemd      Install a per-user systemd unit (never started).
  --with-tgs     Install animated sticker support (needs a C compiler and CMake).
  --upgrade      Safely upgrade an existing installation.
  --help         Show this help.

Environment:
  BOT_OBORMOT_HOME               Installation directory (default: ~/bot-obormot).
  BOT_OBORMOT_RELEASE_URL        Release asset base URL (used for local mirrors).
  BOT_OBORMOT_RELEASE_TAG        Release tag for a custom release URL.
  BOT_OBORMOT_GITHUB_REPOSITORY  GitHub repository (default: WhlteAdmln/bot-obormot).
  GITHUB_TOKEN                   Optional GitHub API token.

Requires Linux with glibc, Python 3.11+, venv, curl and sha256sum.
The installer never installs operating system packages; it prints the commands.
EOF
}

need_value() {
	[ "$#" -ge 2 ] || die "Option $1 requires a value."
	case "$2" in
	'' | -*)
		die "Invalid value for $1: $2"
		;;
	esac
}

print_os_hint() {
	printf '%s\n' "[$APP_NAME] Install the missing packages with one of:" >&2
	printf '%s\n' "  Debian/Ubuntu: sudo apt-get install $1" >&2
	printf '%s\n' "  Fedora/RHEL:   sudo dnf install $2" >&2
	printf '%s\n' "  Arch Linux:    sudo pacman -S $3" >&2
}

while [ "$#" -gt 0 ]; do
	case "$1" in
	--version)
		need_value "$@"
		VERSION=$2
		shift
		;;
	--nightly)
		CHANNEL="nightly"
		;;
	--systemd)
		CREATE_SYSTEMD=1
		;;
	--with-tgs)
		WITH_TGS=1
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

if [ "$UPGRADE" -eq 1 ] && [ "$CREATE_SYSTEMD" -eq 1 ]; then
	die "--upgrade never touches the systemd unit; do not combine it with --systemd."
fi

if [ -n "$VERSION" ] && [ "$CHANNEL" = "nightly" ]; then
	die "Use only one of --version or --nightly."
fi

case "$VERSION" in
'')
	;;
*[!0-9A-Za-z.+-]* | [!0-9]*)
	die "Invalid version: $VERSION"
	;;
esac

case "$GITHUB_REPOSITORY" in
*/*)
	case "$GITHUB_REPOSITORY" in
	*[!A-Za-z0-9._/-]* | */*/* | /* | */)
		die "Invalid GitHub repository: $GITHUB_REPOSITORY"
		;;
	esac
	;;
*)
	die "BOT_OBORMOT_GITHUB_REPOSITORY must have owner/name format."
	;;
esac

[ -n "${HOME:-}" ] && [ -d "$HOME" ] ||
	die "HOME must point to an existing directory."

if command -v apk >/dev/null 2>&1; then
	die "Alpine Linux is not supported: release wheels require glibc."
fi

if [ -n "${BOT_OBORMOT_HOME:-}" ]; then
	HOME_DIR=$BOT_OBORMOT_HOME
else
	HOME_DIR=$HOME/bot-obormot
fi

case "$HOME_DIR" in
/*)
	;;
*)
	HOME_DIR=$PWD/$HOME_DIR
	;;
esac

while [ "$HOME_DIR" != "/" ] && [ "${HOME_DIR%/}" != "$HOME_DIR" ]; do
	HOME_DIR=${HOME_DIR%/}
done

case "$HOME_DIR" in
/ | "$HOME")
	die "Refusing unsafe installation directory: $HOME_DIR"
	;;
esac

USER_UNIT_FILE="$HOME/.config/systemd/user/bot-obormot.service"
USER_UNIT_BACKUP="$USER_UNIT_FILE.bak"

refuse_active_service() {
	if command -v systemctl >/dev/null 2>&1 &&
		systemctl --user is-active --quiet bot-obormot.service; then
		die "The bot-obormot user service is active. Stop it manually before upgrading."
	fi
}

LEGACY_UPGRADE=0
LEGACY_DIR=""
LEGACY_MIGRATION_STARTED=0
LEGACY_MIGRATION_SUCCEEDED=0
LEGACY_UNIT_BACKED_UP=0
LEGACY_UNIT_TEMP=""

# Move the 0.1.x source files from the directory $1 to the directory $2.
move_legacy_files() {
	for name in bot prompts pyproject.toml requirements.txt requirements-dev.txt \
		requirements-lock.txt install.sh docs README.md README.ru.md CHANGELOG.md \
		LICENSE .env.example; do
		if [ -e "$1/$name" ] || [ -L "$1/$name" ]; then
			mv "$1/$name" "$2/" || return 1
		fi
	done
}

# Succeeds when the virtual environment has the given top-level package.
venv_has_package() {
	"$HOME_DIR/.venv/bin/python" -c 'import sys, sysconfig
from pathlib import Path
paths = sysconfig.get_paths()
name = sys.argv[1]
found = any((Path(paths[key]) / name).is_dir() for key in ("purelib", "platlib"))
raise SystemExit(0 if found else 1)' "$1" >/dev/null 2>&1
}

legacy_version() {
	version=$(sed -n 's/^version = "\([0-9A-Za-z.+-]*\)"$/\1/p' "$HOME_DIR/pyproject.toml" 2>/dev/null | sed -n '1p')
	printf '%s' "${version:-0.1.x}"
}

if [ "$UPGRADE" -eq 1 ]; then
	[ -d "$HOME_DIR" ] && [ ! -L "$HOME_DIR" ] ||
		die "Upgrade requires an existing installation directory: $HOME_DIR"
	[ -f "$HOME_DIR/.env" ] && [ ! -L "$HOME_DIR/.env" ] ||
		die "Upgrade requires an existing regular .env file."
	[ -d "$HOME_DIR/.venv" ] && [ ! -L "$HOME_DIR/.venv" ] ||
		die "Upgrade requires an existing .venv directory."
	[ -x "$HOME_DIR/.venv/bin/python" ] ||
		die "The existing virtual environment has no executable Python interpreter."
	[ ! -e "$HOME_DIR/.venv.new" ] && [ ! -L "$HOME_DIR/.venv.new" ] ||
		die "Refusing to overwrite stale upgrade directory: $HOME_DIR/.venv.new"
	[ ! -e "$HOME_DIR/.venv.prev" ] && [ ! -L "$HOME_DIR/.venv.prev" ] ||
		die "Refusing to overwrite stale upgrade backup: $HOME_DIR/.venv.prev"

	if [ -f "$HOME_DIR/bot/main.py" ] && ! venv_has_package bot_obormot; then
		LEGACY_UPGRADE=1
		LEGACY_DIR="$HOME_DIR/.legacy-$(legacy_version)"
		[ ! -e "$LEGACY_DIR" ] && [ ! -L "$LEGACY_DIR" ] ||
			die "Refusing to overwrite legacy source backup: $LEGACY_DIR"
		if [ -e "$USER_UNIT_FILE" ] || [ -L "$USER_UNIT_FILE" ]; then
			[ ! -e "$USER_UNIT_BACKUP" ] && [ ! -L "$USER_UNIT_BACKUP" ] ||
				die "Refusing to overwrite systemd unit backup: $USER_UNIT_BACKUP"
		fi
	fi

	# Keep animated sticker support when the old environment already had it.
	if venv_has_package rlottie_python; then
		WITH_TGS=1
	fi

	refuse_active_service
else
	if [ -e "$HOME_DIR" ] || [ -L "$HOME_DIR" ]; then
		die "Installation directory already exists: $HOME_DIR. Use --upgrade to update an existing installation."
	fi
fi

command -v curl >/dev/null 2>&1 || die "curl is required."
command -v sha256sum >/dev/null 2>&1 || {
	print_os_hint coreutils coreutils coreutils
	die "sha256sum is required."
}

find_python() {
	for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
		if command -v "$candidate" >/dev/null 2>&1; then
			candidate_path=$(command -v "$candidate")
			if "$candidate_path" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
				PYTHON_BIN=$candidate_path
				return 0
			fi
		fi
	done
	return 1
}

if ! find_python; then
	print_os_hint "python3 python3-venv" "python3" "python"
	die "Python 3.11 or newer is required."
fi

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/bot-obormot-install.XXXXXX") ||
	die "Could not create a temporary directory."

cleanup() {
	result=$?
	trap - 0
	rm -rf "$TMP_DIR"
	if [ -n "$LEGACY_UNIT_TEMP" ]; then
		rm -f "$LEGACY_UNIT_TEMP"
	fi
	if [ "$result" -ne 0 ] &&
		[ "$LEGACY_MIGRATION_STARTED" -eq 1 ] &&
		[ "$LEGACY_MIGRATION_SUCCEEDED" -ne 1 ]; then
		log "Restoring the legacy source tree."
		move_legacy_files "$LEGACY_DIR" "$HOME_DIR" ||
			printf '%s\n' "[$APP_NAME] ERROR: Could not restore the legacy source files." >&2
		if [ "$LEGACY_UNIT_BACKED_UP" -eq 1 ]; then
			cp -p "$USER_UNIT_BACKUP" "$USER_UNIT_FILE" ||
				printf '%s\n' "[$APP_NAME] ERROR: Could not restore the user systemd unit." >&2
			if command -v systemctl >/dev/null 2>&1; then
				systemctl --user daemon-reload ||
					printf '%s\n' "[$APP_NAME] ERROR: Could not reload the restored user systemd unit." >&2
			fi
		fi
		rmdir "$LEGACY_DIR" 2>/dev/null || :
	fi
	if [ "$UPGRADE" -eq 1 ]; then
		rm -rf "$HOME_DIR/.venv.new"
		if [ "$UPGRADE_BACKUP" -eq 1 ] &&
			[ ! -e "$HOME_DIR/.venv" ] &&
			[ -e "$HOME_DIR/.venv.prev" ]; then
			mv "$HOME_DIR/.venv.prev" "$HOME_DIR/.venv" ||
				printf '%s\n' "[$APP_NAME] ERROR: Could not restore the previous virtual environment." >&2
		fi
	fi
	if [ "$INSTALL_CREATED" -eq 1 ] && [ "$INSTALL_SUCCEEDED" -ne 1 ]; then
		rm -rf "$HOME_DIR"
	fi
	exit "$result"
}

trap cleanup 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

"$PYTHON_BIN" -m venv "$TMP_DIR/venv-probe" >/dev/null 2>&1 || {
	print_os_hint "python3-venv" "python3" "python"
	die "Python venv is unavailable. Install the venv package for Python 3.11+."
}

"$TMP_DIR/venv-probe/bin/python" -m pip --version >/dev/null 2>&1 ||
	die "Python venv does not provide pip. Install the matching venv package."

rm -rf "$TMP_DIR/venv-probe"

fetch_api() {
	api_url=$1
	api_output=$2
	if [ -n "${GITHUB_TOKEN:-}" ]; then
		curl -fLsS --retry 3 --connect-timeout 15 \
			-H 'Accept: application/vnd.github+json' \
			-H "Authorization: Bearer $GITHUB_TOKEN" \
			-o "$api_output" "$api_url"
	else
		curl -fLsS --retry 3 --connect-timeout 15 \
			-H 'Accept: application/vnd.github+json' \
			-o "$api_output" "$api_url"
	fi
}

RELEASE_TAG=${BOT_OBORMOT_RELEASE_TAG:-local}

if [ -n "${BOT_OBORMOT_RELEASE_URL:-}" ]; then
	RELEASE_URL=${BOT_OBORMOT_RELEASE_URL%/}
elif [ -n "$VERSION" ]; then
	RELEASE_TAG="v$VERSION"
	RELEASE_URL="https://github.com/$GITHUB_REPOSITORY/releases/download/$RELEASE_TAG"
else
	if [ "$CHANNEL" = "nightly" ]; then
		API_URL="https://api.github.com/repos/$GITHUB_REPOSITORY/releases?per_page=30"
		log "Looking up the newest prerelease."
	else
		API_URL="https://api.github.com/repos/$GITHUB_REPOSITORY/releases/latest"
		log "Looking up the latest stable release."
	fi
	API_JSON="$TMP_DIR/release.json"
	fetch_api "$API_URL" "$API_JSON" ||
		die "Could not retrieve the $CHANNEL GitHub release. Use --version X to choose one."

	RELEASE_INFO="$TMP_DIR/release-info.txt"
	"$PYTHON_BIN" - "$API_JSON" "$RELEASE_INFO" "$CHANNEL" <<'PY' ||
import json
import re
import sys

source, destination, channel = sys.argv[1:]
with open(source, encoding="utf-8") as stream:
    data = json.load(stream)

if channel == "nightly":
    if not isinstance(data, list):
        raise SystemExit("Invalid release list")
    candidates = [
        item for item in data
        if isinstance(item, dict) and item.get("prerelease") and not item.get("draft")
    ]
    if not candidates:
        raise SystemExit("No prerelease is published")
    release = candidates[0]
else:
    release = data

if not isinstance(release, dict) or release.get("draft"):
    raise SystemExit("Invalid release metadata")

tag = release.get("tag_name")
if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", tag):
    raise SystemExit("Invalid release tag")

assets = release.get("assets") or []
wheels = [
    item for item in assets
    if isinstance(item, dict)
    and isinstance(item.get("name"), str)
    and item["name"].startswith("bot_obormot-")
    and item["name"].endswith(".whl")
]

with open(destination, "w", encoding="utf-8") as stream:
    stream.write(tag + "\n")
    stream.write(str(len(wheels)) + "\n")
PY
		die "GitHub returned invalid release metadata."
	RELEASE_TAG=$(sed -n '1p' "$RELEASE_INFO")
	WHEEL_ASSET_COUNT=$(sed -n '2p' "$RELEASE_INFO")

	if [ "$WHEEL_ASSET_COUNT" -eq 0 ]; then
		die "Release $RELEASE_TAG has no wheel asset. Use the installer at https://raw.githubusercontent.com/$GITHUB_REPOSITORY/$RELEASE_TAG/install.sh"
	fi

	if [ "$WHEEL_ASSET_COUNT" -ne 1 ]; then
		die "Release $RELEASE_TAG contains multiple bot_obormot wheels."
	fi

	RELEASE_URL="https://github.com/$GITHUB_REPOSITORY/releases/download/$RELEASE_TAG"
fi

case "$RELEASE_TAG" in
'' | *[!A-Za-z0-9._+-]*)
	die "Invalid release tag: $RELEASE_TAG"
	;;
esac

download_asset() {
	asset_name=$1
	curl -fLsS --retry 3 --connect-timeout 15 --max-time 120 \
		-o "$TMP_DIR/$asset_name" "$RELEASE_URL/$asset_name" ||
		die "Could not download release asset: $asset_name (release $RELEASE_TAG)."
}

log "Selected release: $RELEASE_TAG."
download_asset SHA256SUMS

VERIFY_SUMS="$TMP_DIR/verified-SHA256SUMS"
WHEEL_NAME=$(
	"$PYTHON_BIN" - "$TMP_DIR/SHA256SUMS" "$VERIFY_SUMS" <<'PY'
import re
import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
entries = {}
for line in source.read_text(encoding="utf-8").splitlines():
    match = re.fullmatch(r"([0-9a-fA-F]{64})  ([A-Za-z0-9_.+-]+)", line)
    if match:
        digest, name = match.groups()
        if name in entries:
            raise SystemExit("Duplicate SHA256SUMS entry: " + name)
        entries[name] = digest

wheels = [
    name for name in entries
    if name.startswith("bot_obormot-") and name.endswith(".whl")
]
if not wheels:
    print("__NO_WHEEL__")
    raise SystemExit(0)
if len(wheels) != 1:
    raise SystemExit("SHA256SUMS must contain exactly one bot_obormot wheel")
if "constraints.txt" not in entries:
    raise SystemExit("SHA256SUMS does not contain constraints.txt")

wheel = wheels[0]
lines = [
    f"{entries[wheel]}  {wheel}",
    f"{entries['constraints.txt']}  constraints.txt",
]
destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(wheel)
PY
) || die "Release SHA256SUMS is invalid."

if [ "$WHEEL_NAME" = "__NO_WHEEL__" ]; then
	die "Release $RELEASE_TAG has no wheel asset. Use the installer at https://raw.githubusercontent.com/$GITHUB_REPOSITORY/$RELEASE_TAG/install.sh"
fi

download_asset "$WHEEL_NAME"
download_asset constraints.txt

(cd "$TMP_DIR" && sha256sum -c "$VERIFY_SUMS") ||
	die "Release SHA-256 verification failed."

if [ "$WITH_TGS" -eq 1 ]; then
	WHEEL_TARGET="$TMP_DIR/$WHEEL_NAME[tgs]"
else
	WHEEL_TARGET="$TMP_DIR/$WHEEL_NAME"
fi

# Install the wheel into the given virtual environment, with pinned dependencies.
install_wheel() {
	"$1/bin/python" -m pip install \
		--disable-pip-version-check \
		--constraint "$TMP_DIR/constraints.txt" \
		"$WHEEL_TARGET" || {
		if [ "$WITH_TGS" -eq 1 ]; then
			print_os_hint "build-essential cmake" "gcc-c++ cmake" "base-devel cmake"
		fi
		return 1
	}
}

if [ "$UPGRADE" -eq 1 ]; then
	if [ "$LEGACY_UPGRADE" -eq 1 ]; then
		log "Moving legacy source files to $LEGACY_DIR."
		mkdir -m 700 "$LEGACY_DIR" ||
			die "Could not create the legacy source backup directory."
		LEGACY_MIGRATION_STARTED=1
		move_legacy_files "$HOME_DIR" "$LEGACY_DIR" ||
			die "Could not move the legacy source files."

		log "Installing the verified release wheel into the existing virtual environment."
		install_wheel "$HOME_DIR/.venv" ||
			die "Could not upgrade the legacy virtual environment."

		APP_CLI="$HOME_DIR/.venv/bin/bot-obormot"
		if [ -e "$USER_UNIT_FILE" ] || [ -L "$USER_UNIT_FILE" ]; then
			log "Updating the existing per-user systemd unit."
			cp -p "$USER_UNIT_FILE" "$USER_UNIT_BACKUP" ||
				die "Could not back up the existing user systemd unit."
			LEGACY_UNIT_BACKED_UP=1
			BOT_OBORMOT_HOME="$HOME_DIR" "$APP_CLI" service install --user --print \
				>"$TMP_DIR/bot-obormot.service" ||
				die "Could not render the new user systemd unit."
			LEGACY_UNIT_TEMP=$(mktemp "${USER_UNIT_FILE%/*}/.bot-obormot.service.XXXXXX") ||
				die "Could not create a temporary user systemd unit."
			cat "$TMP_DIR/bot-obormot.service" >"$LEGACY_UNIT_TEMP" ||
				die "Could not write the new user systemd unit."
			chmod 644 "$LEGACY_UNIT_TEMP" ||
				die "Could not set permissions on the new user systemd unit."
			mv "$LEGACY_UNIT_TEMP" "$USER_UNIT_FILE" ||
				die "Could not replace the existing user systemd unit."
			LEGACY_UNIT_TEMP=""
			systemctl --user daemon-reload ||
				die "Could not reload the user systemd manager."
		fi

		DOCTOR_OUTPUT="$TMP_DIR/doctor-legacy.txt"
		if BOT_OBORMOT_HOME="$HOME_DIR" "$APP_CLI" doctor --offline >"$DOCTOR_OUTPUT" 2>&1; then
			cat "$DOCTOR_OUTPUT"
		else
			cat "$DOCTOR_OUTPUT"
			die "bot-obormot doctor failed after the legacy upgrade. The old source and user unit will be restored."
		fi

		LEGACY_MIGRATION_SUCCEEDED=1
		INSTALL_SUCCEEDED=1
		cat <<EOF

Upgrade completed successfully.

Application directory:
  $HOME_DIR

Legacy source backup:
  $LEGACY_DIR

The installer preserved .env, data/ and the existing virtual environment.
The installer did not restart or enable the systemd service.

When ready, restart the bot user service:
  systemctl --user restart bot-obormot.service
EOF
		log "Upgraded the legacy installation to release $RELEASE_TAG."
		exit 0
	fi

	NEW_VENV="$HOME_DIR/.venv.new"
	NEW_CLI="$NEW_VENV/bin/bot-obormot"

	log "Creating a staged virtual environment."
	"$PYTHON_BIN" -m venv "$NEW_VENV" ||
		die "Could not create the staged virtual environment."

	log "Installing the verified release wheel into the staged environment."
	install_wheel "$NEW_VENV" ||
		die "Could not install the bot-obormot release wheel into the staged environment."

	log "Checking the staged installation in offline mode."
	DOCTOR_OUTPUT="$TMP_DIR/doctor-upgrade.txt"
	if BOT_OBORMOT_HOME="$HOME_DIR" "$NEW_CLI" doctor --offline \
		>"$DOCTOR_OUTPUT" 2>&1; then
		cat "$DOCTOR_OUTPUT"
	else
		cat "$DOCTOR_OUTPUT"
		die "Staged bot-obormot doctor --offline failed. The existing installation was not replaced."
	fi

	refuse_active_service

	log "Switching the application virtual environment."
	mv "$HOME_DIR/.venv" "$HOME_DIR/.venv.prev" ||
		die "Could not move the existing virtual environment to its backup."
	UPGRADE_BACKUP=1

	mv "$NEW_VENV" "$HOME_DIR/.venv" ||
		die "Could not activate the staged virtual environment. The previous environment will be restored."

	if ! rm -rf "$HOME_DIR/.venv.prev"; then
		log "WARNING: Could not remove the previous environment backup: $HOME_DIR/.venv.prev"
	fi
	UPGRADE_BACKUP=0

	INSTALL_SUCCEEDED=1
	cat <<EOF

Upgrade completed successfully.

Application directory:
  $HOME_DIR

The installer preserved .env, data/ and the existing systemd unit.
The installer did not restart or enable the systemd service.

If the bot-obormot user service is installed, restart it manually when ready:
  systemctl --user restart bot-obormot.service
EOF
	log "Upgraded to release $RELEASE_TAG."
	exit 0
fi

log "Creating installation directory: $HOME_DIR"
mkdir -p "${HOME_DIR%/*}"
mkdir "$HOME_DIR" || die "Could not create installation directory: $HOME_DIR"
INSTALL_CREATED=1

log "Creating Python virtual environment."
"$PYTHON_BIN" -m venv "$HOME_DIR/.venv" ||
	die "Could not create the application virtual environment."

APP_CLI="$HOME_DIR/.venv/bin/bot-obormot"

log "Installing the verified release wheel."
install_wheel "$HOME_DIR/.venv" ||
	die "Could not install the bot-obormot release wheel."

log "Creating the protected configuration file."
BOT_OBORMOT_HOME="$HOME_DIR" "$APP_CLI" init ||
	die "bot-obormot init failed."

# A fresh .env still holds template values, so doctor is informational here.
DOCTOR_OUTPUT="$TMP_DIR/doctor.txt"
if BOT_OBORMOT_HOME="$HOME_DIR" "$APP_CLI" doctor --offline >"$DOCTOR_OUTPUT" 2>&1; then
	cat "$DOCTOR_OUTPUT"
else
	cat "$DOCTOR_OUTPUT"
	log "doctor reported problems above. Edit $HOME_DIR/.env and run doctor again."
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
	log "ffmpeg is missing; video and animation will be unavailable."
	print_os_hint "ffmpeg" "ffmpeg" "ffmpeg"
fi

if [ "$CREATE_SYSTEMD" -eq 1 ]; then
	log "Installing the per-user systemd unit."
	BOT_OBORMOT_HOME="$HOME_DIR" "$APP_CLI" service install --user ||
		die "Could not install the user systemd unit."
fi

INSTALL_SUCCEEDED=1

cat <<EOF

Installation completed successfully.

Application directory:
  $HOME_DIR

Next steps:
  1. Edit the protected configuration: $HOME_DIR/.env
     (set BOT_TOKEN, SUPERVISOR_ID and the LLM server)
  2. Check it: BOT_OBORMOT_HOME="$HOME_DIR" "$APP_CLI" doctor
  3. Run the bot: BOT_OBORMOT_HOME="$HOME_DIR" "$APP_CLI" run

The installer does not enable or start the systemd service.
EOF

log "Installed release $RELEASE_TAG."
