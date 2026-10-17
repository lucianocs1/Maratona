"""Envio de e-mail pelo servidor (smtplib da biblioteca padrão), configurado só por variáveis de ambiente.

FAROL_SMTP_HOST, FAROL_SMTP_PORTA, FAROL_SMTP_USUARIO, FAROL_SMTP_SENHA, FAROL_SMTP_REMETENTE e
FAROL_SMTP_SEGURANCA (starttls, ssl ou nenhuma). Sem FAROL_SMTP_HOST, ou com FAROL_EMAIL=0, o envio por
e-mail fica desligado.
Localmente, o Mailpit (caixa de teste em 127.0.0.1:1025, nada sai para a internet):
  FAROL_SMTP_HOST=127.0.0.1, FAROL_SMTP_PORTA=1025, FAROL_SMTP_SEGURANCA=nenhuma.
A senha do SMTP nunca vai para o código, o git ou o log.
"""

import os
from email.utils import getaddresses
import smtplib
import ssl
from email.message import EmailMessage

from .segredos import segredo

TEMPO = 20   # segundos de espera pelo servidor de e-mail


class FalhaEnvio(RuntimeError):
    """O servidor de e-mail recusou ou não respondeu (a mensagem é curta e sem a senha)."""


def configuracao() -> dict | None:
    host = segredo("FAROL_SMTP_HOST")
    if not host or os.environ.get("FAROL_EMAIL") == "0":
        return None
    seg = (segredo("FAROL_SMTP_SEGURANCA") or "starttls").lower()
    return {"host": host, "porta": int(segredo("FAROL_SMTP_PORTA") or (465 if seg == "ssl" else 587)),
            "usuario": segredo("FAROL_SMTP_USUARIO"), "senha": segredo("FAROL_SMTP_SENHA"),
            "remetente": segredo("FAROL_SMTP_REMETENTE") or "Norte <avisos@farol.example>", "seguranca": seg}


def ligado() -> bool:
    return configuracao() is not None


def remetente() -> str:
    c = configuracao()
    return c["remetente"] if c else "Norte <avisos@farol.example>"


# domínios reservados para teste e documentação (RFC 2606 e 6761): na demonstração, só eles recebem
DOMINIOS_TESTE = (".example", ".test", ".invalid", ".localhost", "example.com", "example.net", "example.org")


def destino_real(endereco: str) -> bool:
    d = endereco.rsplit("@", 1)[-1].strip().lower().rstrip(">")
    return not any(d == x.lstrip(".") or d.endswith(x if x.startswith(".") else "." + x) or d == x for x in DOMINIOS_TESTE)


def enviar(msg: EmailMessage) -> None:
    """Entrega a mensagem ao servidor de e-mail; FalhaEnvio se ele recusar algum destinatário ou falhar.
    Demonstração (sem FAROL_EMAIL_REAL=1): só para domínios de teste (.example etc.), conferido antes de conectar;
    um domínio real nunca recebe nada dos dados fictícios."""
    if os.environ.get("FAROL_EMAIL_REAL") != "1":
        destinos = [a for _, a in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", []) + msg.get_all("Bcc", []))]
        if any(destino_real(a) for a in destinos):
            raise FalhaEnvio("ambiente de demonstração: só e-mails de domínios de teste (.example); nada foi enviado")
    c = configuracao()
    if not c:
        raise FalhaEnvio("envio por e-mail desligado neste servidor (sem FAROL_SMTP_HOST)")
    try:
        if c["seguranca"] == "ssl":
            s = smtplib.SMTP_SSL(c["host"], c["porta"], timeout=TEMPO, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(c["host"], c["porta"], timeout=TEMPO)
        with s:
            if c["seguranca"] == "starttls":
                s.starttls(context=ssl.create_default_context())
            if c["usuario"]:
                s.login(c["usuario"], c["senha"] or "")
            recusados = s.send_message(msg)
        if recusados:
            raise FalhaEnvio("o servidor de e-mail recusou o destinatário")
    except FalhaEnvio:
        raise
    except (smtplib.SMTPException, OSError) as e:
        raise FalhaEnvio(f"o servidor de e-mail não aceitou a mensagem ({type(e).__name__})") from None
