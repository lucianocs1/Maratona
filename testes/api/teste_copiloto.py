"""Teste do copiloto do aviso: verificador, provedor simulado e rota (FastAPI em processo, Postgres local).

Roda num esquema próprio (FAROL_ESQUEMA=teste_copiloto), apagado no fim. Confere:
- o verificador: aprova texto fiel e recusa comunidade omitida, município omitido, data/horário/telefone
  perdidos, número inventado (UC, coordenada, "milhares de clientes"), e-mail, link, nome inventado e
  texto acima do limite;
- o provedor simulado: os 4 pedidos produzem textos que o verificador aprova, o pedido livre entende
  palavras-chave e recusa o que não entende, e a chave nunca é exigida;
- a rota: quem pode (Operador e Admin da empresa sim; Consulta e Admin do Farol não; sem login, 401),
  o isolamento entre empresas, os erros (422/404/503), a recusa quando o provedor erra, e o registro
  de atividade só com o resultado (nunca o texto).

Uso (na raiz): uv run python -W ignore testes/api/teste_copiloto.py
"""

import os
import sys

os.environ["FAROL_ESQUEMA"] = "teste_copiloto"
os.environ["FAROL_IA"] = "simulado"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.apresentacao import copiloto  # noqa: E402
from comunidades.banco import acesso as banco_acesso  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo.verificador import verificar  # noqa: E402
from comunidades.semente import semear  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


AVISO = ("Atenção, moradores de Graminha, Boa Sorte e Piacatuba, e de parte de Tomé Nogueira, além de localidades "
         "vizinhas, em Leopoldina (distritos Piacatuba e Sede): no dia 20/11, das 8h às 14h, haverá desligamento "
         "programado de energia para manutenção na rede. Programe-se! Dúvidas: (32) 3333-4444.")
COMUNIDADES = ["Graminha", "Boa Sorte", "Piacatuba", "Tomé Nogueira", "Sítio Esquecido"]  # a última não é citada no aviso
MUN = "Leopoldina"


def v(texto, **kw):
    return verificar(AVISO, texto, COMUNIDADES, MUN, **kw)


# ---------- 1. Verificador ----------
fiel = ("Atenção, moradores de Graminha, Boa Sorte, Piacatuba e Tomé Nogueira, em Leopoldina: dia 20/11, das 8h às 14h, "
        "desligamento programado. Dúvidas: (32) 3333-4444.")
conferir("verificador: aprova o texto fiel (mesmo sem a comunidade que o original não cita)", v(fiel).ok, str(v(fiel).motivos))
maus = {
    "comunidade omitida": (fiel.replace("Boa Sorte, ", ""), "Boa Sorte"),
    "município omitido": (fiel.replace(", em Leopoldina", ""), "município"),
    "data perdida": (fiel.replace("20/11", "em breve"), "20"),
    "horário perdido": (fiel.replace("das 8h às 14h", "de manhã"), "14"),
    "telefone perdido": (fiel.replace(" Dúvidas: (32) 3333-4444.", ""), "3333"),
    "número inventado": (fiel + " Afetará 3500 clientes.", "3500"),
    "número de UC": (fiel + " UC 1234567.", "1234567"),
    "coordenada": (fiel + " Ponto -21.13,-42.37.", "21"),
    "e-mail": (fiel + " Escreva para fulano@exemplo.com.", "e-mail"),
    "link": (fiel + " Veja https://exemplo.com/aviso", "link"),
    "comunidade inventada": (fiel.replace("Piacatuba e", "Piacatuba, Fazenda Nova e"), "Fazenda"),
    "nome de pessoa": (fiel + " Falar com o Sr. Joaquim Silva.", "Joaquim"),
    "vazio": ("   ", "vazio"),
}
for nome, (texto, pista) in maus.items():
    r = v(texto)
    conferir(f"verificador: recusa {nome}", not r.ok and any(pista in m for m in r.motivos), str(r.motivos))
r = v(fiel, max_caracteres=40)
conferir("verificador: recusa texto acima do limite do canal", not r.ok and "limite" in r.motivos[0], str(r.motivos))
conferir("verificador: nome permitido (a distribuidora) não é recusado", verificar(AVISO, fiel + " Atenciosamente, Energisa.", COMUNIDADES, MUN,
         permitidas={"Energisa"}).ok)
conferir("verificador: maiúscula depois de ponto é só início de frase",
         v(fiel + " Obrigado pela compreensão.").ok)

# ---------- 2. Provedor simulado ----------
for pedido in copiloto.PEDIDOS:
    texto = copiloto.reescrever(AVISO, pedido)
    _, limite = copiloto.instrucao(pedido)
    r = v(texto, max_caracteres=limite or 3000)
    conferir(f"simulado: pedido {pedido} sai aprovado pelo verificador", r.ok and texto != AVISO, f"{texto!r} {r.motivos}")
conferir("simulado: o curto é mesmo mais curto", len(copiloto.reescrever(AVISO, "curto")) < len(AVISO))
conferir("simulado: pedido livre entende palavras-chave", copiloto.reescrever(AVISO, "livre", "faça uma mensagem para o whatsapp").startswith("Desligamento"))
try:
    copiloto.reescrever(AVISO, "livre", "traduza para o japonês")
    conferir("simulado: pedido livre que não entende é recusado com mensagem", False)
except copiloto.CopilotoIndisponivel as e:
    conferir("simulado: pedido livre que não entende é recusado com mensagem", "entende" in str(e), str(e))
try:
    copiloto.reescrever("texto qualquer fora do modelo", "curto")
    conferir("simulado: texto fora do modelo padrão é recusado com mensagem", False)
except copiloto.CopilotoIndisponivel as e:
    conferir("simulado: texto fora do modelo padrão é recusado com mensagem", "Desfazer" in str(e), str(e))
erros_instr = []
for ped, livre in (("inexistente", ""), ("livre", ""), ("livre", "x" * 300)):
    try:
        copiloto.instrucao(ped, livre)
        erros_instr.append((ped, len(livre)))
    except ValueError:
        pass
conferir("pedido: desconhecido, livre vazio e livre longo demais viram ValueError", not erros_instr, str(erros_instr))

# ---------- 3. Rota ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_copiloto CASCADE")
senhas = {email: s for _, email, s in semear()}
NOVA = "Lanterna-do-Farol-2026"


def cliente(email=None) -> TestClient:
    api_acesso._tentativas_ip.clear()
    cli = TestClient(app, base_url="http://farol.teste")
    if email:
        cli.post("/api/entrar", json={"email": email, "senha": senhas[email]})
        cli.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
    return cli


op = cliente("operador@emg.example")
dono = banco_acesso.usuario_por_email("operador@emg.example")
municipio = {"codigo_ibge": "3138401", "nome": MUN, "uf": "MG", "ucs": 120, "segundos": 20, "aviso": AVISO,
             "equipamento_vital": {"sim": 0, "nao": 120, "a_confirmar": 0}, "hoje": None,
             "comunidades": [{"nome": n, "distrito": "Sede", "afetadas": 10, "total": 20, "parcial": False,
                              "fragmento": False, "confianca": 0.9} for n in COMUNIDADES]}
id_ = banco_acesso.gravar_aviso(dono["empresa_id"], dono["id"], "20/11", "8h às 14h", "pt-BR",
                                {"linhas": 120, "validas": 120, "problemas": 0, "fora_da_concessao": 0, "prazo": {}}, [municipio], "manutencao_preventiva", "Manutenção preventiva", lambda i: f"aviso {i}")["id"]
rota = f"/api/historico/{id_}/municipios/3138401/reescrever"
pedido = {"texto": AVISO, "pedido": "whatsapp"}

conferir("config: a IA aparece como simulada", op.get("/api/config").json()["ia"]["provedor"] == "simulado"
         and set(op.get("/api/config").json()["ia"]["pedidos"]) == set(copiloto.PEDIDOS))
conferir("sem login: 401", cliente().post(rota, json=pedido).status_code == 401)
r = op.post(rota, json=pedido).json()
conferir("Operador: texto reescrito e verificado", r["verificado"] and r["texto"].startswith("Desligamento") and "*" not in r["texto"] and r["provedor"] == "simulado" and not r["motivos"], str(r))
conferir("Admin da empresa: pode", cliente("admin@emg.example").post(rota, json=pedido).status_code == 200)
conferir("Consulta: não pode (403)", cliente("consulta@emg.example").post(rota, json=pedido).status_code == 403)
conferir("Admin do Farol: não pode (403)", cliente("admin@farol.example").post(rota, json=pedido).status_code == 403)

# o texto da caixa pode ter sido editado; a conferência é sempre contra o aviso original do banco
editado = AVISO.replace("Boa Sorte e ", "")
r = op.post(rota, json={"texto": editado, "pedido": "curto"}).json()
conferir("texto editado sem uma comunidade: recusado, o texto atual é mantido", not r["verificado"] and r["texto"] == editado
         and any("Boa Sorte" in m for m in r["motivos"]), str(r))

# o provedor erra: o servidor descarta o texto e mantém o atual
original = copiloto._simulado
copiloto._simulado = lambda texto, pedido, livre: texto.replace("20/11", "21/11") + " Afetará 5000 UCs."
r = op.post(rota, json={"texto": AVISO, "pedido": "acolhedor"}).json()
copiloto._simulado = original
conferir("provedor que inventa dado: recusado e texto original devolvido", not r["verificado"] and r["texto"] == AVISO
         and "5000" in " ".join(r["motivos"]) and "21" in " ".join(r["motivos"]), str(r))

erros = {"pedido inexistente": op.post(rota, json={**pedido, "pedido": "xyz"}).status_code,
         "livre vazio": op.post(rota, json={**pedido, "pedido": "livre"}).status_code,
         "texto vazio": op.post(rota, json={**pedido, "texto": "  "}).status_code,
         "texto longo": op.post(rota, json={**pedido, "texto": "a " * 2000}).status_code}
conferir("erros: pedido inexistente, livre vazio, texto vazio e longo (422)", all(c == 422 for c in erros.values()), str(erros))
conferir("aviso inexistente: 404", op.post("/api/historico/999999/municipios/3138401/reescrever", json=pedido).status_code == 404)
conferir("município fora do aviso: 404", op.post(f"/api/historico/{id_}/municipios/0000000/reescrever", json=pedido).status_code == 404)
conferir("provedor sem entender o texto: 503 com a mensagem", op.post(rota, json={"texto": "qualquer coisa", "pedido": "curto"}).status_code == 503)

# outra empresa não alcança o aviso desta
conferir("isolamento: aviso de outra empresa não é encontrado", banco_acesso.aviso(id_, dono["empresa_id"] + 1000) is None)

# desligado
copiloto.PROVEDOR = "0"
conferir("FAROL_IA=0: a rota responde 503 e a configuração avisa a tela",
         op.post(rota, json=pedido).status_code == 503 and op.get("/api/config").json()["ia"]["ativa"] is False)
copiloto.PROVEDOR = "simulado"

# registro de atividade: só o resultado
with conectar() as c, c.cursor() as cur:
    cur.execute("SELECT detalhe FROM registro WHERE acao = 'reescreveu o aviso com IA'")
    reg = [d for (d,) in cur.fetchall()]
conferir("registro: guarda pedido e resultado, nunca o texto", len(reg) >= 4 and all("Graminha" not in d and "20/11" not in d for d in reg)
         and any("recusado" in d for d in reg) and any("aprovado" in d for d in reg), str(reg))

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_copiloto CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
