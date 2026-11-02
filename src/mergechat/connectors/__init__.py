"""Platform connector abstractions."""

from .base import Connector
from .registry import ConnectorRegistry, ConnectResult

__all__ = ["ConnectResult", "Connector", "ConnectorRegistry"]
