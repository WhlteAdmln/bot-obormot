from bot.config.paths import PROJECT_ROOT


def load_default_system_prompt() -> str:
    prompt_path = PROJECT_ROOT / "prompts" / "systemPrompt.md"

    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Файл системного промпта не найден: {prompt_path}"
        ) from error

    if not prompt:
        raise ValueError(f"Файл системного промпта пуст: {prompt_path}")

    return prompt
