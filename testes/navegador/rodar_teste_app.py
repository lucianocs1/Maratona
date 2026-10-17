"""Roda o teste da tela (teste_app.mjs) contra uma API de teste, com usuários de teste.

1. Cria o esquema teste_app no Postgres (usuários de verdade não são tocados) e roda a semente.
2. O Operador fica com a senha temporária (o navegador passa pela troca obrigatória); os outros
   três recebem senhas de teste já trocadas.
3. Sobe a API na porta 8001 com esse esquema, roda o teste no Node e, no fim, derruba o servidor e
   apaga o esquema. As senhas de teste só existem durante o teste.

Uso (na raiz): uv run python testes/navegador/rodar_teste_app.py [script.mjs] [--email]
  script.mjs: o teste a rodar (padrão teste_app.mjs; a verificação geral é teste_verificacao.mjs)
  --email: sobe o Mailpit (caixa de teste, nada sai para a internet) e liga o e-mail e o cofre dos arquivos
"""

import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

os.environ["FAROL_ESQUEMA"] = "teste_app"
os.environ["FAROL_IA"] = "simulado"   # o teste não gasta crédito nem depende da internet, mesmo com o .env em anthropic

from comunidades.senhas import hash_senha  # noqa: E402
from comunidades.banco import acesso as banco  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
PORTA = 8001
SMTP, WEB = 1135, 8135          # Mailpit deste teste (outras portas que as do teste_radio)
SCRIPT = next((a for a in sys.argv[1:] if a.endswith(".mjs")), "teste_app.mjs")
EMAIL = "--email" in sys.argv[1:]


def apagar_esquema():
    with conectar() as c:
        c.execute("DROP SCHEMA IF EXISTS teste_app CASCADE")


apagar_esquema()
senhas = {email: s for _, email, s in semear()}
for email in ("admin@emg.example", "consulta@emg.example", "admin@farol.example"):
    senhas[email] = f"Teste-{secrets.token_urlsafe(9)}"
    banco.definir_senha(banco.usuario_por_email(email)["id"], hash_senha(senhas[email]), trocar_senha=False)

env = {**os.environ, "PYTHONIOENCODING": "utf-8", "FAROL_EMAIL": "0"}   # o e-mail ligado é testado em testes/api/teste_radio.py
caixa = None
if EMAIL:
    mailpit = RAIZ / "data" / "raw" / "mailpit" / "mailpit.exe"
    if not mailpit.exists():
        print("Mailpit não encontrado em data/raw/mailpit/ (ver ORIGEM.md).")
        sys.exit(2)
    caixa = subprocess.Popen([str(mailpit), "--smtp", f"127.0.0.1:{SMTP}", "--listen", f"127.0.0.1:{WEB}", "--smtp-auth-accept-any",
                              "--smtp-auth-allow-insecure"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", SMTP), 1).close()
            break
        except OSError:
            time.sleep(0.2)
    env.pop("FAROL_EMAIL")
    env.update({"FAROL_SMTP_HOST": "127.0.0.1", "FAROL_SMTP_PORTA": str(SMTP), "FAROL_SMTP_SEGURANCA": "nenhuma",
                "FAROL_SMTP_USUARIO": "", "FAROL_SMTP_SENHA": "", "FAROL_SMTP_REMETENTE": "Norte <avisos@farol.example>",
                "FAROL_URL_PUBLICA": f"http://127.0.0.1:{PORTA}", "FAROL_MAILPIT": f"http://127.0.0.1:{WEB}",
                "FAROL_CHAVE_ARQUIVOS": base64.urlsafe_b64encode(os.urandom(32)).decode()})
api = subprocess.Popen([sys.executable, "-m", "uvicorn", "comunidades.api.app:app", "--host", "127.0.0.1", "--port", str(PORTA), "--no-proxy-headers"],
                       env=env, cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/api/saude", timeout=2)
            break
        except OSError:
            time.sleep(0.3)
    teste = subprocess.run(["node", str(RAIZ / "testes" / "navegador" / SCRIPT)], cwd=RAIZ,
                           env={**env, "FAROL_URL": f"http://127.0.0.1:{PORTA}", "FAROL_TESTE_SENHAS": json.dumps(senhas)})
finally:
    api.terminate()
    api.wait(timeout=20)
    if caixa:
        caixa.terminate()
    apagar_esquema()
sys.exit(teste.returncode)
