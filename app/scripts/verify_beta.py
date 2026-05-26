from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import text

from app.core.database import AsyncSessionLocal


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_PREDIO_ID = "331a61bd-9a88-497a-b3cb-19fcd5cd926f"
BBOX_PROJECTED_LA_PAZ = {
    "xmin": 590000,
    "ymin": 8170000,
    "xmax": 600000,
    "ymax": 8185000,
}
BBOX_GEOGRAPHIC_LA_PAZ = {
    "xmin": -68.18,
    "ymin": -16.54,
    "xmax": -68.08,
    "ymax": -16.44,
}
WATCH_TABLES = ("appraisal_case", "predio_manual_data")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _feature_count(payload: dict[str, Any] | None) -> int:
    if not payload:
        return 0
    features = payload.get("features") or []
    return len(features) if isinstance(features, list) else 0


def _check(
    results: list[CheckResult],
    name: str,
    ok: bool,
    detail: str,
) -> None:
    results.append(CheckResult(name=name, ok=ok, detail=detail))


async def _count_table(table_name: str) -> int | None:
    async with AsyncSessionLocal() as db:
        exists = await db.execute(
            text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {"table_name": f"public.{table_name}"},
        )
        if not exists.scalar():
            return None

        count = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return int(count.scalar_one())


async def _snapshot_counts() -> dict[str, int | None]:
    return {table_name: await _count_table(table_name) for table_name in WATCH_TABLES}


async def _get_json(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = await client.get(path, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


async def _post_json(
    client: httpx.AsyncClient,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = await client.post(path, json=payload)
    response.raise_for_status()
    return response.json()


async def run_beta_checks(api_base_url: str, predio_id: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    before_counts = await _snapshot_counts()
    auth_token = ""

    async with httpx.AsyncClient(base_url=api_base_url, timeout=20.0) as client:
        try:
            health = await _get_json(client, "/api/v2/health")
            _check(results, "health", health.get("status") == "ok", str(health))
        except Exception as exc:  # noqa: BLE001
            _check(results, "health", False, str(exc))

        try:
            auth = await _post_json(
                client,
                "/api/v2/auth/login",
                {
                    "user": os.getenv("CATASTRO_ADMIN_USER", "admin"),
                    "password": os.getenv("CATASTRO_ADMIN_PASSWORD", "change-this-local-password"),
                },
            )
            auth_token = auth.get("access_token") or ""
            _check(results, "auth", auth.get("user") is not None, f"user={auth.get('user')}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "auth", False, str(exc))

        try:
            beta_unauthenticated = await client.get("/api/v2/beta/consultas", params={"limit": 1})
            _check(
                results,
                "beta_admin_protegida",
                beta_unauthenticated.status_code == 401,
                f"status={beta_unauthenticated.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            _check(results, "beta_admin_protegida", False, str(exc))

        try:
            beta_summary = await _get_json(
                client,
                "/api/v2/beta/consultas/resumen",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            beta_list = await _get_json(
                client,
                "/api/v2/beta/consultas",
                {"limit": 5},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            _check(
                results,
                "beta_admin_dashboard",
                "total_consultas" in beta_summary and "items" in beta_list,
                (
                    f"total={beta_summary.get('total_consultas')} "
                    f"visibles={len(beta_list.get('items') or [])}"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            _check(results, "beta_admin_dashboard", False, str(exc))

        try:
            beta_export = await client.get(
                "/api/v2/beta/consultas/export/csv",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            _check(
                results,
                "beta_admin_export_csv",
                beta_export.status_code == 200 and "beta_submission_id" in beta_export.text,
                f"status={beta_export.status_code} bytes={len(beta_export.content)}",
            )
        except Exception as exc:  # noqa: BLE001
            _check(results, "beta_admin_export_csv", False, str(exc))

        try:
            predios_codigo = await _get_json(
                client,
                "/api/v1/predios/search",
                {"q": "331a", "limit": 3},
            )
            count = _feature_count(predios_codigo)
            _check(results, "busqueda_codigo", count > 0, f"features={count}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "busqueda_codigo", False, str(exc))

        try:
            otb_options = await _get_json(
                client,
                "/api/v1/predios/otbs/options",
                {"q": "SOPO", "limit": 5},
            )
            items = otb_options.get("items") or []
            first_name = items[0].get("nombre") if items else "sin_resultado"
            _check(results, "opciones_otb", len(items) > 0, f"items={len(items)} first={first_name}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "opciones_otb", False, str(exc))

        try:
            predios_otb = await _get_json(
                client,
                "/api/v1/predios/search",
                {"otb": "SOPOCACHI", "limit": 3},
            )
            count = _feature_count(predios_otb)
            _check(results, "busqueda_otb", count > 0, f"features={count}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "busqueda_otb", False, str(exc))

        try:
            predios_zona = await _get_json(
                client,
                "/api/v1/predios/search",
                {"q": "SOPOCACHI", "limit": 3},
            )
            count = _feature_count(predios_zona)
            _check(results, "busqueda_zona_texto", count > 0, f"features={count}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "busqueda_zona_texto", False, str(exc))

        try:
            predios_bbox = await _get_json(
                client,
                "/api/v1/predios/bbox",
                {**BBOX_PROJECTED_LA_PAZ, "limit": 10},
            )
            count = _feature_count(predios_bbox)
            _check(results, "capa_predios_bbox", count > 0, f"features={count}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "capa_predios_bbox", False, str(exc))

        try:
            manzanas_bbox = await _get_json(
                client,
                "/api/v1/manzanas/bbox",
                BBOX_PROJECTED_LA_PAZ,
            )
            count = _feature_count(manzanas_bbox)
            _check(results, "capa_manzanas_bbox", count > 0, f"features={count}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "capa_manzanas_bbox", False, str(exc))

        try:
            otb_feature = await _get_json(
                client,
                "/api/v1/predios/otbs/feature",
                {"name": "SOPOCACHI"},
            )
            count = _feature_count(otb_feature)
            _check(results, "feature_otb", count > 0, f"features={count}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "feature_otb", False, str(exc))

        try:
            gis_otbs = await _get_json(
                client,
                "/api/v2/gis/capas/otbs/bbox",
                {**BBOX_GEOGRAPHIC_LA_PAZ, "limit": 5},
            )
            count = _feature_count(gis_otbs)
            _check(results, "capa_gis_otbs", count > 0, f"features={count}")
        except Exception as exc:  # noqa: BLE001
            _check(results, "capa_gis_otbs", False, str(exc))

        try:
            contexto = await _get_json(client, f"/api/v2/predios/{predio_id}/contexto-gis")
            ok = contexto.get("predio_id") == predio_id and contexto.get("superficie_calculo") is not None
            detail = (
                f"superficie={contexto.get('superficie_calculo')} "
                f"zona={contexto.get('zona_tributaria_codigo')} "
                f"riesgo={contexto.get('riesgo_final')}"
            )
            _check(results, "contexto_gis", ok, detail)
        except Exception as exc:  # noqa: BLE001
            _check(results, "contexto_gis", False, str(exc))

        preview_payload = {
            "predio_id": predio_id,
            "gestion_anio": 2026,
            "avaluo_tipo": "FISCAL",
            "bloques": [],
            "usuario": "consulta_publica",
        }
        try:
            preview = await _post_json(client, "/api/v2/avaluos/preview", preview_payload)
            ok = preview.get("preview") is True and preview.get("base_imponible", 0) > 0
            _check(
                results,
                "avaluo_preview",
                ok,
                f"base={preview.get('base_imponible')} impuesto={preview.get('impuesto_estimado')}",
            )
        except Exception as exc:  # noqa: BLE001
            _check(results, "avaluo_preview", False, str(exc))

        calculate_payload = {
            **preview_payload,
            "persistir_override": False,
        }
        try:
            calculated = await _post_json(client, "/api/v2/avaluos/calcular", calculate_payload)
            ok = calculated.get("preview") is True and calculated.get("base_imponible", 0) > 0
            _check(
                results,
                "avaluo_calcular_sin_persistir",
                ok,
                f"preview={calculated.get('preview')} base={calculated.get('base_imponible')}",
            )
        except Exception as exc:  # noqa: BLE001
            _check(results, "avaluo_calcular_sin_persistir", False, str(exc))

    after_counts = await _snapshot_counts()
    changed_tables = [
        f"{table}: {before_counts.get(table)} -> {after_counts.get(table)}"
        for table in WATCH_TABLES
        if before_counts.get(table) != after_counts.get(table)
    ]
    _check(
        results,
        "base_sin_registros_de_prueba",
        not changed_tables,
        "sin cambios" if not changed_tables else "; ".join(changed_tables),
    )

    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verifica la beta local sin persistir avaluos.")
    parser.add_argument(
        "--api",
        default=os.getenv("CATASTRO_API_BASE_URL", DEFAULT_API_BASE_URL),
        help="URL base del backend FastAPI.",
    )
    parser.add_argument(
        "--predio-id",
        default=os.getenv("CATASTRO_TEST_PREDIO_ID", DEFAULT_PREDIO_ID),
        help="Predio estable usado para contexto y avaluo.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    results = asyncio.run(run_beta_checks(args.api.rstrip("/"), args.predio_id))
    failed = [result for result in results if not result.ok]

    print("Verificacion beta local")
    print(f"API: {args.api.rstrip('/')}")
    print(f"Predio test: {args.predio_id}")
    print("")
    for result in results:
        status = "OK" if result.ok else "ERROR"
        print(f"[{status}] {result.name}: {result.detail}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
