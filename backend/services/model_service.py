"""
model_service.py

Expone información del modelo final ÚNICAMENTE a partir de
etapa2_modelo_final_metadata.json. NO carga etapa2_modelo_final.joblib
(esa decisión quedó explícitamente fuera de alcance para esta versión).

Las métricas OOF (MAE, RMSE, R2) provienen exclusivamente de este archivo
y nunca se recalculan a partir del CSV de predicciones.
"""

from __future__ import annotations

import json
from functools import lru_cache

from config import METADATA_MODELO_PATH


@lru_cache(maxsize=1)
def _cargar_metadata() -> dict:
    with open(METADATA_MODELO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def obtener_info_modelo() -> dict:
    meta = _cargar_metadata()
    metricas = meta.get("metricas_OOF", {})
    return {
        "modelo": meta.get("modelo"),
        "conjunto_variables": meta.get("conjunto_variables"),
        "n_observaciones": meta.get("n_observaciones"),
        "n_grupos_espaciales": meta.get("n_grupos_espaciales"),
        "metricas_oof": {
            "mae_t_ha": metricas.get("MAE_t_ha"),
            "rmse_t_ha": metricas.get("RMSE_t_ha"),
            "r2": metricas.get("R2"),
        },
    }
