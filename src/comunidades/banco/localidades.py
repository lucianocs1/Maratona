"""Localidades oficiais do IBGE (Censo 2022) dos municípios da concessão, no banco: nome, categoria e o ponto.

Dado público (o mesmo arquivo de data/raw/localidades, carregado por localidades_oficiais.py). Servem de referência de
nomes oficiais: a camada "Localidades oficiais" do mapa e o relatório de conferência com as comunidades do app
(validacao/localidades.py). Geometrias em SIRGAS 2000 (EPSG:4674). Apagar o município (base_concessao --refazer) apaga as
localidades dele.

Tabela: localidade_oficial.
"""

import shapely

from .base_territorial import SRID
from .conexao import conectar

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS localidade_oficial (
    codigo_ibge  text NOT NULL REFERENCES municipio ON DELETE CASCADE,
    codigo       text NOT NULL,
    nome         text NOT NULL,
    categoria    text NOT NULL,
    ponto        geometry(Point, {SRID}) NOT NULL
);
CREATE INDEX IF NOT EXISTS localidade_oficial_municipio ON localidade_oficial (codigo_ibge);
"""
CASAS = 5   # casas decimais no mapa (cerca de 1 m)


def criar_esquema() -> None:
    with conectar() as c:
        c.execute(ESQUEMA)


def gravar(linhas: list[tuple]) -> int:
    """Substitui as localidades dos municípios das linhas (codigo_ibge, codigo, nome, categoria, ponto shapely)."""
    codigos = sorted({l[0] for l in linhas})
    with conectar() as c, c.cursor() as cur:
        cur.execute("DELETE FROM localidade_oficial WHERE codigo_ibge = ANY(%s)", (codigos,))
        cur.executemany("INSERT INTO localidade_oficial VALUES (%s, %s, %s, %s, ST_GeomFromWKB(%s, %s))",
                        [(m, cod, nome, cat, shapely.to_wkb(p), SRID) for m, cod, nome, cat, p in linhas])
    return len(linhas)


def para_o_mapa(codigos: list[str]) -> list[list]:
    """As localidades dos municípios, para a camada do mapa: [lat, lon, nome, categoria, município]."""
    with conectar() as c, c.cursor() as cur:
        cur.execute(f"SELECT ROUND(ST_Y(l.ponto)::numeric, {CASAS})::float8, ROUND(ST_X(l.ponto)::numeric, {CASAS})::float8,"
                    " l.nome, l.categoria, m.nome FROM localidade_oficial l JOIN municipio m USING (codigo_ibge)"
                    " WHERE l.codigo_ibge = ANY(%s) ORDER BY m.nome, l.nome", (list(codigos),))
        return [list(r) for r in cur.fetchall()]


def todas() -> list[dict]:
    """Todas as localidades, com o ponto (shapely), para o relatório de conferência."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT l.codigo_ibge, m.nome, m.uf, l.codigo, l.nome, l.categoria, ST_AsBinary(l.ponto)"
                    " FROM localidade_oficial l JOIN municipio m USING (codigo_ibge) ORDER BY m.nome, l.nome")
        return [{"codigo_ibge": r[0], "municipio": r[1], "uf": r[2], "codigo": r[3], "nome": r[4], "categoria": r[5],
                 "ponto": shapely.from_wkb(bytes(r[6]))} for r in cur.fetchall()]


def comunidades() -> list[dict]:
    """As comunidades do app (base territorial), com o território (shapely; None se não foi desenhado) e os endereços."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT c.codigo_ibge, m.nome, c.nome, c.distrito, c.enderecos, ST_AsBinary(c.territorio)"
                    " FROM comunidade c JOIN municipio m USING (codigo_ibge) ORDER BY m.nome, c.nome")
        return [{"codigo_ibge": r[0], "municipio": r[1], "nome": r[2], "distrito": r[3], "enderecos": r[4],
                 "territorio": shapely.from_wkb(bytes(r[5])) if r[5] else None} for r in cur.fetchall()]


def totais(codigos: list[str]) -> dict:
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT categoria, count(*) FROM localidade_oficial WHERE codigo_ibge = ANY(%s) GROUP BY categoria ORDER BY 2 DESC",
                    (list(codigos),))
        linhas = cur.fetchall()
    return {"total": sum(r[1] for r in linhas), "categorias": {r[0]: r[1] for r in linhas}}
