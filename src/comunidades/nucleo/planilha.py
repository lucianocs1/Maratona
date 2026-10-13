"""Regras da planilha de UCs afetadas (modelo provisório; ver CLAUDE.md, "Planilha de UCs").

Puro: recebe a planilha já lida como tabela de textos (quem lê o arquivo é a API) e devolve as
linhas válidas e os problemas encontrados. Os problemas citam só o número da linha da planilha
(a linha 1 é o cabeçalho), nunca a UC nem a coordenada.
"""

import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

OBRIGATORIAS = ("uc", "latitude", "longitude")
OPCIONAIS = ("equipamento_vital", "classe", "local")
# nomes de coluna aceitos para cada campo (depois de minúsculas, sem acento e com "_" no lugar de espaço)
SINONIMOS = {
    "uc": ("uc", "unidade_consumidora", "numero_uc", "num_uc", "n_uc", "codigo_uc", "instalacao", "numcdc"),
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lon", "long", "lng", "x"),
    "equipamento_vital": ("equipamento_vital", "vital", "equip_vital", "aparelho_vital"),
    "classe": ("classe", "classe_uc", "categoria"),
    # o que o aviso de hoje cita para a UC (o imóvel no rural, a rua no urbano): só para o comparativo
    # a ordem importa: na base da distribuidora a coluna LOCAL é URBANO/RURAL, não o imóvel; por isso
    # endereco vem antes de local (no modelo antigo, sem endereco, local continua valendo)
    "local": ("local_aviso", "imovel", "nome_imovel", "endereco", "local"),
}
SIM = {"sim", "s", "1", "true", "verdadeiro", "x", "yes", "y"}
NAO = {"nao", "n", "0", "false", "falso", "no", ""}
MAX_LINHAS = 50_000
MAX_LOCAL = 80          # caracteres do local de uma UC (o que passar é cortado e apontado)
# Brasil com folga: fora disso a coordenada está errada (ou trocada), não é só fora da concessão
LAT_BR, LON_BR = (-34.5, 6.0), (-74.5, -28.0)


@dataclass
class Planilha:
    validas: pd.DataFrame        # LINHA, UC, LAT, LON, VITAL (True/False/None), CLASSE, LOCAL (None = sem local)
    problemas: pd.DataFrame      # LINHA, MOTIVO (uma linha por problema)
    linhas: int                  # linhas de dados lidas (sem o cabeçalho)
    tem_local: bool = False      # a planilha trouxe a coluna local (dá para montar o aviso de hoje)


class PlanilhaInvalida(ValueError):
    """A planilha inteira não pode ser usada (coluna obrigatória faltando, vazia, grande demais)."""


def _chave(nome: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(nome)) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def colunas(cabecalho: list[str]) -> dict[str, str]:
    """Campo do modelo -> coluna da planilha que o traz (a primeira que bater com um sinônimo)."""
    por_chave = {}
    for c in cabecalho:
        por_chave.setdefault(_chave(c), c)
    achadas = {}
    for campo, nomes in SINONIMOS.items():
        for n in nomes:
            if n in por_chave:
                achadas[campo] = por_chave[n]
                break
    return achadas


def numero(txt) -> float | None:
    """'-21,53' ou '-21.53' -> -21.53; vazio ou inválido -> None. Aceita '1.234,5' e '1,234.5'."""
    s = str(txt).strip().replace(" ", "") if txt is not None and not pd.isna(txt) else ""
    if not s:
        return None
    if "," in s and "." in s:  # o separador decimal é o último que aparece
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v == v and abs(v) != float("inf") else None


def _texto(v) -> str:
    return "" if v is None or pd.isna(v) else str(v).strip()


def validar(t: pd.DataFrame) -> Planilha:
    """t: a planilha como lida (todas as colunas como texto), na ordem das linhas."""
    if len(t) == 0:
        raise PlanilhaInvalida("A planilha não tem nenhuma linha de dados.")
    if len(t) > MAX_LINHAS:
        raise PlanilhaInvalida(f"A planilha tem {len(t):,} linhas; o limite é {MAX_LINHAS:,}.".replace(",", "."))
    col = colunas(list(t.columns))
    faltam = [c for c in OBRIGATORIAS if c not in col]
    if faltam:
        raise PlanilhaInvalida("Faltam colunas obrigatórias: " + ", ".join(faltam)
                               + ". O modelo tem: uc, latitude, longitude, equipamento_vital, classe e local.")
    problemas, validas, vistas = [], [], {}
    for i, r in enumerate(t.itertuples(index=False)):
        linha = i + 2  # a linha 1 é o cabeçalho
        v = dict(zip(t.columns, r))
        uc = _texto(v[col["uc"]])
        if uc.endswith(".0") and uc[:-2].isdigit():  # número lido como decimal pelo Excel
            uc = uc[:-2]
        lat, lon = numero(v[col["latitude"]]), numero(v[col["longitude"]])
        if not uc:
            problemas.append((linha, "sem número de UC"))
            continue
        if lat is None or lon is None:
            problemas.append((linha, "sem coordenada (latitude ou longitude vazia ou inválida)"))
            continue
        if not (LAT_BR[0] <= lat <= LAT_BR[1] and LON_BR[0] <= lon <= LON_BR[1]):
            trocada = LAT_BR[0] <= lon <= LAT_BR[1] and LON_BR[0] <= lat <= LON_BR[1]
            problemas.append((linha, "latitude e longitude parecem trocadas" if trocada else "coordenada fora do Brasil"))
            continue
        if uc in vistas:
            problemas.append((linha, f"UC repetida (já aparece na linha {vistas[uc]})"))
            continue
        vistas[uc] = linha
        vital = None
        if "equipamento_vital" in col:
            txt = _chave(_texto(v[col["equipamento_vital"]]))
            if txt in SIM:
                vital = True
            elif txt in NAO:
                vital = False
            else:
                problemas.append((linha, "equipamento_vital com valor inválido (use sim ou não); a UC entra como \"a confirmar\""))
        classe = _texto(v[col["classe"]]) if "classe" in col else ""
        local = " ".join(_texto(v[col["local"]]).split()) if "local" in col else ""
        if len(local) > MAX_LOCAL:
            problemas.append((linha, f"local com mais de {MAX_LOCAL} caracteres (cortado)"))
            local = local[:MAX_LOCAL].rstrip()
        validas.append((linha, uc, lat, lon, vital, classe, local or None))
    return Planilha(
        validas=pd.DataFrame(validas, columns=["LINHA", "UC", "LAT", "LON", "VITAL", "CLASSE", "LOCAL"]),
        problemas=pd.DataFrame(problemas, columns=["LINHA", "MOTIVO"]),
        linhas=len(t),
        tem_local="local" in col,
    )


def modelo_csv() -> str:
    """O modelo para baixar: cabeçalho e duas linhas de exemplo (fictícias). local: o que o aviso de
    hoje cita para a UC (o imóvel no rural, a rua no urbano), opcional, só para o comparativo."""
    return ("uc;latitude;longitude;equipamento_vital;classe;local\n"
            "0000000001;-21,5321;-42,6412;não;residencial;Rua das Flores\n"
            "0000000002;-21,5410;-42,6503;sim;rural;Sítio Boa Vista\n")
