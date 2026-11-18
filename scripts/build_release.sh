#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:?usage: build_release.sh VERSION}"

if [[ ! "$VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z.+-]*$ ]]; then
  echo "Invalid release version: $VERSION" >&2
  exit 2
fi

SDIST_ROOT="bot_obormot-${VERSION}"

mkdir -p dist
rm -f dist/bot_obormot-*.zip dist/bot_obormot-*.tar.gz dist/bot_obormot-*.whl \
  dist/constraints.txt dist/SHA256SUMS dist/build-provenance.sigstore.json

python3 -m build --sdist --wheel --outdir dist .

shopt -s nullglob
sdists=(dist/bot_obormot-*.tar.gz)
wheels=(dist/bot_obormot-*.whl)
if [[ ${#sdists[@]} -ne 1 ]]; then
  echo "Expected exactly one source distribution in dist/, found ${#sdists[@]}." >&2
  exit 1
fi
if [[ ${#wheels[@]} -ne 1 ]]; then
  echo "Expected exactly one bot_obormot wheel in dist/, found ${#wheels[@]}." >&2
  exit 1
fi

sdist_files="$(tar -tzf "${sdists[0]}")"
if ! grep -Fx "${SDIST_ROOT}/.env.example" <<< "$sdist_files" > /dev/null; then
  echo "Source distribution is missing .env.example." >&2
  exit 1
fi
if grep -Fx "${SDIST_ROOT}/.env" <<< "$sdist_files" > /dev/null; then
  echo "Source distribution must not contain .env." >&2
  exit 1
fi

cp requirements-lock.txt dist/constraints.txt

(
  cd dist
  sha256sum "${sdists[0]##*/}" "${wheels[0]##*/}" constraints.txt > SHA256SUMS
)

printf 'Built dist/%s, dist/%s, dist/constraints.txt and dist/SHA256SUMS\n' \
  "${sdists[0]##*/}" "${wheels[0]##*/}"
