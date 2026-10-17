"""Base de clientes de demonstração (UCs FICTÍCIAS) no formato da base que a Energisa mandou.

A planilha da Energisa (Experimento_Dados_Ficticios - BASE_CLIENTES.xlsx, aba Base_Ficticia) é a BASE
DE CLIENTES, não a lista de um desligamento: no Novo aviso, o operador escolhe quem será desligado
(nucleo/selecao.py). Ela fica fora do git (data/raw/energisa/BASE_CLIENTES.xlsx); esta réplica, que
vai para o git, tem as mesmas colunas, na mesma ordem, com UCs da rede FICTÍCIA de Leopoldina:
circuito = alimentador, transformador = trafo, bairro = a localidade do cadastro fictício.
NOME e ENDERECO vêm com textos de exemplo (nunca um nome que pareça de gente), para o teste conferir
que a leitura os descarta. Cerca de 15% das UCs ficam INATIVAS.

Reprodutível: a mesma semente dá o mesmo arquivo (as datas internas do .xlsx são fixas).
Uso: uv run python -m comunidades.simulacao.base_clientes_demo
"""

import io
from datetime import datetime

import geopandas as gpd
import numpy as np
import openpyxl
import pandas as pd
from pyproj import Transformer

from .. import config as C
from .planilhas_demo import PASTA, _fixo

NOME = "6_base_clientes.xlsx"
ABA = "Base_Ficticia"
# as colunas da base da Energisa, na mesma ordem
COLUNAS = ["EMPRESA", "ANO", "MES", "CIRCUITO", "CONJUNTO", "LOCAL", "TRANSFORMADOR", "NUMCDC", "NOME", "ENDERECO", "BAIRRO",
           "MEDIDOR", "SITUACAO", "DATALIG", "NUM_ROTA", "NUM_CONTA", "TIPO_MEDIDOR", "GRANDEZA", "FASES", "COD_EMPRESA_ANEEL",
           "TUC", "TIPO_BEM", "A2", "A3", "CLASSE", "LOCALIZACAO", "COORD_X", "COORD_Y", "LAT", "LONG", "LAT_GMS", "LONG_GMS",
           "ID_PONTO_ENTREGA", "ID_RAMAL", "COD_POSTE", "NUM_LIVRO", "NUM_CASA", "DATA_COMERCIAL", "DATA_GIS"]
LINHAS = 400
ALIMENTADORES = 3            # os alimentadores fictícios com mais UCs
FRACAO_INATIVA = 0.15
UTM = Transformer.from_crs("EPSG:4674", "EPSG:31983", always_xy=True)   # fuso 23S, o de Leopoldina


def _gms(v: float, pos: str, neg: str) -> str:
    """-21.53 -> 21°31'48.000"S (como na base da Energisa)."""
    a = abs(v)
    g, m = int(a), int((a - int(a)) * 60)
    s = (a - g - m / 60) * 3600
    return f"{g}°{m}'{s:.3f}\"{neg if v < 0 else pos}"


def tabela() -> pd.DataFrame:
    ucs = gpd.read_file(C.SINTETICO / "ucs.gpkg", columns=["UC", "CLASSE", "BAIRRO_LOCALIDADE", "COD_TRAFO", "ALIMENTADOR"],
                        ignore_geometry=True)
    gab = pd.read_csv(C.SINTETICO / "gabarito_uc.csv", dtype={"UC": str}, usecols=["UC", "LAT_REAL", "LON_REAL"])
    ucs = ucs.merge(gab, on="UC").dropna(subset=["ALIMENTADOR", "COD_TRAFO"])
    alims = ucs["ALIMENTADOR"].value_counts().index[:ALIMENTADORES]
    rng = np.random.default_rng(C.SEMENTE)
    t = ucs[ucs["ALIMENTADOR"].isin(alims)].sample(LINHAS, random_state=C.SEMENTE).sort_values(["ALIMENTADOR", "COD_TRAFO", "UC"])
    t = t.reset_index(drop=True)
    n = len(t)
    x, y = UTM.transform(t["LON_REAL"].to_numpy(), t["LAT_REAL"].to_numpy())
    conjunto = {a: f"CONJ{10 + i // 2}" for i, a in enumerate(sorted(alims))}   # dois alimentadores por conjunto
    datas = [datetime(2024, 1, 1) + pd.Timedelta(days=int(d)) for d in rng.integers(0, 900, n)]
    return pd.DataFrame({
        "EMPRESA": "EMP_TESTE", "ANO": [d.year for d in datas], "MES": [d.month for d in datas],
        "CIRCUITO": t["ALIMENTADOR"].to_numpy(), "CONJUNTO": t["ALIMENTADOR"].map(conjunto).to_numpy(),
        "LOCAL": np.where(t["CLASSE"].str.lower() == "rural", "RURAL", "URBANO"), "TRANSFORMADOR": t["COD_TRAFO"].to_numpy(),
        "NUMCDC": [f"{9_000_000 + i:010d}" for i in range(n)],   # UCs novas, fictícias (não são as do cadastro sintético)
        "NOME": [f"Titular de exemplo {i + 1:03d}" for i in range(n)],
        "ENDERECO": [f"Rua de Exemplo {1 + i % 25}, {10 + i}" for i in range(n)],
        "BAIRRO": t["BAIRRO_LOCALIDADE"].fillna("").to_numpy(), "MEDIDOR": [f"MED{100_000 + i}" for i in range(n)],
        "SITUACAO": np.where(rng.random(n) < FRACAO_INATIVA, "INATIVO", "ATIVO"), "DATALIG": datas,
        "NUM_ROTA": rng.integers(1, 51, n), "NUM_CONTA": [700_000 + i for i in range(n)],
        "TIPO_MEDIDOR": rng.choice(["ELETROMECANICO", "ELETRONICO"], n), "GRANDEZA": "ENERGIA",
        "FASES": rng.choice(["MONO", "BI", "TRI"], n), "COD_EMPRESA_ANEEL": 12345, "TUC": rng.integers(10_000, 99_999, n),
        "TIPO_BEM": "MEDICAO", "A2": rng.uniform(1, 99, n).round(2), "A3": rng.uniform(1, 99, n).round(2),
        "CLASSE": t["CLASSE"].to_numpy(), "LOCALIZACAO": "POSTE", "COORD_X": np.round(x, 2), "COORD_Y": np.round(y, 2),
        "LAT": t["LAT_REAL"].round(6).to_numpy(), "LONG": t["LON_REAL"].round(6).to_numpy(),
        "LAT_GMS": [_gms(v, "N", "S") for v in t["LAT_REAL"]], "LONG_GMS": [_gms(v, "E", "W") for v in t["LON_REAL"]],
        "ID_PONTO_ENTREGA": 200_000 + np.arange(n), "ID_RAMAL": 300_000 + np.arange(n),
        "COD_POSTE": [f"P{40_000 + i}" for i in range(n)], "NUM_LIVRO": rng.integers(100, 999, n),
        "NUM_CASA": rng.integers(1, 999, n), "DATA_COMERCIAL": datas, "DATA_GIS": datas,
    })[COLUNAS]


def gerar() -> int:
    t = tabela()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ABA
    ws.append(COLUNAS)
    for linha in t.itertuples(index=False):
        ws.append([v.item() if isinstance(v, np.generic) else v for v in linha])
    b = io.BytesIO()
    wb.save(b)
    PASTA.mkdir(parents=True, exist_ok=True)
    (PASTA / NOME).write_bytes(_fixo(b.getvalue()))
    return len(t)


if __name__ == "__main__":
    print(f"{PASTA / NOME}: {gerar()} linhas (UCs fictícias)")
