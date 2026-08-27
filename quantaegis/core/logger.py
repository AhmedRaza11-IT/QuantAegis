import logging
import sys
from typing import Any
import structlog
from contextvars import ContextVar
from contextlib import contextmanager

from quantaegis.core.config import get_settings

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
trade_symbol: ContextVar[str] = ContextVar("trade_symbol", default="")
trade_order_id: ContextVar[str] = ContextVar("trade_order_id", default="")

def add_context_vars(logger: structlog.BoundLogger, method_name: str, event_dict: dict) -> dict:
    cid = correlation_id.get()
    if cid:
        event_dict["correlation_id"] = cid
    
    sym = trade_symbol.get()
    if sym:
        event_dict["symbol"] = sym
        
    oid = trade_order_id.get()
    if oid:
        event_dict["order_id"] = oid
        
    return event_dict

def configure_logger() -> None:
    settings = get_settings()
    log_level = getattr(logging, settings.app.log_level.upper(), logging.INFO)
    
    is_prod = settings.environment.lower() == "production"

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        add_context_vars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_prod:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

@contextmanager
def bind_trade_context(symbol: str, order_id: str):
    sym_token = trade_symbol.set(symbol)
    oid_token = trade_order_id.set(order_id)
    try:
        yield
    finally:
        trade_symbol.reset(sym_token)
        trade_order_id.reset(oid_token)

def get_logger(name: str) -> structlog.BoundLogger:
    if not structlog.is_configured():
        configure_logger()
    return structlog.get_logger(name)
