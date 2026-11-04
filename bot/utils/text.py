def utf16_length(text: str) -> int:
    """Возвращает длину текста в кодовых единицах UTF-16."""
    return len(text.encode("utf-16-le")) // 2
