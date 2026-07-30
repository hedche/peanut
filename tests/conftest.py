"""Shared pytest fixtures and test environment setup.

``app.config`` instantiates a module-level ``Settings()`` at import time, which
requires a handful of credentials to be present. To keep the unit tests hermetic
and runnable in CI without real secrets, we populate placeholder values for the
required settings before any ``app`` module is imported.

Individual tests that need specific configuration still build their own
``Settings(...)`` instances, so these placeholders only satisfy the import-time
instantiation.
"""

import os

# Required fields on ``app.config.Settings`` that have no default. These must be
# present in the environment before ``app.config`` is imported.
_REQUIRED_ENV_DEFAULTS = {
    "TRELLO_API_KEY": "test-key",
    "TRELLO_API_TOKEN": "test-token",
    "TRELLO_BOARD_ID": "test-board",
    "GOOGLE_API_KEY": "test-google-key",
    "TELEGRAM_BOT_TOKEN": "test-bot-token",
    "TELEGRAM_CHAT_ID": "test-chat-id",
}

for _key, _value in _REQUIRED_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
