from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """
    Defines the application's configuration settings.
    Reads settings from environment variables or a .env file.
    """

    # --- Application Settings ---
    addon_name: str = Field("My Playlist Addon", alias="ADDON_NAME")
    logging_level: str = Field("INFO", alias="LOGGING_LEVEL")

    # --- Database Settings ---
    mongo_uri: str = Field("mongodb://mongodb:27017/mediafusion", alias="MONGO_URI")

    # --- Playlist Parser Settings ---
    # A comma-separated list of M3U playlist URLs to combine and parse.
    combined_playlist_sources: str = Field("", alias="COMBINED_PLAYLIST_SOURCES")

    # Cron schedule for how often to run the parser (e.g., "0 */3 * * *")
    parser_schedule_crontab: str = Field("0 */3 * * *", alias="PARSER_SCHEDULE_CRONTAB")

    # --- Stremio Manifest Settings ---
    # The base URL where your addon is hosted.
    # This is crucial for Stremio to find your addon's resources.
    host_url: str = Field("http://localhost:8000", alias="HOST_URL")
    logo_url: str = Field("https://i.imgur.com/7v3c2g2.png", alias="LOGO_URL")


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

# Create a single, importable instance of the settings
settings = Settings()

