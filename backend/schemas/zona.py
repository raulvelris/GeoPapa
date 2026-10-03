from typing import Dict

from pydantic import BaseModel

from schemas.common import Ubicacion, Rendimiento, VariableValor


class ZonaCompleta(BaseModel):
    """Respuesta de GET /zonas/{grid_code} (resumir_zona)."""

    ubicacion: Ubicacion
    rendimiento: Rendimiento
    variables_agroecologicas: Dict[str, VariableValor]


class VariablesZonaResponse(BaseModel):
    """Respuesta de GET /zonas/{grid_code}/variables (obtener_variables_agroecologicas)."""

    grid_code: int
    variables_agroecologicas: Dict[str, VariableValor]
