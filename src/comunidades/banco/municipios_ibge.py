"""Municípios do Brasil inteiro (malha do IBGE, só dados públicos): para a área de atuação das empresas.

A tabela municipio (base_territorial.py) tem só os municípios com base territorial (a concessão da EMG); esta tem
os 5.570, com o contorno simplificado (para a tela) e um ponto dentro (onde escrever a sigla). Nada de cliente.
Carga: uv run python -m comunidades.municipios_brasil (uma vez; as malhas ficam em data/raw/malhas).
"""

import functools
import json

import shapely

from .conexao import conectar

SRID = 4674
SIMPLIFICAR = 0.002          # graus (cerca de 200 m): contorno para a tela, não para cálculo fino
SIMPLIFICAR_TELA = 0.004     # o mapa das empresas (o Brasil inteiro cabe na tela)

ESQUEMA = f"""
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS municipio_ibge (
    codigo_ibge  text PRIMARY KEY CHECK (codigo_ibge ~ '^[0-9]{{7}}$'),
    nome         text NOT NULL,
    uf           text NOT NULL CHECK (uf ~ '^[A-Z]{{2}}$'),
    contorno     geometry(MultiPolygon, {SRID}) NOT NULL,
    ponto        geometry(Point, {SRID}) NOT NULL
);
CREATE INDEX IF NOT EXISTS municipio_ibge_uf ON municipio_ibge (uf);
CREATE INDEX IF NOT EXISTS municipio_ibge_contorno ON municipio_ibge USING gist (contorno);
"""


def criar_esquema() -> None:
    with conectar() as c:
        c.execute(ESQUEMA)


def _multi(g):
    g = shapely.make_valid(g)
    partes = [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"] \
        + [q for p in getattr(g, "geoms", []) if p.geom_type == "MultiPolygon" for q in p.geoms]
    if g.geom_type == "MultiPolygon":
        partes = list(g.geoms)
    return shapely.MultiPolygon(partes)


def gravar_uf(uf: str, municipios) -> int:
    """Substitui os municípios da UF (GeoDataFrame com CD_MUN, NM_MUN e geometry em EPSG:4674)."""
    linhas = []
    for r in municipios.itertuples():
        g = _multi(shapely.simplify(r.geometry, SIMPLIFICAR, preserve_topology=True))
        linhas.append((str(r.CD_MUN), str(r.NM_MUN), uf, shapely.to_wkb(g), shapely.to_wkb(g.point_on_surface())))
    with conectar() as c, c.cursor() as cur:
        cur.execute("DELETE FROM municipio_ibge WHERE uf = %s", (uf,))
        cur.executemany("INSERT INTO municipio_ibge (codigo_ibge, nome, uf, contorno, ponto)"
                        f" VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromWKB(%s), {SRID}), ST_SetSRID(ST_GeomFromWKB(%s), {SRID}))", linhas)
    lista.cache_clear()
    return len(linhas)


@functools.lru_cache(maxsize=1)
def lista() -> tuple:
    """(codigo_ibge, nome, uf) de todos, em ordem de UF e nome. Vazio se a carga não foi feita."""
    try:
        with conectar() as c:
            return tuple(c.execute("SELECT codigo_ibge, nome, uf FROM municipio_ibge ORDER BY uf, nome").fetchall())
    except Exception:   # tabela ainda não carregada
        return ()


def existentes(codigos: list[str]) -> set[str]:
    with conectar() as c:
        return {r[0] for r in c.execute("SELECT codigo_ibge FROM municipio_ibge WHERE codigo_ibge = ANY(%s)", (list(codigos),)).fetchall()}


def geojson(codigos: list[str], simplificar: float = SIMPLIFICAR_TELA) -> dict:
    """Contorno e ponto (onde escrever) de cada município pedido."""
    if not codigos:
        return {"type": "FeatureCollection", "features": []}
    with conectar() as c:
        linhas = c.execute("SELECT codigo_ibge, nome, uf, ST_X(ponto), ST_Y(ponto),"
                           " ST_AsGeoJSON(ST_SimplifyPreserveTopology(contorno, %s), 4) FROM municipio_ibge"
                           " WHERE codigo_ibge = ANY(%s) ORDER BY codigo_ibge", (simplificar, list(codigos))).fetchall()
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codigo_ibge": r[0], "nome": r[1], "uf": r[2], "ponto": [round(r[4], 5), round(r[3], 5)]},
         "geometry": json.loads(r[5])} for r in linhas]}


def da_uf(uf: str, simplificar: float = SIMPLIFICAR) -> dict:
    """Todos os municípios de uma UF (para marcar no mapa ao cadastrar a área)."""
    return geojson([c for c, _, u in lista() if u == uf], simplificar)


def que_cruzam(geometria_wkb: bytes, minimo: float = 0.5) -> list[str]:
    """Municípios com pelo menos `minimo` da área dentro da geometria importada (KML/GeoJSON da concessão)."""
    with conectar() as c:
        return [r[0] for r in c.execute(
            f"WITH g AS (SELECT ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(%s), {SRID})) AS g)"
            " SELECT m.codigo_ibge FROM municipio_ibge m, g WHERE ST_Intersects(m.contorno, g.g)"
            " AND ST_Area(ST_Intersection(m.contorno, g.g)::geography) >= %s * ST_Area(m.contorno::geography)"
            " ORDER BY m.codigo_ibge", (geometria_wkb, minimo)).fetchall()]
