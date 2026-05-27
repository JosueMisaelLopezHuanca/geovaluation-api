from pathlib import Path

from app.core.sync_database import sync_engine


DEFAULT_SQL_FILES = (
    "03_predio_contexto_espacial.sql",
    "04_appraisal_v2.sql",
    "05_appraisal_v2_precision.sql",
    "06_appraisal_v2_consolidation.sql",
    "07_predio_otb_contexto.sql",
    "08_normativa_gt_2015_vigente.sql",
    "09_propiedad_horizontal_impbi_referencia.sql",
    "10_consultas_beta_publicas.sql",
)


def apply_updates() -> list[str]:
    root_dir = Path(__file__).resolve().parents[2]
    db_init_dir = root_dir / "db_init"
    applied_files: list[str] = []

    raw_connection = sync_engine.raw_connection()
    try:
        raw_connection.autocommit = True
        with raw_connection.cursor() as cursor:
            for file_name in DEFAULT_SQL_FILES:
                sql_path = db_init_dir / file_name
                cursor.execute(sql_path.read_text(encoding="utf-8"))
                raw_connection.commit()
                applied_files.append(file_name)
    finally:
        raw_connection.close()

    return applied_files


if __name__ == "__main__":
    for applied_file in apply_updates():
        print(f"Aplicado: {applied_file}")
