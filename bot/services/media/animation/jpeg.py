import io

from PIL import Image

from bot.services.media.animation.limits import MAX_DIMENSION


def image_to_bytes(image: Image.Image) -> bytes:
    """Преобразует кадр в JPEG."""

    image = image.convert("RGBA")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

    background = Image.new("RGBA", image.size, "white")
    background.alpha_composite(image)

    output = io.BytesIO()
    background.convert("RGB").save(
        output,
        format="JPEG",
        quality=82,
        optimize=True,
    )

    return output.getvalue()
