class TaskManagerError(Exception):
    """Base exception for task-manager-cli."""


class ConfigError(TaskManagerError):
    """Raised when configuration is missing or invalid."""


class NotFoundError(TaskManagerError):
    """Raised when a requested object cannot be found."""
