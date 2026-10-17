"""O e-mail do aviso para a rádio: o texto para leitura, o PDF e o MP3 anexos e o botão "Confirmar recebimento".

Só o que a rádio precisa: o texto do aviso (comunidades, data, horário, motivo), o município e o
código de verificação. Nada de nome de pessoa, número de UC, endereço ou coordenada. Todo texto do
HTML passa por html.escape. O link de confirmação leva um token aleatório de uso único (7 dias).
"""

import html
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from .rotulos import HTML_LANG, idioma_valido, t


def mensagem(*, remetente: str, destino: str, municipio: str, uf: str, data: str, horario: str, empresa: str,
             texto: str, codigo: str, link_confirmar: str, pdf: tuple[str, bytes] | None, mp3: tuple[str, bytes] | None,
             aviso_ficticio: str, idioma: str = "pt-BR") -> EmailMessage:
    """O e-mail no idioma do aviso (Fase K), com a versão em texto simples e a em HTML."""
    i = idioma_valido(idioma)
    aviso_ficticio = aviso_ficticio if i == "pt-BR" else t(i, "aviso_ficticio")
    anexos = t(i, "email_anexos_mp3" if mp3 else "email_anexos")
    m = EmailMessage()
    m["From"], m["To"] = remetente, destino
    m["Content-Language"] = HTML_LANG[i]
    m["Subject"] = t(i, "email_assunto", municipio=municipio, uf=uf, data=data, codigo=codigo)
    m["Date"] = formatdate(localtime=False)
    m["Message-ID"] = make_msgid(domain=remetente.rsplit("@", 1)[-1].strip("> ") or "farol.example")
    corpo = (f"{t(i, 'email_intro', empresa=empresa)}\n\n"
             f"{t(i, 'email_municipio')}: {municipio}/{uf}\n{t(i, 'email_data')}: {data}, {t(i, 'email_das')} {horario}\n"
             f"{t(i, 'email_codigo')}: {codigo}\n\n{t(i, 'texto_leitura')}:\n\n{texto}\n\n{anexos}\n\n"
             f"{t(i, 'email_confirme')}\n{link_confirmar}\n\n{aviso_ficticio}\n")
    m.set_content(corpo)
    e = html.escape
    m.add_alternative(f"""<!doctype html><html lang="{HTML_LANG[i]}"><body style="margin:0;background:#E9EEF3;font-family:Arial,sans-serif;color:#0B1B2B">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#FFFFFF;border-radius:12px;overflow:hidden">
<tr><td style="background:#0B1B2B;padding:18px 24px;color:#FFFFFF;font-size:20px;font-weight:bold">Norte
<div style="color:#2EC4B6;font-size:13px;font-weight:normal">{e(t(i, 'slogan'))}</div></td></tr>
<tr><td style="padding:24px">
<p style="margin:0 0 8px">{e(t(i, 'email_intro', empresa=empresa))}</p>
<p style="margin:0 0 16px;color:#13263A"><b>{e(municipio)}/{e(uf)}</b> · {e(data)}, {e(t(i, 'email_das'))} {e(horario)} · {e(t(i, 'email_codigo'))} <b>{e(codigo)}</b></p>
<h2 style="margin:0 0 6px;font-size:16px">{e(t(i, 'texto_leitura'))}</h2>
<p style="margin:0 0 20px;padding:14px;background:#FDF4DE;border:1px solid #2EC4B6;border-radius:8px;font-size:16px;line-height:1.5">{e(texto)}</p>
<p style="margin:0 0 20px">{e(anexos)}</p>
<p style="margin:0 0 20px"><a href="{e(link_confirmar, quote=True)}" style="display:inline-block;background:#2EC4B6;color:#0B1B2B;font-weight:bold;text-decoration:none;padding:14px 22px;border-radius:8px">{e(t(i, 'email_botao'))}</a></p>
<p style="margin:0;color:#4A5560;font-size:13px">{e(t(i, 'email_link_vale'))} {e(aviso_ficticio)}</p>
</td></tr></table></td></tr></table></body></html>""", subtype="html")
    if pdf:
        m.add_attachment(pdf[1], maintype="application", subtype="pdf", filename=pdf[0])
    if mp3:
        m.add_attachment(mp3[1], maintype="audio", subtype="mpeg", filename=mp3[0])
    return m
