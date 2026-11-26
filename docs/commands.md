# Commands

## Telegram commands

The bot works in private chats. `/start` registers the command menu that
matches the role of the user, so administrators and the supervisor see more
commands than regular users.

### All users

| Command | Description |
| --- | --- |
| `/start` | Show the help message and register the command menu. |
| `/history` | Show the history limit. |
| `/history_limit N` | Change the number of exchanges that are sent as context, from 1 to 30. Administrators and the supervisor can set up to `MAX_HISTORY_EXCHANGES`. |
| `/history_clear` | Delete the conversation history. |
| `/forget_me` | Delete all data stored about the user. |
| `/prompt` | Show the current system prompt. |
| `/prompt_set` | Set a personal system prompt. |
| `/prompt_reset` | Return to the default system prompt. |
| `/cancel` | Cancel entering a system prompt. |

### Administrators

| Command | Description |
| --- | --- |
| `/health` | Check the state of the bot's components. |
| `/ban ID` | Block a user. |
| `/unban ID` | Unblock a user. |
| `/history_limit ID N` | Set the history limit of another user, from 1 to `MAX_HISTORY_EXCHANGES`. |

### Supervisor

| Command | Description |
| --- | --- |
| `/admin` | Open the administration panel. |
| `/admins` | List the administrators. |
| `/admin_add ID` | Add an administrator. |
| `/admin_remove ID` | Remove an administrator. |

## Console commands

| Command | Description |
| --- | --- |
| `bot-obormot run` | Run the bot. Use `--env-file PATH` to load an extra file. |
| `bot-obormot version` | Show the installed version. |
| `bot-obormot init` | Create a protected `.env` file. Options: `--token`, `--supervisor`, `--force`. |
| `bot-obormot config check` | Validate the settings. Use `--env-file PATH` to load an extra file. Secret values are never printed. |
| `bot-obormot doctor` | Check Python, the `.env` file and its permissions, the settings, the Telegram token format, ffmpeg, animated sticker support, the database and the servers. Use `--offline` to skip network checks and `--quiet` to print only warnings and failures. |
| `bot-obormot service install` | Install a systemd unit without starting it. Options: `--user` (default), `--system`, `--print`, `--force`. |
| `bot-obormot service uninstall` | Remove the unit file without stopping the service. Options: `--user` (default), `--system`. |
| `bot-obormot service status` | Show the systemd status of the service. Options: `--user` (default), `--system`. |

`python -m bot_obormot` is the same as `bot-obormot`.
