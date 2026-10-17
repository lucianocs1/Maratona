"""Teste da dupla conferência (api/conferencia.py), sem banco.

Confere:
- a conferência é independente: o módulo não importa o tradutor, a leitura nem o openpyxl;
- os exemplos oficiais (Modelo, Postes, planilha_postes_certo), .csv e um .xlsx montado à mão como o
  Excel grava (textos compartilhados, booleanos, fórmulas com e sem valor guardado, linhas puladas, aba
  oculta) passam: os três números batem com o JSON do tradutor;
- JSON sabotado (linha a menos, UC trocada, equipamento vital trocado) e tradutor sabotado (a UC sai
  diferente, uma linha some) são pegos: Divergencia, nada é gerado;
- arquivo que não dá para reler: Divergencia (a conferência não falha em silêncio).

Uso (na raiz): uv run python -W ignore testes/planilha/teste_conferencia.py
"""

import ast
import io
import json
import sys
import zipfile
from pathlib import Path

import openpyxl

from comunidades.api import conferencia as C
from comunidades.api import leitura
from comunidades.fontes.concessao import contorno
from comunidades.nucleo import coordenadas as K
from comunidades.nucleo import esquema_planilha as E
from comunidades.nucleo import planilha as P

resultados = []
EXEMPLOS = Path(__file__).resolve().parent / "exemplos"
PAR = P.Parametros(dentro=K.Area(contorno()))


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def traduzir(conteudo: bytes, aba=None):
    t = leitura.ler_tabela(conteudo, aba)
    return P.montar(t.campos, t.cabecalho, t.linhas, PAR, empresa="EMG", gerado_em="2026-10-13T12:00", gerado_por="Teste (Operador)",
                    arquivo={"nome": "x", "sha256": "b" * 64, "formato": t.formato, "aba": t.aba, "colunas_ignoradas": t.colunas_ignoradas})


def passa(nome, conteudo, aba=None):
    m = traduzir(conteudo, aba)
    try:
        C.conferir(conteudo, m)
        conferir(f"conferência bate: {nome}", True)
    except C.Divergencia as e:
        conferir(f"conferência bate: {nome}", False, str(e))
    return m


def pega(nome, conteudo, m):
    try:
        C.conferir(conteudo, m)
        conferir(f"conferência pega: {nome}", False)
    except C.Divergencia:
        conferir(f"conferência pega: {nome}", True)


# ---------- independência ----------
fonte = Path(C.__file__).read_text(encoding="utf-8")
importados = {a.name for n in ast.walk(ast.parse(fonte)) if isinstance(n, ast.Import) for a in n.names} | \
             {n.module or "" for n in ast.walk(ast.parse(fonte)) if isinstance(n, ast.ImportFrom)}
proibidos = [m for m in importados if any(x in m for x in ("planilha", "coordenadas", "leitura", "openpyxl", "nucleo", "esquema"))]
conferir("independente: não importa tradutor, leitura, núcleo nem openpyxl", not proibidos and "defusedxml" in importados, str(importados))

# ---------- arquivos que passam ----------
postes = (EXEMPLOS / "planilha_postes.xlsx").read_bytes()
mm = passa("exemplo, aba Modelo", postes, "Modelo")
mp = passa("exemplo, aba Postes", postes, "Postes")
passa("planilha_postes_certo (NUMCDC)", (EXEMPLOS / "planilha_postes_certo.xlsx").read_bytes())
csv_ = ("uc;latitude;longitude;equipamento_vital;local;NOME\n"
        "1;-21,530443;-42,638946;sim;Rua A;Fulano\n;;;;;Só nome (linha que não conta)\n"
        "2;-21,5306;-42,6390;SIM;Rua B;\n2;-21,5307;-42,6391;não;Rua C;\n3.0;-23,55;-46,63;x;;\n").encode("cp1252")
passa(".csv (Windows-1252, linha só com coluna descartada, UC repetida, '3.0')", csv_)


def xlsx_a_mao(linhas: list[list], oculta: list[list] | None = None) -> bytes:
    """.xlsx mínimo como o Excel grava: textos em sharedStrings.xml, booleanos, fórmulas, linhas puladas."""
    M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    textos: list[str] = []

    def celula(ref, v):
        if v is None:
            return ""
        if isinstance(v, tuple):                                   # ("=formula", valor guardado ou None)
            f, guardado = v
            val = "" if guardado is None else f"<v>{guardado}</v>"
            return f'<c r="{ref}"><f>{f[1:]}</f>{val}</c>'
        if isinstance(v, bool):
            return f'<c r="{ref}" t="b"><v>{int(v)}</v></c>'
        if isinstance(v, (int, float)):
            return f'<c r="{ref}"><v>{v}</v></c>'
        if v not in textos:
            textos.append(v)
        return f'<c r="{ref}" t="s"><v>{textos.index(v)}</v></c>'

    def aba(ls):
        corpo = []
        for numero, linha in ls:
            cs = "".join(celula(f"{chr(65 + i)}{numero}", v) for i, v in enumerate(linha))
            corpo.append(f'<row r="{numero}">{cs}</row>')
        return f'<?xml version="1.0"?><worksheet xmlns="{M}"><sheetData>{"".join(corpo)}</sheetData></worksheet>'

    abas = [("Dados", linhas, "visible")] + ([("Escondida", oculta, "hidden")] if oculta else [])
    xml_abas = {f"xl/worksheets/sheet{i + 1}.xml": aba(ls) for i, (_, ls, _) in enumerate(abas)}
    sst = (f'<?xml version="1.0"?><sst xmlns="{M}" count="{len(textos)}" uniqueCount="{len(textos)}">'
           + "".join(f"<si><t>{t}</t></si>" for t in textos) + "</sst>")
    tipos = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
             + "".join(f'<Override PartName="/{n}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                       for n in xml_abas)
             + '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
             '</Types>')
    rels_raiz = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Id="rId1" Type="{R}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb = (f'<?xml version="1.0"?><workbook xmlns="{M}" xmlns:r="{R}"><sheets>'
          + "".join(f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"' + ("" if e == "visible" else f' state="{e}"') + "/>"
                    for i, (n, _, e) in enumerate(abas)) + "</sheets></workbook>")
    rels_wb = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               + "".join(f'<Relationship Id="rId{i + 1}" Type="{R}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                         for i in range(len(abas)))
               + f'<Relationship Id="rIdS" Type="{R}/sharedStrings" Target="sharedStrings.xml"/></Relationships>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, xml in {"[Content_Types].xml": tipos, "_rels/.rels": rels_raiz, "xl/workbook.xml": wb,
                          "xl/_rels/workbook.xml.rels": rels_wb, "xl/sharedStrings.xml": sst, **xml_abas}.items():
            z.writestr(nome, xml)
    return b.getvalue()


linhas_excel = [
    (1, ["uc", "latitude", "longitude", "equipamento_vital", "local", "NOME"]),
    (2, [53464097, -21.530443, -42.638946, "SIM", "Rua 792", "Fulano"]),
    (4, ["0002", -21.5306, -42.6390, True, ("=B4", None), None]),          # linha 3 pulada; local com fórmula sem valor
    (5, [("=1+2", 3), -21.5307, -42.6391, ("=\"sim\"", None), "Rua C", None]),  # uc de fórmula com valor guardado
    (6, [None, None, None, None, None, "Só o nome"]),                      # só coluna descartada: não conta
    (7, [5.3464098e7, -21.5308, -42.6392, "não", None, None]),             # número em notação científica
    (8, [("=X1", None), -21.5309, -42.6393, "sim", None, None]),           # uc com fórmula sem valor
]
excel = xlsx_a_mao(linhas_excel, oculta=[(1, ["uc", "latitude", "longitude"]), (2, ["OCULTA", -21.53, -42.63])])
me = passa(".xlsx à mão (textos compartilhados, booleano, fórmulas, linha pulada, aba oculta)", excel)
conferir("o .xlsx à mão foi lido pelo tradutor como o esperado", me.resumo.total == 5 and {p.uc for p in me.pontos if p.uc}
         == {"53464097", "0002", "3", "53464098"}, f"{me.resumo.model_dump_json()} {[p.uc for p in me.pontos]}")
lido = C.contar(excel, "xlsx", "Dados")
conferir("a conferência leu os mesmos números à parte", lido == {"total": 5, "ucs": {"53464097", "0002", "3", "53464098"}, "vital_sim": 3},
         str(lido))

# ---------- JSON sabotado ----------
def sabotado(m, mexer):
    d = json.loads(E.texto(m))
    mexer(d)
    return E.validar_dados(d)


def tira_linha(d):   # some a última linha, e o resumo é ajustado para o esquema ainda passar
    p = d["pontos"].pop()
    d["arquivo"]["linhas"] -= 1
    d["resumo"]["total"] -= 1
    chave = {"ok": "ok", "corrigida": "corrigidas", "rejeitada": "rejeitadas"}[p["status"]]
    d["resumo"][chave] -= 1
    d["resumo"]["avisos"] -= len(p["avisos"])
    if p["status"] != "rejeitada":
        v = p["equipamento_vital"]
        d["resumo"]["equipamento_vital"]["a_confirmar" if v is None else "sim" if v else "nao"] -= 1


def troca_uc(d):
    d["pontos"][0]["uc"] = "99999999"


def troca_vital(d):
    p = d["pontos"][0]
    era = p["equipamento_vital"]
    p["equipamento_vital"] = not era
    ev = d["resumo"]["equipamento_vital"]
    ev["sim" if era else "nao"] -= 1
    ev["nao" if era else "sim"] += 1


for nome, mexer in [("uma linha a menos no JSON", tira_linha), ("UC trocada no JSON", troca_uc),
                    ("equipamento vital trocado no JSON", troca_vital)]:
    pega(nome, postes, sabotado(mp, mexer))

# ---------- tradutor sabotado ----------
uc_original = P._uc
P._uc = lambda v: (lambda r: ((r[0] + "0") if r[0] else r[0], r[1]))(uc_original(v))   # a UC sai com um zero a mais
try:
    pega("tradutor que muda a UC", postes, traduzir(postes, "Postes"))
finally:
    P._uc = uc_original
ponto_original = P._ponto
P._ponto = lambda n, v, c, p, e: (lambda pt: {**pt, "equipamento_vital": False})(ponto_original(n, v, c, p, e))   # perde o vital
try:
    pega("tradutor que perde o equipamento vital", postes, traduzir(postes, "Postes"))
finally:
    P._ponto = ponto_original
pega("arquivo que não dá para reler (aba sumiu)", postes, sabotado(mp, lambda d: d["arquivo"].update(aba="Outra")))
pega("arquivo corrompido", b"PK\x03\x04" + b"\0" * 100, mp)

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
