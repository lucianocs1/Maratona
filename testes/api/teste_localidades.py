"""Teste das localidades oficiais do IBGE (a camada do mapa e o relatório de conferência): banco, API e planilhas.

Roda num esquema próprio para o acesso (FAROL_ESQUEMA=teste_localidades), apagado no fim; as localidades e as comunidades
são lidas da base pública. Confere:
- o banco: as 470 localidades dos 66 municípios (a mesma base do IBGE que o projeto já usa), com nome e categoria, cada uma
  dentro de alguma comunidade nossa, sem repetir o par (município, código);
- a API: os três perfis da empresa veem; o Admin do Norte (403) e quem não entrou (401) não; só a área da empresa; formato
  [lat, lon, nome, categoria, município], dado público sem nenhum dado pessoal;
- o relatório: as três planilhas saem com acento para o Excel (utf-8-sig, ";"), com as colunas de decisão em branco, e os
  números batem com a conta direta.

Uso (na raiz): uv run python -W ignore testes/api/teste_localidades.py
"""

import csv
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["FAROL_ESQUEMA"] = "teste_localidades"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco import localidades as banco  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo import localidades as regra  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.validacao import localidades as relatorio  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(consulta, args=()):
    with conectar() as c:
        cur = c.execute(consulta, args)
        return cur.fetchall() if cur.description else []


UBA = "3169901"

# ---------- 1. O banco ----------
total = sql("SELECT count(*) FROM localidade_oficial")[0][0]
n_mun = sql("SELECT count(DISTINCT codigo_ibge) FROM localidade_oficial")[0][0]
conferir("470 localidades oficiais nos 66 municípios da concessão", total == 470 and n_mun == 66, f"{total} em {n_mun}")
repetidas = sql("SELECT count(*) FROM (SELECT codigo_ibge, codigo, nome, ST_AsText(ponto) FROM localidade_oficial GROUP BY 1, 2, 3, 4 HAVING count(*) > 1) q")[0][0]
conferir("nenhuma linha repetida (ao rodar o carregador de novo ele substitui, não duplica)", repetidas == 0, str(repetidas))
sedes = sql("SELECT count(*) FROM localidade_oficial WHERE categoria = 'Cidade'")[0][0]
conferir("cada município tem a sua sede (Cidade): 66", sedes == 66, str(sedes))
fora = sql("SELECT count(*) FROM localidade_oficial l WHERE NOT EXISTS (SELECT 1 FROM comunidade c WHERE c.codigo_ibge = l.codigo_ibge"
           " AND c.territorio IS NOT NULL AND ST_Contains(c.territorio, l.ponto))")[0][0]
conferir("toda localidade oficial cai dentro de alguma comunidade nossa (o mapa cobre todas)", fora == 0, str(fora))
colunas = {r[0] for r in sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'localidade_oficial'")}
conferir("só as colunas públicas: município, código, nome, categoria e ponto", colunas == {"codigo_ibge", "codigo", "nome", "categoria", "ponto"}, str(sorted(colunas)))

# ---------- 2. A API ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_localidades CASCADE")
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
r = op.get("/api/localidades-oficiais")
j = r.json()
conferir("Operador: 470 localidades, com a fonte", r.status_code == 200 and len(j["localidades"]) == 470 and j["fonte"].startswith("IBGE"), f"{r.status_code} {len(j.get('localidades', []))}")
conferir("formato [lat, lon, nome, categoria, município]", all(len(p) == 5 and isinstance(p[0], float) and isinstance(p[1], float) and all(isinstance(x, str) and x for x in p[2:])
                                                           for p in j["localidades"]))
conferir("os pontos estão na região da concessão (MG e RJ)", all(-23 < p[0] < -19.5 and -45 < p[1] < -41.5 for p in j["localidades"]))
conferir("Admin da empresa e Consulta também veem (dado público)", adm.get("/api/localidades-oficiais").status_code == 200 and con.get("/api/localidades-oficiais").status_code == 200)
conferir("Admin do Norte não vê o mapa operacional (403)", nor.get("/api/localidades-oficiais").status_code == 403)
conferir("sem login: 401", TestClient(app, base_url="http://farol.teste").get("/api/localidades-oficiais").status_code == 401)
texto = str(j)
conferir("a resposta não tem nada além de nome, categoria e município (nenhum número longo, e-mail ou CPF)", not re.search(r"(?<![.\d-])\d{6,}", texto) and "@" not in texto)

# ---------- 3. O isolamento pela área de atuação ----------
dono = sql("SELECT empresa_id FROM usuario WHERE email = 'operador@emg.example'")[0][0]
sql("DELETE FROM empresa_municipio WHERE empresa_id = %s AND codigo_ibge <> %s", (dono, UBA))
so_uba = op.get("/api/localidades-oficiais").json()["localidades"]
esperado = sql("SELECT count(*) FROM localidade_oficial WHERE codigo_ibge = %s", (UBA,))[0][0]
conferir("com a área só em Ubá, a resposta traz só as localidades de Ubá", len(so_uba) == esperado and {p[4] for p in so_uba} == {"Ubá"}, f"{len(so_uba)} x {esperado}")

# ---------- 4. O relatório de conferência ----------
oficiais, comunidades = banco.todas(), banco.comunidades()
rel = relatorio.conferir(oficiais, comunidades)
c = rel["conferencia"]
igual = sum(1 for l in c if l["casamento"] == regra.IGUAL)
conferir("a conta do relatório fecha: 470 linhas, e igual + parecido + sem par = 470", len(c) == 470 and sum(1 for l in c if l["casamento"] in (regra.IGUAL, regra.PARECIDO, regra.SEM_PAR)) == 470, str(len(c)))
conferir("mais da metade das localidades casam por nome (hoje 279 de 470)", 250 <= igual + sum(1 for l in c if l["casamento"] == regra.PARECIDO) <= 330, str(igual))
conferir("nenhuma localidade cai fora de todas as comunidades", all(l["comunidade_onde_o_ponto_cai"] != "nenhuma" for l in c))
conferir("o resumo tem uma linha por município e as somas batem", len(rel["resumo"]) == 66 and sum(x["localidades_ibge"] for x in rel["resumo"]) == 470
         and sum(x["comunidades_nossas"] for x in rel["resumo"]) == len(comunidades))
conferir("as comunidades sem nome oficial = as nossas menos as que têm par", len(rel["sem_nome_oficial"]) == len(comunidades) - sum(x["comunidades_com_par_no_ibge"] for x in rel["resumo"]))

with tempfile.TemporaryDirectory() as pasta:
    relatorio.SAIDA = Path(pasta)
    rc = relatorio.executar()
    arquivos = {n: (Path(pasta) / n) for n in ("conferencia_localidades.csv", "comunidades_sem_nome_oficial.csv", "resumo_por_municipio.csv")}
    conferir("as três planilhas foram gravadas", rc == 0 and all(p.exists() and p.stat().st_size > 100 for p in arquivos.values()))
    cru = arquivos["conferencia_localidades.csv"].read_bytes()
    conferir("com acento para o Excel: utf-8 com marca (BOM), separador ';' e 'Além Paraíba' legível", cru.startswith(b"\xef\xbb\xbf") and "Além Paraíba".encode() in cru)
    with open(arquivos["conferencia_localidades.csv"], encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    conferir("a conferência tem 470 linhas e as colunas de decisão do negócio em branco",
             len(linhas) == 470 and all(l["decisao_negocio"] == "" and l["observacao_negocio"] == "" for l in linhas)
             and {"municipio", "localidade_ibge", "categoria", "casamento", "comunidade_nossa", "ponto_no_territorio_dela", "atencao"} <= set(linhas[0]))
    with open(arquivos["comunidades_sem_nome_oficial.csv"], encoding="utf-8-sig", newline="") as f:
        sem = list(csv.DictReader(f, delimiter=";"))
    conferir("as sem nome oficial vêm das maiores para as menores e com a coluna de sugestão em branco",
             [int(x["enderecos"]) for x in sem] == sorted((int(x["enderecos"]) for x in sem), reverse=True) and all(x["nome_oficial_sugerido"] == "" for x in sem))

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_localidades CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
