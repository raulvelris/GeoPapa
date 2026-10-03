from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.common import Ubicacion, Rendimiento, VariableValor


class CompararZonasRequest(BaseModel):
    """Body de POST /comparar-zonas. Requiere al menos 2 grid_codes; si se
    envía 1 o 0, Pydantic devuelve 422 automáticamente antes de llegar al
    endpoint."""

    grid_codes: List[int] = Field(
        ...,
        min_length=2,
        description="Lista de al menos 2 grid_codes a comparar.",
        examples=[[4843916, 4848234]],
    )


class ZonaComparada(BaseModel):
    ubicacion: Ubicacion
    rendimiento: Rendimiento
    variables_agroecologicas: Dict[str, VariableValor]
    delta_rendimiento_estimado_t_ha: Optional[float] = Field(
        default=None,
        description="Diferencia respecto a la primera zona de la lista (None para la zona de referencia).",
    )
    delta_variables: Optional[Dict[str, float]] = None


class CompararZonasResponse(BaseModel):
    """Respuesta de POST /comparar-zonas (comparar_zonas)."""

    zona_referencia: int
    zonas: List[ZonaComparada]
