"""Teste da Fase C: mensagem pelo modelo da empresa, rádios, envio (e-mail, WhatsApp, cópia), confirmação e cofre.

Sobe o Mailpit (caixa de e-mail de teste, data/raw/mailpit/mailpit.exe) em portas próprias, só em
127.0.0.1: nada sai para a internet. Roda num esquema próprio do Postgres, apagado no fim. Confere:
- nucleo/mensagem.py: campos, trechos opcionais que somem, nomes sem o sufixo, modelo inválido recusado;
- nucleo/economia.py: por minuto (calculada), valor fechado (só informada), nunca inventa;
- nucleo/radios.py: alcance por município ou por comunidade com o distrito (homônimo não confunde);
- cofre.py: AES-256-GCM, arquivo alterado ou trocado de envio não abre;
- configuração da empresa (só Admin), mensagem do aviso pelo modelo, {codigo} preenchido depois de gravar;
- rádios (Operador acrescenta, só o Admin altera), sugestão por comunidade e "sem rádio";
- envio por e-mail: PDF e MP3 anexos no Mailpit, guardados cifrados no banco, link de confirmação de
  uso único (GET só mostra; POST confirma; vencido e repetido recusados), status e auditoria;
- WhatsApp (wa.me com o texto) e cópia; valor gravado no envio; economia calculada e informada;
- texto com número de UC ou e-mail recusado; aviso cancelado não envia; limite de e-mails por hora;
  falha do servidor de e-mail vira "falhou"; sem SMTP, o e-mail fica desligado;
- outra empresa não vê envios nem arquivos; Consulta vê o comprovante mas não envia.

Uso (na raiz): uv run python -W ignore testes/api/teste_radio.py
"""

import base64
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SMTP, WEB = 1125, 8125
os.environ.update({"FAROL_ESQUEMA": "teste_radio", "FAROL_SMTP_HOST": "127.0.0.1", "FAROL_SMTP_PORTA": str(SMTP),
                   "FAROL_SMTP_SEGURANCA": "nenhuma", "FAROL_SMTP_REMETENTE": "Norte <avisos@farol.example>",
                   "FAROL_URL_PUBLICA": "http://farol.teste",
                   "FAROL_CHAVE_ARQUIVOS": base64.urlsafe_b64encode(os.urandom(32)).decode()})

from fastapi.testclient import TestClient  # noqa: E402

from comunidades import cofre  # noqa: E402
from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api import app as app_mod  # noqa: E402
from comunidades.api import radio as radio_mod  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo import economia as E  # noqa: E402
from comunidades.nucleo import mensagem as M  # noqa: E402
from comunidades.nucleo import radios as R  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.simulacao import planilhas_teste  # noqa: E402

resultados = []
NOVA = "Lanterna-do-Farol-2026"


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(q, args=()):
    with conectar() as c, c.cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


# ---------- 1. Regras puras ----------
V = {"distribuidora": "Distribuidora EMG", "municipio": "Leopoldina", "data": "20/11", "inicio": "8h", "fim": "14h",
     "motivo": "poda de árvores perto da rede", "comunidades": "Graminha e Boa Sorte", "comunidades_parciais": "Tomé Nogueira",
     "telefone_atendimento": "0800 701 0102", "codigo": "FRL-AAAA-BBBB-CCCC"}
conferir("mensagem: o modelo padrão com todos os campos", M.montar(M.PADRAO, V) ==
         "Atenção, ouvintes. A Distribuidora EMG informa: no dia 20/11, das 8h às 14h, haverá desligamento programado de energia "
         "para poda de árvores perto da rede nas comunidades Graminha e Boa Sorte. Ficará sem energia parte de: Tomé Nogueira. "
         "Programe-se. Dúvidas: 0800 701 0102.", M.montar(M.PADRAO, V))
sem = M.montar(M.PADRAO, {**V, "telefone_atendimento": "", "comunidades_parciais": ""})
conferir("mensagem: trechos opcionais com campo vazio somem inteiros", "Dúvidas" not in sem and "parte de" not in sem
         and sem.endswith("Programe-se."), sem)
so_parciais = M.montar(M.PADRAO, {**V, "comunidades": ""})
conferir("mensagem: sem comunidade inteira, some o 'nas comunidades'", "nas comunidades" not in so_parciais
         and "rede. Ficará sem energia parte de: Tomé Nogueira." in so_parciais, so_parciais)
mun = {"codigo_ibge": "3138401", "nome": "Leopoldina", "comunidades": [{"nome": "Piacatuba (Tebas)", "distrito": "Tebas"}, {"nome": "Graminha", "distrito": "Piacatuba"},
                                             {"nome": "Piacatuba (Piacatuba)", "distrito": "Piacatuba", "parcial": True}]}
vm = M.valores_do_municipio(mun, distribuidora="X", data="1/1", horario="8h às 14h", motivo="m")
conferir("mensagem: nomes sem o sufixo de distrito, lista falada, início e fim", vm["comunidades"] == "Piacatuba e Graminha"
         and vm["comunidades_parciais"] == "Piacatuba" and (vm["inicio"], vm["fim"]) == ("8h", "14h"), json.dumps(vm, ensure_ascii=False))
for nome, modelo, trecho in [("campo desconhecido", "no dia {data} {comunidades} {cliente}", "desconhecido"),
                             ("colchete aberto", "[no dia {data} {comunidades}", "colchete"),
                             ("colchete dentro de colchete", "[a [b] {data}] {comunidades}", "colchetes"),
                             ("chave solta", "no dia {data} {comunidades} }", "chave"), ("sem {data}", "{comunidades}", "{data}"),
                             ("vazio", " ", "vazio"), ("controle", "{data}{comunidades}\x07", "controle")]:
    conferir(f"modelo recusado: {nome}", trecho in (M.problema_modelo(modelo) or ""), str(M.problema_modelo(modelo)))
conferir("modelo padrão aceito", M.problema_modelo(M.PADRAO) is None)

c = E.calcular("minuto", Decimal("150.00"), 20, 200)
conferir("economia por minuto com o aviso de hoje: calculada (200-20) s x R$150/min", c == {"custo": Decimal("50.00"),
         "economia": Decimal("450.00"), "economia_tipo": "calculada", "tempo_economizado": 180}, str(c))
conferir("por minuto sem o aviso de hoje e sem custo antigo: sem economia (não inventa)",
         E.calcular("minuto", Decimal("150"), 20)["economia"] is None)
conferir("por minuto sem o aviso de hoje, com custo antigo informado: informada",
         E.calcular("minuto", Decimal("150"), 20, None, Decimal("300"))["economia_tipo"] == "informada")
conferir("valor fechado sem custo antigo: sem economia; tempo economizado se há o aviso de hoje",
         E.calcular("fechado", Decimal("200"), 20, 200) == {"custo": Decimal("200"), "economia": None, "economia_tipo": None,
                                                           "tempo_economizado": 180})
conferir("valor fechado com custo antigo: informada (antigo - valor)",
         E.calcular("fechado", Decimal("200"), 20, None, Decimal("650"))["economia"] == Decimal("450.00"))
conferir("reais: '1.234,56', 'R$ 10', 99.999", (E.reais("1.234,56"), E.reais("R$ 10"), E.reais(99.999)) ==
         (Decimal("1234.56"), Decimal("10.00"), Decimal("100.00")))
for v in ("-5", "abc", "100001", "NaN", True):
    try:
        E.reais(v)
        conferir(f"reais recusa {v!r}", False)
    except ValueError:
        conferir(f"reais recusa {v!r}", True)

radios = [{"id": 1, "alcance": {"municipios": ["3138401"], "comunidades": []}},
          {"id": 2, "alcance": {"municipios": [], "comunidades": [{"municipio": "3138401", "nome": "Piacatuba", "distrito": "Tebas"}]}}]
cob = R.cobertura(radios[1:], mun)
conferir("alcance por comunidade: Piacatuba (Tebas) sim, Piacatuba (Piacatuba) e Graminha não (homônimo não confunde)",
         cob["radios"] == [{"radio_id": 2, "municipio_inteiro": False, "comunidades": 1}]
         and cob["sem_radio"] == ["Graminha (Piacatuba)", "Piacatuba (Piacatuba)"], json.dumps(cob, ensure_ascii=False))
conferir("alcance pelo município inteiro: nenhuma sem rádio", R.cobertura(radios, mun)["sem_radio"] == [])
try:
    R.normalizar_alcance({"municipios": ["9999999"]}, {"3138401"})
    conferir("alcance com município fora da concessão: recusado", False)
except ValueError:
    conferir("alcance com município fora da concessão: recusado", True)

seg = cofre.cifrar(b"%PDF conteudo secreto", 1, 10, "pdf")
conferir("cofre: ida e volta, sem o texto claro", cofre.decifrar(seg, 1, 10, "pdf") == b"%PDF conteudo secreto" and b"secreto" not in seg)
for nome, args in [("um byte alterado", (seg[:-1] + bytes([seg[-1] ^ 1]), 1, 10, "pdf")), ("de outro envio", (seg, 1, 11, "pdf")),
                   ("de outra empresa", (seg, 2, 10, "pdf")), ("como MP3", (seg, 1, 10, "mp3"))]:
    try:
        cofre.decifrar(*args)
        conferir(f"cofre recusa: {nome}", False)
    except cofre.Violado:
        conferir(f"cofre recusa: {nome}", True)

# ---------- 2. Mailpit e API ----------
MAILPIT = RAIZ / "data" / "raw" / "mailpit" / "mailpit.exe"
if not MAILPIT.exists():
    print("Mailpit não encontrado em data/raw/mailpit/ (ver docs ou rode o download).")
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
    with conectar() as cx:
        cx.execute("DROP SCHEMA IF EXISTS teste_radio CASCADE")
    senhas = {e: s for _, e, s in semear()}

    def pronto(email, senha=None):
        api_acesso._tentativas_ip.clear()
        cl = TestClient(app, base_url="http://farol.teste")
        cl.post("/api/entrar", json={"email": email, "senha": senha or senhas[email]})
        cl.post("/api/senha", json={"atual": senha or senhas[email], "nova": NOVA})
        return cl

    op, adm, con = pronto("operador@emg.example"), pronto("admin@emg.example"), pronto("consulta@emg.example")
    publico = TestClient(app, base_url="http://farol.teste")
    t = planilhas_teste.planilha("CF-0066")
    planilha = t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")

    def gerar(cliente=op, tipo="poda"):
        app_mod._envios.clear()
        r = cliente.post("/api/planilha", files={"arquivo": ("p.csv", planilha)}, data={"data": "12/11", "horario": "8h às 14h", "tipo": tipo})
        return cliente.post("/api/avisos", json={"pacote": r.json()["pacote"], "data": "12/11", "horario": "8h às 14h", "conferi": True,
                                                 "tipo": tipo}).json()

    # configuração
    conferir("configuração: Operador e Consulta não veem nem mudam (403)", op.get("/api/empresa/configuracao").status_code == 403
             and con.put("/api/empresa/configuracao", json={}).status_code == 403)
    cfg = adm.get("/api/empresa/configuracao").json()
    conferir("configuração: padrões (modelo padrão, limite 2%, fuso 31983)", cfg["modelo_mensagem"] == M.PADRAO
             and cfg["limite_rejeicao"] == 0.02 and cfg["epsg_utm"] == 31983 and cfg["padroes"], json.dumps(cfg, ensure_ascii=False)[:200])
    ruim = adm.put("/api/empresa/configuracao", json={**{k: cfg[k] for k in ("nome_mensagem", "telefone", "limite_rejeicao", "epsg_utm",
                                                                             "antecedencia_dias")}, "modelo_mensagem": "dia {data} {cliente}"})
    conferir("configuração: modelo com campo desconhecido recusado (422)", ruim.status_code == 422 and "cliente" in ruim.text, ruim.text[:120])
    novo = {"modelo_mensagem": M.PADRAO, "nome_mensagem": "Distribuidora EMG", "telefone": "0800 701 0102", "limite_rejeicao": 0.05,
            "epsg_utm": 31983, "antecedencia_dias": 15}
    ok = adm.put("/api/empresa/configuracao", json=novo)
    conferir("configuração: Admin salva; a auditoria diz o que mudou", ok.status_code == 200 and ok.json()["telefone"] == "0800 701 0102"
             and "telefone" in sql("SELECT detalhe FROM registro WHERE acao = 'alterou a configuração da empresa' ORDER BY id DESC LIMIT 1")[0][0])

    a = gerar()
    leo = a["municipios"][0]
    conferir("aviso: a mensagem da rádio pelo modelo da empresa (motivo, telefone, sem sufixo de distrito)",
             leo["mensagem"].startswith("Atenção, ouvintes. A Distribuidora EMG informa: no dia 12/11, das 8h às 14h, haverá desligamento "
                                        "programado de energia para poda de árvores perto da rede nas comunidades ")
             and leo["mensagem"].endswith("Dúvidas: 0800 701 0102.") and "(Tebas)" not in leo["mensagem"]
             and leo["segundos_mensagem"] == round(len(leo["mensagem"].split()) / 2.5), leo["mensagem"])
    hist = op.get(f"/api/historico/{a['id']}").json()["municipios"][0]
    conferir("histórico: guarda a mensagem da rádio", hist["mensagem"] == leo["mensagem"])
    adm.put("/api/empresa/configuracao", json={**novo, "modelo_mensagem": M.PADRAO + " Código {codigo}."})
    a2 = gerar()
    conferir("modelo com {codigo}: a mensagem sai com o código do aviso (também no histórico)",
             a2["municipios"][0]["mensagem"].endswith(f"Código {a2['codigo']}.")
             and op.get(f"/api/historico/{a2['id']}").json()["municipios"][0]["mensagem"].endswith(f"Código {a2['codigo']}."),
             a2["municipios"][0]["mensagem"][-60:])
    adm.put("/api/empresa/configuracao", json=novo)

    # rádios
    dados_leo = {"nome": "Rádio Leopoldina FM (demonstração)", "email": "leopoldina.fm@example.com", "whatsapp": "(32) 99999-0001",
                 "alcance": {"municipios": ["3138401"]}, "valor_padrao": "120,00", "cobranca": "minuto"}
    conferir("Operador não cadastra rádio (403): só o Admin da empresa (Fase J)", op.post("/api/radios", json=dados_leo).status_code == 403)
    r_leo = adm.post("/api/radios", json=dados_leo)
    conferir("Admin da empresa cadastra rádio", r_leo.status_code == 200 and r_leo.json()["radio"]["whatsapp"] == "32999990001", r_leo.text[:160])
    dup = adm.post("/api/radios", json={**dados_leo, "nome": "  rádio leopoldina FM  (demonstração) "})
    conferir("rádio com o mesmo nome (maiúsculas e espaços à parte) recusada (409), com o campo", dup.status_code == 409
             and dup.headers.get("X-Farol-Campo") == "nome", dup.text[:120])
    leo_id = r_leo.json()["radio"]["id"]
    r_pia = adm.post("/api/radios", json={"nome": "Rádio Comunitária de Tebas (demonstração)", "email": "tebas@example.com",
                                          "alcance": {"comunidades": [{"municipio": "3138401", "nome": "Piacatuba", "distrito": "Tebas"}]},
                                          "valor_padrao": "300", "cobranca": "fechado"})
    pia_id = r_pia.json()["radio"]["id"]
    conferir("Operador não altera rádio (403); Admin altera", op.patch(f"/api/radios/{leo_id}", json={"nome": "x"}).status_code == 403
             and adm.patch(f"/api/radios/{pia_id}", json={"nome": "Rádio Comunitária de Tebas (demonstração)", "email": "tebas@example.com",
                                                         "alcance": {"comunidades": [{"municipio": "3138401", "nome": "Piacatuba", "distrito": "Tebas"}]},
                                                         "valor_padrao": "350", "cobranca": "fechado"}).status_code == 200)
    erros = {"e-mail inválido": {"nome": "R", "email": "nao-e-email"}, "sem contato": {"nome": "Rádio X"},
             "município fora da concessão": {"nome": "Rádio X", "email": "x@example.com", "alcance": {"municipios": ["3550308"]}},
             "WhatsApp curto": {"nome": "Rádio X", "whatsapp": "1234"}}
    respostas = {k: adm.post("/api/radios", json=d) for k, d in erros.items()}
    conferir("rádio inválida recusada (422), com o campo do erro", all(r.status_code == 422 for r in respostas.values())
             and [r.headers.get("X-Farol-Campo") for r in respostas.values()] == ["nome", "email", "alcance", "whatsapp"],
             str({k: (r.status_code, r.headers.get("X-Farol-Campo")) for k, r in respostas.items()}))
    # pedidos de rádio (Fase J): o Operador pede; o Admin atende (cadastra a partir do pedido) ou recusa com motivo
    ped = op.post("/api/radios/pedidos", json={"nome": "Rádio Pedida (demonstração)", "cidade": "Leopoldina", "contato": "pedida@example.com",
                                               "observacao": "Cobre a zona rural."})
    ped2 = op.post("/api/radios/pedidos", json={"nome": "Rádio Pedida (demonstração)", "cidade": "leopoldina"})
    ped3 = op.post("/api/radios/pedidos", json={"nome": "Rádio Recusada (demonstração)", "cidade": "Tebas", "observacao": "CPF 123.456.789-00"})
    ped4 = op.post("/api/radios/pedidos", json={"nome": "Rádio Recusada (demonstração)", "cidade": "Tebas", "contato": "(32) 3441-0000"})
    conferir("pedido de rádio: o Operador pede; repetido (409) e com dado pessoal na observação (422) recusados",
             ped.status_code == 200 and ped2.status_code == 409 and ped3.status_code == 422 and ped3.headers.get("X-Farol-Campo") == "observacao"
             and ped4.status_code == 200, f"{ped.status_code} {ped2.status_code} {ped3.status_code} {ped4.status_code}")
    conferir("pedido de rádio: o Admin da empresa não pede (403) e o Operador não recusa (403)",
             adm.post("/api/radios/pedidos", json={"nome": "Rádio X", "cidade": "Leopoldina"}).status_code == 403
             and op.post(f"/api/radios/pedidos/{ped4.json()['pedido']['id']}/recusar", json={"motivo": "não"}).status_code == 403)
    lista_adm, lista_op = adm.get("/api/radios/pedidos").json()["pedidos"], op.get("/api/radios/pedidos").json()["pedidos"]
    conferir("pedido de rádio: o Admin vê os pedidos da empresa, com quem pediu", len(lista_adm) == 2 and all(p["status"] == "aberto"
             and p["por"] == "Operador da EMG" for p in lista_adm) and len(lista_op) == 2)
    atendido = adm.post("/api/radios", json={"nome": "Rádio Pedida (demonstração)", "email": "pedida@example.com",
                                             "alcance": {"municipios": ["3138401"]}, "pedido_id": ped.json()["pedido"]["id"]})
    de_novo = adm.post("/api/radios", json={"nome": "Rádio Pedida 2 (demonstração)", "email": "pedida@example.com",
                                            "alcance": {"municipios": ["3138401"]}, "pedido_id": ped.json()["pedido"]["id"]})
    sem_motivo = adm.post(f"/api/radios/pedidos/{ped4.json()['pedido']['id']}/recusar", json={"motivo": ""})
    recusa = adm.post(f"/api/radios/pedidos/{ped4.json()['pedido']['id']}/recusar", json={"motivo": "A rádio não cobre Tebas."})
    finais = {p["nome"]: p for p in adm.get("/api/radios/pedidos").json()["pedidos"]}
    conferir("pedido de rádio: atender cadastra a rádio e fecha o pedido (uma vez só); recusar exige o motivo",
             atendido.status_code == 200 and de_novo.status_code == 409 and sem_motivo.status_code == 422 and recusa.status_code == 200
             and finais["Rádio Pedida (demonstração)"]["status"] == "atendido" and finais["Rádio Pedida (demonstração)"]["radio_id"] == atendido.json()["radio"]["id"]
             and finais["Rádio Recusada (demonstração)"]["motivo_recusa"] == "A rádio não cobre Tebas.",
             f"{atendido.status_code} {de_novo.status_code} {sem_motivo.status_code} {recusa.status_code}")
    adm.patch(f"/api/radios/{atendido.json()['radio']['id']}", json={"nome": "Rádio Pedida (demonstração)", "email": "pedida@example.com",
                                                                    "alcance": {"municipios": ["3138401"]}, "ativa": False})
    sug = op.get(f"/api/historico/{a['id']}/radios").json()
    sl = next(m for m in sug["municipios"] if m["nome"] == "Leopoldina")
    sj = next(m for m in sug["municipios"] if m["nome"] == "São João Nepomuceno")
    conferir("sugestão: Leopoldina com as duas rádios (a de Tebas só pela Piacatuba de Tebas); São João sem rádio",
             {x["radio_id"] for x in sl["radios"]} == {leo_id, pia_id} and next(x for x in sl["radios"] if x["radio_id"] == pia_id)["comunidades"] == 1
             and not sl["sem_radio"] and not sj["radios"] and len(sj["sem_radio"]) >= 1, json.dumps(sug["municipios"], ensure_ascii=False)[:300])

    # envio por e-mail
    texto = leo["mensagem"]
    ra = op.post(f"/api/historico/{a['id']}/envios", json={"municipio": "3138401", "radio_id": leo_id, "canal": "email", "texto": texto,
                                                           "valor": "150,00", "cobranca": "minuto"})
    env = ra.json().get("envio", {})
    seg_hoje = leo["hoje"]["segundos"]
    esperado = (Decimal(seg_hoje - env.get("segundos", 0)) * 150 / 60).quantize(Decimal("0.01"))
    conferir("e-mail: entregue, com custo e economia calculada pelo tempo no ar (aviso de hoje x Norte)",
             ra.status_code == 200 and env["status"] == "entregue" and env["economia_tipo"] == "calculada"
             and env["economia"] == f"{esperado:.2f}" and env["tempo_economizado"] == seg_hoje - env["segundos"]
             and env["arquivos"] == ["mp3", "pdf"], ra.text[:300])
    msgs = mailpit("/api/v1/messages")["messages"]
    conferir("Mailpit: 1 e-mail para a rádio, assunto com o município e o código", len(msgs) == 1 and msgs[0]["To"][0]["Address"] == "leopoldina.fm@example.com"
             and "Leopoldina/MG" in msgs[0]["Subject"] and a["codigo"] in msgs[0]["Subject"], json.dumps(msgs[:1], ensure_ascii=False)[:300])
    corpo = mailpit(f"/api/v1/message/{msgs[0]['ID']}")
    anexos = {x["ContentType"]: x for x in corpo["Attachments"]}
    conferir("e-mail: PDF e MP3 anexos, o texto e o botão 'Confirmar recebimento'", set(anexos) == {"application/pdf", "audio/mpeg"}
             and texto in corpo["Text"] and "Confirmar recebimento" in corpo["HTML"], str(set(anexos)))
    ucs = [u for u in t["uc"].astype(str)]
    conferir("e-mail: nenhum número de UC nem coordenada", not any(u in corpo["Text"] + corpo["HTML"] for u in ucs)
             and not re.search(r"-21[.,]\d{4}", corpo["Text"] + corpo["HTML"]))
    pdf_anexo = mailpit(f"/api/v1/message/{msgs[0]['ID']}/part/{anexos['application/pdf']['PartID']}")
    conferir("e-mail: o anexo é um PDF", pdf_anexo[:5] == b"%PDF-", str(pdf_anexo[:8]))
    guardados = sql("SELECT tipo, tamanho, cifrado FROM arquivo_envio WHERE envio_id = %s ORDER BY tipo", (env["id"],))
    conferir("cofre: PDF e MP3 guardados cifrados (sem '%PDF' nem o texto no banco)", [g[0] for g in guardados] == ["mp3", "pdf"]
             and all(bytes(g[2]).startswith(b"FAR1") and b"%PDF" not in bytes(g[2]) and texto[:30].encode() not in bytes(g[2]) for g in guardados))
    baixado = con.get(f"/api/envios/{env['id']}/arquivos/pdf")
    conferir("Consulta baixa o PDF enviado (comprovante), igual ao anexo", baixado.status_code == 200 and baixado.content == pdf_anexo)
    link = re.search(r"http://farol\.teste(/confirmar/[A-Za-z0-9_-]+)", corpo["Text"]).group(1)
    pagina = publico.get(link)
    conferir("link: abrir só mostra a página (com o botão), sem confirmar; CSP própria", pagina.status_code == 200
             and "Confirmar recebimento" in pagina.text and "form-action 'self'" in pagina.headers["content-security-policy"]
             and op.get(f"/api/historico/{a['id']}/envios").json()["envios"][0]["status"] == "entregue", pagina.text[:120])
    fora = publico.post(link, headers={"Origin": "https://malicioso.example"})
    conferir("confirmar de outra origem: recusado (403)", fora.status_code == 403)
    conf = publico.post(link)
    st = op.get(f"/api/historico/{a['id']}/envios").json()["envios"][0]
    reg = sql("SELECT usuario_nome, detalhe FROM registro WHERE acao = 'rádio confirmou o recebimento'")
    conferir("confirmar (POST): 200, envio 'confirmado' com a hora, auditoria sem usuário (foi a rádio)",
             conf.status_code == 200 and "Recebimento confirmado" in conf.text and st["status"] == "confirmado" and st["confirmado_em"]
             and reg and reg[0][0] is None and "Rádio Leopoldina FM" in reg[0][1], f"{conf.status_code} {reg}")
    conferir("o link só vale uma vez (410)", publico.post(link).status_code == 410)
    conferir("token inexistente: 404 na página, 410 ao confirmar", publico.get("/confirmar/" + "a" * 43).status_code == 404
             and publico.post("/confirmar/" + "a" * 43).status_code == 410)

    # link vencido
    rb = op.post(f"/api/historico/{a['id']}/envios", json={"municipio": "3138401", "radio_id": pia_id, "canal": "email", "texto": texto,
                                                           "valor": "350", "cobranca": "fechado", "custo_antigo": "800"})
    envb = rb.json()["envio"]
    conferir("valor fechado com custo antigo informado: economia informada (800 - 350)", envb["economia"] == "450.00"
             and envb["economia_tipo"] == "informada", json.dumps(envb)[:200])
    msg2 = next(m for m in mailpit("/api/v1/messages")["messages"] if m["To"][0]["Address"] == "tebas@example.com")
    link2 = re.search(r"(/confirmar/[A-Za-z0-9_-]+)", mailpit(f"/api/v1/message/{msg2['ID']}")["Text"]).group(1)
    sql("UPDATE envio SET token_expira = now() - interval '1 minute' WHERE id = %s", (envb["id"],))
    conferir("link vencido (mais de 7 dias): 410 e nada confirmado", publico.get(link2).status_code == 410
             and publico.post(link2).status_code == 410 and sql("SELECT status FROM envio WHERE id = %s", (envb["id"],))[0][0] == "entregue")

    # WhatsApp e cópia
    rw = op.post(f"/api/historico/{a['id']}/envios", json={"municipio": "3138401", "radio_id": leo_id, "canal": "whatsapp", "texto": texto,
                                                           "valor": "150", "cobranca": "minuto"})
    conferir("WhatsApp: link wa.me com o número (55 + DDD) e o texto; auditoria", rw.status_code == 200
             and rw.json()["whatsapp_url"].startswith("https://wa.me/5532999990001?text=Aten%C3%A7%C3%A3o")
             and sql("SELECT 1 FROM registro WHERE acao = 'enviou por WhatsApp'"), rw.text[:200])
    rc = op.post(f"/api/historico/{a['id']}/envios", json={"municipio": "3138401", "radio_id": pia_id, "canal": "copia", "texto": texto,
                                                           "valor": "350", "cobranca": "fechado"})
    conferir("copiar: envio registrado, sem economia (sem custo antigo)", rc.status_code == 200 and rc.json()["envio"]["economia"] is None
             and sql("SELECT 1 FROM registro WHERE acao = 'copiou a mensagem para a rádio'"))

    # valor gravado no envio e sugestão pelo último usado
    adm.patch(f"/api/radios/{leo_id}", json={"nome": "Rádio Leopoldina FM (demonstração)", "email": "leopoldina.fm@example.com",
                                             "whatsapp": "32999990001", "alcance": {"municipios": ["3138401"]}, "valor_padrao": "999",
                                             "cobranca": "minuto"})
    envs = op.get(f"/api/historico/{a['id']}/envios").json()["envios"]
    sug2 = next(r for r in op.get("/api/radios").json()["radios"] if r["id"] == leo_id)
    conferir("mudar o preço da rádio não muda o passado; a sugestão é o último valor usado", envs[0]["valor"] == "150.00"
             and sug2["valor_padrao"] == "999.00" and sug2["valor_sugerido"] == "150.00", json.dumps(sug2)[:200])

    # textos e situações recusadas
    base_envio = {"municipio": "3138401", "radio_id": leo_id, "canal": "copia", "valor": "1", "cobranca": "fechado"}
    for nome, txt in [("número de UC", texto + " UC 3000029045."), ("e-mail", texto + " fulano@example.com"),
                      ("site", texto + " www.exemplo.com"), ("vazio", "   ")]:
        conferir(f"texto recusado: {nome} (422)", op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "texto": txt}).status_code == 422)
    conferir("valor inválido ou ausente: 422", op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "texto": texto, "valor": "-1"}).status_code == 422
             and op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "texto": texto, "valor": ""}).status_code == 422)
    conferir("Consulta não envia (403) mas vê os envios", con.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "texto": texto}).status_code == 403
             and len(con.get(f"/api/historico/{a['id']}/envios").json()["envios"]) == 4)
    # adulteração no cofre
    # inverte os bits de um byte (trocar por 0x00 falhava 1 vez em 256: quando o byte já era zero, nada mudava)
    sql("UPDATE arquivo_envio SET cifrado = set_byte(cifrado, 39, 255 - get_byte(cifrado, 39)) WHERE envio_id = %s AND tipo = 'pdf'", (env["id"],))
    adult = con.get(f"/api/envios/{env['id']}/arquivos/pdf")
    conferir("arquivo alterado no banco: 409 'não confere', nada entregue, na auditoria", adult.status_code == 409
             and sql("SELECT 1 FROM registro WHERE acao = 'arquivo enviado não confere (cofre)'"), adult.text[:120])

    # limite, falha e e-mail desligado
    radio_mod._emails.clear()
    radio_mod.LIMITE_EMAILS = 1
    um = op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "canal": "email", "texto": texto, "valor": "2"})
    dois = op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "canal": "email", "texto": texto, "valor": "3"})
    radio_mod.LIMITE_EMAILS = 30
    radio_mod._emails.clear()
    conferir("limite de e-mails por hora: depois, 429", um.status_code == 200 and dois.status_code == 429, f"{um.status_code} {dois.status_code}")
    os.environ["FAROL_SMTP_PORTA"] = "1"     # porta fechada: o servidor de e-mail não responde
    falha = op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "canal": "email", "texto": texto, "valor": "4"})
    # logo depois de uma falha, o mesmo envio pode ser tentado de novo (não é duplicata); o repetido de um enviado é (409)
    os.environ["FAROL_SMTP_PORTA"] = "1"
    falha2 = op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "canal": "email", "texto": texto, "valor": "4"})
    os.environ["FAROL_SMTP_PORTA"] = str(SMTP)
    repetido = op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "canal": "email", "texto": texto, "valor": "2"})
    conferir("envio repetido em menos de um minuto: 409 (clique duplo); depois de uma falha, pode tentar de novo",
             falha2.status_code == 200 and repetido.status_code == 409, f"{falha2.status_code} {repetido.status_code}")
    os.environ["FAROL_SMTP_PORTA"] = str(SMTP)
    conferir("servidor de e-mail fora do ar: envio 'falhou', com aviso e auditoria", falha.status_code == 200
             and falha.json()["envio"]["status"] == "falhou" and "não foi entregue" in falha.json().get("erro", "")
             and sql("SELECT 1 FROM registro WHERE acao = 'envio por e-mail falhou'"), falha.text[:200])
    os.environ["FAROL_EMAIL"] = "0"
    deslig = op.post(f"/api/historico/{a['id']}/envios", json={**base_envio, "canal": "email", "texto": texto, "valor": "5"})
    conferir("e-mail desligado (FAROL_EMAIL=0 ou sem SMTP): 503 e a configuração diz", deslig.status_code == 503
             and op.get("/api/config").json()["email"] is False, deslig.text[:120])
    del os.environ["FAROL_EMAIL"]

    # aviso cancelado e outra empresa
    op.post(f"/api/historico/{a2['id']}/cancelar", json={"motivo": "teste de cancelamento"})
    conferir("aviso cancelado: nada é enviado (409)", op.post(f"/api/historico/{a2['id']}/envios", json={**base_envio, "texto": texto}).status_code == 409)
    far = pronto("admin@farol.example")
    r = far.post("/api/empresas", json={"nome": "Outra", "sigla": "OUT", "dominio": "out.example", "admin_nome": "Admin Outra",
                                        "admin_email": "admin@out.example"})
    outra = pronto("admin@out.example", r.json()["senha_temporaria"])
    conferir("outra empresa: não vê envios, arquivos, rádios nem sugestão da EMG",
             outra.get(f"/api/historico/{a['id']}/envios").status_code == 404 and outra.get(f"/api/envios/{env['id']}/arquivos/mp3").status_code == 404
             and outra.get("/api/radios").json()["radios"] == [] and outra.get(f"/api/historico/{a['id']}/radios").status_code == 404
             and outra.patch(f"/api/radios/{leo_id}", json={"nome": "Invasão", "email": "x@example.com"}).status_code == 404)
    conferir("auditoria íntegra depois de tudo", adm.get("/api/auditoria/verificar").json()["ok"] is True)
finally:
    caixa.terminate()
    caixa.wait(timeout=10)
    with conectar() as cx:
        cx.execute("DROP SCHEMA IF EXISTS teste_radio CASCADE")

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
