"""Teste da auditoria encadeada e do registro do desligamento (FastAPI em processo, Postgres local).

Confere:
- a corrente (nucleo/auditoria.py): ida e volta; conteúdo alterado, linha apagada no meio e fora de ordem
  são apontados na linha certa;
- no banco: UPDATE, DELETE e TRUNCATE no registro dão erro (só inclusão);
- adulteração direta no banco (com o gatilho desligado pelo dono) é detectada pela verificação;
- quem fez vem do login: nome e perfil copiados na linha (renomear o usuário depois não muda o passado;
  um campo "usuario" no pedido é ignorado);
- migração: linhas antigas (sem hash) ganham a corrente uma vez, e o gatilho passa a valer;
- tipo de desligamento: lista fechada e "Outro" curto, sem número longo nem e-mail;
- o aviso guarda tipo, motivo, quem pediu (nome e perfil) e o código de verificação FRL-..., que aponta
  para a linha "gerou aviso" da auditoria; outra empresa não acha o código;
- cancelar e mudar a data: só quem gera aviso; a auditoria guarda o antes e o depois; cancelado não muda mais;
- PDF e edição da mensagem registrados; /api/auditoria/verificar: íntegra para o Admin da empresa.

Uso (na raiz): uv run python -W ignore testes/api/teste_auditoria.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ["FAROL_ESQUEMA"] = "teste_auditoria"

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api import app as app_mod  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco import acesso as banco  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo import auditoria as A  # noqa: E402
from comunidades.nucleo import tipos_desligamento as T  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.simulacao import planilhas_teste  # noqa: E402

resultados = []
NOVA = "Lanterna-do-Farol-2026"


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(q, args=()):
    with conectar() as c, c.cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


def erro_sql(q) -> str:
    try:
        sql(q)
        return ""
    except psycopg.Error as e:
        return str(e)


# ---------- 1. A corrente, sem banco ----------
t0 = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
linhas, ant = [], A.INICIO
for i in range(1, 6):
    ln = {"id": i, "quando": t0 + timedelta(seconds=i), "empresa_id": 1, "usuario_id": 2, "usuario_nome": "Fulana", "perfil": "operador",
          "acao": "gerou aviso", "detalhe": f"aviso {i}", "hash_anterior": ant}
    ln["hash"] = A.hash_linha(ln)
    linhas.append(ln)
    ant = ln["hash"]
conferir("corrente íntegra: ok, 5 linhas", A.verificar(linhas)["ok"] and A.verificar(linhas)["linhas"] == 5)
alterada = [dict(x) for x in linhas]
alterada[2]["detalhe"] = "aviso 99"
conferir("conteúdo alterado: apontado na linha 3", A.verificar(alterada)["quebra_id"] == 3
         and A.verificar(alterada)["motivo"] == "conteúdo alterado", json.dumps(A.verificar(alterada)))
sem_meio = linhas[:2] + linhas[3:]
conferir("linha apagada no meio: apontada na seguinte (4)", A.verificar(sem_meio)["quebra_id"] == 4
         and "apagada" in A.verificar(sem_meio)["motivo"], json.dumps(A.verificar(sem_meio)))
trocadas = [linhas[0], linhas[2], linhas[1]] + linhas[3:]
conferir("fora de ordem: apontado", not A.verificar(trocadas)["ok"], json.dumps(A.verificar(trocadas)))
reassinada = [dict(x) for x in linhas]
reassinada[2]["detalhe"] = "aviso 99"
reassinada[2]["hash"] = A.hash_linha(reassinada[2])
conferir("alterar e refazer o hash da linha não basta: a seguinte não aponta mais para ela",
         A.verificar(reassinada)["quebra_id"] == 4, json.dumps(A.verificar(reassinada)))
conferir("código de verificação: FRL- e 12 caracteres do hash", A.codigo_verificacao("3f2a91c07b44" + "0" * 52) == "FRL-3F2A-91C0-7B44")

# ---------- 2. Tipos de desligamento ----------
conferir("tipo da lista: o motivo da mensagem", T.motivo("poda") == ("poda", "poda de árvores perto da rede"))
casos = {"vazio": "", "curto": "ab", "longo": "x" * 201, "UC": "religar a UC 3000029045", "CPF": "cliente 123.456.789-00",
         "telefone": "ligar (32) 99999-1234", "e-mail": "falar com fulano@exemplo.com", "site": "ver www.exemplo.com"}
for nome, texto in casos.items():
    try:
        T.motivo("outro", texto)
        conferir(f"Outro recusado: {nome}", False)
    except ValueError:
        conferir(f"Outro recusado: {nome}", True)
conferir("Outro aceito: texto curto, limpo", T.motivo("outro", "  troca de\tcruzeta  ") == ("outro", "troca de cruzeta"))
try:
    T.motivo("xyz")
    conferir("tipo inexistente: ValueError", False)
except ValueError:
    conferir("tipo inexistente: ValueError", True)

# ---------- 3. Migração: linhas antigas, sem hash ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_auditoria CASCADE")
    c.execute("CREATE SCHEMA teste_auditoria")
    c.execute("CREATE TABLE teste_auditoria.empresa (id bigserial PRIMARY KEY, nome text NOT NULL, sigla text NOT NULL UNIQUE,"
              " dominio text NOT NULL, status text NOT NULL DEFAULT 'ativa', criada_em timestamptz NOT NULL DEFAULT now())")
    c.execute("CREATE TABLE teste_auditoria.usuario (id bigserial PRIMARY KEY, empresa_id bigint REFERENCES teste_auditoria.empresa,"
              " email text NOT NULL UNIQUE, nome text NOT NULL, perfil text NOT NULL, senha_hash text NOT NULL, trocar_senha boolean NOT NULL DEFAULT true,"
              " status text NOT NULL DEFAULT 'ativo', tentativas integer NOT NULL DEFAULT 0, bloqueado_ate timestamptz,"
              " criado_em timestamptz NOT NULL DEFAULT now(), ultimo_acesso timestamptz)")
    c.execute("CREATE TABLE teste_auditoria.registro (id bigserial PRIMARY KEY, quando timestamptz NOT NULL DEFAULT now(),"
              " usuario_id bigint REFERENCES teste_auditoria.usuario ON DELETE SET NULL, empresa_id bigint REFERENCES teste_auditoria.empresa"
              " ON DELETE SET NULL, acao text NOT NULL, detalhe text NOT NULL DEFAULT '')")
    c.execute("INSERT INTO teste_auditoria.empresa (nome, sigla, dominio) VALUES ('Antiga', 'ANT', 'ant.example')")
    c.execute("INSERT INTO teste_auditoria.usuario (empresa_id, email, nome, perfil, senha_hash) VALUES (1, 'velho@ant.example', 'Usuário Antigo', 'operador', 'x')")
    for i in range(3):
        c.execute("INSERT INTO teste_auditoria.registro (usuario_id, empresa_id, acao, detalhe) VALUES (1, 1, 'entrou', %s)", (f"antiga {i}",))
banco.criar_esquema()
v = banco.verificar_registro()
antigas = sql("SELECT usuario_nome, perfil, hash IS NOT NULL FROM registro ORDER BY id")
conferir("migração: as 3 linhas antigas ganham nome, perfil e a corrente íntegra", v["ok"] and v["linhas"] == 3
         and antigas == [("Usuário Antigo", "operador", True)] * 3, f"{v} {antigas}")
conferir("migração: rodar de novo não muda nada", (banco.criar_esquema() or True) and banco.verificar_registro() == v)
with conectar() as c:
    c.execute("DROP SCHEMA teste_auditoria CASCADE")

# ---------- 4. API: tipo, aviso, código e quem fez ----------
senhas = {e: s for _, e, s in semear()}


def pronto(email):
    api_acesso._tentativas_ip.clear()
    c = TestClient(app, base_url="http://farol.teste")
    c.post("/api/entrar", json={"email": email, "senha": senhas[email]})
    c.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
    return c


op, adm, con, far = (pronto(e) for e in ("operador@emg.example", "admin@emg.example", "consulta@emg.example", "admin@farol.example"))
planilha = planilhas_teste.planilha("CF-0066").to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")


def conferir_e_gerar(c, tipo="poda", outro=None, extra=None):
    app_mod._envios.clear()
    r = c.post("/api/planilha", files={"arquivo": ("p.csv", planilha)},
               data={"data": "12/11", "horario": "8h às 14h", "tipo": tipo, **({"tipo_outro": outro} if outro else {})})
    if r.status_code != 200:
        return r
    return c.post("/api/avisos", json={"pacote": r.json()["pacote"], "data": "12/11", "horario": "8h às 14h", "conferi": True,
                                       "tipo": tipo, "tipo_outro": outro, **(extra or {})})


r = conferir_e_gerar(op, "outro", "religar a UC 3000029045")
conferir("Outro com número de UC: recusado já no Conferir (422)", r.status_code == 422 and "números longos" in r.json()["detail"], r.text[:120])
g = conferir_e_gerar(op, "poda", extra={"usuario": "Nome Digitado", "usuario_id": 999})
j = g.json()
conferir("aviso gerado: tipo, motivo, código FRL e quem pediu (nome e perfil do login, não o digitado)",
         g.status_code == 200 and j["desligamento"] == {"tipo": "poda", "rotulo": "Poda de árvores", "motivo": "poda de árvores perto da rede"}
         and j["codigo"].startswith("FRL-") and j["usuario"] == "Operador da EMG" and j["usuario_perfil"] == "Operador", g.text[:200])
h = op.get(f"/api/historico/{j['id']}").json()
conferir("histórico: o mesmo código, tipo, quem pediu e situação 'gerado'",
         h["codigo"] == j["codigo"] and h["desligamento"]["tipo"] == "poda" and h["usuario"] == "Operador da EMG"
         and h["usuario_perfil"] == "Operador" and h["status"] == "gerado", json.dumps(h, ensure_ascii=False)[:200])
linha = sql("SELECT usuario_nome, perfil, detalhe, hash FROM registro WHERE acao = 'gerou aviso' ORDER BY id DESC LIMIT 1")[0]
conferir("auditoria: 'gerou aviso' com o nome e o perfil do login; o código do aviso sai do hash dessa linha",
         linha[0] == "Operador da EMG" and linha[1] == "operador" and f"aviso {j['id']}" in linha[2]
         and A.codigo_verificacao(linha[3]) == j["codigo"] and "Nome Digitado" not in json.dumps(sql("SELECT detalhe, usuario_nome FROM registro")),
         str(linha))
vc = con.get(f"/api/verificar/{j['codigo']}")
conferir("verificar código (Consulta da mesma empresa): a linha 'gerou aviso', por quem, auditoria íntegra",
         vc.status_code == 200 and vc.json()["acao"] == "gerou aviso" and vc.json()["por"] == "Operador da EMG" and vc.json()["auditoria_integra"],
         vc.text[:200])
conferir("verificar código: formato errado 422, inexistente 404", con.get("/api/verificar/ABC").status_code == 422
         and con.get("/api/verificar/FRL-0000-0000-0000").status_code == 404)

# outra empresa não acha o código
r = far.post("/api/empresas", json={"nome": "Cooperativa Teste", "sigla": "CTE", "dominio": "cte.example",
                                    "admin_nome": "Admin CTE", "admin_email": "admin@cte.example"})
cte = TestClient(app, base_url="http://farol.teste")
cte.post("/api/entrar", json={"email": "admin@cte.example", "senha": r.json()["senha_temporaria"]})
cte.post("/api/senha", json={"atual": r.json()["senha_temporaria"], "nova": NOVA})
conferir("outra empresa: o código da EMG não é achado (404)", cte.get(f"/api/verificar/{j['codigo']}").status_code == 404)
conferir("Admin do Norte acha o código de qualquer empresa", far.get(f"/api/verificar/{j['codigo']}").status_code == 200)

# renomear o usuário depois não muda o passado
sql("UPDATE usuario SET nome = 'Operador Renomeado' WHERE email = 'operador@emg.example'")
op.post(f"/api/historico/{j['id']}/municipios/3138401/pdf", json={"texto": "Texto do aviso para a rádio."})
nomes = [n for (n,) in sql("SELECT usuario_nome FROM registro WHERE usuario_id = (SELECT id FROM usuario WHERE email = 'operador@emg.example') ORDER BY id")]
conferir("renomear o usuário: linhas antigas com o nome antigo; a nova (gerou PDF) com o nome novo",
         nomes[0] == "Operador da EMG" and nomes[-1] == "Operador Renomeado" and op.get(f"/api/historico/{j['id']}").json()["usuario"] == "Operador da EMG",
         str(nomes[-3:]))
sql("UPDATE usuario SET nome = 'Operador da EMG' WHERE email = 'operador@emg.example'")

# ---------- 5. Só inclusão, no banco ----------
conferir("UPDATE no registro: recusado pelo banco", "só inclusão" in erro_sql("UPDATE registro SET detalhe = 'x'"))
conferir("DELETE no registro: recusado pelo banco", "só inclusão" in erro_sql("DELETE FROM registro"))
conferir("TRUNCATE no registro: recusado pelo banco", "só inclusão" in erro_sql("TRUNCATE registro"))
def _rotas(rs):
    for r_ in rs:
        yield from _rotas(r_.original_router.routes) if hasattr(r_, "original_router") else [r_]


todas_rotas = [(getattr(r_, "path", ""), getattr(r_, "methods", set()) or set()) for r_ in _rotas(app.routes)]
conferir("a API não tem rota que altere ou apague o registro (só GET em /api/registro e /api/auditoria)",
         any(p == "/api/registro" for p, _ in todas_rotas) and not any(
             p.startswith(("/api/registro", "/api/auditoria")) and (ms - {"GET", "HEAD"}) for p, ms in todas_rotas), str(todas_rotas[-5:]))

# ---------- 6. Cancelar, mudar a data, PDF e edição ----------
conferir("Consulta não cancela, não muda a data nem registra PDF (403)",
         con.post(f"/api/historico/{j['id']}/cancelar", json={"motivo": "teste"}).status_code == 403
         and con.post(f"/api/historico/{j['id']}/data", json={"data": "13/11", "horario": "9h"}).status_code == 403
         and con.post(f"/api/historico/{j['id']}/municipios/3138401/pdf").status_code == 403)
md = op.post(f"/api/historico/{j['id']}/data", json={"data": "13/11", "horario": "9h às 15h"})
det = sql("SELECT detalhe FROM registro WHERE acao = 'mudou a data do aviso' ORDER BY id DESC LIMIT 1")
conferir("mudar a data: 200, o aviso com a data nova e a auditoria com o antes e o depois",
         md.status_code == 200 and md.json()["data"] == "13/11" and det and det[0][0] == f"aviso {j['id']}: de 12/11, 8h às 14h para 13/11, 9h às 15h",
         f"{md.text[:120]} {det}")
op.put(f"/api/historico/{j['id']}/municipios/3138401/texto", json={"texto": "Texto final editado para a rádio."})
conferir("texto final diferente do gerado: 'editou a mensagem' na auditoria",
         bool(sql("SELECT 1 FROM registro WHERE acao = 'editou a mensagem'")))
conferir("PDF registrado: 'gerou PDF'", bool(sql("SELECT 1 FROM registro WHERE acao = 'gerou PDF'")))
cx = op.post(f"/api/historico/{j['id']}/cancelar", json={"motivo": "chuva forte prevista"})
conferir("cancelar: 200, situação 'cancelado', motivo na auditoria", cx.status_code == 200 and cx.json()["status"] == "cancelado"
         and sql("SELECT detalhe FROM registro WHERE acao = 'cancelou o aviso'")[0][0] == f"aviso {j['id']}: chuva forte prevista", cx.text[:120])
conferir("cancelado: não cancela de novo nem muda a data (409)",
         op.post(f"/api/historico/{j['id']}/cancelar", json={"motivo": "de novo"}).status_code == 409
         and op.post(f"/api/historico/{j['id']}/data", json={"data": "14/11", "horario": "9h"}).status_code == 409)
conferir("cancelar com motivo que parece dado pessoal: 422",
         op.post(f"/api/historico/{conferir_e_gerar(op).json()['id']}/cancelar", json={"motivo": "cliente 123.456.789-00"}).status_code == 422)
conferir("outra empresa não cancela aviso da EMG (404)", cte.post(f"/api/historico/{j['id']}/cancelar", json={"motivo": "teste"}).status_code == 404)

# ---------- 7. Verificar a corrente pela API e detectar adulteração ----------
va = adm.get("/api/auditoria/verificar")
conferir("Admin da empresa: auditoria íntegra (sem o número das linhas de outras empresas)", va.status_code == 200
         and va.json() == {"ok": True, "motivo": None}, va.text)
conferir("Operador e Consulta não verificam a auditoria (403)", op.get("/api/auditoria/verificar").status_code == 403
         and con.get("/api/auditoria/verificar").status_code == 403)
alvo = sql("SELECT id FROM registro WHERE acao = 'cancelou o aviso'")[0][0]
sql("ALTER TABLE registro DISABLE TRIGGER USER")       # só o dono da tabela consegue (simula quem tem acesso ao banco)
sql("UPDATE registro SET detalhe = 'aviso 1: motivo trocado' WHERE id = %s", (alvo,))
vf = far.get("/api/auditoria/verificar").json()
conferir("adulteração no banco: detectada na linha alterada (Admin do Norte vê onde)", vf["ok"] is False and vf["quebra_id"] == alvo
         and vf["motivo"] == "conteúdo alterado", json.dumps(vf))
conferir("adulteração: o Admin da empresa vê que não confere", adm.get("/api/auditoria/verificar").json()["ok"] is False)
meio = sql("SELECT id FROM registro ORDER BY id LIMIT 1 OFFSET 5")[0][0]
sql("UPDATE registro SET detalhe = d.detalhe FROM (SELECT %s::text AS detalhe) d WHERE id = %s",
    (f"aviso {j['id']}: chuva forte prevista", alvo))
sql("DELETE FROM registro WHERE id = %s", (meio,))
vd = banco.verificar_registro()
conferir("linha apagada no meio: detectada na seguinte", vd["ok"] is False and vd["quebra_id"] > meio and "apagada" in vd["motivo"], json.dumps(vd))
sql("ALTER TABLE registro ENABLE TRIGGER USER")

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_auditoria CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
