def factor_pendiente_desde_dn(pendiente_dn: int | None) -> float:
    if pendiente_dn is None:
        return 1.0
    if pendiente_dn <= 1:
        return 1.0
    if pendiente_dn == 2:
        return 0.9
    return 0.8


def factor_riesgo_desde_dn(riesgo_dn: int | None) -> float:
    if riesgo_dn is None:
        return 1.0
    # Ajuste conservador inicial mientras no exista una tabla oficial de riesgo cargada.
    return max(0.7, 1.0 - (riesgo_dn * 0.1))


def calcular_valor_terreno(
    superficie_terreno: float,
    valor_base_m2: float,
    factor_servicios: float,
    factor_pendiente: float,
    factor_riesgo: float,
) -> tuple[float, float]:
    valor_unitario_aplicado = (
        valor_base_m2 * factor_servicios * factor_pendiente * factor_riesgo
    )
    valor_terreno = superficie_terreno * valor_unitario_aplicado
    return round(valor_terreno, 2), round(valor_unitario_aplicado, 4)


def calcular_impuesto(base_imponible: float, alicuota_impuesto: float) -> float:
    return round(base_imponible * alicuota_impuesto, 3)


def calcular_valor_construccion(
    superficie_construida: float,
    valor_tipologia_m2: float,
    factor_depreciacion: float,
) -> tuple[float, float]:
    valor_unitario_aplicado = valor_tipologia_m2 * factor_depreciacion
    valor_construccion = superficie_construida * valor_unitario_aplicado
    return round(valor_construccion, 2), round(valor_unitario_aplicado, 4)
