"""Rutas del panel de observabilidad (solo admin) y de los derechos sobre los datos (descargar y borrar)."""

import dataclasses

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.main import app
from app.models.account import UserAccount
from app.models.observability import AgentRun
from app.models.pc import PcBuild
from app.routers.pc import get_assistant_llm

from .apoyo import pid, token


@pytest.fixture()
def sin_modelo():
    app.dependency_overrides[get_assistant_llm] = lambda: None
    yield
    app.dependency_overrides.pop(get_assistant_llm, None)


def test_panel_pide_admin_y_muestra_la_traza(env, sin_modelo, monkeypatch):
    client, _ = env
    ana, beto = token(client, "ana@correo.cl"), token(client, "beto@correo.cl")
    r = client.post("/api/v1/pc/assistant", json={"messages": [{"role": "user", "content": "pc para programar con 700 mil"}]}, headers=ana).json()
    assert client.get("/api/v1/observability/metrics").status_code == 401

    monkeypatch.setattr("app.core.security.settings", dataclasses.replace(settings, admin_emails="ana@correo.cl"))
    assert client.get("/api/v1/observability/metrics", headers=beto).status_code == 403
    data = client.get("/api/v1/observability/metrics", params={"hours": 1}, headers=ana).json()
    assert data["summary"]["runs"] == 1 and data["summary"]["by_flow"]["asistente_pc"]["runs"] == 1
    assert {s["key"] for s in data["slo"]} >= {"latencia_p95", "tasa_error"}

    detalle = client.get(f"/api/v1/observability/runs/{r['run_id']}", headers=ana).json()
    assert {s["name"] for s in detalle["spans"]} >= {"entender", "recomendador", "rag_guias", "explicar"}
    assert detalle["input_preview"] == "pc para programar con 700 mil"
    assert client.get("/api/v1/observability/runs/nada", headers=ana).status_code == 404
    assert client.get("/api/v1/observability/runs", params={"status": "ok"}, headers=ana).json()["items"][0]["run_id"] == r["run_id"]
    assert "todobarato_ai_runs_total" in client.get("/api/v1/observability/prometheus", headers=ana).text


def test_descargar_y_borrar_mis_datos(env, sin_modelo):
    client, Session = env
    ana, beto = token(client, "ana@correo.cl"), token(client, "beto@correo.cl")
    items = [{"slot": "cpu", "product_id": pid(Session, "Ryzen 5 5600")}]
    client.post("/api/v1/me/pcs", json={"name": "Mi PC", "items": items}, headers=ana)
    client.post("/api/v1/me/pcs", json={"name": "PC de Beto", "items": items}, headers=beto)
    client.post("/api/v1/pc/assistant", json={"messages": [{"role": "user", "content": "pc para oficina con 400 mil"}]}, headers=ana)

    datos = client.get("/api/v1/me/data", headers=ana).json()
    assert datos["account"]["email"] == "ana@correo.cl" and [c["name"] for c in datos["computers"]] == ["Mi PC"]
    assert datos["ai_usage"]["runs"] == 1

    assert client.request("DELETE", "/api/v1/me/data", json={"confirm": "si"}, headers=ana).status_code == 422
    borrado = client.request("DELETE", "/api/v1/me/data", json={"confirm": "BORRAR"}, headers=ana).json()
    assert borrado["deleted"]["pc_builds"] == 1 and borrado["deleted"]["agent_runs"] == 1 and borrado["account_deleted"]

    with Session() as db:
        assert [pc.name for pc in db.scalars(select(PcBuild))] == ["PC de Beto"]
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 0
        assert db.scalar(select(UserAccount).where(UserAccount.email == "ana@correo.cl")) is None
    login = client.post("/api/v1/auth/login", json={"email": "ana@correo.cl", "password": "clave-segura-123"})
    assert login.status_code == 401
