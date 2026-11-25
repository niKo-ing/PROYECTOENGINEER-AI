"""Cuentas propias: hash de contraseñas, tokens y rutas /auth."""

import time

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import local_auth
from app.core.local_auth import decode_local_token, hash_password, is_local_token, issue_token, verify_password
from app.core.security import validate_token
from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_PER_MINUTE", "1000")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_hash_y_verificacion():
    stored = hash_password("clave-segura-123")
    assert stored.startswith("scrypt$") and "clave-segura-123" not in stored
    assert verify_password("clave-segura-123", stored)
    assert not verify_password("otra-clave", stored)
    assert not verify_password("x", "formato-raro")


def test_dos_hashes_de_la_misma_clave_son_distintos():
    assert hash_password("misma-clave-1") != hash_password("misma-clave-1")


def test_token_propio_se_valida_y_vence():
    token, ttl = issue_token("u-1", "a@b.cl", "Ana")
    assert is_local_token(token)
    assert decode_local_token(token)["sub"] == "u-1"
    assert validate_token(token).email == "a@b.cl"
    viejo, _ = issue_token("u-1", "a@b.cl", now=time.time() - ttl - 10)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_local_token(viejo)


def test_token_firmado_con_otro_secreto_se_rechaza():
    falso = jwt.encode({"iss": local_auth.LOCAL_ISSUER, "aud": local_auth.LOCAL_AUDIENCE, "sub": "x", "exp": time.time() + 60}, "otro-secreto", algorithm="HS256")
    with pytest.raises(Exception):
        validate_token(falso)


def test_registro_login_y_me(client):
    r = client.post("/api/v1/auth/register", json={"email": "Ana@Correo.cl", "password": "clave-segura-123", "display_name": "  Ana   Pérez "})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "ana@correo.cl" and body["user"]["display_name"] == "Ana Pérez"

    assert client.post("/api/v1/auth/register", json={"email": "ana@correo.cl", "password": "clave-segura-123", "display_name": "Ana"}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"email": "ana@correo.cl", "password": "mala"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "nadie@correo.cl", "password": "mala"}).json()["detail"] == "Correo o contraseña incorrectos"

    login = client.post("/api/v1/auth/login", json={"email": "ANA@correo.cl", "password": "clave-segura-123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["display_name"] == "Ana Pérez"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_registro_valida_clave_y_correo(client):
    assert client.post("/api/v1/auth/register", json={"email": "b@correo.cl", "password": "corta", "display_name": "Bea"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={"email": "sin-arroba", "password": "clave-segura-123", "display_name": "Bea"}).status_code == 422


def test_token_propio_abre_el_perfil(client):
    token = client.post("/api/v1/auth/register", json={"email": "c@correo.cl", "password": "clave-segura-123", "display_name": "Caro"}).json()["access_token"]
    r = client.get("/api/v1/me/profile", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (200, 404)
