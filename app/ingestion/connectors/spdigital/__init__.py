"""SP Digital connector — HTTP + meta tag extraction for VTEX product pages."""

from app.ingestion.connectors.spdigital.connector import SPDigitalConnector
from app.ingestion.connectors.spdigital.parser import RawProductData, SPDigitalParser

__all__ = ["SPDigitalConnector", "SPDigitalParser", "RawProductData"]
