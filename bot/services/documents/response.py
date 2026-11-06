from bot.errors import DocumentAPIError


def validate_document_response(result: object) -> dict:
    """Проверяет структуру ответа Document Engine без преобразования данных."""
    if not isinstance(result, dict):
        raise DocumentAPIError(
            502,
            "Invalid response from Document Engine",
        )

    if not isinstance(result.get("text"), str):
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid text",
        )

    if not isinstance(result.get("format"), str):
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid format",
        )

    if not isinstance(result.get("characters"), int):
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid character count",
        )

    # Older audiodoc versions may omit this field; when present, it must be boolean.
    if "truncated" in result and not isinstance(result["truncated"], bool):
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid truncated flag",
        )

    return result
