from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from schemas.common import Coordenadas


class RankingItem(BaseModel):
    grid_code: int
    departamento: str
    provincia: str
    coordenadas: Coordenadas
    rendimiento_estimado_t_ha: float
    ajustado_por_valor_negativo: bool


class RankingResponse(BaseModel):
    """Respuesta de GET /ranking (ranking_rendimiento)."""

    orden: Literal["mayor", "menor"]
    n_solicitado: int
    departamento_filtrado: Optional[str] = None
    total_celdas_consideradas: int
    resultados: List[RankingItem]
    advertencia: Optional[str] = Field(
        default=None,
        description="Aviso descriptivo si el departamento filtrado tiene pocas celdas.",
    )
