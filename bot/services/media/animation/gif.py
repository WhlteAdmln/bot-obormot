import io

from PIL import Image

from bot.services.media.animation.jpeg import image_to_bytes
from bot.services.media.animation.sampling import sample_frame_indices


def extract_gif(data: bytes) -> list[bytes]:
    """Извлекает равномерно распределённые кадры GIF через Pillow."""

    with Image.open(io.BytesIO(data)) as animation:
        total = getattr(animation, "n_frames", 1)

        if total <= 0:
            raise ValueError("GIF does not contain frames")

        indices = sample_frame_indices(total)
        frames = []

        for index in indices:
            animation.seek(index)
            frame = animation.convert("RGBA").copy()
            frames.append(image_to_bytes(frame))

        return frames
