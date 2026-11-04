from bot.errors.base import BotServiceError


class LLMError(BotServiceError):
    """Ошибка взаимодействия с LLM."""


class LLMUnavailableError(LLMError):
    """LLM недоступна или не удалось установить соединение."""


class LLMTimeoutError(LLMError):
    """Истекло время ожидания ответа LLM."""


class LLMAPIError(LLMError):
    """LLM вернула ошибку API."""

    def __init__(self, status: int, detail: str = ""):
        self.status = status
        self.detail = detail
        super().__init__(f"LLM API HTTP {status}: {detail}")
