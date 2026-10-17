"""Clientes FICTÍCIOS da concessão no banco (camada do mapa; também a base para as planilhas de teste mais adiante).

Um cliente por endereço do CNEFE, ligado ao transformador mais próximo e ao circuito (alimentador) dele
(clientes_concessao.py). Minimização: só o ponto, a classe, vital, ativa, o transformador e o circuito; nunca número
de UC, nome de titular nem endereço (o número, quando uma planilha de teste precisar, nasce na hora).
Geometrias em SIRGAS 2000 (EPSG:4674). Apagar o município (base_concessao --refazer) apaga os clientes dele.

Tabela: cliente_ficticio.
"""

import geopandas as gpd
import shapely

from .base_territorial import SRID
from .conexao import conectar

CLASSES = ("Residencial", "Rural", "Comercial", "Poder Público")   # classe 1 a 4 (o índice + 1 vai para o banco)
VITAL_PCT = 0.012            # equipamento vital: só entre residenciais e rurais (fictício, semente fixa)
INATIVA_PCT = 0.03           # UC inativa (fictício)
LIMITE_PONTOS = 20000        # pontos devolvidos por consulta de perto (o resto vira "cortado")
LIMITE_CELULAS = 4000        # quadradinhos de densidade por consulta
PIXELS_CELULA = 40           # lado de cada quadradinho de densidade, em pixels da tela
CASAS = 5                    # casas decimais no mapa (cerca de 1 m)

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS cliente_ficticio (
    codigo_ibge  text NOT NULL REFERENCES municipio ON DELETE CASCADE,
    classe       smallint NOT NULL,
    vital        boolean NOT NULL,
    ativa        boolean NOT NULL,
    trafo        text NOT NULL,
    alimentador  text NOT NULL,
    ponto        geometry(Point, {SRID}) NOT NULL
);
CREATE INDEX IF NOT EXISTS cliente_ficticio_municipio ON cliente_ficticio (codigo_ibge);
CREATE INDEX IF NOT EXISTS cliente_ficticio_ponto ON cliente_ficticio USING gist (ponto);
"""


def criar_esquema() -> None:
    with conectar() as c:
        c.execute(ESQUEMA)


def municipios_com_clientes() -> set[str]:
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT DISTINCT codigo_ibge FROM cliente_ficticio")
        return {r[0] for r in cur.fetchall()}


def trafos_do_municipio(codigo: str) -> gpd.GeoDataFrame:
    """Os transformadores da rede fictícia do município: COD_TRAFO e o ponto (EPSG:4674)."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT codigo, ST_AsBinary(ponto) FROM rede_trafo WHERE codigo_ibge = %s", (codigo,))
        linhas = cur.fetchall()
    return gpd.GeoDataFrame({"COD_TRAFO": [r[0] for r in linhas]},
                            geometry=[shapely.from_wkb(bytes(r[1])) for r in linhas], crs=f"EPSG:{SRID}")


def trechos_do_municipio(codigo: str) -> gpd.GeoDataFrame:
    """Os trechos de média tensão da rede fictícia do município: ALIMENTADOR e a linha (EPSG:4674)."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT alimentador, ST_AsBinary(linha) FROM rede_trecho WHERE codigo_ibge = %s", (codigo,))
        linhas = cur.fetchall()
    return gpd.GeoDataFrame({"ALIMENTADOR": [r[0] for r in linhas]},
                            geometry=[shapely.from_wkb(bytes(r[1])) for r in linhas], crs=f"EPSG:{SRID}")


def gravar(codigo: str, classe, vital, ativa, trafo, alimentador, pontos) -> int:
    """Substitui os clientes do município (numa transação só, por COPY). Vetores do mesmo tamanho; pontos em EPSG:4674."""
    hexes = shapely.to_wkb(shapely.set_srid(pontos, SRID), hex=True, include_srid=True)
    with conectar() as c, c.cursor() as cur:
        cur.execute("DELETE FROM cliente_ficticio WHERE codigo_ibge = %s", (codigo,))
        with cur.copy("COPY cliente_ficticio (codigo_ibge, classe, vital, ativa, trafo, alimentador, ponto) FROM STDIN") as cp:
            for linha in zip(classe, vital, ativa, trafo, alimentador, hexes):
                cp.write_row((codigo, int(linha[0]), bool(linha[1]), bool(linha[2]), linha[3], linha[4], linha[5]))
    return len(classe)


def totais(codigos: list[str]) -> dict:
    """Quantos clientes há nos municípios, por classe, com vitais e inativas (só contagens)."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT classe, count(*), count(*) FILTER (WHERE vital), count(*) FILTER (WHERE NOT ativa)"
                    " FROM cliente_ficticio WHERE codigo_ibge = ANY(%s) GROUP BY classe ORDER BY classe", (list(codigos),))
        linhas = cur.fetchall()
    return {"total": sum(r[1] for r in linhas), "vitais": sum(r[2] for r in linhas), "inativas": sum(r[3] for r in linhas),
            "classes": {CLASSES[r[0] - 1]: r[1] for r in linhas}}


def consultar(codigos: list[str], sul: float, oeste: float, norte: float, leste: float, zoom: int) -> dict:
    """Os clientes dentro da janela do mapa, só dos municípios permitidos. De longe, a densidade em quadradinhos
    [lat, lon, n, vitais]; de perto (zoom 15 ou mais), os pontos [lat, lon, classe, vital, ativa]."""
    janela = "ponto && ST_MakeEnvelope(%s, %s, %s, %s, %s) AND codigo_ibge = ANY(%s)"
    args = (oeste, sul, leste, norte, SRID, list(codigos))
    with conectar() as c, c.cursor() as cur:
        if zoom >= 15:
            cur.execute(f"SELECT ROUND(ST_Y(ponto)::numeric, {CASAS})::float8, ROUND(ST_X(ponto)::numeric, {CASAS})::float8, classe, vital, ativa"
                        f" FROM cliente_ficticio WHERE {janela} LIMIT %s", (*args, LIMITE_PONTOS + 1))
            linhas = [list(r) for r in cur.fetchall()]
            return {"modo": "pontos", "pontos": linhas[:LIMITE_PONTOS], "cortado": len(linhas) > LIMITE_PONTOS}
        lado = PIXELS_CELULA * 360 / (256 * 2 ** zoom)    # graus por quadradinho
        # o ponto cai no nó da grade mais próximo: o nó é o centro do quadradinho
        cur.execute(f"SELECT ROUND(ST_Y(g)::numeric, {CASAS})::float8, ROUND(ST_X(g)::numeric, {CASAS})::float8, n, vitais FROM ("
                    f" SELECT ST_SnapToGrid(ponto, %s) AS g, count(*) AS n, count(*) FILTER (WHERE vital) AS vitais"
                    f" FROM cliente_ficticio WHERE {janela} GROUP BY 1) q ORDER BY n DESC LIMIT %s",
                    (lado, *args, LIMITE_CELULAS))
        return {"modo": "densidade", "lado": round(lado, 6), "celulas": [list(r) for r in cur.fetchall()]}
