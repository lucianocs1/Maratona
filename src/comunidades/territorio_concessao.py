"""Refaz só o desenho do território das comunidades da concessão, a partir do que já está no banco.

Usa os endereços de referência e o contorno de cada município (nada de CNEFE nem de internet): troca a
coluna comunidade.territorio pelo território que cobre o município inteiro, sem vazios entre comunidades
(nucleo/algoritmo.territorios_cobrindo) e dá a cada cidade a sua cor e a cada comunidade o seu tom. Não muda comunidades, contagens nem quem é afetado: é só o desenho do mapa.
Depois de rodar, reinicie a API (ela guarda os territórios em memória).

Uso: uv run python -m comunidades.territorio_concessao [--so cod1,cod2]
"""

import sys
import time

import geopandas as gpd
import shapely

from .banco.base_territorial import SRID, _multi, colorir_mapa, criar_esquema
from .banco.conexao import conectar
from .nucleo.algoritmo import territorios_cobrindo

CRS_M = "EPSG:5880"   # Brasil Policônico (SIRGAS 2000), em metros: o mesmo para todos os municípios


def _municipio(cur, cod: str) -> tuple[int, int]:
    cur.execute("SELECT ST_AsBinary(contorno) FROM municipio WHERE codigo_ibge = %s", (cod,))
    contorno = gpd.GeoSeries([shapely.from_wkb(bytes(cur.fetchone()[0]))], crs=SRID).to_crs(CRS_M).iloc[0]
    cur.execute("SELECT comunidade, ST_X(ponto), ST_Y(ponto) FROM endereco_referencia WHERE codigo_ibge = %s", (cod,))
    r = cur.fetchall()
    e = gpd.GeoDataFrame({"COMUNIDADE": [x[0] for x in r]},
                         geometry=gpd.points_from_xy([x[1] for x in r], [x[2] for x in r]), crs=SRID).to_crs(CRS_M)
    t = territorios_cobrindo(e, "COMUNIDADE", contorno).to_crs(SRID)
    cur.executemany("UPDATE comunidade SET territorio = ST_GeomFromWKB(%s, %s) WHERE codigo_ibge = %s AND nome = %s",
                    [(_multi(g), SRID, cod, n) for n, g in zip(t["COMUNIDADE"], t.geometry)])
    return len(e), len(t)


def main(argv: list[str]) -> int:
    criar_esquema()   # acrescenta a coluna cor, se faltar
    so = set(argv[argv.index("--so") + 1].split(",")) if "--so" in argv else None
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT codigo_ibge, nome FROM municipio ORDER BY codigo_ibge")
        alvos = [(a, b) for a, b in cur.fetchall() if so is None or a in so]
    for cod, nome in alvos:
        t0 = time.time()
        with conectar() as c, c.cursor() as cur:   # uma transação por município
            n, k = _municipio(cur, cod)
        print(f"{cod} {nome}: {n} endereços, {k} territórios ({time.time() - t0:.0f}s)", flush=True)
    print(f"{colorir_mapa()[1]} comunidades coloridas (cidade de uma cor, comunidades em tons).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
