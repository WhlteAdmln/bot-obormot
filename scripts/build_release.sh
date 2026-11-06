#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:?Использование: build_release.sh VERSION}"

if [[ ! "$VERSION" =~ ^([0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?|ci-[0-9a-f]{7})$ ]]; then
	echo "Ошибка: недопустимый формат версии: $VERSION" >&2
	echo "Ожидается X.Y.Z, X.Y.Z-suffix или ci-<7 hex chars>" >&2
	exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

NAME="bot-obormot-${VERSION}"
ARCHIVE="dist/${NAME}.zip"

FILES=(
	bot
	prompts
	requirements.txt
	requirements-lock.txt
	.env.example
	install.sh
	README.md
	README.ru.md
	LICENSE
	docs
)

for file in "${FILES[@]}"; do
	if ! git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
		echo "Ошибка: файл или каталог не отслеживается Git: $file" >&2
		exit 1
	fi
done

mkdir -p dist
rm -f dist/bot-obormot-*.zip dist/SHA256SUMS

git archive \
	--format=zip \
	--prefix="${NAME}/" \
	--output="$ARCHIVE" \
	HEAD \
	"${FILES[@]}"

if command -v sha256sum >/dev/null 2>&1; then
	(cd dist && sha256sum "${NAME}.zip" >SHA256SUMS)
elif command -v shasum >/dev/null 2>&1; then
	(cd dist && shasum -a 256 "${NAME}.zip" >SHA256SUMS)
else
	echo "Ошибка: необходим sha256sum или shasum" >&2
	exit 1
fi

echo "Архив создан: $ARCHIVE"
echo "Контрольная сумма: dist/SHA256SUMS"
