"""A página pública em que a rádio confirma o recebimento do aviso (sem login, sem script).

Todo texto passa por html.escape. O botão é um formulário POST para a mesma página (a CSP desta página
libera só form-action 'self'); abrir o link não confirma nada.
"""

import html

from .rotulos import HTML_LANG, idioma_valido, t


def pagina(titulo: str, texto: str, acao: str | None = None, idioma: str = "pt-BR") -> str:
    """A página no idioma do aviso (Fase K); o atributo lang acompanha o texto."""
    e, i = html.escape, idioma_valido(idioma)
    botao = (f'<form method="post" action="{e(acao, quote=True)}"><button type="submit">{e(t(i, "conf_botao"))}</button></form>'
             if acao else "")
    return f"""<!doctype html>
<html lang="{HTML_LANG[i]}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Norte · {e(titulo)}</title>
<link rel="icon" type="image/svg+xml" href="/assets/marca/farol-pequeno.svg">
<link rel="stylesheet" href="/assets/app/confirmar.css"></head>
<body><main class="caixa"><img src="/assets/marca/farol.svg" alt="" width="56" height="56">
<p class="marca">Norte</p><h1>{e(titulo)}</h1><p>{e(texto)}</p>{botao}</main></body></html>"""
