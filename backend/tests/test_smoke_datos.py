"""Prueba rápida sin llamar a Gemini API.
Ejecutar desde backend/: python tests/test_smoke_datos.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data_service import get_data_service
from services import model_service
from tools import geospatial_tools as gt


def main():
    ds = get_data_service()
    assert len(ds.df) == 1983, len(ds.df)
    assert len(ds.departamentos_disponibles()) == 21

    info = model_service.obtener_info_modelo()
    assert info["modelo"] == "XGBoost"
    assert abs(info["metricas_oof"]["mae_t_ha"] - 7.2550368804433285) < 1e-9

    zona = gt.consultar_zona(4843916)
    assert round(zona["rendimiento"]["rendimiento_estimado_t_ha"], 4) == 20.5882

    zona_neg = gt.consultar_zona(5319211)
    assert zona_neg["rendimiento"]["rendimiento_estimado_t_ha"] == 0.0
    assert zona_neg["rendimiento"]["ajustado_por_valor_negativo"] is True

    busqueda = gt.buscar_zonas("Junin", limite=2)
    assert busqueda["total_encontrado"] == 183

    ranking = gt.ranking_rendimiento(n=3, departamento="Cusco")
    assert ranking["resultados"][0]["grid_code"] == 5323518

    print("OK: datos, metadata y 7 tools base cargan correctamente.")
    print("Celdas:", len(ds.df))
    print("Departamentos:", len(ds.departamentos_disponibles()))
    print("Modelo:", info["modelo"], "-", info["conjunto_variables"])
    print("MAE OOF:", info["metricas_oof"]["mae_t_ha"])


if __name__ == "__main__":
    main()
