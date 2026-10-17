"""Teste do custo do aviso no ar (a rádio cobra por spot de 30 s): regra, configuração, painel e API.

Roda num esquema próprio (FAROL_ESQUEMA=teste_custo), apagado no fim. Confere:
- a regra (nucleo/custo.py): 20 s = 1 spot, 30 s = 1, 31 s = 2, 100 s = 4, 0 s = 0; o valor é spots x preço x veiculações;
- a configuração ([radio] em distribuidoras/*.toml): as duas distribuidoras de demonstração trazem o preço de
  referência e a fonte; sem a seção vale preço 0 (só spots); valores absurdos são recusados com mensagem;
- o painel: os spots do comparativo somam município a município (cada aviso ocupa spots inteiros);
- a API: /api/config entrega a tabela de rádio à tela, e o histórico nunca guarda valor em reais.

Uso (na raiz): uv run python -W ignore testes/api/teste_custo.py
"""

import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

os.environ["FAROL_ESQUEMA"] = "teste_custo"
os.environ["FAROL_IA"] = "simulado"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades import distribuidora  # noqa: E402
from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import DIST, app  # noqa: E402
from comunidades.banco import acesso as banco_acesso  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo import painel  # noqa: E402
from comunidades.nucleo.custo import TabelaRadio, custo, spots  # noqa: E402
from comunidades.semente import semear  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


# ---------- 1. Regra ----------
casos = {0: 0, 1: 1, 20: 1, 30: 1, 31: 2, 60: 2, 61: 3, 100: 4}
erradas = {s: spots(s) for s, n in casos.items() if spots(s) != n}
conferir("spots: 0 s = 0, 20 s = 1, 30 s = 1, 31 s = 2, 100 s = 4 (a rádio cobra o spot inteiro)", not erradas, str(erradas))
conferir("spots com spot de 15 s: 40 s = 3", spots(40, 15) == 3)
conferir("custo: 100 s a R$ 80 = R$ 320 (4 spots); 20 s = R$ 80; em 3 veiculações = R$ 240",
         custo(100, 80) == 320 and custo(20, 80) == 80 and custo(20, 80, 3) == 240)
conferir("custo: centavos arredondados (1 spot a R$ 33,333 x 3 = R$ 100,00)", custo(10, 33.333, 3) == 100.0)

# ---------- 2. Configuração ----------
for nome in ("demo-leopoldina", "demo-muriae"):
    r = distribuidora.carregar(Path("distribuidoras") / f"{nome}.toml").radio
    conferir(f"{nome}.toml: spot de 30 s, preço de referência, 1 veiculação e a fonte", r.spot_segundos == 30 and r.preco_spot > 0
             and r.veiculacoes == 1 and "confirmar com a emissora" in r.fonte, str(r))
modelo = (Path("distribuidoras") / "demo-leopoldina.toml").read_text(encoding="utf-8")
sem_radio = modelo[:modelo.index("[radio]")] + modelo[modelo.index("[obra]"):]


def com_toml(texto):
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8") as f:
        f.write(texto)
    try:
        return distribuidora.carregar(f.name).radio
    finally:
        os.unlink(f.name)


conferir("sem a seção [radio]: preço 0 e 30 s (a tela mostra só os spots)", com_toml(sem_radio) == TabelaRadio())
bloco = modelo[modelo.index("[radio]"):modelo.index("[obra]")]
for nome, alterado in (("spot de 1 s", bloco.replace("spot_segundos = 30", "spot_segundos = 1")),
                       ("preço negativo", bloco.replace("spot_reais = 80.0", "spot_reais = -5.0")),
                       ("preço em texto", bloco.replace("spot_reais = 80.0", 'spot_reais = "oitenta"')),
                       ("zero veiculações", bloco.replace("veiculacoes = 1", "veiculacoes = 0")),
                       ("fonte enorme", bloco.replace('fonte = "', 'fonte = "' + "x" * 400))):
    try:
        com_toml(modelo.replace(bloco, alterado))
        conferir(f"configuração recusa {nome}", False)
    except distribuidora.ConfiguracaoInvalida as e:
        conferir(f"configuração recusa {nome}", "radio." in str(e), str(e))

# ---------- 3. Painel ----------
BRASILIA = timezone(timedelta(hours=-3))
agora = datetime.now(BRASILIA)


def mun(cod, segundos, hoje_seg):
    return {"codigo_ibge": cod, "nome": f"M{cod}", "uf": "MG", "ucs": 10, "segundos": segundos, "aviso": "x " * 10,
            "equipamento_vital": {"sim": 0, "nao": 10, "a_confirmar": 0},
            "hoje": {"locais": 5, "palavras": 50, "segundos": hoje_seg} if hoje_seg else None,
            "comunidades": [{"nome": "C", "afetadas": 10}]}


avisos = [{"id": 1, "criado_em": agora, "data": "01/01", "horario": "8h", "municipios": [mun("1", 20, 100), mun("2", 31, 45)]}]
comp = painel.resumir(avisos, agora.date())["comparativo"]
conferir("painel: spots somados por município (hoje 4 + 2 = 6; Farol 1 + 2 = 3)", (comp["spots_hoje"], comp["spots_farol"]) == (6, 3), str(comp))
comp15 = painel.resumir(avisos, agora.date(), 15)["comparativo"]
conferir("painel: com spot de 15 s (hoje 7 + 3 = 10; Farol 2 + 3 = 5)", (comp15["spots_hoje"], comp15["spots_farol"]) == (10, 5), str(comp15))
sem_hoje = painel.resumir([{**avisos[0], "municipios": [mun("1", 20, None)]}], agora.date())["comparativo"]
conferir("painel: município sem aviso de hoje não entra nos spots do comparativo", (sem_hoje["spots_hoje"], sem_hoje["spots_farol"]) == (0, 0))

# ---------- 4. API ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_custo CASCADE")
senhas = {email: s for _, email, s in semear()}
NOVA = "Lanterna-do-Farol-2026"
api_acesso._tentativas_ip.clear()
op = TestClient(app, base_url="http://farol.teste")
op.post("/api/entrar", json={"email": "operador@emg.example", "senha": senhas["operador@emg.example"]})
op.post("/api/senha", json={"atual": senhas["operador@emg.example"], "nova": NOVA})
cfg = op.get("/api/config").json()
conferir("/api/config: a tela recebe a tabela de rádio da distribuidora", cfg["radio"] == DIST.radio.para_tela() and cfg["radio"]["spot_segundos"] == 30, str(cfg.get("radio")))

dono = banco_acesso.usuario_por_email("operador@emg.example")
municipio = {**mun("3138401", 20, 100), "nome": "Leopoldina"}
id_ = banco_acesso.gravar_aviso(dono["empresa_id"], dono["id"], f"{date.today() + timedelta(days=5):%d/%m}", "8h às 14h", "pt-BR",
                                {"linhas": 1, "validas": 1, "problemas": 0, "fora_da_concessao": 0, "prazo": {}}, [municipio], "manutencao_preventiva", "Manutenção preventiva", lambda i: f"aviso {i}")["id"]
p = op.get("/api/painel").json()["comparativo"]
conferir("/api/painel: o comparativo traz os spots (4 contra 1)", (p["spots_hoje"], p["spots_farol"]) == (4, 1), str(p))
j = op.post("/api/painel/perguntar", json={"pergunta": "Quanto tempo o aviso por comunidade economiza no rádio?"}).json()
conferir("Pergunte ao painel: o comparativo inclui a linha de spots e a resposta os cita", ["Spots de rádio (30 s)", 4, 1] in j["tabela"]["linhas"]
         and "4 spots contra 1" in j["resposta"], str(j)[:300])
guardado = str(banco_acesso.aviso(id_, dono["empresa_id"]))
conferir("histórico: nenhum valor em reais é gravado", "preco" not in guardado and "R$" not in guardado and "reais" not in guardado)

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_custo CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
