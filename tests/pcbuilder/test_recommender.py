"""Recomendador: siempre compatible, respeta presupuesto y preferencias, y prioriza según el uso."""

import pytest

from app.pcbuilder.compatibility import check_build
from app.pcbuilder.parts import Build
from app.pcbuilder.recommender import USE_CASES, Needs, performance_score, recommend, suggest_upgrades


@pytest.mark.parametrize("use_case", list(USE_CASES))
@pytest.mark.parametrize("budget", [600_000, 1_000_000, 1_800_000])
def test_siempre_compatible_completo_y_en_presupuesto(catalog, use_case, budget):
    rec = recommend(catalog, Needs(use_case, budget))
    report = check_build(rec.build)
    assert report.compatible and report.complete, report.as_dict()
    if rec.within_budget:
        assert rec.build.total_clp <= budget


def test_presupuesto_insuficiente_devuelve_el_minimo(catalog):
    rec = recommend(catalog, Needs("gaming_1440", 300_000))
    assert not rec.within_budget and rec.build.parts
    assert "minimo" in rec.alternatives


def test_preferencias_de_marca_wifi_y_tamano(catalog):
    rec = recommend(catalog, Needs("gaming_1080", 1_200_000, cpu_brand="amd", gpu_brand="nvidia", wifi=True, small=True))
    assert rec.build.one("cpu").brand == "AMD"
    assert rec.build.one("gpu").get("chip") == "NVIDIA"
    assert rec.build.one("motherboard").get("wifi") and rec.build.one("motherboard").get("form_factor") == "ITX"
    assert rec.build.one("case").get("form_factors") == ["ITX"]


def test_oficina_no_compra_tarjeta_grafica(catalog):
    rec = recommend(catalog, Needs("oficina", 450_000))
    assert rec.build.one("gpu") is None and rec.build.one("cpu").get("igpu")


def test_juegos_gasta_mas_en_tarjeta_que_en_procesador(catalog):
    rec = recommend(catalog, Needs("gaming_1440", 1_400_000))
    assert rec.build.one("gpu").price_clp > rec.build.one("cpu").price_clp


def test_mas_presupuesto_nunca_rinde_menos(catalog):
    scores = [recommend(catalog, Needs("gaming_1080", b)).score for b in (600_000, 800_000, 1_000_000, 1_400_000)]
    assert scores == sorted(scores)


def test_procesador_de_alto_consumo_no_va_en_placa_de_entrada(catalog):
    for budget in (1_400_000, 2_000_000):
        rec = recommend(catalog, Needs("edicion", budget))
        assert "vrm" not in {i.code for i in rec.report.issues}


def test_puntaje_castiga_desbalance(by_name):
    # Con la misma tarjeta tope, un procesador débil rinde mucho menos en juegos que uno equilibrado (media armónica),
    # aunque la diferencia de precio sea pequeña frente al total.
    debil = Build([by_name("Core i3-12100F"), by_name("RTX 4070 Ti SUPER")])
    fuerte = Build([by_name("Ryzen 7 7800X3D"), by_name("RTX 4070 Ti SUPER")])
    assert performance_score(debil, "gaming_1440") < performance_score(fuerte, "gaming_1440") * 0.9
    # En oficina la tarjeta no suma: solo cuenta el procesador.
    assert performance_score(debil, "oficina") == debil.one("cpu").get("cpu_score")


def test_mejoras_para_un_equipo_viejo(catalog, by_name):
    viejo = Build([by_name("Ryzen 5 3600"), by_name("B450M PRO-VDH"), by_name("FURY Beast 16GB (2x8) DDR4"), by_name("GTX 1660 SUPER"),
                   by_name("A400"), by_name("P450B"), by_name("MX330-G")])
    opciones = suggest_upgrades(viejo, catalog, "gaming_1080", 350_000)
    assert opciones
    mejor = opciones[0]
    assert mejor.cost_clp <= 350_000 and mejor.score_after > mejor.score_before and mejor.report.compatible
    # Una tarjeta nueva que necesita más fuente trae la fuente incluida en el costo.
    for opcion in opciones:
        assert check_build(Build([p for p in viejo.parts if p.slot not in opcion.remove_slots] + opcion.buy)).compatible


def test_sin_presupuesto_no_hay_mejoras(catalog, by_name):
    equipo = Build([by_name("Ryzen 5 3600"), by_name("B450M PRO-VDH"), by_name("GTX 1660 SUPER"), by_name("P450B")])
    assert suggest_upgrades(equipo, catalog, "gaming_1080", 10_000) == []
