"""Reglas del motor de compatibilidad: cada una con un caso que la dispara y uno que no."""

from app.pcbuilder.compatibility import check_build, estimate_power
from app.pcbuilder.parts import Build, Part


def codes(build):
    return {i.code: i.level for i in check_build(build).issues}


def test_equipo_completo_y_compatible(by_name):
    build = Build([by_name("Ryzen 5 7600"), by_name("B650M GAMING PLUS"), by_name("Vengeance 32GB (2x16) DDR5"), by_name("RTX 4060 WINDFORCE"),
                   by_name("NV3 1TB"), by_name("CV550"), by_name("4000D")])
    report = check_build(build)
    assert report.compatible and report.complete
    assert not report.errors
    assert "stock_cooler" in codes(build)


def test_socket_distinto(by_name):
    assert codes(Build([by_name("Ryzen 5 7600"), by_name("B550M PRO-VDH")]))["socket"] == "error"


def test_ddr4_en_placa_ddr5(by_name):
    c = codes(Build([by_name("Ryzen 5 7600"), by_name("B650M GAMING PLUS"), by_name("FURY Beast 16GB (2x8) DDR4")]))
    assert c["ram_type"] == "error" and c["ram_cpu"] == "error"


def test_ranuras_de_ram(by_name):
    build = Build([by_name("A520M-K"), by_name("FURY Beast 16GB (2x8) DDR4"), by_name("Vengeance LPX 32GB")])
    c = codes(build)
    assert c["ram_slots"] == "error" and c["ram_kits"] == "warning"


def test_placa_atx_en_gabinete_matx(by_name):
    assert codes(Build([by_name("TUF GAMING B650-PLUS"), by_name("Q300L")]))["form_factor"] == "error"


def test_tarjeta_demasiado_larga(by_name):
    assert codes(Build([by_name("RX 7700 XT"), by_name("Terra")]))["gpu_length"] == "error"
    assert "gpu_length" not in codes(Build([by_name("RTX 4060 WINDFORCE"), by_name("Terra")]))


def test_disipador_alto_en_gabinete_bajo(by_name):
    c = codes(Build([by_name("Ryzen 7 7800X3D"), by_name("NH-D15"), by_name("Q300L")]))
    assert c["cooler_height"] == "error"


def test_radiador_sin_lugar(by_name):
    assert codes(Build([by_name("Ryzen 7 7800X3D"), by_name("Kraken 360"), by_name("H5 Flow")]))["radiator"] == "error"


def test_procesador_sin_disipador(by_name):
    assert codes(Build([by_name("Ryzen 7 7800X3D")]))["no_cooler"] == "error"
    assert codes(Build([by_name("Ryzen 5 5600")]))["stock_cooler"] == "info"


def test_disipador_sin_anclaje(by_name):
    assert codes(Build([by_name("Core i5-14600K"), by_name("NH-L9a-AM5")]))["cooler_socket"] == "error"


def test_disipador_debil(by_name):
    assert codes(Build([by_name("Ryzen 9 7900X"), by_name("NH-L9a-AM5")]))["cooler_weak"] == "warning"


def test_sin_video(by_name):
    assert codes(Build([by_name("Core i5-12400F")]))["no_video"] == "error"
    assert "no_video" not in codes(Build([by_name("Ryzen 5 5600G")]))


def test_fuente_insuficiente_y_justa(by_name):
    insuf = Build([by_name("Core i7-14700K"), by_name("RTX 4070 Ti SUPER"), by_name("P450B")])
    assert codes(insuf)["psu_insufficient"] == "error"
    justa = Build([by_name("Ryzen 5 5600"), by_name("RX 6600"), by_name("P450B")])
    assert codes(justa)["psu_tight"] == "warning"
    load, rec = estimate_power(justa)
    assert load == 60 + 88 + 132 and rec == 500


def test_fuente_sfx_en_gabinete_atx_y_al_reves(by_name):
    assert codes(Build([by_name("RM750e"), by_name("NR200P")]))["psu_form"] == "error"


def test_ranuras_m2(by_name):
    build = Build([by_name("A520M-K"), by_name("NV3 1TB"), by_name("SN770")])
    assert codes(build)["m2_slots"] == "error"


def test_solo_disco_mecanico(by_name):
    assert codes(Build([by_name("A520M-K"), by_name("BarraCuda")]))["hdd_only"] == "warning"


def test_cuello_de_botella(by_name):
    assert codes(Build([by_name("Core i3-12100F"), by_name("RTX 4070 Ti SUPER")]))["cpu_bottleneck"] == "warning"


def test_procesador_k_en_placa_de_entrada(by_name):
    assert codes(Build([by_name("Core i7-14700K"), by_name("H610M-E")]))["vrm"] == "warning"
    assert "vrm" not in codes(Build([by_name("Core i7-14700K"), by_name("Z790-P")]))


def test_pieza_escrita_a_mano_sin_datos_no_rompe():
    build = Build([Part(slot="gpu", name="Tarjeta vieja sin ficha"), Part(slot="cpu", name="CPU sin datos")])
    report = check_build(build)
    assert report.compatible and not report.complete


def test_resumen_y_faltantes(by_name):
    report = check_build(Build([by_name("Ryzen 5 7600")]))
    data = report.as_dict()
    assert "placa madre" in data["summary"] and "motherboard" in data["missing"]
