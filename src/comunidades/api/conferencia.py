"""Dupla conferência da planilha: uma rotina independente relê o arquivo e confere o JSON do tradutor.

Independente de propósito: não importa nada do tradutor (nucleo/planilha.py, nucleo/coordenadas.py)
nem da leitura (api/leitura.py), nem usa o openpyxl. Lê o .xlsx direto do zip, com o XML pelo
defusedxml (workbook, relações, textos compartilhados e a aba), e o .csv pelo módulo csv. As regras
mínimas que precisa (nomes das colunas de UC e de equipamento vital, colunas que contam para a linha
não estar vazia, como a UC vira texto) são uma cópia própria, escrita à parte.

Confere três números contra o JSON: o total de linhas lidas, o conjunto de UCs e quantas linhas têm
equipamento vital "sim". Qualquer diferença bloqueia: nada é gerado.
Roda só depois que o portão (api/leitura.py) aceitou o arquivo, então tamanho e zip já foram conferidos.
"""

import csv
import io
import posixpath
import re
import unicodedata
import zipfile

from defusedxml import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}

# cópia própria (não importar do tradutor): nomes de coluna, na ordem de preferência
NOMES_UC = ("uc", "unidade_consumidora", "numero_uc", "num_uc", "n_uc", "codigo_uc", "instalacao", "numcdc")
NOMES_VITAL = ("equipamento_vital", "vital", "equip_vital", "aparelho_vital")
# colunas que fazem a linha contar (as que o modelo lê); uma linha só com outras colunas preenchidas não conta
NOMES_QUE_CONTAM = set(NOMES_UC + NOMES_VITAL) | {
    "latitude", "lat", "y", "longitude", "lon", "long", "lng", "x", "classe", "classe_uc", "categoria",
    "local_aviso", "imovel", "nome_imovel", "endereco", "local", "transformador", "trafo", "cod_trafo", "codigo_trafo",
    "cod_transformador", "circuito", "alimentador", "cod_circuito", "codigo_circuito", "coordenada", "coordenadas",
    "lat_lon", "latlon", "lat_long", "latitude_longitude", "gps", "lat_gms", "latitude_gms", "long_gms", "lon_gms",
    "longitude_gms", "coord_x", "utm_x", "x_utm", "easting", "coord_y", "utm_y", "y_utm", "northing",
    "conjunto", "conjunto_eletrico", "cod_conjunto", "codigo_conjunto", "bairro", "nome_bairro",
    "situacao", "situacao_uc", "status_uc", "situacao_cliente"}
VITAL_SIM = {"sim", "s", "1", "true", "verdadeiro", "x", "yes", "y"}
MAX_UC, MAX_CELULA = 40, 200


FORMULA = object()   # célula com fórmula e sem valor guardado: não é vazia, mas também não é UC nem "sim"


class Divergencia(Exception):
    """A conferência independente não bateu com o JSON do tradutor."""


def _nome(n) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(n)) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _texto_uc(v) -> str | None:
    """A UC como texto, do jeito mais simples possível (None: célula sem UC válida)."""
    if v is None or v is FORMULA or isinstance(v, bool):
        return None
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return None
        v = int(v) if v.is_integer() else v
    s = unicodedata.normalize("NFC", str(v))
    s = " ".join("".join(c if unicodedata.category(c)[0] != "C" else " " for c in s).split())
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s if s and len(s) <= MAX_UC and len(str(v)) <= MAX_CELULA else None


def _vazio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


# ---------- .xlsx lido à mão ----------
def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _valor(c, compartilhados: list[str]):
    """Valor de uma célula do XML: texto, número, booleano; fórmula sem valor guardado vira None."""
    t = c.get("t", "n")
    if t == "inlineStr":
        return "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
    v = c.find("m:v", NS)
    if v is None or v.text is None:
        return FORMULA if c.find("m:f", NS) is not None else None
    if t == "s":
        return compartilhados[int(v.text)]
    if t == "b":
        return v.text == "1"
    if t in ("str", "e"):
        return v.text
    numero = float(v.text)
    return int(numero) if numero.is_integer() and "." not in v.text and "e" not in v.text.lower() else numero


def _linhas_xlsx(conteudo: bytes, aba: str) -> list[list]:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        alvo = {r.get("Id"): r.get("Target") for r in rels.findall("pr:Relationship", NS)}
        folha = next((s for s in wb.iterfind("m:sheets/m:sheet", NS)
                      if " ".join("".join(ch for ch in s.get("name") if unicodedata.category(ch)[0] != "C").split())[:31] == aba
                      and s.get("state", "visible") == "visible"), None)
        if folha is None:
            raise Divergencia("a aba usada pelo tradutor não foi encontrada")
        caminho = alvo[folha.get(f"{{{NS['r']}}}id")]
        caminho = caminho.lstrip("/") if caminho.startswith("/") else posixpath.normpath(posixpath.join("xl", caminho))
        compartilhados = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iterfind("m:si", NS):
                compartilhados.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        linhas = []
        for row in ET.fromstring(z.read(caminho)).iterfind("m:sheetData/m:row", NS):
            celulas = {_col(c.get("r")): _valor(c, compartilhados) for c in row.iterfind("m:c", NS)}
            numero = int(row.get("r"))
            while len(linhas) < numero - 1:          # linhas que o XML pulou (vazias)
                linhas.append([])
            linhas.append([celulas.get(i) for i in range(max(celulas, default=-1) + 1)])
        return linhas


def _linhas_csv(conteudo: bytes) -> list[list]:
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252")
    primeira = texto.split("\n", 1)[0]
    sep = ";" if primeira.count(";") >= primeira.count(",") else ","
    return [list(r) for r in csv.reader(io.StringIO(texto, newline=""), delimiter=sep)]


# ---------- a conferência ----------
def contar(conteudo: bytes, formato: str, aba: str | None) -> dict:
    """Os três números, lidos do arquivo de forma independente."""
    linhas = _linhas_xlsx(conteudo, aba) if formato == "xlsx" else _linhas_csv(conteudo)
    cab = [_nome(c) if c is not None else "" for c in (linhas[0] if linhas else [])]
    acha = lambda nomes: next((cab.index(n) for n in nomes if n in cab), None)
    i_uc, i_vital = acha(NOMES_UC), acha(NOMES_VITAL)
    contam = [i for i, n in enumerate(cab) if n in NOMES_QUE_CONTAM]
    total, ucs, vital = 0, set(), 0
    celula = lambda r, i: r[i] if i is not None and i < len(r) else None
    for r in linhas[1:]:
        if all(_vazio(celula(r, i)) for i in contam):
            continue
        total += 1
        uc = _texto_uc(celula(r, i_uc))
        if uc:
            ucs.add(uc)
        v = celula(r, i_vital)
        if v is True or (not isinstance(v, bool) and v is not None and v is not FORMULA and _nome(v) in VITAL_SIM):
            vital += 1
    return {"total": total, "ucs": ucs, "vital_sim": vital}


def conferir(conteudo: bytes, modelo) -> None:
    """Compara os três números com o JSON; levanta Divergencia (nada é gerado) se algum não bate."""
    try:
        lido = contar(conteudo, modelo.arquivo.formato, modelo.arquivo.aba)
    except Divergencia:
        raise
    except Exception:  # noqa: BLE001 (a conferência não pode falhar em silêncio)
        raise Divergencia("a conferência independente não conseguiu reler o arquivo") from None
    json_ucs = {p.uc for p in modelo.pontos if p.uc}
    json_vital = sum(1 for p in modelo.pontos if p.equipamento_vital is True)
    diferencas = []
    if lido["total"] != modelo.resumo.total:
        diferencas.append("total de linhas")
    if lido["ucs"] != json_ucs:
        diferencas.append("conjunto de UCs")
    if lido["vital_sim"] != json_vital:
        diferencas.append("equipamento vital")
    if diferencas:
        raise Divergencia("a conferência independente não bateu (" + ", ".join(diferencas) + ")")
