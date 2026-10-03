"""
geospatial_tools.py

Las 7 funciones de consulta pedidas. Son la ÚNICA vía por la que cualquier
capa superior (endpoints REST o el LLM vía tool-use) puede obtener datos
numéricos o geográficos. Ninguna de estas funciones inventa columnas: todas
leen exclusivamente de las columnas reales verificadas en config.py.

Todas devuelven dicts/listas de dicts (JSON-serializables) y lanzan
excepciones controladas (ZonaNoEncontradaError, DepartamentoNoEncontradoError)
que la capa de API (Paso 4) traducirá a códigos HTTP apropiados, y que
chat_service (Paso 5) traducirá a un mensaje de error legible para el LLM.

Ninguna función aquí recalcula MAE/RMSE/R2 ni usa el target como predictor.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from config import (
    COL_GRID_CODE,
    COL_X,
    COL_Y,
    COL_DEPARTAMENTO,
    COL_PROVINCIA,
    COL_REFERENCIA_MAPSPAM,
    COL_PREDICCION_BRUTA,
    COL_RENDIMIENTO_ESTIMADO,
    COL_AJUSTADO_NEGATIVO,
    VARIABLES_AGROECOLOGICAS,
    GRUPO_VARIABLE,
    UMBRAL_POCAS_CELDAS,
    MENSAJE_POCAS_CELDAS,
    MENSAJE_VALOR_AJUSTADO,
    LIMITE_BUSQUEDA_DEFAULT,
    LIMITE_RANKING_DEFAULT,
    LIMITE_RANKING_MAX,
)
from services.data_service import (
    get_data_service,
    DataService,
    ZonaNoEncontradaError,
    DepartamentoNoEncontradoError,
)

# Re-exportadas para que otras capas puedan importarlas desde este módulo
__all__ = [
    "ZonaNoEncontradaError",
    "DepartamentoNoEncontradoError",
    "consultar_zona",
    "buscar_zonas",
    "resumir_zona",
    "comparar_zonas",
    "ranking_rendimiento",
    "obtener_variables_agroecologicas",
    "estadisticas_departamento",
]


# ---------------------------------------------------------------------------
# Helpers internos de serialización (no son tools públicas)
# ---------------------------------------------------------------------------

def _ubicacion(fila: pd.Series) -> dict:
    return {
        "grid_code": int(fila[COL_GRID_CODE]),
        "departamento": fila[COL_DEPARTAMENTO],
        "provincia": fila[COL_PROVINCIA],
        "coordenadas": {"x": float(fila[COL_X]), "y": float(fila[COL_Y])},
    }


def _rendimiento(fila: pd.Series) -> dict:
    bloque = {
        "rendimiento_estimado_t_ha": round(float(fila[COL_RENDIMIENTO_ESTIMADO]), 4),
        "prediccion_modelo_final_t_ha_bruta": round(float(fila[COL_PREDICCION_BRUTA]), 4),
        "rendimiento_referencia_mapspam_t_ha": round(float(fila[COL_REFERENCIA_MAPSPAM]), 4),
        "ajustado_por_valor_negativo": bool(fila[COL_AJUSTADO_NEGATIVO]),
    }
    if bloque["ajustado_por_valor_negativo"]:
        bloque["nota"] = MENSAJE_VALOR_AJUSTADO
    return bloque


def _variables_agroecologicas(fila: pd.Series) -> dict:
    variables = {}
    for col in VARIABLES_AGROECOLOGICAS:
        grupo, unidad = GRUPO_VARIABLE[col]
        variables[col] = {
            "valor": round(float(fila[col]), 4),
            "grupo": grupo,
            "unidad": unidad,
        }
    return variables


def _advertencia_pocas_celdas(n_celdas: int) -> Optional[str]:
    return MENSAJE_POCAS_CELDAS if n_celdas < UMBRAL_POCAS_CELDAS else None


# ---------------------------------------------------------------------------
# 1. consultar_zona
# ---------------------------------------------------------------------------

def consultar_zona(grid_code: int, ds: Optional[DataService] = None) -> dict:
    """Ubicación, coordenadas, rendimiento estimado y principales variables
    agroecológicas de una celda."""
    ds = ds or get_data_service()
    fila = ds.obtener_fila(grid_code)  # lanza ZonaNoEncontradaError si no existe

    return {
        "ubicacion": _ubicacion(fila),
        "rendimiento": _rendimiento(fila),
        "variables_agroecologicas": _variables_agroecologicas(fila),
    }


# ---------------------------------------------------------------------------
# 2. buscar_zonas
# ---------------------------------------------------------------------------

def buscar_zonas(
    texto: str,
    limite: int = LIMITE_BUSQUEDA_DEFAULT,
    ds: Optional[DataService] = None,
) -> dict:
    """Busca por departamento, provincia o grid_code exacto. No existe nivel
    distrital en el dataset."""
    ds = ds or get_data_service()

    if not texto or not texto.strip():
        return {"total_encontrado": 0, "resultados": [], "texto_buscado": texto}

    resultados_df = ds.buscar_por_texto(texto)
    total = len(resultados_df)

    resultados = [
        {
            **_ubicacion(fila),
            "rendimiento_estimado_t_ha": round(float(fila[COL_RENDIMIENTO_ESTIMADO]), 4),
        }
        for _, fila in resultados_df.head(limite).iterrows()
    ]

    return {
        "texto_buscado": texto,
        "total_encontrado": total,
        "mostrando": len(resultados),
        "resultados": resultados,
    }


# ---------------------------------------------------------------------------
# 3. resumir_zona
# ---------------------------------------------------------------------------

def resumir_zona(grid_code: int, ds: Optional[DataService] = None) -> dict:
    """Objeto estructurado con toda la información relevante de una zona,
    pensado como contexto para que el LLM redacte una explicación en
    lenguaje natural (el LLM no debe agregar ni inferir números nuevos)."""
    ds = ds or get_data_service()
    fila = ds.obtener_fila(grid_code)

    resumen = {
        "ubicacion": _ubicacion(fila),
        "rendimiento": _rendimiento(fila),
        "variables_agroecologicas": _variables_agroecologicas(fila),
    }
    return resumen


# ---------------------------------------------------------------------------
# 4. comparar_zonas
# ---------------------------------------------------------------------------

def comparar_zonas(grid_codes: list[int], ds: Optional[DataService] = None) -> dict:
    """Compara 2 o más zonas por rendimiento estimado y variables
    agroecológicas disponibles. Los deltas se calculan respecto a la
    primera zona de la lista."""
    ds = ds or get_data_service()

    if not grid_codes or len(grid_codes) < 2:
        raise ValueError("comparar_zonas requiere al menos 2 grid_codes.")

    filas = [ds.obtener_fila(gc) for gc in grid_codes]  # lanza si alguno no existe

    zonas = []
    for fila in filas:
        zonas.append(
            {
                "ubicacion": _ubicacion(fila),
                "rendimiento": _rendimiento(fila),
                "variables_agroecologicas": _variables_agroecologicas(fila),
            }
        )

    referencia = zonas[0]
    for zona in zonas[1:]:
        zona["delta_rendimiento_estimado_t_ha"] = round(
            zona["rendimiento"]["rendimiento_estimado_t_ha"]
            - referencia["rendimiento"]["rendimiento_estimado_t_ha"],
            4,
        )
        zona["delta_variables"] = {
            var: round(
                zona["variables_agroecologicas"][var]["valor"]
                - referencia["variables_agroecologicas"][var]["valor"],
                4,
            )
            for var in VARIABLES_AGROECOLOGICAS
        }

    return {
        "zona_referencia": referencia["ubicacion"]["grid_code"],
        "zonas": zonas,
    }


# ---------------------------------------------------------------------------
# 5. ranking_rendimiento
# ---------------------------------------------------------------------------

def ranking_rendimiento(
    n: int = LIMITE_RANKING_DEFAULT,
    orden: str = "mayor",
    departamento: Optional[str] = None,
    ds: Optional[DataService] = None,
) -> dict:
    """Zonas con mayor o menor rendimiento estimado. `orden` acepta
    'mayor' o 'menor'. Si `departamento` no existe, lanza
    DepartamentoNoEncontradoError (no devuelve lista vacía silenciosa)."""
    ds = ds or get_data_service()

    orden = orden.strip().lower()
    if orden not in ("mayor", "menor"):
        raise ValueError("orden debe ser 'mayor' o 'menor'.")

    n = max(1, min(int(n), LIMITE_RANKING_MAX))

    if departamento is not None:
        df = ds.filtrar_por_departamento(departamento)  # lanza si no existe
    else:
        df = ds.df

    ascendente = orden == "menor"
    df_ordenado = df.sort_values(COL_RENDIMIENTO_ESTIMADO, ascending=ascendente)

    resultados = [
        {
            **_ubicacion(fila),
            "rendimiento_estimado_t_ha": round(float(fila[COL_RENDIMIENTO_ESTIMADO]), 4),
            "ajustado_por_valor_negativo": bool(fila[COL_AJUSTADO_NEGATIVO]),
        }
        for _, fila in df_ordenado.head(n).iterrows()
    ]

    respuesta = {
        "orden": orden,
        "n_solicitado": n,
        "departamento_filtrado": departamento,
        "total_celdas_consideradas": len(df),
        "resultados": resultados,
    }

    if departamento is not None:
        advertencia = _advertencia_pocas_celdas(len(df))
        if advertencia:
            respuesta["advertencia"] = advertencia

    return respuesta


# ---------------------------------------------------------------------------
# 6. obtener_variables_agroecologicas
# ---------------------------------------------------------------------------

def obtener_variables_agroecologicas(grid_code: int, ds: Optional[DataService] = None) -> dict:
    """Únicamente las 15 variables agroecológicas disponibles en el CSV
    (17 predictores del modelo menos las coordenadas x, y). No incluye
    variables mencionadas en el metadata como 'evaluadas' (topografía,
    clima dinámico) porque esas columnas no existen en este dataset."""
    ds = ds or get_data_service()
    fila = ds.obtener_fila(grid_code)

    return {
        "grid_code": int(fila[COL_GRID_CODE]),
        "variables_agroecologicas": _variables_agroecologicas(fila),
    }


# ---------------------------------------------------------------------------
# 7. estadisticas_departamento
# ---------------------------------------------------------------------------

def estadisticas_departamento(departamento: str, ds: Optional[DataService] = None) -> dict:
    """Cantidad de celdas y estadísticas descriptivas (promedio, mínimo,
    máximo, desviación estándar) del rendimiento estimado y, como
    contraste, del rendimiento de referencia MAPSPAM. Estas estadísticas
    NO son las métricas oficiales de desempeño del modelo (esas son
    exclusivamente las OOF del metadata) — son estadísticas descriptivas
    de los valores dentro del departamento."""
    ds = ds or get_data_service()
    df = ds.filtrar_por_departamento(departamento)  # lanza si no existe

    n_celdas = len(df)

    def _stats(col: str) -> dict:
        serie = df[col]
        return {
            "promedio": round(float(serie.mean()), 4),
            "minimo": round(float(serie.min()), 4),
            "maximo": round(float(serie.max()), 4),
            "desviacion_estandar": round(float(serie.std()) if n_celdas > 1 else 0.0, 4),
        }

    respuesta = {
        "departamento": ds.resolver_departamento(departamento),
        "n_celdas": n_celdas,
        "rendimiento_estimado_t_ha": _stats(COL_RENDIMIENTO_ESTIMADO),
        "rendimiento_referencia_mapspam_t_ha": _stats(COL_REFERENCIA_MAPSPAM),
        "n_celdas_ajustadas_por_valor_negativo": int(df[COL_AJUSTADO_NEGATIVO].sum()),
    }

    advertencia = _advertencia_pocas_celdas(n_celdas)
    if advertencia:
        respuesta["advertencia"] = advertencia

    return respuesta
