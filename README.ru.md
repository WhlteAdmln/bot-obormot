# bot-obormot

Асинхронный Telegram-бот (Python 3.11+, aiogram 3), который даёт доступ к
языковой модели в личных чатах через OpenAI-совместимый API. История диалогов
хранится в SQLite. Аудио и документы можно по желанию обрабатывать через
[audiodoc](https://github.com/WhlteAdmln/audiodoc).

English version: [README.md](README.md).

## Возможности

- Потоковые ответы от любого OpenAI-совместимого сервера, например llama.cpp или vLLM.
- Ответ приходит reply на ваше сообщение, а Markdown и HTML в ответе отображаются как форматирование Telegram.
- История у каждого пользователя с настраиваемыми лимитами и личные системные промпты.
- Изображения, GIF, видео и анимированные стикеры обрабатываются локально.
- Голосовые сообщения, аудиофайлы и документы через audiodoc (по желанию).
- Супервайзер, администраторы и список разрешённых пользователей управляют доступом.
- `bot-obormot doctor` проверяет установку, а установщик безопасно обновляет её.

## Установка

Нужны Linux с glibc, Python 3.11+ с модулем `venv`, `curl` и токен бота от
[@BotFather](https://t.me/BotFather). Для видео установите `ffmpeg`.

### Установщик (рекомендуется)

```bash
curl -fsSL https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh | sh
```

Установщик скачивает wheel последнего релиза GitHub, проверяет его SHA-256,
создаёт `~/bot-obormot` с виртуальным окружением и защищённым `.env` и никогда
не ставит системные пакеты. Параметры указываются после `-s --`:
`--version X`, `--nightly` (новейший prerelease), `--systemd` (пользовательский
unit без запуска), `--with-tgs` (анимированные стикеры, нужны компилятор C и CMake).

```bash
nano ~/bot-obormot/.env                      # укажите BOT_TOKEN и SUPERVISOR_ID
~/bot-obormot/.venv/bin/bot-obormot doctor   # проверка установки
~/bot-obormot/.venv/bin/bot-obormot run      # или: service install, см. ниже
```

Для обновления выполните ту же команду с `-s -- --upgrade`. Обновление
сохраняет `.env`, `data/` и unit, подменяет виртуальное окружение только после
успешной проверки в staging и откатывается при сбое. Каталог версии 0.1.x тоже
мигрирует: старые исходники переносятся в `.legacy-<версия>/`.

### Docker Compose

```bash
cp .env.example .env                 # укажите BOT_TOKEN и SUPERVISOR_ID
docker compose up -d
```

Образ работает от непривилегированного пользователя, хранит данные в томе
`bot_obormot_data` и проверяет себя командой `bot-obormot doctor --offline`.

### Из исходников

```bash
python3 -m venv .venv && .venv/bin/pip install -c requirements-lock.txt .
.venv/bin/bot-obormot init           # создаёт ~/bot-obormot/.env
.venv/bin/bot-obormot run
```

Чтобы запускать бота через systemd, используйте `bot-obormot service install`
(для системного unit добавьте `--system`). Команда только записывает unit;
включать и запускать сервис вы будете сами.

## Настройка

Настройки берутся из `.env` в `BOT_OBORMOT_HOME` (по умолчанию `~/bot-obormot`)
и из окружения. Все параметры описаны в [docs/configuration.md](docs/configuration.md).

| Параметр | Значение |
|----------|----------|
| `BOT_TOKEN` | Токен Telegram-бота (обязателен) |
| `SUPERVISOR_ID` | Числовой Telegram ID владельца (обязателен) |
| `ADMIN_IDS`, `ALLOWED_USERS` | Начальные администраторы и статический список разрешённых |
| `ALLOW_ALL_USERS` | `true` открывает бота всем, кто не заблокирован |
| `LLM_BASE_URL`, `LLM_MODEL` | OpenAI-совместимый сервер и имя модели |
| `LLM_API_KEY` | API-ключ сервера LLM |
| `LLM_CONTEXT_SIZE` | Укажите, если сервер не сообщает размер контекста |
| `DATABASE_PATH` | Файл SQLite относительно домашнего каталога |
| `AUDIODOC_URL` | Базовый URL audiodoc; пустое значение отключает аудио и документы |

Подробности о серверах LLM — в [docs/llm-servers.md](docs/llm-servers.md).

## Команды

Для всех: `/start`, `/history`, `/history_limit`, `/history_clear`,
`/forget_me`, `/prompt`, `/prompt_set`, `/prompt_reset`, `/cancel`.
Администраторы: `/health`, `/ban`, `/unban`. Супервайзер: `/admin`, `/admins`,
`/admin_add`, `/admin_remove`. Консольные команды: `run`, `version`, `init`,
`config check`, `doctor` и `service`. Подробности — в
[docs/commands.md](docs/commands.md).

## Подключение к audiodoc

1. Установите и запустите audiodoc на хосте, доступном боту.
2. В audiodoc создайте отдельные API-ключи для аудио и для документов.
3. Укажите в `AUDIODOC_URL` базовый адрес audiodoc, например
   `http://127.0.0.1:8000`.
4. Укажите в `AUDIODOC_AUDIO_KEY` и `AUDIODOC_DOCUMENT_KEY` ключи из шага 2.
5. Выполните `bot-obormot doctor`; строка audiodoc должна быть `OK`.
6. Перезапустите бота.

Между сервисами используйте частную сеть или HTTPS. Схема сети, ротация ключей
и диагностика описаны в руководстве audiodoc
[connecting the bot](https://github.com/WhlteAdmln/audiodoc/blob/main/docs/connecting-the-bot.md).
Старые имена `WHISPER_*` и `DOCUMENT_*` пока работают, но устарели и будут
удалены в 0.3.0.

## Документация

- [Настройка](docs/configuration.md) и [команды](docs/commands.md)
- [Серверы LLM](docs/llm-servers.md) и [безопасность](docs/security.md)
- [Архитектура](docs/architecture.md) ([на русском](docs/architecture.ru.md))
- [Участие в разработке](CONTRIBUTING.md), [политика безопасности](SECURITY.md)
  и [журнал изменений](CHANGELOG.md)

Лицензия MIT. Для разработки выполните `make install-dev` и `make check`.
