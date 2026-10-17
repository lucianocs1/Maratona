"""Teste das planilhas de demonstração (testes/planilha/exemplos/demo/, UCs fictícias) pela API.

Cada uma tem de terminar como o roteiro da apresentação diz (docs/DEMO.md):
1. correta: nenhum alerta, o aviso sai;
2. coordenadas corrigidas: 6 corrigidas, listadas e nos pontos do mapa; o aviso sai;
3. equipamento vital rejeitado: alerta vermelho com as 2 linhas; o aviso não sai, nem com justificativa;
4. muitas rejeições: acima de 2%; sem justificativa não sai, com ela sai;
5. maliciosa (macro): recusada na porta (422), nada é lido nem gravado.
Também confere que a geração gera de novo o mesmo arquivo (reprodutível).

Uso (na raiz, com o banco local): uv run python -W ignore testes/planilha/teste_demo.py
"""

import hashlib
import os
import sys
from pathlib import Path

os.environ["FAROL_ESQUEMA"] = "teste_demo"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import app as app_mod  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402

DEMO = Path(__file__).resolve().parent / "exemplos" / "demo"
resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_demo CASCADE")
temp = {e: s for _, e, s in semear()}["operador@emg.example"]
cli = TestClient(app, base_url="http://farol.teste")
cli.post("/api/entrar", json={"email": "operador@emg.example", "senha": temp})
cli.post("/api/senha", json={"atual": temp, "nova": "Lanterna-do-Farol-2026"})


def importar(nome):
    app_mod._envios.clear()
    return cli.post("/api/planilha", files={"arquivo": (nome, (DEMO / nome).read_bytes())}, data={"data": "20/11", "horario": "8h às 14h"})


def gerar(j, justificativa=None):
    return cli.post("/api/avisos", json={"pacote": j["pacote"], "data": "20/11", "horario": "8h às 14h", "conferi": True,
                                         "justificativa": justificativa})


def avisos():
    with conectar() as c:
        return c.execute("SELECT count(*) FROM aviso").fetchone()[0]


r = importar("1_correta.xlsx")
j = r.json()
c = j.get("conferencia", {})
conferir("1 correta: sem bloqueio, sem suspeito, sem rejeição, o aviso sai",
         r.status_code == 200 and not c["vital_bloqueio"] and not c["suspeitos"] and c["numeros"]["rejeitadas"] == 0
         and c["numeros"]["corrigidas"] == 0 and gerar(j).status_code == 200, str(c)[:300])

r = importar("2_coordenadas_corrigidas.xlsx")
j = r.json()
conferir("2 corrigidas: 6 corrigidas (listadas e nos pontos do mapa), nenhuma rejeitada, o aviso sai",
         r.status_code == 200 and j["conferencia"]["numeros"]["corrigidas"] == 6 and len(j["traducao"]["corrigidas"]) == 6
         and len(j["pontos_corrigidos"]) == 6 and j["conferencia"]["numeros"]["rejeitadas"] == 0 and not j["conferencia"]["vital_bloqueio"]
         and gerar(j).status_code == 200, str(j.get("traducao", {}).get("corrigidas")))

r = importar("3_vital_rejeitado.xlsx")
j = r.json()
antes = avisos()
g = gerar(j, justificativa="tentando gerar mesmo assim")
conferir("3 vital rejeitado: alerta vermelho com 2 linhas; o aviso não sai, nem com justificativa",
         r.status_code == 200 and len(j["conferencia"]["vital_bloqueio"]) == 2 and g.status_code == 422 and avisos() == antes,
         f"{j['conferencia']['vital_bloqueio']} {g.status_code} {g.text[:120]}")

r = importar("4_muitas_rejeicoes.xlsx")
j = r.json()
rej = j["conferencia"]["rejeicao"]
sem, com = gerar(j), gerar(j, justificativa="Demonstração: planilha com linhas ruins de propósito.")
conferir("4 muitas rejeições: acima de 2%, sem justificativa 422, com justificativa 200",
         r.status_code == 200 and rej["acima"] and 0.05 < rej["fracao"] < 0.12 and not j["conferencia"]["vital_bloqueio"]
         and sem.status_code == 422 and com.status_code == 200, f"{rej} {sem.status_code} {com.status_code}")

antes = avisos()
r = importar("5_maliciosa_macro.xlsx")
conferir("5 maliciosa (macro): recusada na porta (422), nada gravado", r.status_code == 422 and "macro" in r.json()["detail"].lower()
         and avisos() == antes, f"{r.status_code} {r.text[:120]}")

# reprodutível: gerar de novo dá os mesmos bytes
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DEMO.glob("*.xlsx"))}
from comunidades.simulacao import planilhas_demo  # noqa: E402

planilhas_demo.gerar()
de_novo = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DEMO.glob("*.xlsx"))}
conferir("gerar as planilhas de novo dá os mesmos arquivos (byte a byte)", hashes == de_novo and len(hashes) == 6,
         str({k: (hashes.get(k, "")[:8], v[:8]) for k, v in de_novo.items()}))

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_demo CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
