"""
Schemas Pydantic compartidos entre varios endpoints.

Los nombres de campo aquí son estables a propósito (coinciden 1:1 con las
claves que ya devuelven las funciones de tools/geospatial_tools.py) para no
romper al frontend una vez que empiece a consumir la API.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field


class Coordenadas(BaseModel):
    x: float
    y: float


class Ubicacion(BaseModel):
    grid_code: int
    departamento: str
    provincia: str
    coordenadas: Coordenadas


class Rendimiento(BaseModel):
    rendimiento_estimado_t_ha: float = Field(
        ...,
        description=(
            "Valor OPERATIVO mostrado al usuario/mapa: predicción del modelo "
            "final con clip a 0 si el valor bruto era negativo."
        ),
    )
    prediccion_modelo_final_t_ha_bruta: float = Field(
        ...,
        description=(
            "Valor bruto de la predicción del modelo, sin ajustar. Se conserva "
            "únicamente para trazabilidad, no se usa para presentación."
        ),
    )
    rendimiento_referencia_mapspam_t_ha: float = Field(
        ...,
        description="Rendimiento de referencia (target original MAPSPAM). No es una predicción del modelo.",
    )
    ajustado_por_valor_negativo: bool
    nota: Optional[str] = None


class VariableValor(BaseModel):
    valor: float
    grupo: str
    unidad: str


VariablesAgroecologicas = Dict[str, VariableValor]
