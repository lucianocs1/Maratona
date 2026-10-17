"""Nenhum True/False/None/null para quem lê (Bloco B, 15/10/2026): relatórios na tela (JSON que a tela mostra), em CSV e em PDF,
nos 3 idiomas, com os filtros ligados (inclusive "só acessos"). Também confere a explicação de quando "só acessos" dá 0.

Num esquema próprio (FAROL_ESQUEMA=teste_sem_booleanos, apagado no fim), com a semente de demonstração.
Uso (na raiz): uv run python -W ignore testes/api/teste_sem_booleanos.py
"""

import base64
import json
import os
import re
import sys
import zlib
from datetime import datetime, timedelta, timezone

os.environ.update({"FAROL_ESQUEMA": "teste_sem_booleanos", "FAROL_EMAIL": "0",
                   "FAROL_CHAVE_ARQUIVOS": base64.urlsafe_b64encode(os.urandom(32)).decode()})

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.semente_demo import semear_demo  # noqa: E402

PROIBIDO = re.compile(r"\b(True|False|None|null|undefined|NaN)\b")
NOVA = "Lanterna-do-Farol-2026"
resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def texto_pdf(b: bytes) -> str:
    partes = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", b, re.S):
        try:
            partes.append(zlib.decompressobj().decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    return " ".join("".join(x.replace("\\(", "(").replace("\\)", ")") for x in re.findall(r"\(((?:\\.|[^\\)])*)\)", ln))
                    for ln in "\n".join(partes).splitlines())


def valores(x):
    """Os textos que a tela mostra: os valores do documento (as chaves são nomes internos, nunca aparecem)."""
    if isinstance(x, dict):
        for v in x.values():
            yield from valores(v)
    elif isinstance(x, list):
        for v in x:
            yield from valores(v)
    elif isinstance(x, str):
        yield x
    elif x is None or isinstance(x, bool):
        pass   # valores não-texto: a tela os formata (nunca os escreve crus); o que importa são os textos prontos


try:
    with conectar() as c:
        c.execute("DROP SCHEMA IF EXISTS teste_sem_booleanos CASCADE")
    senhas = {e: s for _, e, s in semear()}
    semear_demo()

    def pronto(email):
        api_acesso._tentativas_ip.clear()
        cl = TestClient(app, base_url="http://farol.teste")
        cl.post("/api/entrar", json={"email": email, "senha": senhas[email]})
        cl.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
        return cl

    adm, far = pronto("admin@emg.example"), pronto("admin@farol.example")
    hoje = datetime.now(timezone(timedelta(hours=-3))).date()
    mes, ano = f"{hoje:%Y-%m}", hoje.year
    casos = [(adm, "mensal", f"mes={mes}"), (adm, "custos", f"ano={ano}"), (adm, "comunidades", f"ano={ano}"), (adm, "prazos", f"mes={mes}"),
             (adm, "auditoria", f"mes={mes}&so_acessos=true"), (adm, "auditoria", f"mes={mes}"),
             (far, "acessos", f"mes={mes}&so_acessos=true&empresa=EMG"), (far, "acessos", f"mes={mes}")]
    achados = []
    for idioma in ("pt-BR", "en", "es"):
        h = {"X-Farol-Idioma": idioma}
        for cl, tipo, q in casos:
            r = cl.get(f"/api/relatorios/{tipo}?{q}", headers=h)
            if r.status_code != 200:
                achados.append(f"{idioma} {tipo} tela: {r.status_code}")
                continue
            j = r.json()
            for s in valores({k: j.get(k) for k in ("documento", "subtitulo", "filtros", "periodo")}):
                if PROIBIDO.search(s):
                    achados.append(f"{idioma} {tipo} tela: {s[:80]}")
            for fmt in ("csv", "pdf"):
                b = cl.get(f"/api/relatorios/{tipo}.{fmt}?{q}", headers=h)
                txt = b.content.decode("utf-8-sig", "replace") if fmt == "csv" else texto_pdf(b.content)
                if b.status_code != 200:
                    achados.append(f"{idioma} {tipo}.{fmt}: {b.status_code}")
                elif (m := PROIBIDO.search(txt)):
                    achados.append(f"{idioma} {tipo}.{fmt}: …{txt[max(0, m.start() - 40):m.end() + 20]}…")
    conferir(f"{len(casos)} relatórios x 3 idiomas x tela/CSV/PDF: nenhum True/False/None/null/undefined/NaN", not achados,
             "\n  " + "\n  ".join(achados[:10]))
    r = far.get(f"/api/relatorios/acessos?mes={mes}&so_acessos=true&pessoa=Ninguem").json()
    conferir("filtro 'só acessos' aparece como 'sim' (nunca True)", "True" not in json.dumps(r["documento"], ensure_ascii=False))
    # 0 acessos com outras ações: o relatório diz por quê
    with conectar() as c:
        c.execute("INSERT INTO empresa (nome, sigla, dominio) VALUES ('Sem Acessos (teste)', 'SAC', 'sac.example')")
    far.post("/api/empresas", json={"nome": "Outra (teste)", "sigla": "OUT", "dominio": "out.example", "admin_nome": "Admin Outra",
                                    "admin_email": "admin@out.example"})
    r = far.get(f"/api/relatorios/acessos?mes={mes}&so_acessos=true&empresa=OUT").json()
    alertas = " ".join(r["documento"].get("alertas") or [])
    conferir("0 acessos: explica que há ações de outro tipo e como vê-las", r["total"] == 0 and "desmarque" in alertas and "Só acessos" in alertas, alertas[:200])
    r = far.get(f"/api/relatorios/acessos?mes={mes}&so_acessos=true&empresa=OUT", headers={"X-Farol-Idioma": "en"}).json()
    conferir("a explicação no idioma do relatório (inglês)", "uncheck" in " ".join(r["documento"].get("alertas") or []))
finally:
    with conectar() as c:
        c.execute("DROP SCHEMA IF EXISTS teste_sem_booleanos CASCADE")

for r in resultados:
    print(r[0], r[1], f"-> {r[2]}" if r[0] != "OK  " and r[2] else "")
falhas = sum(r[0] != "OK  " for r in resultados)
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
