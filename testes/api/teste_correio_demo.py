"""E-mail na demonstração (Bloco E, 15/10/2026): sem FAROL_EMAIL_REAL=1, só domínios reservados para teste recebem; um
domínio real é recusado ANTES de conectar ao servidor de e-mail (nada sai). Sem banco e sem SMTP.

Uso (na raiz): uv run python -W ignore testes/api/teste_correio_demo.py
"""

import os
import socket
import sys
from email.message import EmailMessage

os.environ.pop("FAROL_EMAIL_REAL", None)
os.environ.update({"FAROL_SMTP_HOST": "127.0.0.1", "FAROL_SMTP_PORTA": "9", "FAROL_SMTP_SEGURANCA": "nenhuma"})

from comunidades import correio  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


teste = ["radio@example.com", "admin@emg.example", "x@exemplo.example", "a@b.test", "c@sub.example.org", "d@algo.localhost"]
reais = ["carlos@energisa.com.br", "fulano@gmail.com", "x@example.com.br", "y@notexample.com"]
conferir("domínios de teste (RFC 2606/6761) passam", not any(correio.destino_real(e) for e in teste), str([e for e in teste if correio.destino_real(e)]))
conferir("domínios reais são reconhecidos", all(correio.destino_real(e) for e in reais), str([e for e in reais if not correio.destino_real(e)]))

conexoes = []
original = socket.create_connection
socket.create_connection = lambda *a, **k: conexoes.append(a) or original(*a, **k)
for destino, campo in [("carlos@energisa.com.br", "To"), ("radio@example.com, fulano@gmail.com", "To"), ("y@notexample.com", "Bcc")]:
    m = EmailMessage()
    m[campo] = destino
    if campo != "To":
        m["To"] = "radio@example.com"
    m["Subject"] = "teste"
    try:
        correio.enviar(m)
        recusado = False
    except correio.FalhaEnvio as e:
        recusado = "demonstração" in str(e)
    conferir(f"domínio real em {campo} ({destino}): recusado", recusado)
conferir("nenhuma conexão ao servidor de e-mail foi aberta para esses envios", not conexoes, str(conexoes))
socket.create_connection = original

for r in resultados:
    print(r[0], r[1], f"-> {r[2]}" if r[0] != "OK  " and r[2] else "")
falhas = sum(r[0] != "OK  " for r in resultados)
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
