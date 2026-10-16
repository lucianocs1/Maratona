"""Caminhos e parâmetros globais do projeto, derivados do município da distribuidora ativa.

O município (código IBGE, nome e UF) vem do arquivo da distribuidora
(distribuidoras/demo-leopoldina.toml por padrão, ou o indicado em FAROL_DISTRIBUIDORA,
que o comando `comunidades --distribuidora` preenche). Dele saem os arquivos do IBGE,
as pastas de dados e saída, a sigla da rede fictícia e a projeção métrica (zona UTM).
"""

import os
import tomllib
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DISTRIBUIDORAS = RAIZ / "distribuidoras"
DISTRIBUIDORA_PADRAO = DISTRIBUIDORAS / "demo-leopoldina.toml"
ARQ_DISTRIBUIDORA = Path(os.environ.get("FAROL_DISTRIBUIDORA") or DISTRIBUIDORA_PADRAO)

# Leopoldina, o primeiro município do projeto, continua nas pastas originais (data/interim,
# data/sintetico, saida/); os outros ganham subpastas (data/<municipio>/, saida/<municipio>/).
MUNICIPIO_PASTAS_ORIGINAIS = "3138401"


def segredo(nome: str, padrao: str = "") -> str:
    """Valor de uma configuração sensível ou de ambiente: a variável de ambiente ou, se não existir, a linha
    NOME=valor do .env na raiz (o arquivo de FAROL_ENV, se definido). O .env é ignorado pelo git."""
    if os.environ.get(nome):
        return os.environ[nome]
    arquivo = RAIZ / (os.environ.get("FAROL_ENV") or ".env")
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            chave, _, valor = linha.strip().partition("=")
            if chave.strip() == nome and valor.strip():
                return valor.strip().strip('"').strip("'")
    return padrao


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def sigla_automatica(nome: str) -> str:
    """Primeira letra + próximas consoantes diferentes (LEOPOLDINA -> LPD); completa com as vogais."""
    letras = [c for c in sem_acento(nome).upper() if c.isalpha()]
    sigla = letras[:1]
    for c in letras[1:]:
        if len(sigla) == 3:
            break
        if c not in "AEIOU" and c not in sigla:
            sigla.append(c)
    for c in letras[1:]:
        if len(sigla) == 3:
            break
        if c not in sigla:
            sigla.append(c)
    return "".join(sigla)


def crs_utm(lon: float, lat: float) -> str:
    """Zona UTM SIRGAS 2000 da posição (sul: EPSG 31960 + zona; norte: 31954 + zona)."""
    zona = int((lon + 180) // 6) + 1
    return f"EPSG:{(31960 if lat < 0 else 31954) + zona}"


with open(ARQ_DISTRIBUIDORA, "rb") as _f:
    _mun = tomllib.load(_f)["distribuidora"]
COD_MUNICIPIO = str(_mun["codigo_ibge"])
NOME_MUNICIPIO = _mun["municipio"]
UF = _mun["uf"]
SIGLA_REDE = _mun.get("sigla_rede") or sigla_automatica(NOME_MUNICIPIO)
SLUG = "-".join(sem_acento(NOME_MUNICIPIO).lower().replace("'", " ").split())

DADOS = RAIZ / "data"
RAW = DADOS / "raw"                # brutos compartilhados (CNEFE por município, setores e localidades por UF)
if COD_MUNICIPIO == MUNICIPIO_PASTAS_ORIGINAIS:
    INTERIM, SINTETICO, SAIDA = DADOS / "interim", DADOS / "sintetico", RAIZ / "saida"
else:
    INTERIM, SINTETICO, SAIDA = DADOS / SLUG / "interim", DADOS / SLUG / "sintetico", RAIZ / "saida" / SLUG
# INTERIM: dados reais recortados/limpos (IBGE, OSM); SINTETICO: camadas fictícias da distribuidora

CRS_GEO = "EPSG:4674"      # SIRGAS 2000 (lat/long), padrão IBGE
CRS_WEB = "EPSG:4326"
CRS_METRICO = None         # zona UTM do município, para distâncias em metros (definida abaixo)

SEMENTE = 42  # reprodutibilidade de tudo que é sorteado

# Arquivos do IBGE (o nome do CSV do CNEFE é conferido depois do download, em fontes/dados.py)
NOME_ARQUIVO_IBGE = "_".join(sem_acento(NOME_MUNICIPIO).upper().replace("'", " ").replace("-", " ").split())
_cnefe = sorted((RAW / "cnefe").glob(f"{COD_MUNICIPIO}_*.csv"))
ARQ_CNEFE = _cnefe[0] if _cnefe else RAW / "cnefe" / f"{COD_MUNICIPIO}_{NOME_ARQUIVO_IBGE}.csv"
ARQ_LOCALIDADES = RAW / "localidades" / UF / f"{UF}_localidades_2022.gpkg"
ARQ_SETORES = RAW / f"setores_{UF.lower()}" / f"{UF}_setores_CD2022.shp"


def definir_crs(municipio_geo) -> str:
    """Define CRS_METRICO pelo centro do município (geometria em lat/long)."""
    global CRS_METRICO
    c = municipio_geo.centroid
    CRS_METRICO = crs_utm(c.x, c.y)
    return CRS_METRICO


for _p in (INTERIM, SINTETICO, SAIDA):
    _p.mkdir(parents=True, exist_ok=True)

# Nas execuções seguintes, a projeção sai do contorno do município já gravado
if (INTERIM / "municipio.gpkg").exists():
    import geopandas as _gpd
    definir_crs(_gpd.read_file(INTERIM / "municipio.gpkg").to_crs(CRS_GEO).union_all())
