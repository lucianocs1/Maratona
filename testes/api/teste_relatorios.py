"""Teste da Fase D: prazo, relatório do período (mensal), comprovante, auditoria, acessos e painel do mês.

Roda num esquema próprio do Postgres (apagado no fim), com a semente de acesso e a de demonstração
(semente_demo: avisos, rádios e envios FICTÍCIOS). Confere:
- nucleo/prazo.py: 72 h, 5 dias úteis com equipamento vital (pulando o fim de semana), sem envio = fora da conta;
- os números do relatório batem com o banco (custo, envios, confirmados, economia calculada e informada);
- filtros (município, tipo, rádio, pessoa), comparação com o mês anterior, fora do prazo, sem envio, cancelados;
- PDF e CSV: cada exportação na auditoria com quem gerou, código FRL que /api/verificar acha, CSV protegido
  contra fórmula; nenhum número de UC nos relatórios;
- comprovante do aviso (JSON e PDF), só da própria empresa;
- relatório de auditoria (só Admin da empresa) e auditoria geral de acessos (só Admin do Norte, filtro por empresa);
- painel do mês (gasto, economizado, avisos, % no prazo) igual ao relatório do mês;
- a semente de demonstração não duplica ao rodar de novo.

Uso (na raiz): uv run python -W ignore testes/api/teste_relatorios.py
"""

import json
import os
import re
import sys
import zlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

os.environ["FAROL_ESQUEMA"] = "teste_relatorio"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo import prazo as P  # noqa: E402
from comunidades.nucleo import relatorio as R  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.semente_demo import semear_demo  # noqa: E402

resultados = []
NOVA = "Lanterna-do-Farol-2026"
BR = timezone(timedelta(hours=-3))


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(q, args=()):
    with conectar() as c, c.cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


def texto_pdf(b: bytes) -> str:
    partes = []
    # decompressobj ignora o que sobra depois do fim do zlib (o \r\n antes de endstream; um \r no fim dos dados não quebra)
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", b, re.S):
        try:
            partes.append(zlib.decompressobj().decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    return " ".join("".join(x.replace("\\(", "(").replace("\\)", ")") for x in re.findall(r"\(((?:\\.|[^\\)])*)\)", ln))
                    for ln in "\n".join(partes).splitlines())


# ---------- 1. Prazo (puro) ----------
gerado = datetime(2026, 10, 5, 10, 0, tzinfo=BR)        # segunda-feira
ini = P.inicio("09/10", "8h às 14h", gerado)            # sexta, 8h
conferir("início do desligamento: 09/10/2026 às 8h (Brasília)", ini == datetime(2026, 10, 9, 8, 0, tzinfo=BR), str(ini))
conferir("72 h: envio na segunda às 10h para sexta 8h está no prazo", P.situacao(ini, gerado, False)["no_prazo"] is True)
conferir("72 h: envio na quarta às 9h está fora (1 h de atraso)", P.situacao(ini, datetime(2026, 10, 7, 9, 0, tzinfo=BR), False)
         == {"no_prazo": False, "limite": datetime(2026, 10, 6, 8, 0, tzinfo=BR), "atraso_horas": 25.0})
seg = P.inicio("12/10", "8h", gerado)                    # segunda seguinte
conferir("5 dias úteis antes de segunda 12/10 8h: segunda 05/10 8h (pula o fim de semana)",
         P.limite(seg, True) == datetime(2026, 10, 5, 8, 0, tzinfo=BR), str(P.limite(seg, True)))
conferir("vital: envio na segunda 05/10 às 10h fica fora (2 h de atraso)", P.situacao(seg, gerado, True)["atraso_horas"] == 2.0)
conferir("sem envio: fora da conta (None)", P.situacao(seg, None, True)["no_prazo"] is None)
conferir("horário inválido: sem início", P.inicio("09/10", "manhã", gerado) is None and P.inicio("31/02", "8h", gerado) is None)

# ---------- 2. Relatório (puro) ----------
m1 = {"codigo_ibge": "1", "nome": "A", "uf": "MG", "ucs": 10, "equipamento_vital": {"sim": 1},
      "comunidades": [{"nome": "X", "distrito": "D", "afetadas": 10}]}
m2 = {"codigo_ibge": "2", "nome": "B", "uf": "MG", "ucs": 5, "equipamento_vital": {"sim": 0},
      "comunidades": [{"nome": "X", "distrito": "D", "afetadas": 5}, {"nome": "Y", "distrito": "E", "afetadas": 1}]}
av = [{"id": 1, "criado_em": gerado, "data": "20/10", "horario": "8h às 14h", "tipo": "poda", "status": "gerado", "usuario": "Ana", "municipios": [m1]},
      {"id": 2, "criado_em": gerado, "data": "06/10", "horario": "8h", "tipo": "obra", "status": "gerado", "usuario": "Bia", "municipios": [m2]},
      {"id": 3, "criado_em": gerado, "data": "20/10", "horario": "8h", "tipo": "obra", "status": "cancelado", "usuario": "Bia", "municipios": [m2]}]
en = [{"id": 1, "aviso_id": 1, "municipio": "1", "radio_id": 7, "radio_nome": "=Rádio 7", "canal": "email", "valor": Decimal("90"), "custo": Decimal("30"),
       "economia": Decimal("200"), "economia_tipo": "calculada", "segundos": 20, "tempo_economizado": 133, "status": "confirmado",
       "criado_em": gerado, "confirmado_em": gerado, "cobranca": "minuto", "criado_por_nome": "Ana"},
      {"id": 2, "aviso_id": 2, "municipio": "2", "radio_id": 8, "radio_nome": "Rádio 8", "canal": "copia", "valor": Decimal("100"), "custo": Decimal("100"),
       "economia": Decimal("50"), "economia_tipo": "informada", "segundos": 15, "tempo_economizado": None, "status": "enviado",
       "criado_em": gerado, "confirmado_em": None, "cobranca": "fechado", "criado_por_nome": "Bia"}]
rel = R.mensal(av, en, gerado.date(), gerado.date())
r = rel["resumo"]
conferir("resumo: 2 desligamentos, 1 cancelado, custo 130, calculada 200, informada 50, 1 no prazo de 2",
         (r["desligamentos"], r["cancelados"], r["custo"], r["economia_calculada"], r["economia_informada"], r["no_prazo"], r["com_envio"],
          r["pct_no_prazo"]) == (2, 1, "130.00", "200.00", "50.00", 1, 2, 50.0), json.dumps(r))
conferir("por comunidade: X em A e X em B são comunidades diferentes (município)", len(rel["por_comunidade"]) == 3)
conferir("fora do prazo: o aviso 2 (desligamento no dia seguinte)", [x["aviso"] for x in rel["fora_do_prazo"]] == [2])
conferir("filtro por rádio: só o aviso que foi para ela", R.mensal(av, en, gerado.date(), gerado.date(), {"radio": 8})["resumo"]["desligamentos"] == 1)
conferir("filtro por pessoa e por tipo", R.mensal(av, en, gerado.date(), gerado.date(), {"pessoa": "Ana"})["resumo"]["desligamentos"] == 1
         and R.mensal(av, en, gerado.date(), gerado.date(), {"tipo": "obra"})["resumo"]["cancelados"] == 1)
cs = R.mensal_csv(rel, "Fulana (Operador)", "FRL-AAAA-BBBB-CCCC")
conferir("CSV: rádio com '=' no nome sai com apóstrofo", ";'=Rádio 7;" in cs, cs[-300:])
comp = R.comparar(rel, R.mensal([], [], gerado.date(), gerado.date()))
conferir("comparação: diferenças, e % no prazo sem o anterior fica sem diferença", comp["desligamentos"]["diferenca"] == 2
         and comp["custo"]["diferenca"] == "130.00" and comp["pct_no_prazo"]["diferenca"] is None, json.dumps(comp)[:200])

# ---------- 3. Banco, semente de demonstração e API ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_relatorio CASCADE")
senhas = {e: s for _, e, s in semear()}
demo = semear_demo()
conferir("semente de demonstração: avisos, envios e rádios", demo["criados"] >= 12 and demo["envios"] >= 10 and demo["radios"] == 4, str(demo))
conferir("semente de demonstração de novo: não duplica", semear_demo()["criados"] == 0 and sql("SELECT count(*) FROM radio")[0][0] == 4)


def pronto(email, senha=None):
    api_acesso._tentativas_ip.clear()
    cl = TestClient(app, base_url="http://farol.teste")
    cl.post("/api/entrar", json={"email": email, "senha": senha or senhas[email]})
    cl.post("/api/senha", json={"atual": senha or senhas[email], "nova": NOVA})
    return cl


op, adm, con, far = (pronto(e) for e in ("operador@emg.example", "admin@emg.example", "consulta@emg.example", "admin@farol.example"))
hoje = datetime.now(BR).date()
mes, anterior = f"{hoje:%Y-%m}", R.mes_anterior(hoje.replace(day=1))
juntos = {}
for m_ in (anterior, mes):
    j = con.get(f"/api/relatorios/mensal?mes={m_}").json()
    juntos[m_] = j
ent = sum(j["resumo"]["envios"] for j in juntos.values())
custo = sum(Decimal(j["resumo"]["custo"]) for j in juntos.values())
db = sql("SELECT count(*), sum(custo), sum(economia) FILTER (WHERE economia_tipo = 'calculada') FROM envio")[0]
conferir("relatório (Consulta): envios e custo dos dois meses batem com o banco", ent == db[0] and custo == db[1], f"{ent} {custo} x {db}")
calc = sum(Decimal(j["resumo"]["economia_calculada"]) for j in juntos.values())
conferir("economia calculada dos dois meses = soma no banco", calc == db[2], f"{calc} x {db[2]}")
j = juntos[mes]
todos = {k: sum(x["resumo"][k] for x in juntos.values()) for k in ("desligamentos", "cancelados")}
conferir("um cancelado, um sem envio e um fora do prazo no período da demonstração", todos["cancelados"] == 1
         and sum(len(x["sem_envio"]) for x in juntos.values()) == 1 and sum(len(x["fora_do_prazo"]) for x in juntos.values()) >= 1,
         json.dumps({k: [len(x[k]) for x in juntos.values()] for k in ("sem_envio", "fora_do_prazo")}))
conferir("por rádio: soma dos envios = envios do resumo", sum(x["envios"] for x in j["por_radio"]) == j["resumo"]["envios"])
conferir("comparação com o mês anterior presente (↑↓ % no resumo do documento)",
         any(c["contra"] == "mês anterior" for x in j["documento"]["resumo"] for c in x["comparacoes"]),
         json.dumps(j["documento"]["resumo"], ensure_ascii=False)[:300])
conferir("lista detalhada: um item por aviso do período, com o código FRL", len(j["lista"]) == j["resumo"]["desligamentos"] + j["resumo"]["cancelados"]
         and all((x["codigo"] or "").startswith("FRL-") for x in j["lista"]))
leo = next(c for c, n in j["opcoes"]["municipios"] if n.startswith("Leopoldina"))
fl = con.get(f"/api/relatorios/mensal?mes={mes}&municipio={leo}").json()
conferir("filtro por município: só avisos que passam por ele", fl["resumo"]["desligamentos"] <= j["resumo"]["desligamentos"]
         and all("Leopoldina" in x["municipios"] for x in fl["lista"]))
pessoa = "Admin da EMG"
fp = con.get(f"/api/relatorios/mensal?mes={anterior}&pessoa={pessoa}").json()
conferir("filtro por pessoa: só os avisos que ela pediu", all(x["por"] == pessoa for x in fp["lista"]))
ft = con.get(f"/api/relatorios/mensal?mes={anterior}&tipo=poda").json()
conferir("filtro por tipo: só desse tipo", all(x["tipo"] == "Poda de árvores" for x in ft["lista"]))
rid = juntos[anterior]["opcoes"]["radios"][0][0]
fr = con.get(f"/api/relatorios/mensal?mes={anterior}&radio={rid}").json()
conferir("filtro por rádio: só os envios dela", {x["radio"] for x in fr["por_radio"]} <= {juntos[anterior]["opcoes"]["radios"][0][1]})
conferir("período inválido: 422", con.get("/api/relatorios/mensal?mes=2026-13").status_code == 422
         and con.get("/api/relatorios/mensal?inicio=2026-10-10&fim=2026-01-01").status_code == 422)

textos = json.dumps(juntos, ensure_ascii=False)
conferir("relatório sem número de UC (nenhuma sequência de 10 algarismos)", not re.search(r"\b3\d{9}\b", textos))

# exportações e código
p = con.get(f"/api/relatorios/mensal.pdf?mes={anterior}")
cod = p.headers.get("x-codigo", "")
txt = texto_pdf(p.content)
conferir("PDF do período: gerado por (nome e perfil) e o código", p.content[:5] == b"%PDF-" and "Consulta da EMG (Consulta)" in txt and cod in txt
         and "Como calculamos" in txt and not re.search(r"\b3\d{9}\b", txt), txt[:200])
vc = adm.get(f"/api/verificar/{cod}")
conferir("o código do relatório está na auditoria (verificar)", vc.status_code == 200 and vc.json()["acao"] == "gerou relatório mensal (PDF)"
         and vc.json()["por"] == "Consulta da EMG", vc.text[:160])
cv = con.get(f"/api/relatorios/mensal.csv?mes={anterior}")
conferir("CSV do período: cabeçalho com quem gerou e o código; uma linha por aviso", cv.status_code == 200 and "Consulta da EMG (Consulta)" in cv.text
         and cv.headers["x-codigo"] in cv.text and cv.text.count("\r\n") > 20, cv.text[:200])

# comprovante
aid = juntos[anterior]["lista"][0]["aviso"]
cp = con.get(f"/api/historico/{aid}/comprovante").json()
conferir("comprovante (Consulta): quem pediu, tipo, municípios, comunidades, envios, prazo e custo",
         cp["aviso"] == aid and cp["por"] and cp["tipo"] and cp["municipios"] and "regra" in cp["prazo"] and "custo" in cp, json.dumps(cp)[:200])
cpdf = con.get(f"/api/historico/{aid}/comprovante.pdf")
conferir("comprovante em PDF com o código do aviso e o do comprovante", cpdf.content[:5] == b"%PDF-" and cp["codigo"] in texto_pdf(cpdf.content)
         and cpdf.headers["x-codigo"] in texto_pdf(cpdf.content))

# auditoria e acessos
ra = adm.get(f"/api/relatorios/auditoria?mes={mes}")
conferir("relatório de auditoria (Admin da empresa): linhas com quem e perfil", ra.status_code == 200 and ra.json()["total"] > 5
         and any(x["acao"] == "semente de demonstração" for x in ra.json()["linhas"]), ra.text[:160])
conferir("relatório de auditoria: Operador, Consulta e Admin do Norte não (403)", all(c_.get(f"/api/relatorios/auditoria?mes={mes}").status_code == 403
                                                                                     for c_ in (op, con, far)))
so = adm.get(f"/api/relatorios/auditoria?mes={mes}&so_acessos=true").json()
conferir("relatório de auditoria: só acessos", so["total"] > 0 and {x["acao"] for x in so["linhas"]} <= set(__import__("comunidades.api.relatorios", fromlist=["x"]).ACESSOS))
apdf = adm.get(f"/api/relatorios/auditoria.pdf?mes={mes}")
acsv = adm.get(f"/api/relatorios/auditoria.csv?mes={mes}&pessoa=Operador da EMG")
conferir("auditoria em PDF e CSV (filtro por pessoa), com o código", apdf.content[:5] == b"%PDF-" and acsv.status_code == 200
         and "Operador da EMG" in acsv.text and "Admin da EMG;" not in acsv.text and acsv.headers["x-codigo"] in acsv.text,
         acsv.text[:400])
r = far.post("/api/empresas", json={"nome": "Outra", "sigla": "OUT", "dominio": "out.example", "admin_nome": "Admin Outra",
                                    "admin_email": "admin@out.example"})
outra = pronto("admin@out.example", r.json()["senha_temporaria"])
ac = far.get(f"/api/relatorios/acessos?mes={mes}").json()
conferir("acessos (Admin do Norte): de todas as empresas", {"EMG", "OUT"} <= {x["empresa"] for x in ac["linhas"]}, str({x["empresa"] for x in ac["linhas"]}))
conferir("acessos: filtro por empresa", {x["empresa"] for x in far.get(f"/api/relatorios/acessos?mes={mes}&empresa=OUT").json()["linhas"]} == {"OUT"})
conferir("acessos: Admin da empresa não (403)", adm.get(f"/api/relatorios/acessos?mes={mes}").status_code == 403
         and far.get(f"/api/relatorios/acessos.pdf?mes={mes}").content[:5] == b"%PDF-")
conferir("outra empresa: relatório vazio e comprovante da EMG 404", outra.get(f"/api/relatorios/mensal?mes={anterior}").json()["resumo"]["desligamentos"] == 0
         and outra.get(f"/api/historico/{aid}/comprovante").status_code == 404)
pm = con.get("/api/painel").json()["mes"]
conferir("painel do mês = relatório do mês (gasto, economizado, avisos, % no prazo)",
         (pm["gasto"], pm["economia_calculada"], pm["desligamentos"], pm["pct_no_prazo"]) ==
         (j["resumo"]["custo"], j["resumo"]["economia_calculada"], j["resumo"]["desligamentos"], j["resumo"]["pct_no_prazo"]), json.dumps(pm))
conferir("cada exportação ficou na auditoria com o nome de quem gerou", sql("SELECT count(*) FROM registro WHERE acao LIKE 'gerou relatório%%' "
                                                                            "OR acao LIKE 'gerou comprovante%%' OR acao LIKE 'gerou auditoria%%'")[0][0] >= 6)
conferir("auditoria íntegra", far.get("/api/auditoria/verificar").json()["ok"])

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_relatorio CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
