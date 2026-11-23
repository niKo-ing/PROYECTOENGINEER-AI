"""SP Digital cerró: el conector ya no se registra en app/main.py ni en app/routers/admin.py. Se conserva como
ejemplo de conector y para las pruebas del pipeline de ingesta. Los precios de tiendas vienen de SoloTodo
(app/pcbuilder/solotodo.py)."""

"""SP Digital connector — HTTP + meta tag extraction for VTEX product pages."""

from app.ingestion.connectors.spdigital.connector import SPDigitalConnector
from app.ingestion.connectors.spdigital.parser import RawProductData, SPDigitalParser

__all__ = ["SPDigitalConnector", "SPDigitalParser", "RawProductData"]
