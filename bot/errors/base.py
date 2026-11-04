class BotServiceError(Exception):
    """Базовая ошибка внутренних сервисов бота."""


class ValidationError(BotServiceError):
    """Ошибка проверки входных данных."""


class InputTooLongError(ValidationError):
    """Пользовательское сообщение превышает допустимую длину."""


class DatabaseError(BotServiceError):
    """Ошибка SQLite или операций с базой данных."""


class MediaError(BotServiceError):
    """Ошибка обработки или хранения медиафайлов."""
