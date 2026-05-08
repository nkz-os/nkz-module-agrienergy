"""
AgriEnergy Orchestrator Backend - Configuration

Environment-based configuration using pydantic-settings.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "AgriEnergy Orchestrator"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # API
    api_prefix: str = "/api/agrienergy"
    cors_origins: list[str] = []  # Set via CORS_ORIGINS env var; empty = deny all cross-origin

    # Keycloak / JWT Authentication
    keycloak_url: str = "https://auth.example.com/auth"  # Override via KEYCLOAK_URL
    keycloak_realm: str = "nekazari"
    jwt_audience: str = "account"
    jwt_issuer: str = ""  # Auto-derived from keycloak_url + realm if empty
    
    # Service-to-service authentication
    module_management_key: str = ""

    # Context Broker (Orion-LD) for creating entities (e.g. AgriSolarPark). If empty, create_entity is no-op.
    context_broker_url: str = ""  # e.g. http://orion-ld:1026/ngsi-ld/v1

    # NGSI-LD @context URL (set via CONTEXT_URL env var in K8s). Used in Link header
    # when sending application/json to Orion-LD. ETSI NGSI-LD mandatory.
    context_url: str = ""  # e.g. https://nkz.robotika.cloud/ngsi-ld-context.json

    # N8N webhook for daily aggregation (Odoo/FinBridge). If empty, FinBridgeEmitter uses in-cluster default.
    agrienergy_n8n_webhook_url: str = ""  # e.g. https://n8n.example.com/webhook/agrienergy-aggregation

    # Database (optional - uncomment if using)
    # database_url: str = ""
    
    # Redis (for caching/celery - optional)
    # redis_url: str = ""
    
    @property
    def jwt_issuer_url(self) -> str:
        """Get the JWT issuer URL."""
        if self.jwt_issuer:
            return self.jwt_issuer
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"
    
    @property
    def jwks_url(self) -> str:
        """Get the JWKS URL for token verification."""
        return f"{self.jwt_issuer_url}/protocol/openid-connect/certs"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
