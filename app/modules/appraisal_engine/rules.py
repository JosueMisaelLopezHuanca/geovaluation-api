OFFICIAL_SERVICES = {
    "AGUA POTABLE",
    "ALCANTARILLADO",
    "ENERGIA ELECTRICA",
    "TELEFONO",
}


def compute_service_score(services: list[str]) -> tuple[float, list[str]]:
    official = [service for service in services if service in OFFICIAL_SERVICES]
    score = min(0.80, len(official) * 0.20)
    return round(score, 4), official


def choose_surface(
    superficie_gis: float,
    superficie_legal: float | None,
    superficie_manual: float | None,
) -> tuple[float, str]:
    if superficie_manual is not None:
        return round(float(superficie_manual), 2), "superficie_manual"
    return round(float(superficie_gis), 2), "superficie_gis"


def calculate_land_value(
    superficie_calculo: float,
    valor_unitario: float,
    puntaje_servicios: float,
    factor_pendiente: float,
) -> tuple[float, float]:
    valor_unitario_aplicado = valor_unitario * puntaje_servicios * factor_pendiente
    valor_terreno = superficie_calculo * valor_unitario_aplicado
    return round(valor_terreno, 2), round(valor_unitario_aplicado, 4)


def calculate_building_block_value(
    superficie: float,
    valor_tipologia: float,
    factor_antiguedad: float,
) -> float:
    return round(superficie * valor_tipologia * factor_antiguedad, 2)


def calculate_tax(base_imponible: float, alicuota: float) -> float:
    return round(base_imponible * alicuota, 2)

