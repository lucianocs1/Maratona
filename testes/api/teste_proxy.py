"""Teste do IP e do esquema atrás do proxy (api/proxy.py), sem banco.

Confere:
- X-Forwarded-For inventado pelo cliente não vale: com 1 salto, o IP é o último da lista (o que o
  proxy acrescentou); com 2 saltos, o penúltimo; com menos itens que saltos, fica o IP da conexão;
- trocar o X-Forwarded-For a cada tentativa não escapa do limite de tentativas de login por IP;
- X-Forwarded-Proto: https nas URLs que a API monta (request.url e o redirecionamento da barra
  final), e um valor estranho é ignorado;
- fora de produção (sem o middleware) os cabeçalhos são ignorados;
- a API de produção liga o middleware; o Dockerfile não confia em X-Forwarded-* pelo uvicorn.

Uso (na raiz): uv run python -W ignore testes/api/teste_proxy.py
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from comunidades.api import acesso
from comunidades.api.proxy import ProxyConfiavel

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def app_de_teste(saltos: int | None) -> TestClient:
    """Uma API mínima que devolve o IP e a URL que a requisição vê (None: sem o middleware)."""
    a = FastAPI()

    @a.get("/quem")
    def quem(request: Request) -> dict:
        return {"ip": request.client.host, "url": str(request.url), "esquema": request.url.scheme}

    @a.post("/entrar")
    def entrar(request: Request) -> dict:
        acesso._limite_ip(request.client.host)   # o mesmo limite do login de verdade
        return {"ok": True}

    if saltos is not None:
        a.add_middleware(ProxyConfiavel, saltos=saltos)
    return TestClient(a, base_url="http://farol.teste")


xff = lambda v: {"X-Forwarded-For": v}

# --- produção, 1 salto (Render)
cli = app_de_teste(1)
conferir("sem X-Forwarded-For: IP da conexão", cli.get("/quem").json()["ip"] == "testclient")
r = cli.get("/quem", headers=xff("6.6.6.6, 1.2.3.4")).json()
conferir("cliente escreve 6.6.6.6, proxy acrescenta 1.2.3.4: vale 1.2.3.4", r["ip"] == "1.2.3.4", r)
r = cli.get("/quem", headers={"X-Forwarded-For": "6.6.6.6", "x-forwarded-for": "1.2.3.4"}).json()
conferir("cabeçalho repetido: vale o último item", r["ip"] == "1.2.3.4", r)

# --- 2 saltos (ex.: outro proxy na frente do Render)
r = app_de_teste(2).get("/quem", headers=xff("6.6.6.6, 5.5.5.5, 1.2.3.4")).json()
conferir("2 saltos: vale o penúltimo (5.5.5.5)", r["ip"] == "5.5.5.5", r)
r = app_de_teste(2).get("/quem", headers=xff("1.2.3.4")).json()
conferir("2 saltos e 1 item só: fica o IP da conexão", r["ip"] == "testclient", r)
try:
    ProxyConfiavel(None, saltos=0)
    conferir("0 saltos é recusado", False)
except ValueError:
    conferir("0 saltos é recusado", True)

# --- limite de tentativas com X-Forwarded-For trocado a cada tentativa
acesso._tentativas_ip.clear()
codigos = [cli.post("/entrar", headers=xff(f"10.0.{i}.{i}, 9.9.9.9")).status_code for i in range(acesso.LIMITE_IP + 5)]
conferir(f"X-Forwarded-For diferente a cada tentativa: bloqueado (429) depois de {acesso.LIMITE_IP}",
         codigos[:acesso.LIMITE_IP] == [200] * acesso.LIMITE_IP and set(codigos[acesso.LIMITE_IP:]) == {429},
         codigos)
acesso._tentativas_ip.clear()

# --- esquema
r = cli.get("/quem", headers={"X-Forwarded-Proto": "https"}).json()
conferir("X-Forwarded-Proto https: a URL que a API vê é https", r["esquema"] == "https" and r["url"].startswith("https://farol.teste/"), r)
r = cli.get("/quem", headers={"X-Forwarded-Proto": "http, https"}).json()
conferir("X-Forwarded-Proto com lista: vale o último (do proxy)", r["esquema"] == "https", r)
r = cli.get("/quem", headers={"X-Forwarded-Proto": "javascript"}).json()
conferir("X-Forwarded-Proto estranho é ignorado", r["esquema"] == "http", r)
r = cli.get("/quem/", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False)
conferir("redirecionamento da barra final sai em https", r.status_code in (307, 308)
         and r.headers.get("location", "").startswith("https://farol.teste/quem"), r.headers.get("location"))

# --- fora de produção: nada muda
dev = app_de_teste(None)
r = dev.get("/quem", headers={**xff("6.6.6.6, 1.2.3.4"), "X-Forwarded-Proto": "https"}).json()
conferir("fora de produção: X-Forwarded-For e -Proto ignorados", r["ip"] == "testclient" and r["esquema"] == "http", r)

# --- a API de verdade e o Dockerfile
from comunidades.api import app as modulo_app  # noqa: E402

tem = any(m.cls is ProxyConfiavel for m in modulo_app.app.user_middleware)
conferir("API local (FAROL_PRODUCAO desligado) sem o middleware", tem == modulo_app.PRODUCAO, f"PRODUCAO={modulo_app.PRODUCAO}")
docker = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text(encoding="utf-8")
cmd = next(l for l in docker.splitlines() if l.startswith("CMD"))
conferir("Dockerfile: uvicorn com --no-proxy-headers e sem --forwarded-allow-ips",
         "--no-proxy-headers" in cmd and "forwarded-allow-ips" not in cmd, cmd)
if not os.environ.get("FAROL_PRODUCAO"):
    import subprocess
    r = subprocess.run([sys.executable, "-c", "from comunidades.api.app import app; from comunidades.api.proxy import ProxyConfiavel;"
                        "print(any(m.cls is ProxyConfiavel for m in app.user_middleware))"],
                       env={**os.environ, "FAROL_PRODUCAO": "1"}, capture_output=True, text=True)
    conferir("API com FAROL_PRODUCAO=1 liga o middleware", r.stdout.strip() == "True", (r.stdout + r.stderr)[-300:])

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
