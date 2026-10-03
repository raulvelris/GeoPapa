"""
data_service.py

Carga en memoria, UNA sola vez, el CSV de predicciones y expone utilidades
de acceso. Es la única capa que toca el DataFrame directamente; el resto
del backend (tools, endpoints, chat) siempre pasa por aquí.

Reglas que este módulo garantiza:
- El CSV original NUNCA se modifica en disco (se lee en modo solo lectura;
  las columnas derivadas se agregan solo a la copia en memoria).
- Se agregan exactamente dos columnas derivadas:
    * rendimiento_estimado_t_ha = max(prediccion_modelo_final_t_ha, 0)
    * ajustado_por_valor_negativo = True si se aplicó el clip
- El target de referencia (rendimiento_referencia_mapspam_t_ha) y la
  predicción del modelo (prediccion_modelo_final_t_ha /
  rendimiento_estimado_t_ha) se mantienen siempre en campos separados.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from typing import Optional

import pandas as pd

from config import (
    CSV_PREDICCIONES_PATH,
    COL_GRID_CODE,
    COL_X,
    COL_Y,
    COL_DEPARTAMENTO,
    COL_PROVINCIA,
    COL_PREDICCION_BRUTA,
    COL_RENDIMIENTO_ESTIMADO,
    COL_AJUSTADO_NEGATIVO,
)


class ZonaNoEncontradaError(Exception):
    """La celda/grid_code solicitada no existe en el dataset."""


class DepartamentoNoEncontradoError(Exception):
    """El departamento solicitado no existe en el dataset (ADM1_NAME)."""


def _normalizar_texto(texto: str) -> str:
    """Minúsculas y sin tildes, para hacer matching robusto de nombres
    geográficos (ej. 'Junín' vs 'junin')."""
    if texto is None:
        return ""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto


class DataService:
    """Contenedor único del DataFrame de predicciones, cargado en memoria."""

    def __init__(self, csv_path=CSV_PREDICCIONES_PATH):
        self.csv_path = csv_path
        self.df = self._cargar_dataframe(csv_path)

        # Índices auxiliares para búsquedas rápidas y normalizadas.
        self._df_por_depto_normalizado = {
            _normalizar_texto(d): d for d in self.df[COL_DEPARTAMENTO].unique()
        }
        self._df_por_provincia_normalizado = {
            _normalizar_texto(p): p for p in self.df[COL_PROVINCIA].unique()
        }

    @staticmethod
    def _cargar_dataframe(csv_path) -> pd.DataFrame:
        df = pd.read_csv(csv_path)

        # --- columnas derivadas (solo en memoria, no se escribe a disco) ---
        df[COL_AJUSTADO_NEGATIVO] = df[COL_PREDICCION_BRUTA] < 0
        df[COL_RENDIMIENTO_ESTIMADO] = df[COL_PREDICCION_BRUTA].clip(lower=0)

        # grid_code como índice adicional (rápido) sin perder la columna
        df = df.set_index(COL_GRID_CODE, drop=False)
        return df

    # ------------------------------------------------------------------
    # Acceso por zona individual
    # ------------------------------------------------------------------
    def obtener_fila(self, grid_code: int) -> pd.Series:
        try:
            return self.df.loc[int(grid_code)]
        except (KeyError, ValueError, TypeError):
            raise ZonaNoEncontradaError(
                f"No existe la celda con grid_code={grid_code} en el dataset."
            )

    def existe_grid_code(self, grid_code) -> bool:
        try:
            return int(grid_code) in self.df.index
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Resolución de nombres geográficos (departamento / provincia)
    # ------------------------------------------------------------------
    def resolver_departamento(self, nombre: str) -> Optional[str]:
        """Devuelve el nombre EXACTO del departamento tal como aparece en el
        CSV (ADM1_NAME), o None si no hay coincidencia exacta normalizada."""
        return self._df_por_depto_normalizado.get(_normalizar_texto(nombre))

    def resolver_provincia(self, nombre: str) -> Optional[str]:
        return self._df_por_provincia_normalizado.get(_normalizar_texto(nombre))

    def departamentos_disponibles(self) -> list[str]:
        return sorted(self.df[COL_DEPARTAMENTO].unique().tolist())

    def provincias_disponibles(self, departamento: Optional[str] = None) -> list[str]:
        if departamento is None:
            return sorted(self.df[COL_PROVINCIA].unique().tolist())
        dep_exacto = self.resolver_departamento(departamento)
        if dep_exacto is None:
            raise DepartamentoNoEncontradoError(
                f"Departamento no encontrado: '{departamento}'."
            )
        sub = self.df[self.df[COL_DEPARTAMENTO] == dep_exacto]
        return sorted(sub[COL_PROVINCIA].unique().tolist())

    # ------------------------------------------------------------------
    # Filtro por departamento (para estadísticas / ranking)
    # ------------------------------------------------------------------
    def filtrar_por_departamento(self, departamento: str) -> pd.DataFrame:
        dep_exacto = self.resolver_departamento(departamento)
        if dep_exacto is None:
            raise DepartamentoNoEncontradoError(
                f"Departamento no encontrado: '{departamento}'. "
                f"Departamentos disponibles: {', '.join(self.departamentos_disponibles())}."
            )
        return self.df[self.df[COL_DEPARTAMENTO] == dep_exacto]

    # ------------------------------------------------------------------
    # Búsqueda libre por texto (departamento, provincia o grid_code)
    # ------------------------------------------------------------------
    def buscar_por_texto(self, texto: str) -> pd.DataFrame:
        """Busca coincidencias por substring normalizado en departamento o
        provincia; si el texto es numérico, intenta también como grid_code
        exacto. Devuelve un DataFrame (posiblemente vacío)."""
        texto_norm = _normalizar_texto(texto)

        if texto.strip().isdigit() and self.existe_grid_code(texto.strip()):
            return self.df.loc[[int(texto.strip())]]

        mask_depto = self.df[COL_DEPARTAMENTO].apply(
            lambda v: texto_norm in _normalizar_texto(v)
        )
        mask_prov = self.df[COL_PROVINCIA].apply(
            lambda v: texto_norm in _normalizar_texto(v)
        )
        return self.df[mask_depto | mask_prov]

    # ------------------------------------------------------------------
    # Datos mínimos para visualización cartográfica
    # ------------------------------------------------------------------
    def obtener_datos_mapa(self) -> list[dict]:
        """Devuelve las celdas necesarias para el frontend Leaflet.

        El dataset MapSPAM usa una grilla de 5 minutos de arco (1/12 grado).
        x/y representan el centro de cada celda, por lo que se calcula un
        rectángulo de ±1/24 grado para dibujar la celda sin enviar las 92
        variables del dataset al navegador.
        """
        half_cell = 1.0 / 24.0
        columnas = [
            COL_GRID_CODE,
            COL_X,
            COL_Y,
            COL_DEPARTAMENTO,
            COL_PROVINCIA,
            COL_RENDIMIENTO_ESTIMADO,
            COL_AJUSTADO_NEGATIVO,
        ]
        sub = self.df[columnas]

        resultado = []
        for fila in sub.itertuples(index=False):
            grid_code, x, y, departamento, provincia, rendimiento, ajustado = fila
            x = float(x)
            y = float(y)
            resultado.append({
                "grid_code": int(grid_code),
                "x": x,
                "y": y,
                "departamento": str(departamento),
                "provincia": str(provincia),
                "rendimiento_estimado_t_ha": round(float(rendimiento), 4),
                "ajustado_por_valor_negativo": bool(ajustado),
                "limites": {
                    "south": y - half_cell,
                    "west": x - half_cell,
                    "north": y + half_cell,
                    "east": x + half_cell,
                },
            })
        return resultado


@lru_cache(maxsize=1)
def get_data_service() -> DataService:
    """Punto único de acceso al servicio (carga perezosa, una sola vez por
    proceso). Usar siempre esta función en vez de instanciar DataService
    directamente, para no recargar el CSV en cada request."""
    return DataService()
