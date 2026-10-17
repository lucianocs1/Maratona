"""Planilhas de demonstração (UCs FICTÍCIAS) para a apresentação e para o teste testes/planilha/teste_demo.py.

Todas partem das UCs fictícias a jusante de uma chave da rede fictícia de Leopoldina (planilhas_teste),
uma chave cujas UCs ficam todas dentro de Leopoldina, e mudam só o necessário para cada caso:
1_correta.xlsx                  tudo certo: a conferência não acusa nada e o aviso sai;
2_coordenadas_corrigidas.xlsx   6 linhas com latitude e longitude trocadas ou sem o sinal: corrigidas e
                                destacadas no mapa (nenhuma com equipamento vital);
3_vital_rejeitado.xlsx          2 linhas com equipamento vital (uma sem coordenada, uma em São Paulo):
                                alerta vermelho e o aviso não sai;
4_muitas_rejeicoes.xlsx         cerca de 8% das linhas rejeitadas (sem UC, sem coordenada, coordenada em
                                texto): acima do limite de 2%, o aviso só sai com justificativa;
5_maliciosa_macro.xlsx          um .xlsx com macro (vbaProject.bin): recusado na porta, nada é lido;
6_base_clientes.xlsx            a base de clientes no formato da Energisa (simulacao/base_clientes_demo.py):
                                o operador escolhe quem será desligado (mapa, filtros ou a planilha inteira).
Reprodutível: a mesma semente dá os mesmos arquivos (as datas internas do .xlsx são fixas).
Uso: uv run python -m comunidades.simulacao.planilhas_demo
"""

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import openpyxl
import shapely
import shapely.ops
from pyproj import Transformer

from .. import config as C
from ..fontes import base_territorial as BT
from . import planilhas_teste

PASTA = C.RAIZ / "testes" / "planilha" / "exemplos" / "demo"
CHAVES = ("CF-0040", "CF-0041", "CF-0052", "CF-0053", "CF-0060", "CF-0061", "CF-0030", "CF-0031", "CF-0020", "CF-0021")
COLUNAS = ["uc", "latitude", "longitude", "equipamento_vital", "classe", "local"]
DATA_FIXA = datetime(2026, 10, 14, 12, 0)


def _base():
    """UCs fictícias de uma chave com 150 a 600 UCs, todas dentro de Leopoldina (sem divisa)."""
    leo = shapely.ops.transform(Transformer.from_crs(BT.CRS_BASE, "EPSG:4674", always_xy=True).transform, BT.contorno())
    chaves = gpd.read_file(C.SINTETICO / "chaves.gpkg", ignore_geometry=True)["COD_CHAVE"].tolist()
    for chave in list(CHAVES) + chaves:
        try:
            t = planilhas_teste.planilha(chave)
        except ValueError:
            continue
        if 150 <= len(t) <= 600 and shapely.contains_xy(leo, t["longitude"], t["latitude"]).all():
            return chave, t.reset_index(drop=True)
    raise RuntimeError("Nenhuma chave serve para a demonstração.")


def _gravar(t, nome: str) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "UCs afetadas"
    ws.append(COLUNAS)
    for linha in t[COLUNAS].itertuples(index=False):
        ws.append([None if (isinstance(v, float) and np.isnan(v)) else v for v in linha])
    b = io.BytesIO()
    wb.save(b)
    destino = PASTA / nome
    destino.write_bytes(_fixo(b.getvalue()))
    return destino


def _fixo(xlsx: bytes, extra: dict[str, bytes] | None = None) -> bytes:
    """O .xlsx com datas fixas (nas entradas do zip e no docProps/core.xml): o mesmo arquivo a cada geração."""
    quando = DATA_FIXA.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    b = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(xlsx)) as z, zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as novo:
        itens = [(i.filename, z.read(i.filename)) for i in z.infolist()] + list((extra or {}).items())
        for nome, dados in itens:
            if nome == "docProps/core.xml":
                dados = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*", lambda m: m.group(1) + quando, dados)
            novo.writestr(zipfile.ZipInfo(nome, DATA_FIXA.timetuple()[:6]), dados, zipfile.ZIP_DEFLATED)
    return b.getvalue()


def _com_macro(origem: Path, destino: Path) -> None:
    """O mesmo .xlsx com um vbaProject.bin dentro (macro): o portão recusa antes de abrir."""
    destino.write_bytes(_fixo(origem.read_bytes(), {"xl/vbaProject.bin": b"\xd0\xcf\x11\xe0 macro de demonstracao (inofensiva)"}))


def gerar() -> dict[str, int]:
    PASTA.mkdir(parents=True, exist_ok=True)
    chave, t = _base()
    rng = np.random.default_rng(C.SEMENTE)
    t["latitude"], t["longitude"] = t["latitude"].astype(object), t["longitude"].astype(object)
    feitos = {}

    feitos["1_correta.xlsx"] = len(t)
    _gravar(t, "1_correta.xlsx")

    c = t.copy()
    linhas = rng.choice(len(c), 6, replace=False)
    for k, i in enumerate(linhas):
        la, lo = float(t.at[i, "latitude"]), float(t.at[i, "longitude"])
        c.at[i, "latitude"], c.at[i, "longitude"] = [(lo, la), (lo, la), (lo, la), (la, -lo), (la, -lo), (-la, -lo)][k]
        c.at[i, "equipamento_vital"] = "não"
    feitos["2_coordenadas_corrigidas.xlsx"] = len(c)
    _gravar(c, "2_coordenadas_corrigidas.xlsx")

    v = t.copy()
    a, b = rng.choice(len(v), 2, replace=False)
    v.at[a, "equipamento_vital"], v.at[a, "latitude"], v.at[a, "longitude"] = "sim", None, None
    v.at[b, "equipamento_vital"], v.at[b, "latitude"], v.at[b, "longitude"] = "sim", -23.5505, -46.6333
    feitos["3_vital_rejeitado.xlsx"] = len(v)
    _gravar(v, "3_vital_rejeitado.xlsx")

    r = t.copy()
    ruins = rng.choice(len(r), max(3, round(0.08 * len(r))), replace=False)
    for k, i in enumerate(ruins):
        r.at[i, "equipamento_vital"] = "não"
        if k % 3 == 0:
            r.at[i, "uc"] = None
        elif k % 3 == 1:
            r.at[i, "latitude"], r.at[i, "longitude"] = None, None
        else:
            r.at[i, "latitude"], r.at[i, "longitude"] = "sem GPS", "sem GPS"
    feitos["4_muitas_rejeicoes.xlsx"] = len(r)
    _gravar(r, "4_muitas_rejeicoes.xlsx")

    _com_macro(PASTA / "1_correta.xlsx", PASTA / "5_maliciosa_macro.xlsx")
    feitos["5_maliciosa_macro.xlsx"] = len(t)

    from . import base_clientes_demo   # aqui: ele usa PASTA e _fixo deste módulo
    feitos[base_clientes_demo.NOME] = base_clientes_demo.gerar()
    print(f"Chave {chave} (fictícia): {len(t)} UCs")
    return feitos


if __name__ == "__main__":
    for nome, n in gerar().items():
        print(f"{PASTA / nome}: {n} linhas")
