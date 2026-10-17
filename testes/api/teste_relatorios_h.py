"""Teste da Fase H: relatórios completos, segunda via, envio por e-mail, ficha da comunidade e alerta de repetição.

Roda num esquema próprio do Postgres (apagado no fim), com a semente de acesso e a de demonstração (dados
FICTÍCIOS) e o Mailpit (caixa de e-mail de teste, data/raw/mailpit/mailpit.exe) em portas próprias. Confere:
- as contas puras (nucleo/relatorios.py): comparação ↑↓ %, duração, projeção, orçamento, repetição,
  intervalo, diferenças antes → depois, reais e CSV protegido contra fórmula;
- um PDF por relatório (mensal, custos, comunidades, prazos, comunidade, auditoria e acessos) com o rodapé
  "Gerado por <nome> (<perfil>) ... página X de Y", o código FRL e a página "Como calculamos";
- a segunda via: o código acha a linha na auditoria e o SHA-256 do PDF; a via baixada é idêntica (mesmo SHA);
- o "Enviar": só e-mails do domínio da empresa, até 5, limite por hora, Consulta não envia, acessos sem envio;
  o e-mail chega com o PDF (mesmo SHA) e os destinatários ficam na auditoria;
- varredura de minimização em todos os PDFs, CSVs e e-mails: nenhum número de UC nem coordenada;
- ficha da comunidade, mapa de calor, linha do tempo do aviso e o alerta de repetição;
- toda linha da auditoria com usuário tem nome e perfil.

Uso (na raiz): uv run python -W ignore testes/api/teste_relatorios_h.py
"""

import base64
import email
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SMTP, WEB = 1126, 8126
os.environ.update({"FAROL_ESQUEMA": "teste_relatorios_h", "FAROL_SMTP_HOST": "127.0.0.1", "FAROL_SMTP_PORTA": str(SMTP),
                   "FAROL_SMTP_SEGURANCA": "nenhuma", "FAROL_SMTP_REMETENTE": "Norte <avisos@farol.example>",
                   "FAROL_URL_PUBLICA": "http://farol.teste",
                   "FAROL_CHAVE_ARQUIVOS": base64.urlsafe_b64encode(os.urandom(32)).decode()})
os.environ.pop("FAROL_EMAIL", None)

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api import app as app_mod  # noqa: E402
from comunidades.api import relatorios as rel_mod  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo import relatorios as RH  # noqa: E402
from comunidades.nucleo.auditoria import diferencas  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.semente_demo import semear_demo  # noqa: E402

app = app_mod.app
resultados = []
NOVA = "Lanterna-do-Farol-2026"
BR = timezone(timedelta(hours=-3))
UC = re.compile(r"\b3\d{9}\b")                       # número de UC (10 algarismos)
COORD = re.compile(r"-\d{1,2}[.,]\d{4,}")            # coordenada em graus decimais


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(q, args=()):
    with conectar() as c, c.cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


def texto_pdf(b: bytes) -> str:
    partes = []
    # decompressobj ignora o que sobra depois do fim do zlib (o \r\n antes de endstream; um \r no fim dos dados não quebra)
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", b, re.S):
        try:
            partes.append(zlib.decompressobj().decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    return " ".join("".join(x.replace("\\(", "(").replace("\\)", ")") for x in re.findall(r"\(((?:\\.|[^\\)])*)\)", ln))
                    for ln in "\n".join(partes).splitlines())


def minimo(texto: str) -> bool:
    """Nenhum número de UC nem coordenada."""
    return not UC.search(texto) and not COORD.search(texto)


# ---------- 1. Contas (puro) ----------
conferir("comparar: ↑ 10,0%, ↓ 10,0%, = 0,0%; sem anterior ou anterior zero: None",
         (RH.comparar(110, 100), RH.comparar(90, 100), RH.comparar(100, 100), RH.comparar(5, 0), RH.comparar(5, None))
         == ("↑ 10,0%", "↓ 10,0%", "= 0,0%", None, None))
conferir("duração: '8h às 14h' = 6 h, '8h30 às 12h' = 3,5 h, só o início: None",
         (RH.duracao_horas("8h às 14h"), RH.duracao_horas("8h30 às 12h"), RH.duracao_horas("8h")) == (6.0, 3.5, None))
gastos = [100, 200, 300] + [0] * 9
p_aberto, p_fechado = RH.projecao(gastos, 3, False), RH.projecao(gastos, 3, True)
conferir("projeção (março em andamento): 600 + média de 2 meses fechados (150) x 9 = 1.950",
         (p_aberto["acumulado"], p_aberto["media"], p_aberto["restantes"], p_aberto["projecao"]) == (600, Decimal("150.00"), 9, Decimal("1950.00"))
         and "x 9" in p_aberto["conta"], p_aberto["conta"])
conferir("projeção (março fechado): 600 + 200 x 9 = 2.400", p_fechado["projecao"] == Decimal("2400.00"), p_fechado["conta"])
conferir("projeção em janeiro sem mês fechado: nenhuma", RH.projecao([50] + [0] * 11, 1, False)["projecao"] is None)
o1, o2 = RH.orcamento(Decimal("2400"), Decimal("600"), 2000), RH.orcamento(Decimal("1950"), Decimal("600"), 2000)
conferir("orçamento: 30% usado; alerta só quando a projeção passa do orçamento",
         o1["usado"] == 30.0 and o1["alerta"] and o2["alerta"] is None and RH.orcamento(1, 1, None)["usado"] is None, str(o1))
d0 = date(2026, 3, 1)
conferir("repetição: 3 desligamentos em 30 dias (2 em 15)", RH.repeticao([d0, d0 + timedelta(10), d0 + timedelta(20), d0 + timedelta(40)], 3, 30) == 3
         and RH.repeticao([d0, d0 + timedelta(10), d0 + timedelta(20)], 3, 15) == 2)
conferir("intervalo médio entre desligamentos: 15 dias", RH.intervalo_medio([d0, d0 + timedelta(10), d0 + timedelta(30)]) == 15.0)
conferir("diferenças antes → depois (só o que mudou)", diferencas({"a": 1, "b": "x"}, {"a": 2, "b": "x"}, {"a": "valor", "b": "nome"}) == "valor: 1 → 2"
         and diferencas({"a": 1}, {"a": 1}, {"a": "valor"}) == "nada mudou")
conferir("reais: R$ 1.234,50", RH.brl(Decimal("1234.5")) == "R$ 1.234,50")
_q = datetime(2026, 3, 10, 10, 0, tzinfo=BR)
_av = [{"id": 1, "criado_em": _q, "data": "20/03", "horario": "8h às 10h", "tipo": "poda", "status": "cancelado", "usuario": "Ana", "resumo": {},
        "municipios": [{"codigo_ibge": "1", "nome": "A", "ucs": 3, "equipamento_vital": {"sim": 0}, "comunidades": [{"nome": "X", "afetadas": 3}]}]}]
_en = [{"id": 1, "aviso_id": 1, "municipio": "1", "radio_id": 7, "radio_nome": "R", "canal": "email", "valor": Decimal("80"), "custo": Decimal("80"),
        "economia": Decimal("0"), "economia_tipo": "calculada", "segundos": 20, "status": "confirmado", "criado_em": _q, "criado_por_nome": "Ana"}]
_n = RH.numeros(_av, _en, date(2026, 3, 1), date(2026, 3, 31), {})
conferir("aviso cancelado: não conta como desligamento, mas o envio pago entra no gasto",
         _n["desligamentos"] == 0 and _n["cancelados"] == 1 and _n["gasto"] == Decimal("80") and RH._gasto_por_mes(_av, _en, 2026, {})[0][2] == 80,
         str({k: _n[k] for k in ("desligamentos", "cancelados", "gasto")}))
doc_f = {"titulo": "t", "resumo": [], "secoes": [{"tipo": "tabela", "titulo": "s", "colunas": ["a"], "linhas": [["=1+1"], ["@SOMA(A1)"]]}],
         "como_calculamos": ["x"]}
cf = RH.csv_documento(doc_f, "sub", "Ana (Operador)", "FRL-AAAA-BBBB-CCCC")
conferir("CSV: célula com '=' ou '@' sai com apóstrofo", "'=1+1" in cf and "'@SOMA(A1)" in cf, cf)

# ---------- 2. Mailpit, banco e semente ----------
MAILPIT = RAIZ / "data" / "raw" / "mailpit" / "mailpit.exe"
if not MAILPIT.exists():
    print("Mailpit não encontrado em data/raw/mailpit/.")
    sys.exit(2)
caixa = subprocess.Popen([str(MAILPIT), "--smtp", f"127.0.0.1:{SMTP}", "--listen", f"127.0.0.1:{WEB}", "--smtp-auth-accept-any",
                          "--smtp-auth-allow-insecure"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def mailpit(caminho: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{WEB}{caminho}", timeout=10) as r:
        dados = r.read()
        return json.loads(dados) if r.headers.get_content_type() == "application/json" else dados


for _ in range(100):
    try:
        socket.create_connection(("127.0.0.1", SMTP), 1).close()
        mailpit("/api/v1/messages")
        break
    except OSError:
        time.sleep(0.2)

try:
    with conectar() as c:
        c.execute("DROP SCHEMA IF EXISTS teste_relatorios_h CASCADE")
    senhas = {e: s for _, e, s in semear()}
    semear_demo()

    def pronto(email_, senha=None):
        api_acesso._tentativas_ip.clear()
        cl = TestClient(app, base_url="http://farol.teste")
        cl.post("/api/entrar", json={"email": email_, "senha": senha or senhas[email_]})
        cl.post("/api/senha", json={"atual": senha or senhas[email_], "nova": NOVA})
        return cl

    op, adm, con, far = (pronto(e) for e in ("operador@emg.example", "admin@emg.example", "consulta@emg.example", "admin@farol.example"))
    hoje = datetime.now(BR).date()
    mes = f"{hoje:%Y-%m}"
    calor = con.get("/api/comunidades/calor").json()
    chave = max(calor["comunidades"], key=calor["comunidades"].get)
    cod_mun, nome_com, distrito = chave.split("|")
    q_com = f"municipio={cod_mun}&nome={urllib.parse.quote(nome_com)}" + (f"&distrito={urllib.parse.quote(distrito)}" if distrito else "")
    conferir("mapa de calor: desligamentos por comunidade nos últimos 12 meses", calor["maximo"] >= 1 and len(calor["comunidades"]) > 3,
             json.dumps(calor)[:200])

    # ---------- 3. Um PDF e um CSV por relatório ----------
    casos = [("mensal", op, "Operador da EMG (Operador)", f"mes={mes}"), ("custos", con, "Consulta da EMG (Consulta)", f"ano={hoje.year}"),
             ("comunidades", op, "Operador da EMG (Operador)", f"ano={hoje.year}"), ("prazos", adm, "Admin da EMG (Admin da empresa)", f"mes={mes}"),
             ("comunidade", con, "Consulta da EMG (Consulta)", q_com), ("auditoria", adm, "Admin da EMG (Admin da empresa)", f"mes={mes}"),
             ("acessos", far, "Admin do Norte (Admin do Norte)", f"mes={mes}")]
    pdfs, arquivos = {}, []
    for tipo, cl, quem, q in casos:
        j = cl.get(f"/api/relatorios/{tipo}?{q}")
        p = cl.get(f"/api/relatorios/{tipo}.pdf?{q}")
        cv = cl.get(f"/api/relatorios/{tipo}.csv?{q}")
        txt = texto_pdf(p.content) if p.status_code == 200 else ""
        cod, sha = p.headers.get("x-codigo", "?"), p.headers.get("x-sha256", "?")
        pdfs[tipo] = (p.content, cod, sha, cl)
        arquivos += [(f"PDF {tipo}", txt), (f"CSV {tipo}", cv.text), (f"tela {tipo}", j.text)]
        conferir(f"{tipo}: tela, PDF e CSV (200)", (j.status_code, p.status_code, cv.status_code) == (200, 200, 200),
                 f"{j.status_code} {p.status_code} {cv.status_code} {p.text[:120] if p.status_code != 200 else ''}")
        conferir(f"{tipo}: rodapé com quem gerou, data, código e 'página 1 de N'; 'Como calculamos'",
                 p.content[:5] == b"%PDF-" and f"Gerado por {quem} em" in txt and cod in txt and re.search(r"página 1 de \d+", txt)
                 and "Como calculamos" in txt,
                 str([f"Gerado por {quem} em" in txt, cod in txt, bool(re.search(r"página 1 de \d+", txt)), "Como calculamos" in txt,
                      re.findall(r"página \d+ de ?\d*", txt)[:3]]))
        conferir(f"{tipo}: X-Sha256 = SHA-256 do PDF; CSV com o código e quem gerou",
                 sha == hashlib.sha256(p.content).hexdigest() and cv.headers.get("x-codigo", "!") in cv.text and quem in cv.text)
        conferir(f"{tipo}: o código está na auditoria com nome e perfil",
                 sql("SELECT count(*) FROM registro WHERE acao = %s AND usuario_nome IS NOT NULL AND perfil IS NOT NULL",
                     (f"gerou relatório {tipo} (PDF)",))[0][0] >= 1)
    conferir("custos: projeção com a conta escrita", "x" in (con.get(f"/api/relatorios/custos?ano={hoje.year}").json().get("projecao") or {})
             .get("conta", ""))
    na_tela = con.get(f"/api/relatorios/mensal?mes={mes}").json()
    conferir("a tela também vai para a auditoria ('gerou relatório mensal (tela)')",
             sql("SELECT count(*) FROM registro WHERE acao = 'gerou relatório mensal (tela)' AND usuario_nome = 'Consulta da EMG'")[0][0] >= 1)

    # ---------- 4. Segunda via ----------
    pdf_m, cod_m, sha_m, _ = pdfs["mensal"]
    vc = adm.get(f"/api/verificar/{cod_m}").json()
    conferir("verificar: o código acha a linha e o SHA-256 do PDF", vc.get("sha256_pdf") == sha_m and vc.get("por") == "Operador da EMG",
             json.dumps(vc)[:200])
    vias = op.get("/api/relatorios/vias").json()["vias"]
    via = next((v for v in vias if v["codigo"] == cod_m), None)
    conferir("vias: a do mensal na lista, com SHA-256 e quem gerou", via is not None and via["sha256"] == sha_m and via["por"] == "Operador da EMG")
    b = op.get(f"/api/relatorios/vias/{via['id']}.pdf")
    conferir("segunda via idêntica (mesmo SHA-256, mesmos bytes)", b.status_code == 200 and b.content == pdf_m
             and hashlib.sha256(b.content).hexdigest() == sha_m == b.headers.get("x-sha256"))
    conferir("baixar a via fica na auditoria", sql("SELECT count(*) FROM registro WHERE acao = 'baixou a segunda via do relatório' AND detalhe LIKE %s",
                                                    (f"{cod_m}%",))[0][0] == 1)
    cifrado = sql("SELECT cifrado FROM relatorio_via WHERE codigo = %s", (cod_m,))[0][0]
    conferir("a via está cifrada no banco (sem %PDF nem texto do relatório)", b"%PDF" not in bytes(cifrado) and b"Gerado por" not in bytes(cifrado))
    via_aud = next(v for v in adm.get("/api/relatorios/vias").json()["vias"] if v["tipo"] == "auditoria")
    conferir("Consulta não vê nem baixa a via da auditoria (404)", all(v["tipo"] != "auditoria" for v in con.get("/api/relatorios/vias").json()["vias"])
             and con.get(f"/api/relatorios/vias/{via_aud['id']}.pdf").status_code == 404)
    conferir("outra empresa não baixa a via (Admin do Norte: 404)", far.get(f"/api/relatorios/vias/{via['id']}.pdf").status_code == 404)

    # ---------- 5. Enviar ----------
    corpo = {"filtros": {"mes": mes}, "destinatarios": ["diretoria@emg.example", "Financeiro@EMG.example"]}
    conferir("Consulta não envia (403)", con.post("/api/relatorios/mensal/enviar", json=corpo).status_code == 403)
    fora = op.post("/api/relatorios/mensal/enviar", json={**corpo, "destinatarios": ["diretoria@emg.example", "alguem@gmail.com"]})
    conferir("e-mail fora do domínio da empresa: 422 e nada enviado", fora.status_code == 422 and "gmail.com" in fora.text
             and mailpit("/api/v1/messages")["total"] == 0, fora.text[:160])
    seis = op.post("/api/relatorios/mensal/enviar", json={**corpo, "destinatarios": [f"p{i}@emg.example" for i in range(6)]})
    conferir("mais de 5 destinatários: 422", seis.status_code == 422)
    conferir("acessos (todas as empresas) não tem envio", far.post("/api/relatorios/acessos/enviar", json=corpo).status_code in (404, 405))
    ok = op.post("/api/relatorios/mensal/enviar", json=corpo)
    rj = ok.json() if ok.status_code == 200 else {}
    conferir("envio do mensal (Operador): 200, dois destinatários", ok.status_code == 200
             and rj["destinatarios"] == ["diretoria@emg.example", "financeiro@emg.example"], ok.text[:200])
    msgs = mailpit("/api/v1/messages")["messages"]
    conferir("Mailpit: 1 e-mail para os dois endereços", len(msgs) == 1 and {t["Address"] for t in msgs[0]["To"]}
             == {"diretoria@emg.example", "financeiro@emg.example"}, json.dumps(msgs)[:200])
    bruto = mailpit(f"/api/v1/message/{msgs[0]['ID']}/raw")
    em = email.message_from_bytes(bruto)
    anexo = next((pt.get_payload(decode=True) for pt in em.walk() if pt.get_content_type() == "application/pdf"), b"")
    texto_email = "\n".join(pt.get_payload(decode=True).decode("utf-8", "replace") for pt in em.walk()
                            if pt.get_content_type() in ("text/plain", "text/html"))
    conferir("e-mail: PDF anexo com o mesmo SHA-256 da via; código e quem gerou no texto",
             hashlib.sha256(anexo).hexdigest() == rj.get("sha256") and rj.get("codigo", "!") in texto_email and "Operador da EMG" in texto_email,
             texto_email[:200])
    arquivos += [("e-mail", texto_email), ("PDF do e-mail", texto_pdf(anexo))]
    conferir("o envio fica na auditoria com os destinatários e o SHA-256",
             sql("SELECT count(*) FROM registro WHERE acao = 'enviou relatório mensal por e-mail' AND detalhe LIKE %s AND detalhe LIKE %s",
                 ("%diretoria@emg.example%", f"%{rj.get('sha256')}%"))[0][0] == 1)
    conferir("Admin da empresa envia a auditoria", adm.post("/api/relatorios/auditoria/enviar",
                                                           json={"filtros": {"mes": mes}, "destinatarios": ["auditoria@emg.example"]}).status_code == 200)
    conferir("Operador não envia a auditoria (403)", op.post("/api/relatorios/auditoria/enviar",
                                                            json={"filtros": {"mes": mes}, "destinatarios": ["a@emg.example"]}).status_code == 403)
    op_id = op.get("/api/eu").json()["usuario"]["id"]
    rel_mod._envios[op_id].extend([time.monotonic()] * rel_mod.LIMITE_ENVIOS_REL)
    conferir(f"limite: o {rel_mod.LIMITE_ENVIOS_REL + 1}º envio na mesma hora é recusado (429)",
             op.post("/api/relatorios/mensal/enviar", json=corpo).status_code == 429)
    rel_mod._envios.clear()
    conferir("filtro com texto longo demais no envio: 422", op.post("/api/relatorios/mensal/enviar",
                                                                   json={**corpo, "filtros": {"pessoa": "x" * 300}}).status_code == 422)

    # ---------- 6. Ficha, linha do tempo e repetição ----------
    fi = con.get(f"/api/comunidades/ficha?{q_com}")
    conferir("ficha da comunidade: 200, com desligamentos dos últimos 12 meses", fi.status_code == 200 and json.dumps(fi.json()).count("{") > 1,
             fi.text[:200])
    arquivos.append(("ficha", fi.text))
    aid = sql("SELECT a.id FROM aviso a WHERE EXISTS (SELECT 1 FROM envio e WHERE e.aviso_id = a.id) ORDER BY a.id LIMIT 1")[0][0]
    con.get(f"/api/historico/{aid}/comprovante.pdf")
    lt = con.get(f"/api/historico/{aid}/linha-do-tempo").json()["linhas"]
    conferir("linha do tempo do aviso: em ordem, com nome e perfil, inclui o comprovante",
             lt and all(x["usuario"] and x["perfil"] for x in lt) and any(x["acao"] == "gerou comprovante do aviso (PDF)" for x in lt)
             and [x["quando"] for x in lt] == sorted(x["quando"] for x in lt), json.dumps(lt, ensure_ascii=False)[:300])
    emp_id = sql("SELECT id FROM empresa WHERE sigla = 'EMG'")[0][0]
    m_com = {"codigo_ibge": cod_mun, "nome": "Município", "comunidades": [{"nome": nome_com, "distrito": distrito or None}, {"nome": "Inexistente"}]}
    # o nome guardado pode ter o sufixo " (distrito)": usa o do banco
    for a in sql("SELECT municipios FROM aviso WHERE empresa_id = %s AND status <> 'cancelado'", (emp_id,)):
        for m in a[0]:
            for c in m["comunidades"]:
                if m["codigo_ibge"] == cod_mun and c["nome"].split(" (")[0] == nome_com and (c.get("distrito") or "") == distrito:
                    m_com["comunidades"][0] = {"nome": c["nome"], "distrito": c.get("distrito")}
    resp = {"municipios": [m_com], "conferencia": {"suspeitos": []}}
    rep = app_mod._alerta_repeticao(resp, {"empresa_id": emp_id}, {"repeticao_n": 2, "repeticao_dias": 400})
    sus = resp["conferencia"]["suspeitos"]
    conferir("alerta de repetição: amarelo (suspeito), só a comunidade com desligamento anterior",
             rep and len(sus) == 1 and sus[0]["tipo"] == "repeticao" and len(sus[0]["comunidades"]) == 1 and nome_com in sus[0]["comunidades"][0],
             json.dumps(sus, ensure_ascii=False))
    resp2 = {"municipios": [{"codigo_ibge": cod_mun, "nome": "M", "comunidades": [{"nome": "Inexistente"}]}], "conferencia": {"suspeitos": []}}
    conferir("sem repetição: nenhum alerta", app_mod._alerta_repeticao(resp2, {"empresa_id": emp_id}, {"repeticao_n": 2, "repeticao_dias": 400}) is None
             and not resp2["conferencia"]["suspeitos"])

    # ---------- 7. Minimização e registro ----------
    ruins = [n for n, t in arquivos if not minimo(t)]
    conferir(f"minimização: {len(arquivos)} PDFs, CSVs, telas e e-mails sem número de UC nem coordenada", not ruins, ", ".join(ruins))
    conferir("toda linha com usuário tem nome e perfil", sql("SELECT count(*) FROM registro WHERE usuario_id IS NOT NULL "
                                                              "AND (usuario_nome IS NULL OR perfil IS NULL)")[0][0] == 0)
    conferir("auditoria íntegra", far.get("/api/auditoria/verificar").json()["ok"])
finally:
    caixa.terminate()
    caixa.wait(timeout=10)
    with conectar() as c:
        c.execute("DROP SCHEMA IF EXISTS teste_relatorios_h CASCADE")

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
