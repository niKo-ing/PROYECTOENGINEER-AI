"""Ayudas compartidas por las pruebas de rutas del armador."""

from sqlalchemy import select

from app.models.catalog import Product


def pid(Session, fragment):
    with Session() as db:
        return db.scalar(select(Product.id).where(Product.name.contains(fragment)))


def token(client, email="u@correo.cl"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "clave-segura-123", "display_name": "Usuario"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
