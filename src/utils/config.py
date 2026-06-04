"""Configuration centralisee du projet VelibData.

Usage:
    from src.utils.config import api_settings, azure_settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    velib_station_status_url: str = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_status.json"
    velib_station_info_url: str = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_information.json"
    openmeteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    log_level: str = "INFO"


class AzureSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    adls_account_name: str = ""
    adls_account_key: str = ""
    adls_container_bronze: str = "bronze"
    adls_container_silver: str = "silver"
    adls_container_gold: str = "gold"


api_settings = APISettings()
azure_settings = AzureSettings()
