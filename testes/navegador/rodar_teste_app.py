"""Roda o teste da tela (teste_app.mjs) contra uma API de teste, com usuários de teste.

1. Cria o esquema teste_app no Postgres (usuários de verdade não são tocados) e roda a semente.
2. O Operador fica com a senha temporária (o navegador passa pela troca obrigatória); os outros
   três recebem senhas de teste já trocadas.
3. Sobe a API na porta 8001 com esse esquema, roda o teste no Node e, no fim, derruba o servidor e
   apaga o esquema. As senhas de teste só existem durante o teste.

Uso (na raiz): uv run python testes/navegador/rodar_teste_app.py
"""

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

os.environ["FAROL_ESQUEMA"] = "teste_app"
os.environ["FAROL_IA"] = "simulado"   # o teste não gasta crédito nem depende da internet, mesmo com o .env em anthropic

from comunidades.api.acesso import hash_senha  # noqa: E402
from comunidades.banco import acesso as banco  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
PORTA = 8001


def apagar_esquema():
    with conectar() as c:
        c.execute("DROP SCHEMA IF EXISTS teste_app CASCADE")


apagar_esquema()
senhas = {email: s for _, email, s in semear()}
for email in ("admin@emg.example", "consulta@emg.example", "admin@farol.example"):
    senhas[email] = f"Teste-{secrets.token_urlsafe(9)}"
    banco.definir_senha(banco.usuario_por_email(email)["id"], hash_senha(senhas[email]), trocar_senha=False)

env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
api = subprocess.Popen([sys.executable, "-m", "uvicorn", "comunidades.api.app:app", "--host", "127.0.0.1", "--port", str(PORTA)],
                       env=env, cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/api/saude", timeout=2)
            break
        except OSError:
            time.sleep(0.3)
    teste = subprocess.run(["node", str(RAIZ / "testes" / "navegador" / "teste_app.mjs")], cwd=RAIZ,
                           env={**env, "FAROL_URL": f"http://127.0.0.1:{PORTA}", "FAROL_TESTE_SENHAS": json.dumps(senhas)})
finally:
    api.terminate()
    api.wait(timeout=20)
    apagar_esquema()
sys.exit(teste.returncode)
