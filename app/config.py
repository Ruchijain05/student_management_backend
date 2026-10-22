from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "mysql+pymysql://root:password@localhost:3306/student_management"
    )
    secret_key: str = ""
    access_token_expire_minutes: int = Field(default=60, ge=1, le=1440)
    app_env: Literal["development", "production"] = "production"
    password_reset_otp_console_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
