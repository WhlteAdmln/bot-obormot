import tempfile
from pathlib import Path

from rlottie_python import LottieAnimation

from bot.services.media.animation.jpeg import image_to_bytes
from bot.services.media.animation.sampling import sample_frame_indices


def extract_tgs(data: bytes) -> list[bytes]:
    """Извлекает кадры Telegram TGS."""

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "sticker.tgs"
        path.write_bytes(data)

        with LottieAnimation.from_tgs(str(path)) as animation:
            total = animation.lottie_animation_get_totalframe()

            if total <= 0:
                raise ValueError("TGS animation has no frames")

            indices = sample_frame_indices(total)
            frames = []

            for index in indices:
                image = animation.render_pillow_frame(frame_num=index)
                frames.append(image_to_bytes(image))

            return frames
