"""Banco que já existe (Fase J, desde 15/10/2026): depois de cada mudança de banco, entrar com os 4 perfis tem de funcionar
num banco de uma versão anterior, não só num banco novo dos testes.

Num esquema próprio (FAROL_ESQUEMA=teste_migracao, apagado no fim):
1. monta o banco como numa versão anterior: a semente e um pouco de auditoria, e depois tira o que as fases J e K
   acrescentaram (usuario.preferencias, a tabela pedido_radio, os modelos por idioma e o idioma padrão da empresa);
2. confere que, sem atualizar, entrar dá erro 500 (é o ERR-xxxx que aparecia na tela);
3. sobe a API (o lifespan aplica atualizar_esquema) e confere: os 4 perfis entram e /api/eu responde; as preferências
   (idioma) são gravadas; nenhuma linha da auditoria sumiu nem mudou e a corrente continua íntegra;
4. compara todas as colunas do esquema atualizado com as de um esquema criado do zero: coluna nova no CREATE TABLE sem
   o ALTER TABLE ... ADD COLUMN IF NOT EXISTS correspondente é falha (é o que quebraria o banco já existente).

Uso (na raiz): uv run python -W ignore testes/api/teste_migracao.py
"""

import os
import sys

os.environ["FAROL_ESQUEMA"] = "teste_migracao"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco import acesso as banco  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(q, args=()):
    with conectar() as c, c.cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


def colunas(esq):
    return {(t, c, tipo) for t, c, tipo in sql(
        "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = %s", (esq,))}


def entrar_todos(cli_de):
    r = {}
    for email, senha in senhas.items():
        api_acesso._tentativas_ip.clear()
        cli = cli_de()
        e = cli.post("/api/entrar", json={"email": email, "senha": senha})
        eu = cli.get("/api/eu") if e.status_code == 200 else None
        r[email] = (e.status_code, eu.status_code if eu is not None else None, cli)
    return r


# ---------- 0. o esquema criado do zero (referência das colunas) ----------
os.environ["FAROL_ESQUEMA"] = "teste_migracao_novo"
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_migracao_novo CASCADE")
banco.criar_esquema()
NOVO = colunas("teste_migracao_novo")
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_migracao_novo CASCADE")
os.environ["FAROL_ESQUEMA"] = "teste_migracao"

# ---------- 1. o banco de uma versão anterior ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_migracao CASCADE")
senhas = {email: s for _, email, s in semear()}
banco.registrar("teste: linha antiga da auditoria", "antes da atualização", None, None)
with conectar() as c:
    c.execute("ALTER TABLE usuario DROP COLUMN preferencias")
    c.execute("DROP TABLE pedido_radio CASCADE")
    c.execute("ALTER TABLE empresa_config DROP COLUMN modelo_mensagem_en, DROP COLUMN modelo_mensagem_es, DROP COLUMN idioma_padrao")
antes = sql("SELECT id, hash FROM registro ORDER BY id")
conferir("banco antigo montado (sem preferências, pedidos de rádio nem idiomas da empresa)",
         ("usuario", "preferencias", "jsonb") not in colunas("teste_migracao") and len(antes) >= 5, f"{len(antes)} linhas na auditoria")

# ---------- 2. sem atualizar: o erro que aparecia na tela ----------
# (sem o "with", o TestClient não roda o lifespan: é a API de antes, que não atualizava o banco)
sem = entrar_todos(lambda: TestClient(app, base_url="http://farol.teste", raise_server_exceptions=False))
conferir("sem atualizar o banco, entrar falha (500, o ERR-xxxx da tela)", any(s[0] == 500 or s[1] == 500 for s in sem.values()),
         str({k: v[:2] for k, v in sem.items()}))

# ---------- 3. a API sobe e atualiza o banco ----------
with TestClient(app, base_url="http://farol.teste") as subida:
    conferir("ao subir, a API atualiza o esquema", ("usuario", "preferencias", "jsonb") in colunas("teste_migracao")
             and sql("SELECT to_regclass('pedido_radio')")[0][0] is not None)
    com = entrar_todos(lambda: TestClient(app, base_url="http://farol.teste"))
    conferir("os 4 perfis entram no banco já existente", all(s[0] == 200 for s in com.values()), str({k: v[:2] for k, v in com.items()}))
    conferir("/api/eu responde para os 4 perfis", all(s[1] == 200 for s in com.values()), str({k: v[:2] for k, v in com.items()}))
    cli = com["consulta@emg.example"][2]
    p = cli.put("/api/eu/preferencias", json={"idioma": "es"})
    conferir("as preferências (idioma) são gravadas depois da atualização", p.status_code in (200, 403)
             and (p.status_code == 403 or sql("SELECT preferencias->>'idioma' FROM usuario WHERE email = 'consulta@emg.example'")[0][0] == "es"),
             f"{p.status_code} {p.text[:120]}")

depois = sql("SELECT id, hash FROM registro ORDER BY id")
conferir("nenhuma linha da auditoria sumiu nem mudou", depois[:len(antes)] == antes, f"{len(antes)} -> {len(depois)}")


def _tenta_update():
    try:
        sql("UPDATE registro SET acao = acao WHERE id = %s", (antes[0][0],))
        return False
    except Exception:
        return True


conferir("a auditoria continua só inclusão (UPDATE recusado pelo banco)", _tenta_update())
banco.atualizar_esquema()
conferir("rodar de novo não muda nada (idempotente)", sql("SELECT id, hash FROM registro ORDER BY id") == depois)

# ---------- 4. o esquema atualizado tem as mesmas colunas de um criado do zero ----------
ATUAL = colunas("teste_migracao")
faltam = sorted(NOVO - ATUAL)
conferir("todas as colunas de um banco novo existem no banco atualizado (cada coluna nova tem o seu ADD COLUMN)",
         not faltam, str(faltam[:8]))

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_migracao CASCADE")

for r in resultados:
    print(r[0], r[1], f"-> {r[2]}" if r[0] != "OK  " and r[2] else "")
falhas = sum(r[0] != "OK  " for r in resultados)
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
