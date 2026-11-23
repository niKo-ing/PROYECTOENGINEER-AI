"""Rutas /pc y /me/pcs con base en memoria y la semilla del armador."""

from sqlalchemy import select

from app.models.catalog import Product
from app.pcbuilder.catalog import load_parts, seed_pc_parts

from .apoyo import pid, token


def test_semilla_idempotente_y_con_precios(env):
    _, Session = env
    with Session() as db:
        parts = load_parts(db)
        assert len(parts) >= 80
        assert all(p.price_clp for p in parts if not p.legacy)
        assert all(p.price_clp is None for p in parts if p.legacy)
        again = seed_pc_parts(db)
        assert again["created"] == 0
        assert len(load_parts(db)) == len(parts)


def test_slots_componentes_y_ficha(env):
    client, Session = env
    data = client.get("/api/v1/pc/slots").json()
    assert {s["key"] for s in data["slots"]} >= {"cpu", "gpu", "psu"} and data["use_cases"]
    cpus = client.get("/api/v1/pc/components", params={"slot": "cpu"}).json()["items"]
    assert cpus and all(c["slot"] == "cpu" and not c["legacy"] for c in cpus)
    legacy = client.get("/api/v1/pc/components", params={"slot": "cpu", "include_legacy": True}).json()["items"]
    assert len(legacy) > len(cpus)
    ficha = client.get(f"/api/v1/products/{pid(Session, 'Ryzen 5 7600')}").json()
    assert ficha["specs"]["highlights"] and ficha["lowest_price_store"] == "Precio de referencia"


def test_compatibilidad_y_opciones(env):
    client, Session = env
    items = [{"slot": "cpu", "product_id": pid(Session, "Ryzen 5 7600")}, {"slot": "motherboard", "product_id": pid(Session, "B550M PRO-VDH")}]
    report = client.post("/api/v1/pc/compatibility", json={"items": items}).json()["report"]
    assert not report["compatible"] and report["issues"][0]["code"] == "socket"

    opciones = client.post("/api/v1/pc/options", json={"slot": "motherboard", "items": items[:1]}).json()["items"]
    compatibles = [o for o in opciones if o["compatible"]]
    assert compatibles and all(o["specs"]["socket"] == "AM5" for o in compatibles)
    assert opciones[0]["compatible"]  # las compatibles van primero


def test_pieza_de_otro_espacio_se_rechaza(env):
    client, Session = env
    r = client.post("/api/v1/pc/compatibility", json={"items": [{"slot": "gpu", "product_id": pid(Session, "Ryzen 5 7600")}]})
    assert r.status_code == 422


def test_recomendar(env):
    client, _ = env
    rec = client.post("/api/v1/pc/recommend", json={"use_case": "gaming_1080", "budget_clp": 900000}).json()
    assert rec["within_budget"] and rec["report"]["compatible"] and rec["total_clp"] <= 900000
    assert {i["slot"] for i in rec["items"]} >= {"cpu", "motherboard", "ram", "gpu", "storage", "psu", "case"}


def test_mis_computadores_crud_y_aislamiento(env):
    client, Session = env
    ana, beto = token(client, "ana@correo.cl"), token(client, "beto@correo.cl")
    payload = {"name": "Mi PC de la pieza", "kind": "propio", "use_case": "gaming_1080", "items": [
        {"slot": "cpu", "product_id": pid(Session, "Ryzen 5 3600")},
        {"slot": "motherboard", "product_id": pid(Session, "B450M PRO-VDH")},
        {"slot": "ram", "product_id": pid(Session, "FURY Beast 16GB (2x8) DDR4")},
        {"slot": "gpu", "product_id": pid(Session, "GTX 1660 SUPER")},
        {"slot": "storage", "name": "Disco viejo de 1 TB", "specs": {"interface": "SATA", "form": "3.5", "capacity_gb": 1000}},
        {"slot": "psu", "product_id": pid(Session, "P450B")},
        {"slot": "case", "product_id": pid(Session, "MX330-G")},
    ]}
    created = client.post("/api/v1/me/pcs", json=payload, headers=ana)
    assert created.status_code == 201, created.text
    pc = created.json()
    assert pc["report"]["compatible"] and pc["kind"] == "propio" and len(pc["items"]) == 7
    assert any(i["name"] == "Disco viejo de 1 TB" and i["product_id"] is None for i in pc["items"])

    assert client.get(f"/api/v1/me/pcs/{pc['id']}", headers=beto).status_code == 404
    assert client.get("/api/v1/me/pcs", headers=beto).json()["items"] == []
    assert client.get("/api/v1/me/pcs").status_code == 401

    edit = client.patch(f"/api/v1/me/pcs/{pc['id']}", json={"name": "PC de juegos"}, headers=ana).json()
    assert edit["name"] == "PC de juegos"

    mejoras = client.post(f"/api/v1/me/pcs/{pc['id']}/upgrades", json={"budget_clp": 400000}, headers=ana).json()
    assert mejoras["options"] and mejoras["options"][0]["gain_pct"] > 0

    assert client.delete(f"/api/v1/me/pcs/{pc['id']}", headers=ana).status_code == 204
    assert client.get("/api/v1/me/pcs", headers=ana).json()["items"] == []
