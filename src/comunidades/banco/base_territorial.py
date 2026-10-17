"""Base territorial no banco: municípios, comunidades e endereços de referência (só dados públicos).

Nada de cliente entra aqui: os endereços são os do CNEFE do IBGE, com a comunidade limpa e o
distrito. Geometrias em SIRGAS 2000 (EPSG:4674), como o IBGE publica.

Tabelas:
- municipio: contorno, fração dentro da concessão e o acerto da amostra separada (validação);
- comunidade: nome, distrito, total de endereços (o "tamanho" para o aviso) e o território (desenho);
- endereco_referencia: ponto e comunidade de cada endereço (o voto da localização).
"""

import functools
import json

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Transformer

from .conexao import conectar

SRID = 4674

ESQUEMA = f"""
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS municipio (
    codigo_ibge    text PRIMARY KEY,
    nome           text NOT NULL,
    uf             text NOT NULL,
    dentro_concessao real,
    enderecos      integer NOT NULL,
    comunidades    integer NOT NULL,
    validacao      jsonb,
    contorno       geometry(MultiPolygon, {SRID}) NOT NULL,
    atualizado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS comunidade (
    codigo_ibge  text NOT NULL REFERENCES municipio ON DELETE CASCADE,
    nome         text NOT NULL,
    distrito     text NOT NULL,
    enderecos    integer NOT NULL,
    territorio   geometry(MultiPolygon, {SRID}),
    PRIMARY KEY (codigo_ibge, nome)
);
CREATE TABLE IF NOT EXISTS endereco_referencia (
    codigo_ibge  text NOT NULL REFERENCES municipio ON DELETE CASCADE,
    comunidade   text NOT NULL,
    distrito     text NOT NULL,
    ponto        geometry(Point, {SRID}) NOT NULL
);
CREATE INDEX IF NOT EXISTS endereco_referencia_municipio ON endereco_referencia (codigo_ibge);
CREATE INDEX IF NOT EXISTS endereco_referencia_ponto ON endereco_referencia USING gist (ponto);
CREATE INDEX IF NOT EXISTS municipio_contorno ON municipio USING gist (contorno);
"""


def criar_esquema() -> None:
    with conectar() as c:
        c.execute(ESQUEMA)


def _multi(g) -> bytes:
    g = shapely.make_valid(g)
    if g.geom_type == "Polygon":
        g = shapely.MultiPolygon([g])
    elif g.geom_type != "MultiPolygon":  # coleção: só as partes de área
        g = shapely.MultiPolygon([p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
                                 + [q for p in getattr(g, "geoms", []) if p.geom_type == "MultiPolygon" for q in p.geoms])
    return shapely.to_wkb(g)


def gravar_municipio(codigo: str, nome: str, uf: str, dentro: float | None, contorno,
                     enderecos: gpd.GeoDataFrame, territorios: gpd.GeoDataFrame, validacao: dict) -> None:
    """Substitui tudo o que o banco tem do município (numa transação só).
    contorno, enderecos e territorios em EPSG:4674; enderecos com COMUNIDADE e NM_DIST;
    territorios com COMUNIDADE e geometry."""
    tot = enderecos.groupby("COMUNIDADE").agg(N=("NM_DIST", "size"), DIST=("NM_DIST", lambda s: s.mode().iat[0]))
    terr = dict(zip(territorios["COMUNIDADE"], territorios.geometry))
    with conectar() as c, c.cursor() as cur:
        cur.execute("DELETE FROM municipio WHERE codigo_ibge = %s", (codigo,))
        cur.execute("INSERT INTO municipio (codigo_ibge, nome, uf, dentro_concessao, enderecos, comunidades, validacao, contorno)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, ST_GeomFromWKB(%s, %s))",
                    (codigo, nome, uf, dentro, len(enderecos), len(tot), json.dumps(validacao), _multi(contorno), SRID))
        cur.executemany("INSERT INTO comunidade (codigo_ibge, nome, distrito, enderecos, territorio)"
                        " VALUES (%s, %s, %s, %s, ST_GeomFromWKB(%s, %s))",
                        [(codigo, n, r.DIST, int(r.N), _multi(terr[n]) if n in terr else None, SRID)
                         for n, r in tot.iterrows()])
        with cur.copy("COPY endereco_referencia (codigo_ibge, comunidade, distrito, ponto) FROM STDIN") as cp:
            for com, dist, x, y in zip(enderecos["COMUNIDADE"], enderecos["NM_DIST"],
                                       enderecos.geometry.x.to_numpy(), enderecos.geometry.y.to_numpy()):
                cp.write_row((codigo, com, dist, f"SRID={SRID};POINT({x:.6f} {y:.6f})"))


def municipios_gravados() -> dict[str, dict]:
    """codigo_ibge -> {nome, uf, enderecos, comunidades, validacao} do que já está no banco."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT codigo_ibge, nome, uf, enderecos, comunidades, validacao FROM municipio")
        return {r[0]: {"nome": r[1], "uf": r[2], "enderecos": r[3], "comunidades": r[4], "validacao": r[5]}
                for r in cur.fetchall()}


# ---------- Leitura (API): contornos de todos os municípios e endereços só dos que a planilha toca ----------
# Ficam em memória no processo da API; depois de rodar o base_concessao.py de novo, reinicie a API.

@functools.lru_cache(maxsize=1)
def contornos(crs: str) -> tuple:
    """(codigo, nome, uf, contorno em crs) de cada município do banco, em ordem de código."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT codigo_ibge, nome, uf, ST_AsBinary(contorno) FROM municipio ORDER BY codigo_ibge")
        linhas = cur.fetchall()
    g = gpd.GeoSeries([shapely.from_wkb(bytes(r[3])) for r in linhas], crs=SRID).to_crs(crs)
    return tuple((r[0], r[1], r[2], geom) for r, geom in zip(linhas, g))


@functools.lru_cache(maxsize=80)
def enderecos(codigo: str, crs: str) -> tuple:
    """(xy em crs, comunidade, distrito) dos endereços de referência do município."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT comunidade, distrito, ST_X(ponto), ST_Y(ponto) FROM endereco_referencia"
                    " WHERE codigo_ibge = %s ORDER BY ctid", (codigo,))
        linhas = cur.fetchall()
    lon, lat = np.array([r[2] for r in linhas]), np.array([r[3] for r in linhas])
    x, y = Transformer.from_crs(SRID, crs, always_xy=True).transform(lon, lat)
    return (np.c_[x, y], np.array([r[0] for r in linhas], dtype=object), np.array([r[1] for r in linhas], dtype=object))


# ---------- Território para o mapa da tela (só dados públicos, simplificado no PostGIS) ----------
SIMPLIFICAR_MUNICIPIO = 0.0005    # graus (~50 m): contorno dos municípios da concessão
SIMPLIFICAR_COMUNIDADE = 0.0002   # graus (~20 m): território de cada comunidade


def _colecao(linhas: list, props: list[str]) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": dict(zip(props, r[:-1])), "geometry": json.loads(r[-1])} for r in linhas if r[-1]]}


@functools.lru_cache(maxsize=1)
def concessao_geojson() -> dict:
    """Contorno de cada município do banco (codigo, nome, uf)."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT codigo_ibge, nome, uf, ST_AsGeoJSON(ST_SimplifyPreserveTopology(contorno, %s), 5)"
                    " FROM municipio ORDER BY nome", (SIMPLIFICAR_MUNICIPIO,))
        return _colecao(cur.fetchall(), ["codigo_ibge", "nome", "uf"])


@functools.lru_cache(maxsize=80)
def comunidades_geojson(codigo: str) -> dict | None:
    """Território de cada comunidade do município (nome, distrito, enderecos e rotulo, [lat, lon] de um ponto
    sempre dentro dela, para o nome no mapa); None se o município não existe."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT 1 FROM municipio WHERE codigo_ibge = %s", (codigo,))
        if not cur.fetchone():
            return None
        cur.execute("SELECT nome, distrito, enderecos,"
                    " ARRAY[ROUND(ST_Y(p)::numeric, 5)::float8, ROUND(ST_X(p)::numeric, 5)::float8],"
                    " ST_AsGeoJSON(ST_SimplifyPreserveTopology(territorio, %s), 5)"
                    " FROM comunidade, LATERAL ST_PointOnSurface(territorio) AS p"
                    " WHERE codigo_ibge = %s ORDER BY nome", (SIMPLIFICAR_COMUNIDADE, codigo))
        return _colecao(cur.fetchall(), ["nome", "distrito", "enderecos", "rotulo"])


def enderecos_da_comunidade(codigo: str, nome: str, distrito: str | None) -> int | None:
    """Quantos endereços do IBGE a comunidade tem (o nome pode vir sem o sufixo de homônimo)."""
    with conectar() as c:
        r = c.execute("SELECT enderecos FROM comunidade WHERE codigo_ibge = %s AND (nome = %s OR nome LIKE %s)"
                      " AND (%s::text IS NULL OR distrito = %s) ORDER BY nome = %s DESC LIMIT 1",
                      (codigo, nome, nome + " (%", distrito or None, distrito or None, nome)).fetchone()
    return r[0] if r else None
