from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
import os


class Settings(BaseSettings):
    # Telegram
    BOT_TOKENS: str = ""
    CHANNEL_ID: int = 0

    # Security
    ADMIN_API_KEY: str = "change...n"
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    BASE_URL: str = "http://localhost:8080"
    DATABASE_PATH: str = "data/cloudora.db"

    # Proxy (optional)
    PROXY_HOST: Optional[str] = None
    PROXY_PORT: Optional[int] = None
    PROXY_USER: Optional[str] = None
    PROXY_PASS: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.getcwd(), ".env"),
        extra="ignore",
    )

    @property
    def bot_token_list(self) -> List[str]:
        if self.BOT_TOKENS:
            return [t.strip() for t in self.BOT_TOKENS.split(",") if t.strip()]
        token_file = os.path.join(os.getcwd(), "tokens.txt")
        if os.path.exists(token_file):
            with open(token_file) as f:
                return [t.strip() for t in f.readlines() if t.strip()]
        return []


settings = Settings()
