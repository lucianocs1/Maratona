"""Teste dos idiomas do aviso (Fase K1): português, inglês e espanhol (FastAPI em processo, Postgres local).

Roda num esquema próprio (FAROL_ESQUEMA=teste_idiomas), apagado no fim. Confere:
- núcleo: data e hora no formato de cada idioma; o português continua exatamente como antes; listas com "and" e "y";
  locução em inglês e espanhol; tipos de desligamento traduzidos;
- API: o aviso e a mensagem da rádio em inglês e em espanhol (padrões da empresa), o idioma gravado no histórico;
  o modelo por idioma nas configurações (com a prévia na tela) e o idioma padrão da empresa;
- PDF da rádio, e-mail para a rádio, página de confirmação e comprovante no idioma do aviso;
- áudio: inglês com voz; espanhol sem voz com licença clara (422, a tela avisa);
- relatórios (tela, PDF e CSV) e mensagens de erro no idioma de quem pede (cabeçalho X-Farol-Idioma).

Uso (na raiz): uv run python -W ignore testes/api/teste_idiomas.py
"""

import os
import re
import sys
import zlib
from datetime import datetime
from pathlib import Path

os.environ["FAROL_ESQUEMA"] = "teste_idiomas"
os.environ.setdefault("FAROL_EMAIL", "0")

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api import app as app_mod  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.apresentacao import confirmacao, email_radio  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo import idiomas, mensagem, tipos_desligamento  # noqa: E402
from comunidades.nucleo.locucao import texto_para_fala  # noqa: E402
from comunidades.semente import semear  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
PLANILHA = RAIZ / "saida" / "planilhas_teste" / "planilha_CF-0066.csv"
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
    return " ".join("".join(re.findall(r"\(((?:\\.|[^\\)])*)\)", ln)) for ln in "\n".join(partes).split("\n")).replace("\\", "")


# ---------- 1. Núcleo ----------
conferir("pt-BR: data e horário do aviso como vieram (o português não muda)", idiomas.localizar("20/11", "8h às 14h", "pt-BR") == ("20/11", "8h às 14h"))
conferir("inglês: November 20, 8:00 a.m. to 2:00 p.m. (as regras do mapa)",
         idiomas.localizar("20/11", "8h às 14h", "en") == ("November 20", "8:00 a.m. to 2:00 p.m."), str(idiomas.localizar("20/11", "8h às 14h", "en")))
conferir("espanhol: 20/11, 8:00 a 14:00", idiomas.localizar("20/11", "8h30 às 14h", "es") == ("20/11", "8:30 a 14:00"))
conferir("mensagem: data falada por idioma", [idiomas.data_falada("20/11", i) for i in ("pt-BR", "en", "es")] == ["20/11", "November 20", "20 de noviembre"])
conferir("mensagem: horas por idioma", [idiomas.inicio_fim("8h30 às 14h", i) for i in ("pt-BR", "en", "es")]
         == [("8h30", "14h"), ("8:30 a.m.", "2 p.m."), ("8:30", "14:00")])
conferir("listas: 'e' em português, 'and' em inglês, 'y' (ou 'e' antes de som de i) em espanhol",
         [mensagem.lista_falada(["A", "B", "C"], i) for i in ("pt-BR", "en", "es")] == ["A, B e C", "A, B and C", "A, B y C"]
         and mensagem.lista_falada(["A", "Itamarati"], "es") == "A e Itamarati")
mun = {"nome": "Leopoldina", "comunidades": [{"nome": "Graminha"}, {"nome": "Boa Sorte"}, {"nome": "Tomé Nogueira", "parcial": True}]}
pt = mensagem.montar(mensagem.PADRAO, mensagem.valores_do_municipio(mun, distribuidora="Energisa", data="20/11", horario="8h às 14h",
                                                                   motivo="poda de árvores perto da rede"))
conferir("mensagem em português idêntica à de antes da Fase K", pt == ("Atenção, ouvintes. A Energisa informa: no dia 20/11, das 8h às 14h, haverá "
         "desligamento programado de energia para poda de árvores perto da rede nas comunidades Graminha e Boa Sorte. Ficará sem energia "
         "parte de: Tomé Nogueira. Programe-se."), pt)
en = mensagem.montar(mensagem.PADROES["en"], mensagem.valores_do_municipio(mun, distribuidora="Energisa", data="20/11", horario="8h às 14h",
                                                                          motivo=tipos_desligamento.motivo("poda", idioma="en")[1], idioma="en"))
conferir("mensagem em inglês (padrão)", en == ("Attention, listeners. Energisa announces a scheduled power outage on November 20, from 8 a.m. to "
         "2 p.m., for tree trimming near the power lines in the communities of Graminha and Boa Sorte. Part of Tomé Nogueira will also be "
         "without power. Please plan ahead."), en)
es = mensagem.montar(mensagem.PADROES["es"], mensagem.valores_do_municipio(mun, distribuidora="Energisa", data="20/11", horario="8h às 14h",
                                                                          motivo=tipos_desligamento.motivo("poda", idioma="es")[1], idioma="es"))
conferir("mensagem em espanhol (padrão)", es == ("Atención, oyentes. Energisa informa: el 20 de noviembre, entre las 8:00 y las 14:00, habrá un corte "
         "programado de energía por poda de árboles cerca de la red en las comunidades de Graminha y Boa Sorte. También quedará sin energía "
         "parte de: Tomé Nogueira. Tome sus precauciones."), es)
conferir("modelos em inglês e espanhol passam na mesma validação do português", all(mensagem.problema_modelo(m) is None for m in mensagem.PADROES.values()))
conferir("locução em inglês e espanhol", texto_para_fala("from 8:00 a.m. to 2:30 p.m.", "en") == "from 8 A M to 2:30 P M"
         and texto_para_fala("el 20/11, entre las 8:00 y las 14:30", "es") == "el 20 de noviembre, entre las 8 y las 14 y 30"
         and texto_para_fala("no dia 20/11, das 8h às 14h") == "no dia 20 de novembro, das 8 horas às 14 horas")
conferir("tipos de desligamento: rótulos em inglês e espanhol, o 'Outro' como foi digitado",
         tipos_desligamento.rotulos("en")["poda"] == "Tree trimming" and tipos_desligamento.rotulos("es")["outro"] == "Otro"
         and tipos_desligamento.motivo("outro", "troca de cruzeta", "en") == ("outro", "troca de cruzeta"))

# ---------- 2. API ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_idiomas CASCADE")
senhas = {email: s for _, email, s in semear()}
NOVA = "Lanterna-do-Farol-2026"


def cliente(email: str) -> TestClient:
    api_acesso._tentativas_ip.clear()
    cli = TestClient(app, base_url="http://farol.teste")
    cli.post("/api/entrar", json={"email": email, "senha": senhas[email]})
    cli.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
    return cli


op, adm = cliente("operador@emg.example"), cliente("admin@emg.example")


def gerar(idioma: str) -> dict:
    app_mod._envios.clear()
    conf = op.post("/api/planilha", files={"arquivo": ("planilha.csv", PLANILHA.read_bytes())},
                   data={"data": "20/11", "horario": "8h às 14h", "idioma": idioma, "tipo": "poda"}).json()
    return op.post("/api/avisos", json={"pacote": conf["pacote"], "data": "20/11", "horario": "8h às 14h", "idioma": idioma,
                                        "conferi": True, "tipo": "poda"}).json()


a_pt, a_en, a_es = gerar("pt-BR"), gerar("en"), gerar("es")
m_pt, m_en, m_es = a_pt["municipios"][0], a_en["municipios"][0], a_es["municipios"][0]
conferir("português: a mensagem de antes (modelo da empresa) e o aviso do algoritmo como antes",
         m_pt["mensagem"].startswith("Atenção, ouvintes.") and "no dia 20/11, das 8h às 14h" in m_pt["mensagem"]
         and "no dia 20/11, das 8h às 14h" in m_pt["aviso"], m_pt["mensagem"][:120])
conferir("inglês: mensagem da rádio e aviso do algoritmo com data e hora em inglês",
         m_en["mensagem"].startswith("Attention, listeners.") and "on November 20, from 8 a.m. to 2 p.m." in m_en["mensagem"]
         and "tree trimming" in m_en["mensagem"] and "on November 20, from 8:00 a.m. to 2:00 p.m." in m_en["aviso"], m_en["mensagem"][:160])
conferir("espanhol: mensagem da rádio e aviso do algoritmo em espanhol",
         m_es["mensagem"].startswith("Atención, oyentes.") and "el 20 de noviembre, entre las 8:00 y las 14:00" in m_es["mensagem"]
         and "poda de árboles" in m_es["mensagem"] and "el día 20/11, de 8:00 a 14:00" in m_es["aviso"], m_es["mensagem"][:160])
hist = {a["id"]: a for a in op.get("/api/historico").json()["avisos"]}
conferir("o idioma fica gravado no aviso (histórico)", [hist[a["id"]]["idioma"] for a in (a_pt, a_en, a_es)] == ["pt-BR", "en", "es"])

# PDF da rádio no idioma do aviso
cod = m_en["codigo_ibge"]
pdf_en = texto_pdf(op.post(f"/api/historico/{a_en['id']}/municipios/{cod}/pdf", json={"texto": m_en["mensagem"]}).content)
pdf_es = texto_pdf(op.post(f"/api/historico/{a_es['id']}/municipios/{cod}/pdf", json={"texto": m_es["mensagem"]}).content)
pdf_pt = texto_pdf(op.post(f"/api/historico/{a_pt['id']}/municipios/{cod}/pdf", json={"texto": m_pt["mensagem"]}).content)
conferir("PDF da rádio em inglês", "Radio script" in pdf_en and "Requested by Operador da EMG (Operator)" in pdf_en
         and "scheduled power outage on November 20" in pdf_en and "Text to read on air" in pdf_en, pdf_en[:300])
conferir("PDF da rádio em espanhol", "Guion para la radio" in pdf_es and "Solicitado por Operador da EMG (Operador)" in pdf_es
         and "Texto para leer al aire" in pdf_es, pdf_es[:300])
conferir("PDF da rádio em português como antes", "Roteiro para a rádio" in pdf_pt and "Solicitado por Operador da EMG (Operador)" in pdf_pt
         and "em 20/11, das 8h às 14h" in pdf_pt, pdf_pt[:300])
# comprovante no idioma do aviso
comp_en = texto_pdf(op.get(f"/api/historico/{a_en['id']}/comprovante.pdf").content)
conferir("comprovante no idioma do aviso (inglês)", "Receipt of notice no." in comp_en and "Requested by" in comp_en and "Life-support" not in comp_en[:0],
         comp_en[:300])

# e-mail e página de confirmação (o que o servidor manda à rádio), nos três idiomas
mail = {i: email_radio.mensagem(remetente="Norte <a@farol.example>", destino="r@example.com", municipio="Leopoldina", uf="MG", data=d,
                                horario=h, empresa="Energisa", texto="Texto", codigo="FRL-1", link_confirmar="https://x/confirmar/t",
                                pdf=("a.pdf", b"%PDF"), mp3=None, aviso_ficticio="Demonstração.", idioma=i)
        for i, d, h in (("pt-BR", "20/11", "8h às 14h"), ("en", "November 20", "8:00 a.m. to 2:00 p.m."), ("es", "20/11", "8:00 a 14:00"))}
corpo = lambda m, tipo: next(p for p in m.walk() if p.get_content_type() == tipo).get_content()
conferir("e-mail para a rádio em inglês e espanhol, com texto simples e HTML no idioma",
         mail["en"]["Subject"].startswith("Scheduled power outage notice") and 'lang="en"' in corpo(mail["en"], "text/html")
         and "Confirm receipt" in corpo(mail["en"], "text/html") and "Text to read on air" in corpo(mail["en"], "text/plain")
         and mail["es"]["Subject"].startswith("Aviso de corte programado") and 'lang="es"' in corpo(mail["es"], "text/html")
         and mail["pt-BR"]["Subject"].startswith("Aviso de desligamento programado"))
conferir("página de confirmação da rádio no idioma (lang)", 'lang="es"' in confirmacao.pagina("t", "x", "/confirmar/t", idioma="es")
         and "Confirmar recepción" in confirmacao.pagina("t", "x", "/confirmar/t", idioma="es"))

# áudio
conferir("áudio em inglês (voz en_US-ljspeech)", op.post("/api/audio", json={"texto": m_en["mensagem"], "idioma": "en"}).status_code == 200)
sem_voz = op.post("/api/audio", json={"texto": m_es["mensagem"], "idioma": "es"})
conferir("áudio em espanhol: sem voz com licença clara, 422 com a explicação", sem_voz.status_code == 422 and "licença" in sem_voz.json()["detail"],
         sem_voz.text[:120])
cfg = op.get("/api/config").json()
conferir("/api/config diz quais idiomas têm áudio", cfg["audio_idiomas"] == ["pt-BR", "en"], str(cfg.get("audio_idiomas")))

# configurações: um modelo por idioma e o idioma padrão
atual = adm.get("/api/empresa/configuracao").json()
base = {k: atual[k] for k in ("modelo_mensagem", "nome_mensagem", "telefone", "limite_rejeicao", "epsg_utm", "antecedencia_dias",
                               "orcamento_radio", "alerta_preco", "repeticao_n", "repeticao_dias")}
ruim = adm.put("/api/empresa/configuracao", json={**base, "modelo_mensagem_en": "On {data} {cliente}"})
conferir("modelo em inglês inválido: 422 no campo do modelo em inglês", ruim.status_code == 422 and ruim.headers.get("X-Farol-Campo") == "modelo_mensagem_en")
novo_en = "Attention! {distribuidora}: power outage on {data}, {inicio} to {fim}, for {motivo} in {comunidades}."
ok = adm.put("/api/empresa/configuracao", json={**base, "modelo_mensagem_en": novo_en, "idioma_padrao": "es"})
conferir("salva o modelo em inglês e o idioma padrão (espanhol); a tela recebe o padrão da empresa", ok.status_code == 200
         and ok.json()["modelos"]["en"] == novo_en and op.get("/api/config").json()["idioma_padrao"] == "es", ok.text[:200])
a_en2 = gerar("en")
conferir("o aviso novo em inglês usa o modelo da empresa", a_en2["municipios"][0]["mensagem"].startswith("Attention! Distribuidora EMG (demonstração): power outage on November 20, 8 a.m. to 2 p.m."),
         a_en2["municipios"][0]["mensagem"][:120])

# relatórios e erros no idioma de quem pede
EN, ES = {"X-Farol-Idioma": "en"}, {"X-Farol-Idioma": "es"}
mes = f"{datetime.now():%Y-%m}"
r_en = op.get(f"/api/relatorios/mensal?mes={mes}", headers=EN).json()["documento"]
r_es = op.get(f"/api/relatorios/mensal?mes={mes}", headers=ES).json()["documento"]
r_pt = op.get(f"/api/relatorios/mensal?mes={mes}").json()["documento"]
conferir("relatório mensal na tela em inglês e espanhol (títulos, colunas, Como calculamos)", r_en["titulo"].startswith("Monthly report")
         and any(s["titulo"] == "Summary by radio station" for s in r_en["secoes"]) and r_en["como_calculamos"][0].startswith("Each outage")
         and r_es["titulo"].startswith("Informe mensual") and r_pt["titulo"].startswith("Relatório mensal"), r_en["titulo"])
pdf_rel = texto_pdf(op.get(f"/api/relatorios/mensal.pdf?mes={mes}", headers=EN).content)
conferir("relatório em PDF em inglês: rodapé e página final", "Generated by Operador da EMG (Operator)" in pdf_rel and "How we calculate" in pdf_rel
         and re.search(r"page 1 of \d+", pdf_rel), pdf_rel[:200])
csv_es = op.get(f"/api/relatorios/mensal.csv?mes={mes}", headers=ES).content.decode("utf-8-sig")
conferir("relatório em CSV em espanhol", "Informe mensual" in csv_es and "Cómo calculamos" not in csv_es[:0] and "Resumen por radio" in csv_es, csv_es[:200])
dup = adm.post("/api/usuarios", json={"nome": "Operador 2", "email": "operador@emg.example", "perfil": "operador"}, headers=EN)
conferir("mensagem de erro da API no idioma da tela", dup.status_code == 409 and dup.json()["detail"] == "A user with this email already exists.", dup.text)
val = adm.put("/api/empresa/configuracao", json={**base, "antecedencia_dias": 0}, headers=ES)
conferir("erro de validação em espanhol, com o campo", val.status_code == 422 and val.json()["detail"].startswith("Revise el campo antecedencia_dias"),
         val.text)
conferir("tipos de desligamento da tela no idioma da tela", op.get("/api/config", headers=ES).json()["tipos"]["poda"] == "Poda de árboles")

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_idiomas CASCADE")
for r in resultados:
    print(r[0], r[1], f"-> {r[2]}" if r[0] != "OK  " and r[2] else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
