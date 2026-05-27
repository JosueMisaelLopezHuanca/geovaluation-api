OFFICIAL_SERVICES = {
    "AGUA POTABLE",
    "ALCANTARILLADO",
    "ENERGIA ELECTRICA",
    "TELEFONO",
}

APPRAISAL_FISCAL = "FISCAL"
APPRAISAL_COMERCIAL = "COMERCIAL"
MINIMUM_SERVICE_FACTOR = 0.20
MAXIMUM_SERVICE_FACTOR = 0.80

ALL_SERVICES = {
    "AGUA POTABLE",
    "ALCANTARILLADO",
    "ENERGIA ELECTRICA",
    "TELEFONO",
    "GAS DOMICILIARIO",
    "INTERNET",
    "ALUMBRADO PUBLICO",
}


def compute_service_score(services: list[str]) -> tuple[float, list[str]]:
    official = [service for service in services if service in OFFICIAL_SERVICES]
    score = max(MINIMUM_SERVICE_FACTOR, min(MAXIMUM_SERVICE_FACTOR, len(official) * 0.20))
    return round(score, 4), official


def compute_slope_class_factor(pendiente_codigo: int | None) -> float:
    if pendiente_codigo is None or pendiente_codigo <= 1:
        return 1.0
    if pendiente_codigo == 2:
        return 0.9
    return 0.8


def choose_surface(
    superficie_gis: float,
    superficie_legal: float | None,
    superficie_manual: float | None,
) -> tuple[float, str]:
    if superficie_manual is not None:
        return round(float(superficie_manual), 2), "superficie_manual"
    if superficie_legal is not None:
        return round(float(superficie_legal), 2), "superficie_legal"
    return round(float(superficie_gis), 2), "superficie_gis"


def choose_value(manual_value, official_value, automatic_value=None, *, manual_enabled: bool = True):
    if manual_enabled and manual_value is not None:
        return manual_value, "manual"
    if official_value is not None:
        return official_value, "oficial"
    return automatic_value, "automatico"


def compute_difference(superficie_gis: float, superficie_legal: float | None) -> dict:
    if superficie_legal is None or superficie_legal == 0:
        return {
            "diferencia": 0.0,
            "porcentaje_diferencia": None,
            "clasificacion": "SIN_BASE_LEGAL",
            "color": "gris",
        }

    diferencia = abs(float(superficie_gis) - float(superficie_legal))
    porcentaje = (diferencia / float(superficie_legal)) * 100
    if porcentaje < 5:
        clasificacion, color = "OK", "verde"
    elif porcentaje <= 15:
        clasificacion, color = "REVISAR", "amarillo"
    else:
        clasificacion, color = "CRITICO", "rojo"
    return {
        "diferencia": round(diferencia, 2),
        "porcentaje_diferencia": round(porcentaje, 2),
        "clasificacion": clasificacion,
        "color": color,
    }


def calculate_land_value(
    superficie_calculo: float,
    valor_unitario: float,
    puntaje_servicios: float,
    factor_pendiente: float,
    avaluo_tipo: str = APPRAISAL_FISCAL,
    factor_riesgo: float = 1.0,
    coeficiente_comercial: float = 1.0,
    factor_esquina: float = 1.0,
    factor_avenida: float = 1.0,
    factor_forma: float = 1.0,
    factor_uso: float = 1.0,
    ajuste_comercial: float = 1.0,
) -> tuple[float, float]:
    valor_unitario_aplicado = valor_unitario * puntaje_servicios * factor_pendiente

    if avaluo_tipo == APPRAISAL_COMERCIAL:
        valor_unitario_aplicado *= (
            factor_riesgo
            * coeficiente_comercial
            * factor_esquina
            * factor_avenida
            * factor_forma
            * factor_uso
            * ajuste_comercial
        )

    valor_terreno = superficie_calculo * valor_unitario_aplicado
    return round(valor_terreno, 2), round(valor_unitario_aplicado, 4)


def calculate_building_block_value(
    superficie: float,
    valor_tipologia: float,
    factor_antiguedad: float,
    factor_estado: float = 1.0,
) -> float:
    return round(superficie * valor_tipologia * factor_antiguedad * factor_estado, 2)


def calculate_tax(base_imponible: float, alicuota: float) -> float:
    return round(base_imponible * alicuota, 2)


def calculate_progressive_tax(
    base_imponible: float,
    cuota_fija: float,
    alicuota_excedente: float,
    limite_inferior: float,
) -> float:
    excedente = max(0.0, float(base_imponible) - float(limite_inferior))
    return round(float(cuota_fija) + excedente * float(alicuota_excedente), 2)
