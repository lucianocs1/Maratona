"""Microrregiões do IBGE que tocam a área de concessão, no banco: código, nome, mesorregião, UF e o polígono.

Dado público (malha e nomes da API de serviços do IBGE, baixados por microrregioes.py). Cada microrregião cobre a área
inteira dela, sem vazio entre uma e outra; é a divisão que a área de negócio usa para falar de "região". Geometrias em
SIRGAS 2000 (EPSG:4674). Não depende da base territorial: apagar um município não apaga as microrregiões.

Tabela: microrregiao.
"""

import shapely

from .base_territorial import SRID, _multi
from .conexao import conectar

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS microrregiao (
    codigo       text PRIMARY KEY,
    nome         text NOT NULL,
    mesorregiao  text NOT NULL,
    uf           text NOT NULL,
    contorno     geometry(MultiPolygon, {SRID}) NOT NULL
);
CREATE INDEX IF NOT EXISTS microrregiao_contorno ON microrregiao USING gist (contorno);
"""
SIMPLIFICAR = 0.002   # graus (~200 m): basta para o mapa, que mostra a região inteira de longe


def criar_esquema() -> None:
    with conectar() as c:
        c.execute(ESQUEMA)


def gravar(linhas: list[tuple]) -> int:
    """Substitui todas as microrregiões: (codigo, nome, mesorregiao, uf, geometria shapely em EPSG:4674)."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("DELETE FROM microrregiao")
        cur.executemany("INSERT INTO microrregiao VALUES (%s, %s, %s, %s, ST_GeomFromWKB(%s, %s))",
                        [(cod, nome, meso, uf, _multi(g), SRID) for cod, nome, meso, uf, g in linhas])
    return len(linhas)


def para_o_mapa(codigos: list[str]) -> dict:
    """GeoJSON das microrregiões que têm algum município da área (codigos), com quantos municípios da área cada uma
    tem. Só as que tocam a área da empresa."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT r.codigo, r.nome, r.mesorregiao, r.uf,"
                    " (SELECT count(*) FROM municipio m WHERE m.codigo_ibge = ANY(%s)"
                    "  AND ST_Contains(r.contorno, ST_PointOnSurface(m.contorno))),"
                    " ST_AsGeoJSON(ST_SimplifyPreserveTopology(r.contorno, %s), 4),"
                    " ARRAY[ROUND(ST_Y(p)::numeric, 4)::float8, ROUND(ST_X(p)::numeric, 4)::float8]"
                    " FROM microrregiao r, LATERAL ST_PointOnSurface(r.contorno) AS p"
                    " WHERE EXISTS (SELECT 1 FROM municipio m WHERE m.codigo_ibge = ANY(%s)"
                    "  AND ST_Contains(r.contorno, ST_PointOnSurface(m.contorno))) ORDER BY r.nome",
                    (list(codigos), SIMPLIFICAR, list(codigos)))
        linhas = cur.fetchall()
    import json
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": json.loads(g),
         "properties": {"codigo": cod, "nome": nome, "mesorregiao": meso, "uf": uf, "municipios": n, "rotulo": rot}}
        for cod, nome, meso, uf, n, g, rot in linhas]}
