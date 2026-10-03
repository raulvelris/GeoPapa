from pydantic import BaseModel, Field


class LimitesCelda(BaseModel):
    south: float
    west: float
    north: float
    east: float


class CeldaMapa(BaseModel):
    grid_code: int
    x: float = Field(..., description="Longitud del centro de la celda")
    y: float = Field(..., description="Latitud del centro de la celda")
    departamento: str
    provincia: str
    rendimiento_estimado_t_ha: float
    ajustado_por_valor_negativo: bool
    limites: LimitesCelda
