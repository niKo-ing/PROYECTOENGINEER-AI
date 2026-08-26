"""Paris connector — HTTP + RSC payload extraction for Next.js product pages."""

from app.ingestion.connectors.paris.connector import ParisConnector
from app.ingestion.connectors.paris.parser import ParisRSCParser, RawProductData

__all__ = ["ParisConnector", "ParisRSCParser", "RawProductData"]
