"""Endpoint de eventos SNS del worker de ingesta (EP2 ITY1102)."""

import base64
import datetime as dt
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.main import app
from app.routers import eventos

TEMA = "arn:aws:sns:us-east-1:123456789012:tb-ep2-eventos"
CERT_URL = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-prueba.pem"

client = TestClient(app)


@pytest.fixture(scope="module")
def llave_y_cert():
    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    ahora = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(llave.public_key())
        .serial_number(1)
        .not_valid_before(ahora)
        .not_valid_after(ahora + dt.timedelta(days=1))
        .sign(llave, hashes.SHA256())
    )
    return llave, cert


@pytest.fixture(autouse=True)
def entorno(monkeypatch, llave_y_cert):
    monkeypatch.setenv("SNS_TOPIC_ARN_EVENTOS", TEMA)
    monkeypatch.setenv("INGESTION_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(eventos, "_certificado", lambda url: llave_y_cert[1])
    llamadas = []
    monkeypatch.setattr(eventos, "_sincronizar_tiendas", lambda: llamadas.append(1))
    return llamadas


def _firmado(llave, **campos):
    mensaje = {
        "Type": "Notification",
        "MessageId": "abc",
        "TopicArn": TEMA,
        "Message": json.dumps({"tipo": "ingesta_programada"}),
        "Timestamp": "2026-10-25T12:00:00.000Z",
        "SignatureVersion": "2",
        "SigningCertURL": CERT_URL,
        **campos,
    }
    firma = llave.sign(eventos._texto_a_firmar(mensaje), padding.PKCS1v15(), hashes.SHA256())
    mensaje["Signature"] = base64.b64encode(firma).decode()
    return mensaje


def _enviar(mensaje):
    return client.post("/api/v1/eventos/sns", content=json.dumps(mensaje), headers={"Content-Type": "text/plain"})


def test_notificacion_firmada_encola_la_ingesta(llave_y_cert, entorno):
    respuesta = _enviar(_firmado(llave_y_cert[0]))
    assert respuesta.status_code == 202
    assert respuesta.json() == {"estado": "ingesta_encolada"}
    assert entorno == [1]


def test_firma_alterada_se_rechaza(llave_y_cert, entorno):
    mensaje = _firmado(llave_y_cert[0])
    mensaje["Message"] = "otro contenido"
    assert _enviar(mensaje).status_code == 403
    assert entorno == []


def test_tema_distinto_se_rechaza(llave_y_cert):
    mensaje = _firmado(llave_y_cert[0], TopicArn="arn:aws:sns:us-east-1:999:otro")
    assert _enviar(mensaje).status_code == 403


def test_certificado_fuera_de_sns_se_rechaza(llave_y_cert):
    mensaje = _firmado(llave_y_cert[0], SigningCertURL="https://evil.example.com/cert.pem")
    assert _enviar(mensaje).status_code == 403


def test_en_las_replicas_de_la_api_no_existe(llave_y_cert, monkeypatch):
    monkeypatch.setenv("INGESTION_SCHEDULER_ENABLED", "false")
    assert _enviar(_firmado(llave_y_cert[0])).status_code == 404


def test_sin_tema_configurado_no_existe(llave_y_cert, monkeypatch):
    monkeypatch.delenv("SNS_TOPIC_ARN_EVENTOS")
    assert _enviar(_firmado(llave_y_cert[0])).status_code == 404


def test_health_indica_la_replica(monkeypatch):
    monkeypatch.setenv("INSTANCIA", "i-123")
    monkeypatch.setenv("ZONA", "us-east-1a")
    assert client.get("/health").json()["instancia"] == "i-123"
