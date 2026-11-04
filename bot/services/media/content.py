from aiogram.types import Message

from bot.services.media.prompts import get_media_prompt


def get_user_content(
    message: Message,
    image_urls: list[str] | None,
    media_type: str | None,
):
    """Формирует мультимодальное сообщение для LLM."""

    if not image_urls:
        return message.text

    prompt = get_media_prompt(message, media_type)

    content = [{"type": "text", "text": prompt}]

    if len(image_urls) > 1:
        content[0]["text"] += (
            "\n\nКадры расположены в хронологическом порядке. "
            "Рассматривай их как последовательность одной анимации."
        )

    for image_url in image_urls:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            }
        )

    return content
