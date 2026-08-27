from typing import List, Optional
import os
import yaml
from functools import lru_cache
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class AppConfig(BaseModel):
    name: str = "QuantAegis"
    version: str = "0.1.0"
    dry_run: bool = True
    log_level: str = "INFO"

class MT5SymbolConfig(BaseModel):
    symbol: str
    pip_value: float
    lot_step: float
    min_lot: float
    max_lot: float

class MT5Config(BaseModel):
    enabled: bool = False
    symbols: List[MT5SymbolConfig] = Field(default_factory=list)
    higher_timeframe: str = "H1"
    lower_timeframe: str = "M15"
    poll_interval_seconds: int = 15

class CryptoConfig(BaseModel):
    enabled: bool = False
    exchange: str = "binance"
    symbols: List[str] = Field(default_factory=list)
    higher_timeframe: str = "1h"
    lower_timeframe: str = "15m"

class MarketsConfig(BaseModel):
    mt5: MT5Config = Field(default_factory=MT5Config)
    crypto: CryptoConfig = Field(default_factory=CryptoConfig)

class TradingConfig(BaseModel):
    markets: MarketsConfig = Field(default_factory=MarketsConfig)

class StrategyConfig(BaseModel):
    name: str = "MultiTimeframeTrend"
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    rsi_oversold: int = 40
    rsi_overbought: int = 60
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    atr_sl_multiplier: float = 1.5
    atr_tp_multiplier: float = 3.0

class RiskConfig(BaseModel):
    risk_pct_per_trade: float = 0.01
    max_daily_drawdown_pct: float = 0.05
    max_spread_pips: float = 5.0
    max_open_trades: int = 5
    max_retries: int = 3
    retry_delay_seconds: float = 2.0

    @field_validator('risk_pct_per_trade')
    @classmethod
    def check_risk_pct(cls, v: float) -> float:
        if not 0.001 <= v <= 0.10:
            raise ValueError('risk_pct_per_trade must be between 0.001 and 0.10')
        return v

class NotifierConfig(BaseModel):
    daily_summary_time: str = "23:55"
    send_entry_alerts: bool = True
    send_exit_alerts: bool = True
    send_error_alerts: bool = True
    send_daily_summary: bool = True

class Settings(BaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    notifier: NotifierConfig = Field(default_factory=NotifierConfig)

    mt5_login: Optional[str] = Field(None, alias="MT5_LOGIN")
    mt5_password: Optional[str] = Field(None, alias="MT5_PASSWORD")
    mt5_server: Optional[str] = Field(None, alias="MT5_SERVER")
    mt5_path: Optional[str] = Field(None, alias="MT5_PATH")
    
    binance_api_key: Optional[str] = Field(None, alias="BINANCE_API_KEY")
    binance_secret: Optional[str] = Field(None, alias="BINANCE_SECRET")
    
    bybit_api_key: Optional[str] = Field(None, alias="BYBIT_API_KEY")
    bybit_secret: Optional[str] = Field(None, alias="BYBIT_SECRET")
    
    telegram_bot_token: Optional[str] = Field(None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, alias="TELEGRAM_CHAT_ID")

    # WhatsApp Settings (greenapi, ultramsg, twilio, webhook, callmebot)
    whatsapp_enabled: bool = Field(False, alias="WHATSAPP_ENABLED")
    whatsapp_provider: str = Field("greenapi", alias="WHATSAPP_PROVIDER")
    whatsapp_phone_number: Optional[str] = Field(None, alias="WHATSAPP_PHONE_NUMBER")
    whatsapp_api_key: Optional[str] = Field(None, alias="WHATSAPP_API_KEY")
    whatsapp_instance_id: Optional[str] = Field(None, alias="WHATSAPP_INSTANCE_ID")
    whatsapp_webhook_url: Optional[str] = Field(None, alias="WHATSAPP_WEBHOOK_URL")
    twilio_account_sid: Optional[str] = Field(None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(None, alias="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_from: Optional[str] = Field(None, alias="TWILIO_WHATSAPP_FROM")
    
    environment: str = Field("development", alias="ENVIRONMENT")
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True
    )

    @classmethod
    def load_config(cls, path: str = 'config.yaml') -> 'Settings':
        if os.path.exists(path):
            with open(path, 'r') as f:
                yaml_data = yaml.safe_load(f) or {}
            
            # Allow environment variables to override yaml configuration if necessary
            # For simplicity, we initialize Settings with YAML kwargs first. 
            # Note: pydantic_settings handles the env vars overlay natively if configured, 
            # but we explicitly merge dicts here.
            return cls(**yaml_data)
        return cls()

@lru_cache()
def get_settings() -> Settings:
    config_path = os.getenv('QUANTAEGIS_CONFIG_PATH', 'config.yaml')
    return Settings.load_config(config_path)
