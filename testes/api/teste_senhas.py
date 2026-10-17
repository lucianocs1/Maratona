"""Teste do hash de senha e da senha temporária (senhas.py).

Confere:
- Argon2id com m=19 MiB, t=2, p=1 (mínimo da OWASP), conferência certa e errada, hash inválido;
- hash antigo (padrão do argon2-cffi, 64 MiB) continua valendo e é marcado para refazer;
- no máximo HASHES_SIMULTANEOS hashes ao mesmo tempo; quem espera demais recebe Ocupado, e a API
  responde 503 com Retry-After (sem derrubar o servidor);
- senha temporária: 4 grupos de 4, sem caracteres ambíguos, sempre diferente;
- a semente não importa a API (nem o FastAPI).

Uso (na raiz): uv run python -W ignore testes/api/teste_senhas.py
(a parte do 503 usa o Postgres local, num esquema próprio apagado no fim)
"""

import os
import subprocess
import sys
import threading
import time

os.environ["FAROL_ESQUEMA"] = "teste_senhas"

from argon2 import PasswordHasher  # noqa: E402

from comunidades import senhas  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


h = senhas.hash_senha("Lanterna-do-Farol-2026")
conferir("Argon2id, m=19 MiB, t=2, p=1", h.startswith("$argon2id$v=19$m=19456,t=2,p=1$"), h[:40])
conferir("senha certa confere", senhas.conferir(h, "Lanterna-do-Farol-2026"))
conferir("senha errada não confere", not senhas.conferir(h, "lanterna-do-farol-2026"))
conferir("hash inválido não confere (sem erro)", not senhas.conferir("lixo", "x"))
conferir("hash atual não precisa refazer", not senhas.precisa_refazer(h))
antigo = PasswordHasher().hash("Senha-Antiga-2025")
conferir("hash antigo (64 MiB) confere e é marcado para refazer",
         senhas.conferir(antigo, "Senha-Antiga-2025") and senhas.precisa_refazer(antigo), antigo[:40])

# --- fila: no máximo HASHES_SIMULTANEOS ao mesmo tempo
hasher, agora, pico, trava = senhas.HASHER, [0], [0], threading.Lock()
original = hasher.hash


def devagar(senha):
    with trava:
        agora[0] += 1
        pico[0] = max(pico[0], agora[0])
    time.sleep(0.2)
    with trava:
        agora[0] -= 1
    return original(senha)


class Lento:  # o PasswordHasher não deixa trocar o método: troca o objeto
    hash = staticmethod(devagar)


senhas.HASHER = Lento()
ths = [threading.Thread(target=senhas.hash_senha, args=(f"s{i}",)) for i in range(12)]
for t in ths:
    t.start()
for t in ths:
    t.join()
conferir(f"12 hashes ao mesmo tempo: no máximo {senhas.HASHES_SIMULTANEOS} rodando juntos", pico[0] == senhas.HASHES_SIMULTANEOS, str(pico[0]))

espera = senhas.ESPERA_MAXIMA
senhas.ESPERA_MAXIMA = 0.05
erros = []


def tentar(i):
    try:
        senhas.hash_senha(f"s{i}")
    except senhas.Ocupado as e:
        erros.append(str(e))


ths = [threading.Thread(target=tentar, args=(i,)) for i in range(senhas.HASHES_SIMULTANEOS + 3)]
for t in ths:
    t.start()
for t in ths:
    t.join()
senhas.HASHER = hasher
conferir("quem espera demais na fila recebe Ocupado (3 de 7)", len(erros) == 3, str(erros[:1]))

# --- a API responde 503 quando a fila está cheia
from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_senhas CASCADE")
semear()
for _ in range(senhas.HASHES_SIMULTANEOS):
    senhas._vez.acquire()
r = TestClient(app, base_url="http://farol.teste").post("/api/entrar", json={"email": "operador@emg.example", "senha": "x"})
for _ in range(senhas.HASHES_SIMULTANEOS):
    senhas._vez.release()
senhas.ESPERA_MAXIMA = espera
conferir("fila cheia: a API responde 503 com Retry-After", r.status_code == 503 and r.headers.get("retry-after") == "5",
         f"{r.status_code} {r.text[:80]}")
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_senhas CASCADE")

# --- senha temporária
ts = {senhas.senha_temporaria() for _ in range(200)}
amb = set("0O1lI")
conferir("senha temporária: 4 grupos de 4, sem ambíguos, todas diferentes",
         len(ts) == 200 and all(len(t) == 19 and [len(g) for g in t.split("-")] == [4] * 4 and not set(t) & amb for t in ts))

# --- a semente não depende da API
r = subprocess.run([sys.executable, "-c", "import sys, comunidades.semente; "
                    "print(sorted(m for m in sys.modules if m.startswith(('comunidades.api', 'fastapi'))))"],
                   capture_output=True, text=True)
conferir("semente.py não importa a API nem o FastAPI", r.stdout.strip() == "[]", (r.stdout + r.stderr)[-300:])

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
