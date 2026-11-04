from bot.errors.base import BotServiceError


class WhisperError(BotServiceError):
    """Ошибка распознавания аудио."""


class WhisperEmptyAudioError(WhisperError):
    """В аудио не удалось распознать речь."""


class WhisperUnavailableError(WhisperError):
    """Whisper недоступен."""


class WhisperTimeoutError(WhisperError):
    """Истекло время ожидания Whisper."""


class WhisperAPIError(WhisperError):
    """Whisper вернул ошибку API."""
