from typing import List

from pydantic import BaseModel

from schemas.common import Coordenadas


class ResultadoBusqueda(BaseModel):
    grid_code: int
    departamento: str
    provincia: str
    coordenadas: Coordenadas
    rendimiento_estimado_t_ha: float


class BuscarZonasResponse(BaseModel):
    """Respuesta de GET /buscar (buscar_zonas)."""

    texto_buscado: str
    total_encontrado: int
    mostrando: int
    resultados: List[ResultadoBusqueda]
