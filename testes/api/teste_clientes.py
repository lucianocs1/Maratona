"""Teste dos clientes FICTÍCIOS da concessão (a camada "Clientes" do mapa): banco, rede e API.

Roda num esquema próprio para o acesso (FAROL_ESQUEMA=teste_clientes), apagado no fim; os clientes são lidos da base
pública (tabela cliente_ficticio, gerada por clientes_concessao.py). Confere:
- o banco: os 66 municípios têm clientes; o total fecha com os clientes dos transformadores da rede; cada cliente aponta
  para um transformador e um circuito que existem no município; só as colunas permitidas (nada de UC, titular ou endereço);
- a API: só quem gera aviso vê (Admin da empresa e Operador); Consulta e Admin do Norte levam 403; a janela do mapa devolve
  densidade de longe e pontos de perto, no formato certo e sem nenhum número de UC; janela inválida é 422;
- o isolamento: a empresa só vê os clientes dos municípios da área de atuação dela.

Uso (na raiz): uv run python -W ignore testes/api/teste_clientes.py
"""

import json
import os
import re
import sys

os.environ["FAROL_ESQUEMA"] = "teste_clientes"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco import acesso as banco_acesso  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(consulta, args=()):
    with conectar() as c:
        cur = c.execute(consulta, args)
        return cur.fetchall() if cur.description else []


LEOPOLDINA, UBA = "3138401", "3169901"
JANELA = dict(sul=-21.60, oeste=-42.70, norte=-21.48, leste=-42.58)

# ---------- 1. O banco ----------
n_mun = sql("SELECT count(DISTINCT codigo_ibge) FROM cliente_ficticio")[0][0]
conferir("os 66 municípios da concessão têm clientes fictícios", n_mun == 66, str(n_mun))
total = sql("SELECT count(*) FROM cliente_ficticio")[0][0]
uc_trafos = sql("SELECT sum(n_uc) FROM rede_trafo")[0][0]
conferir("o total de clientes fecha com os clientes dos transformadores da rede", total == uc_trafos, f"{total} x {uc_trafos}")
sem_trafo = sql("SELECT count(*) FROM cliente_ficticio c WHERE NOT EXISTS (SELECT 1 FROM rede_trafo t WHERE t.codigo_ibge = c.codigo_ibge AND t.codigo = c.trafo)")[0][0]
conferir("todo cliente aponta para um transformador do próprio município", sem_trafo == 0, str(sem_trafo))
sem_circuito = sql("SELECT count(*) FROM cliente_ficticio c WHERE NOT EXISTS (SELECT 1 FROM rede_trecho r WHERE r.codigo_ibge = c.codigo_ibge AND r.alimentador = c.alimentador)")[0][0]
conferir("todo cliente aponta para um circuito (alimentador) do próprio município", sem_circuito == 0, str(sem_circuito))
colunas = {r[0] for r in sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'cliente_ficticio'")}
conferir("só as colunas permitidas: nada de número de UC, titular ou endereço",
         colunas == {"codigo_ibge", "classe", "vital", "ativa", "trafo", "alimentador", "ponto"}, str(sorted(colunas)))
classes = {r[0] for r in sql("SELECT DISTINCT classe FROM cliente_ficticio")}
conferir("classes de 1 a 4 (residencial, rural, comercial, poder público)", classes <= {1, 2, 3, 4} and len(classes) == 4, str(classes))
vital = sql("SELECT count(*) FILTER (WHERE vital), count(*) FILTER (WHERE vital AND classe IN (3, 4)), count(*) FILTER (WHERE NOT ativa) FROM cliente_ficticio")[0]
conferir("vital só entre residenciais e rurais (cerca de 1,2%); inativas cerca de 3%",
         vital[1] == 0 and 0.008 < vital[0] / total < 0.016 and 0.02 < vital[2] / total < 0.04, str(vital))

# ---------- 2. A API ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_clientes CASCADE")
senhas = {email: s for _, email, s in semear()}
NOVA = "Lanterna-do-Norte-2026"


def entrar(email):
    api_acesso._tentativas_ip.clear()
    cl = TestClient(app, base_url="http://farol.teste")
    cl.post("/api/entrar", json={"email": email, "senha": senhas[email]})
    cl.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
    return cl


op, adm = entrar("operador@emg.example"), entrar("admin@emg.example")
con, nor = entrar("consulta@emg.example"), entrar("admin@farol.example")
r = op.get("/api/clientes/resumo")
j = r.json()
conferir("resumo (Operador): total, vitais, inativas e as 4 classes, só números",
         r.status_code == 200 and j["total"] == total and j["ficticio"] is True and set(j["classes"]) == {"Residencial", "Rural", "Comercial", "Poder Público"}
         and all(isinstance(v, int) for v in j["classes"].values()), str(j))
conferir("resumo e janela: o Admin da empresa vê", adm.get("/api/clientes/resumo").status_code == 200
         and adm.get("/api/clientes", params={**JANELA, "zoom": 12}).status_code == 200)
conferir("Consulta não vê os clientes (403), como já é com os pontos de UC", con.get("/api/clientes/resumo").status_code == 403
         and con.get("/api/clientes", params={**JANELA, "zoom": 12}).status_code == 403)
conferir("Admin do Norte não vê o mapa operacional (403)", nor.get("/api/clientes/resumo").status_code == 403
         and nor.get("/api/clientes", params={**JANELA, "zoom": 12}).status_code == 403)
conferir("sem login: 401", TestClient(app, base_url="http://farol.teste").get("/api/clientes/resumo").status_code == 401)

longe = op.get("/api/clientes", params={**JANELA, "zoom": 12}).json()
conferir("de longe: densidade em quadradinhos [lat, lon, n, vitais]",
         longe["modo"] == "densidade" and len(longe["celulas"]) > 20 and longe["lado"] > 0 and all(len(c) == 4 for c in longe["celulas"])
         and sum(c[2] for c in longe["celulas"]) > 20000, f"{longe['modo']} {len(longe['celulas'])}")
perto = op.get("/api/clientes", params={"sul": -21.535, "oeste": -42.645, "norte": -21.525, "leste": -42.635, "zoom": 16}).json()
conferir("de perto: um ponto por cliente [lat, lon, classe, vital, ativa]",
         perto["modo"] == "pontos" and len(perto["pontos"]) > 50 and all(len(p) == 5 and p[2] in (1, 2, 3, 4) and isinstance(p[3], bool) and isinstance(p[4], bool)
                                                                       for p in perto["pontos"]) and perto["cortado"] is False, f"{perto['modo']} {len(perto['pontos'])}")
conferir("os pontos estão dentro da janela pedida", all(-21.535 <= p[0] <= -21.525 and -42.645 <= p[1] <= -42.635 for p in perto["pontos"]))
texto = json.dumps([longe, perto])
conferir("a resposta não tem número de UC nem de transformador (nenhum inteiro de 6 algarismos ou mais)", not re.search(r"(?<![.\d])\d{6,}", texto))   # inteiros longos; casas decimais de coordenada não contam
for ruim in ({**JANELA, "zoom": 4}, {**JANELA, "zoom": 21}, {"sul": -21.5, "oeste": -42.7, "norte": -21.6, "leste": -42.58, "zoom": 12},
             {"sul": -95, "oeste": -42.7, "norte": -21.6, "leste": -42.58, "zoom": 12}):
    conferir(f"janela inválida é 422 ({ruim['zoom']}, {ruim['sul']})", op.get("/api/clientes", params=ruim).status_code == 422)
conferir("sem a janela: 422", op.get("/api/clientes").status_code == 422)

# ---------- 3. O isolamento pela área de atuação ----------
dono = banco_acesso.usuario_por_email("operador@emg.example")
sql("DELETE FROM empresa_municipio WHERE empresa_id = %s AND codigo_ibge <> %s", (dono["empresa_id"], UBA))
so_uba = op.get("/api/clientes/resumo").json()["total"]
uba = sql("SELECT count(*) FROM cliente_ficticio WHERE codigo_ibge = %s", (UBA,))[0][0]
conferir("com a área só em Ubá, o resumo conta só os clientes de Ubá", so_uba == uba, f"{so_uba} x {uba}")
fora = op.get("/api/clientes", params={**JANELA, "zoom": 12}).json()
conferir("e a janela de Leopoldina volta vazia", fora["celulas"] == [], str(len(fora["celulas"])))

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_clientes CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
