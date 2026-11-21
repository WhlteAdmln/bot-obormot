#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:?usage: build_release.sh VERSION}"

if [[ ! "$VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z.+-]*$ ]]; then
  echo "Invalid release version: $VERSION" >&2
  exit 2
fi

PROJECT_NAME="$(sed -n 's/^name = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)"
if [[ -z "$PROJECT_NAME" ]]; then
  echo "Could not read the project name from pyproject.toml." >&2
  exit 1
fi
DIST_NAME="${PROJECT_NAME//-/_}"
SDIST_ROOT="${DIST_NAME}-${VERSION}"

mkdir -p dist
rm -f "dist/${DIST_NAME}"-*.zip "dist/${DIST_NAME}"-*.tar.gz "dist/${DIST_NAME}"-*.whl \
  dist/constraints.txt dist/SHA256SUMS dist/build-provenance.sigstore.json

python3 -m build --sdist --wheel --outdir dist .

shopt -s nullglob
sdists=("dist/${DIST_NAME}"-*.tar.gz)
wheels=("dist/${DIST_NAME}"-*.whl)
if [[ ${#sdists[@]} -ne 1 ]]; then
  echo "Expected exactly one source distribution in dist/, found ${#sdists[@]}." >&2
  exit 1
fi
if [[ ${#wheels[@]} -ne 1 ]]; then
  echo "Expected exactly one ${DIST_NAME} wheel in dist/, found ${#wheels[@]}." >&2
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
