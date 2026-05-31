from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_file": ".env.local",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # Trello
    trello_api_key: str
    trello_api_token: str
    trello_board_id: str
    trello_list_name: str = ""

    # Google AI Studio (Gemini Developer API)
    google_api_key: str

    # Model selection
    gemini_model: str = "gemini-2.5-flash-lite"
    top_n_for_llm: int = 10
    top_priorities: int = 5
    priorities_per_assignee: int = 5
    priorities_unassigned: int = 3

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_webhook_url: str = ""  # e.g., https://your-domain.com/webhook/telegram
    telegram_message_log_path: str = "/data/telegram_messages.jsonl"

    # Assistant behavior
    assistant_name: str = "Peanut"
    briefing_title: str = "Daily priorities"

    # Retry configuration for 503 errors
    gemini_retry_max_attempts: int = 5
    gemini_retry_initial_wait: float = 2.0
    gemini_retry_max_wait: float = 60.0
    gemini_retry_wait_multiplier: float = 2.0

    # Memory
    memory_file_path: str = "/data/memory.json"

    # Gmail OAuth2 (read-only)
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    gmail_sender_emails: str = ""


settings = Settings()  # type: ignore[call-arg]
