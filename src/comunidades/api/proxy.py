"""IP e esquema de quem acessa, atrás do proxy HTTPS do Render (só em produção).

O cabeçalho X-Forwarded-For é uma lista que cada proxy aumenta pela direita: "cliente, proxy1, ...".
O que o cliente escreve fica à esquerda, então só valem os itens acrescentados pelos nossos proxies,
contados da direita: com FAROL_SALTOS_PROXY=1 (padrão; o Render põe um proxy na frente), o IP é o
último da lista. Assim um X-Forwarded-For inventado não escapa do limite de tentativas de login.
O esquema (https) vem do X-Forwarded-Proto do mesmo proxy, para as URLs que a API monta (como o
redirecionamento da barra final) saírem em https.

Fora de produção os cabeçalhos são ignorados (o uvicorn roda com --no-proxy-headers).
"""

import os

SALTOS = int(os.environ.get("FAROL_SALTOS_PROXY", "1"))


def _lista(scope: dict, nome: bytes) -> list[str]:
    valores = [v.decode("latin-1") for k, v in scope["headers"] if k == nome]
    return [x.strip() for v in valores for x in v.split(",") if x.strip()]


class ProxyConfiavel:
    """Middleware ASGI: troca o cliente e o esquema da requisição pelos que o proxy informou."""

    def __init__(self, app, saltos: int = SALTOS):
        if saltos < 1:
            raise ValueError("FAROL_SALTOS_PROXY: pelo menos 1 (o proxy do Render)")
        self.app, self.saltos = app, saltos

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            ips = _lista(scope, b"x-forwarded-for")
            # menos itens que proxies: a requisição não passou por todos eles; fica o IP da conexão
            if len(ips) >= self.saltos:
                scope = dict(scope, client=(ips[-self.saltos], 0))
            protos = _lista(scope, b"x-forwarded-proto")
            if protos and protos[-1] in ("http", "https"):
                https = protos[-1] == "https"
                scope = dict(scope, scheme=("wss" if https else "ws") if scope["type"] == "websocket"
                             else protos[-1])
        await self.app(scope, receive, send)
