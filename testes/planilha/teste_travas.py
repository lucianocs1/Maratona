"""Teste das travas da conferência (nucleo/travas.py) e do pacote assinado (api/pacote.py), sem banco.

Confere:
- equipamento vital rejeitado, corrigido ou fora da concessão vira alerta vermelho pela linha, e
  bloqueia a geração mesmo com justificativa e "Conferi" marcado;
- limite de rejeição: acima dele, só com justificativa (até 300 caracteres, limpa de controle);
- sem "Conferi os números e o mapa", nada é gerado;
- suspeitos amarelos: ponto isolado, mesma coordenada em muitas UCs e município diferente da maioria;
- UCs opacas no pacote (a mesma UC, o mesmo código; nenhum número original);
- pacote: ida e volta, adulterado, vencido, de outro usuário, de outra empresa, fora do esquema e
  bomba de descompressão (mesmo assinada) são recusados;
- relatório CSV: uma linha por linha, sem UC nem coordenada, e o que começa com = + - @ TAB ou CR
  sai com apóstrofo.

Uso (na raiz): uv run python -W ignore testes/planilha/teste_travas.py
"""

import base64
import gzip
import json
import os
import sys
import time

os.environ.setdefault("FAROL_CHAVE_PACOTE", "chave-de-teste-do-pacote-com-mais-de-32-caracteres")

from comunidades.api import pacote as PC  # noqa: E402
from comunidades.fontes.concessao import contorno  # noqa: E402
from comunidades.nucleo import coordenadas as K  # noqa: E402
from comunidades.nucleo import planilha as P  # noqa: E402
from comunidades.nucleo import travas as T  # noqa: E402

resultados = []
PAR = P.Parametros(dentro=K.Area(contorno()), muitas_ucs=3)
P0 = (-21.530443, -42.638946)


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def montar(linhas, cab=("uc", "latitude", "longitude", "equipamento_vital"), nome="planilha.csv"):
    campos = P.campos_por_indice(list(cab))
    return P.montar(campos, list(cab), [(i + 2, list(v)) for i, v in enumerate(linhas)], PAR,
                    arquivo={"nome": nome, "sha256": "a" * 64, "formato": "csv", "aba": None, "colunas_ignoradas": 0},
                    empresa="EMG", gerado_em="2026-10-14T10:00", gerado_por="Fulana (Operador)")


# ---------- equipamento vital ----------
m = montar([("101", *P0, "sim"),                       # 2: ok
            ("102", P0[1], P0[0], "sim"),              # 3: trocadas -> corrigida
            ("103", -23.55, -46.63, "sim"),            # 4: São Paulo -> rejeitada (fora)
            ("104", "", "", "sim"),                    # 5: sem coordenada -> rejeitada
            ("105", P0[1], P0[0], "não"),              # 6: corrigida sem vital: não bloqueia
            ("106", *P0, "sim")])                      # 7: ok, mas a API diz que ficou fora dos contornos
vb = T.vital_bloqueio(m, linhas_fora={7})
conferir("vital: corrigida, rejeitadas e fora dos contornos, pela linha",
         [(x["linha"], x["situacao"]) for x in vb] == [(3, "corrigida"), (4, "rejeitada"), (5, "rejeitada"), (7, "fora")], json.dumps(vb, ensure_ascii=False))
conferir("vital: o alerta não traz a UC", not any(u in json.dumps(vb) for u in ("101", "102", "103", "104", "106")))
tr = {"vital_bloqueio": vb, "rejeicao": T.rejeicao(m, 0.02)}
conferir("vital bloqueia mesmo com 'Conferi' e justificativa", "equipamento vital" in (T.problema_para_gerar(tr, True, "justifico") or ""))

# ---------- limite de rejeição e confirmação ----------
r = T.rejeicao(m, 0.02)
conferir("rejeição: 2 de 6 (33%) acima de 2%", r == {"rejeitadas": 2, "total": 6, "fracao": 0.3333, "limite": 0.02, "acima": True}, str(r))
conferir("rejeição: exatamente no limite não pede justificativa", T.rejeicao(montar([("1", *P0, "")] * 1), 0.0)["acima"] is False)
livre = {"vital_bloqueio": [], "rejeicao": {**r, "acima": True}}
casos = {
    "acima do limite, sem justificativa": (livre, True, None, "justificativa"),
    "acima do limite, justificativa só de espaços": (livre, True, " \t\n ", "justificativa"),
    "justificativa com 301 caracteres": (livre, True, "x" * 301, "300"),
    "com justificativa e sem 'Conferi'": (livre, False, "motivo", "Conferi"),
    "com justificativa e 'Conferi'": (livre, True, "motivo", None),
    "abaixo do limite, sem 'Conferi'": ({"vital_bloqueio": [], "rejeicao": {**r, "acima": False}}, False, None, "Conferi"),
    "abaixo do limite, com 'Conferi'": ({"vital_bloqueio": [], "rejeicao": {**r, "acima": False}}, True, None, None),
}
for nome, (trava, conferi_, just, esperado) in casos.items():
    p = T.problema_para_gerar(trava, conferi_, just)
    conferir(f"pode gerar? {nome}", (p is None) if esperado is None else (p is not None and esperado in p), str(p))
conferir("justificativa limpa: sem controle, espaços juntados", T.limpar_justificativa("a\x00b\t c\n​d") == "a b c d",
         repr(T.limpar_justificativa("a\x00b\t c\n​d")))

# ---------- suspeitos ----------
iso = montar([("1", *P0, ""), ("2", -21.5305, -42.6390, ""), ("3", -21.12, -42.37, "")])
s = T.suspeitos(iso, {})
conferir("suspeito: ponto isolado (mais de 20 km do vizinho)", [(x["tipo"], x["linhas"]) for x in s] == [("ponto_isolado", [4])], json.dumps(s, ensure_ascii=False))
muitas = montar([(str(i), *P0, "") for i in range(4)])
conferir("suspeito: a mesma coordenada em muitas UCs (3 ou mais)",
         [(x["tipo"], x["ucs"]) for x in T.suspeitos(muitas, {})] == [("muitas_ucs", 4)])
md = T.municipio_diferente({"Leopoldina/MG": list(range(2, 98)), "Cataguases/MG": [98, 99, 100], "Muriaé/MG": [101]})
conferir("suspeito: municípios com até 5% das UCs, com a maioria apontada",
         [(x["municipio"], x["maioria"], x["ucs"]) for x in md] == [("Cataguases/MG", "Leopoldina/MG", 3), ("Muriaé/MG", "Leopoldina/MG", 1)], str(md))
conferir("suspeito: dois municípios equilibrados não são suspeitos", T.municipio_diferente({"A": [2, 3], "B": [4, 5]}) == [])
conferir("suspeito: um município só, nada", T.municipio_diferente({"A": [2]}) == [] and T.municipio_diferente({}) == [])

# ---------- UCs opacas ----------
rep = montar([("53464097", *P0, ""), ("53464098", -21.5306, -42.6391, ""), ("53464097", -21.5307, -42.6392, "")])
op = T.ucs_opacas(rep)
conferir("UCs opacas: u1, u2 e a repetida com o mesmo código", [pt.uc for pt in op.pontos] == ["u1", "u2", "u1"])
conferir("UCs opacas: nenhum número original no JSON, o resto igual", "5346409" not in op.model_dump_json()
         and [pt.model_dump(exclude={"uc"}) for pt in op.pontos] == [pt.model_dump(exclude={"uc"}) for pt in rep.pontos])

# ---------- pacote assinado ----------
pac, vence = PC.assinar(op, 7, 3)
conferir("pacote: ida e volta (mesmo JSON)", PC.abrir(pac, 7, 3).model_dump_json() == op.model_dump_json() and vence - time.time() > 14 * 60)


def recusa(nome, pacote, u=7, e=3, agora=None, trecho=""):
    try:
        PC.abrir(pacote, u, e, agora)
        conferir(f"pacote recusado: {nome}", False)
    except PC.PacoteRecusado as erro:
        conferir(f"pacote recusado: {nome}", trecho in str(erro), str(erro))


v, corpo, ass = pac.split(".")
recusa("um caractere do corpo trocado", f"{v}.{corpo[:10]}{'B' if corpo[10] != 'B' else 'C'}{corpo[11:]}.{ass}", trecho="alterado")
recusa("assinatura trocada", f"{v}.{corpo}.{'0' * 64}", trecho="alterado")
recusa("versão desconhecida", f"v9.{corpo}.{ass}", trecho="alterado")
recusa("vencido (16 minutos depois)", pac, agora=time.time() + 16 * 60, trecho="venceu")
recusa("de outro usuário", pac, u=8, trecho="outro usuário")
recusa("de outra empresa", pac, e=4, trecho="outro usuário")
recusa("texto qualquer", "nada-a-ver", trecho="alterado")
recusa("grande demais", f"{PC.VERSAO}." + "A" * (PC.MAX_PACOTE + 1) + ".x", trecho="inválido")


def assinado(dados: bytes) -> str:
    c = base64.urlsafe_b64encode(gzip.compress(dados, mtime=0)).decode().rstrip("=")
    return f"{PC.VERSAO}.{c}.{PC._assinatura(c)}"


envelope = lambda mm: json.dumps({"u": 7, "e": 3, "vence": int(time.time()) + 600, "f": "escolha", "c": None, "m": mm}).encode()
base = json.loads(op.model_dump_json())
recusa("assinado, mas com campo a mais", assinado(envelope(json.dumps({**base, "extra": 1}))), trecho="esquema")
recusa("assinado, mas com a conta que não fecha", assinado(envelope(json.dumps({**base, "resumo": {**base["resumo"], "ok": 99}}))), trecho="esquema")
recusa("assinado, mas com NaN na coordenada", assinado(envelope(json.dumps(base).replace("-21.530443", "NaN", 1))), trecho="esquema")
recusa("assinado, mas bomba de descompressão (100 MB de espaços)", assinado(b" " * 100_000_000), trecho="grande demais")
recusa("assinado, mas não é JSON", assinado(b"\xff\xfe nada"), trecho="ilegível")

# ---------- fase e critério da escolha (nucleo/selecao.py) ----------
from comunidades.nucleo import selecao as SEL  # noqa: E402

crit = SEL.Criterio(modo="escolha", circuito=("CIR2", "CIR1", "CIR1"))
pe, _ = PC.assinar(op, 7, 3, criterio=crit)
m_, c_ = PC.abrir_escolha(pe, 7, 3)
conferir("pacote da escolha: o critério volta canônico (o mesmo que foi conferido)",
         c_ == SEL.canonico(crit) and m_.model_dump_json() == op.model_dump_json(), str(c_))
pb, _ = PC.assinar(op, 7, 3, fase="base")
try:
    PC.abrir_escolha(pb, 7, 3)
    conferir("pacote da base (só a planilha lida) não gera aviso", False)
except PC.PacoteRecusado as erro:
    conferir("pacote da base (só a planilha lida) não gera aviso", "Escolha quem será desligado" in str(erro), str(erro))
conferir("pacote da base abre na fase base", PC.abrir(pb, 7, 3, fase="base").resumo == op.resumo)
try:
    PC.abrir(pe, 7, 3, fase="base")
    conferir("pacote da escolha recusado onde se pede o da base", False)
except PC.PacoteRecusado:
    conferir("pacote da escolha recusado onde se pede o da base", True)
recusa("assinado, mas com critério fora do esquema", assinado(json.dumps({"u": 7, "e": 3, "vence": int(time.time()) + 600, "f": "escolha",
       "c": json.dumps({"modo": "escolha", "ucs": ["1"]}), "m": op.model_dump_json()}).encode()), trecho="esquema")
conferir("sem critério, o pacote da escolha é a planilha inteira", PC.abrir_escolha(pac, 7, 3)[1] == SEL.Criterio(modo="planilha"))

# ---------- relatório CSV ----------
perigo = montar([("1", *P0, "talvez"), ("2", P0[1], P0[0], ""), ("3", "", "", "")], nome="=cmd|' /C calc'!A0.csv")
csv_ = T.relatorio_csv(perigo)
linhas = csv_.splitlines()
conferir("relatório: cabeçalho, uma linha por linha da planilha", len(linhas) == 2 + 3 and linhas[1].startswith("linha;situacao"), csv_)
conferir("relatório: nome de arquivo com fórmula sai com apóstrofo", linhas[0].startswith("arquivo;'=cmd"), linhas[0])
conferir("relatório: corrigida e rejeitada com o texto da lista fechada",
         linhas[3].startswith("3;corrigida;latitude e longitude estavam trocadas") and linhas[4].startswith("4;rejeitada;sem coordenada"), csv_)
conferir("relatório: nenhuma coordenada", "21.53" not in csv_ and "21,53" not in csv_)
for v_, esperado in [("=1+1", "'=1+1"), ("+55", "'+55"), ("-3", "'-3"), ("@SUM", "'@SUM"), ("\tx", "'\tx"), ("\rx", "'\rx"),
                     ("ok", "ok"), (12, "12"), (None, ""), (True, "sim")]:
    conferir(f"célula segura: {v_!r}", T.celula_segura(v_) == esperado, repr(T.celula_segura(v_)))

# ---------- agrupamento por circuito e transformador ----------
from comunidades.nucleo import agrupamento as G  # noqa: E402

g = G.por_codigo(["CIR1", "CIR2", "CIR1", None, "", "CIR1"], limite=1)
conferir("agrupamento: o maior primeiro, total de códigos e UCs sem código", g == {"grupos": [{"codigo": "CIR1", "ucs": 3}], "total": 2, "sem_codigo": 2}, str(g))

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
