from bot.errors import InputTooLongError

MAX_INPUT_TEXT_LENGTH = 12288


def validate_input_text(text: str):
    """Проверяет максимальную длину пользовательского текста."""

    if len(text) > MAX_INPUT_TEXT_LENGTH:
        raise InputTooLongError(
            f"Сообщение слишком длинное (максимум {MAX_INPUT_TEXT_LENGTH} символов)."
        )
