"""Matriz de permissões: CADA rota da API x CADA perfil (FastAPI em processo, Postgres local).

- Percorre todas as rotas /api do app (inclusive as do router de acesso); rota nova sem linha em
  MATRIZ é falha: quem cria a rota tem de dizer quem pode.
- Para cada rota: sem login, 401 (menos as públicas); cada perfil que não pode, 403; cada perfil que
  pode, passa da permissão (qualquer resposta que não seja 401 nem 403; o corpo vazio costuma dar 422).
- Isolamento: o admin de outra empresa não consegue nada (2xx) nas rotas com o número de um aviso
  ou de um usuário da EMG.
A matriz segue docs/PLANO_FINAL.md (MATRIZ DE PERFIS).

Uso (na raiz): uv run python -W ignore testes/api/teste_matriz.py
"""

import os
import re
import sys

os.environ["FAROL_ESQUEMA"] = "teste_matriz"

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api import app as app_mod  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.simulacao import planilhas_teste  # noqa: E402

PUBLICA = "pública"
FAROL, ADM, OP, CON = "admin_farol", "admin_empresa", "operador", "consulta"
TODOS, EMPRESA, GERA = {FAROL, ADM, OP, CON}, {ADM, OP, CON}, {ADM, OP}
MATRIZ = {
    ("GET", "/"): PUBLICA, ("GET", "/api/saude"): PUBLICA, ("POST", "/api/entrar"): PUBLICA, ("POST", "/api/sair"): PUBLICA,
    ("GET", "/api/eu"): TODOS, ("POST", "/api/senha"): TODOS, ("PUT", "/api/eu/preferencias"): TODOS,
    ("POST", "/api/acessibilidade/relato"): TODOS,   # relatar problema de acessibilidade (vai para a auditoria)
    # dados públicos do território (IBGE) e configuração da tela: qualquer pessoa com login
    ("GET", "/api/config"): TODOS, ("GET", "/api/concessao"): TODOS, ("GET", "/api/modelo-planilha"): TODOS,
    # o mapa operacional (comunidades e rede fictícia): só os perfis da empresa, e só na área de atuação dela;
    # o Admin do Norte tem o mapa das empresas (desde 15/10/2026)
    ("GET", "/api/municipios/{codigo}/comunidades"): EMPRESA, ("GET", "/api/municipios/{codigo}/rede"): EMPRESA,
    ("GET", "/api/clientes"): GERA, ("GET", "/api/clientes/resumo"): GERA,
    ("GET", "/api/localidades-oficiais"): EMPRESA,   # localidades do IBGE (dado público), só a área da empresa   # clientes fictícios: só a área da empresa
    ("GET", "/api/verificar/{codigo}"): TODOS,
    # importar, conferir, gerar, PDF, MP3, JSON com UCs: Admin da empresa e Operador
    ("POST", "/api/planilha"): GERA, ("POST", "/api/avisos"): GERA, ("POST", "/api/planilha/json"): GERA,
    ("POST", "/api/planilha/escolha"): GERA,   # escolher quem será desligado (nucleo/selecao.py)
    ("POST", "/api/planilha/relatorio"): GERA, ("POST", "/api/audio"): GERA,
    ("PUT", "/api/historico/{id_}/municipios/{codigo}/texto"): GERA, ("POST", "/api/historico/{id_}/cancelar"): GERA,
    ("POST", "/api/historico/{id_}/data"): GERA, ("POST", "/api/historico/{id_}/municipios/{codigo}/pdf"): GERA,
    # histórico e dashboard da empresa: os três perfis da empresa
    ("GET", "/api/historico"): EMPRESA, ("GET", "/api/historico/{id_}"): EMPRESA, ("GET", "/api/painel"): EMPRESA,
    # IA (copiloto do aviso e pergunte ao painel): reescrever é de quem gera aviso; perguntar, de quem vê o histórico
    ("POST", "/api/historico/{id_}/municipios/{codigo}/reescrever"): GERA, ("POST", "/api/painel/perguntar"): EMPRESA,
    # usuários da empresa: Admin da empresa
    ("GET", "/api/usuarios"): {ADM}, ("POST", "/api/usuarios"): {ADM}, ("PATCH", "/api/usuarios/{id_}"): {ADM},
    ("POST", "/api/usuarios/{id_}/senha-temporaria"): {ADM},
    # empresas: Admin do Norte; auditoria: Admin do Norte (todas) e Admin da empresa (a dela)
    ("GET", "/api/empresas"): {FAROL}, ("POST", "/api/empresas"): {FAROL}, ("PATCH", "/api/empresas/{id_}"): {FAROL},
    # mapa das empresas e área de atuação: só o Admin do Norte (cadastro, área e contagens; nada operacional)
    ("GET", "/api/empresas/mapa"): {FAROL}, ("GET", "/api/empresas/{id_}/ficha"): {FAROL}, ("PUT", "/api/empresas/{id_}/area"): {FAROL},
    ("POST", "/api/empresas/{id_}/area/arquivo"): {FAROL}, ("GET", "/api/municipios-ibge"): {FAROL},
    ("GET", "/api/municipios-ibge/{uf}/mapa"): {FAROL},
    ("GET", "/api/registro"): {FAROL, ADM}, ("GET", "/api/auditoria/verificar"): {FAROL, ADM},
    # configuração da empresa (modelo da mensagem etc.): Admin da empresa
    ("GET", "/api/empresa/configuracao"): {ADM}, ("PUT", "/api/empresa/configuracao"): {ADM},
    # rádios (Fase J): quem gera aviso lista (para o envio); só o Admin da empresa cadastra, altera e atende ou recusa pedidos;
    # o Operador pede o cadastro de uma rádio que falta e vê os pedidos que fez
    ("GET", "/api/radios"): GERA, ("POST", "/api/radios"): {ADM}, ("PATCH", "/api/radios/{id_}"): {ADM},
    ("POST", "/api/radios/pedidos"): {OP}, ("GET", "/api/radios/pedidos"): GERA, ("POST", "/api/radios/pedidos/{id_}/recusar"): {ADM},
    ("GET", "/api/historico/{id_}/radios"): GERA, ("POST", "/api/historico/{id_}/envios"): GERA,
    # envios e os arquivos enviados (comprovantes): os três perfis da empresa
    ("GET", "/api/historico/{id_}/envios"): EMPRESA, ("GET", "/api/envios/{id_}/arquivos/{tipo}"): EMPRESA,
    # relatórios: o do período e o comprovante (os três perfis da empresa); auditoria da empresa (Admin da empresa);
    # auditoria geral de acessos, de todas as empresas (Admin do Norte)
    ("GET", "/api/historico/{id_}/comprovante"): EMPRESA, ("GET", "/api/historico/{id_}/comprovante.pdf"): EMPRESA,
    # Fase H: cada relatório gera (tela), baixa (PDF/CSV) e envia; Consulta só gera e baixa; auditoria só o Admin da empresa;
    # acessos de todas as empresas só o Admin do Norte (sem envio)
    **{("GET", f"/api/relatorios/{t}"): EMPRESA for t in ("mensal", "custos", "comunidades", "prazos", "comunidade")},
    **{("GET", f"/api/relatorios/{t}.{{formato}}"): EMPRESA for t in ("mensal", "custos", "comunidades", "prazos", "comunidade")},
    **{("POST", f"/api/relatorios/{t}/enviar"): GERA for t in ("mensal", "custos", "comunidades", "prazos", "comunidade")},
    ("GET", "/api/relatorios/auditoria"): {ADM}, ("GET", "/api/relatorios/auditoria.{formato}"): {ADM},
    ("POST", "/api/relatorios/auditoria/enviar"): {ADM},
    ("GET", "/api/relatorios/acessos"): {FAROL}, ("GET", "/api/relatorios/acessos.{formato}"): {FAROL},
    # simulador de economia: os três perfis da empresa veem (tela, PDF, CSV); só o Admin da empresa altera os valores
    ("GET", "/api/relatorios/simulador"): EMPRESA, ("GET", "/api/relatorios/simulador.{formato}"): EMPRESA,
    ("PUT", "/api/empresa/configuracao/simulador"): {ADM},
    ("GET", "/api/relatorios/vias"): TODOS, ("GET", "/api/relatorios/vias/{id_}.pdf"): TODOS,
    ("GET", "/api/historico/{id_}/linha-do-tempo"): EMPRESA,
    ("GET", "/api/comunidades/ficha"): EMPRESA, ("GET", "/api/comunidades/calor"): EMPRESA,
    # a rádio confirma o recebimento pelo link do e-mail, sem login
    ("GET", "/confirmar/{token}"): PUBLICA, ("POST", "/confirmar/{token}"): PUBLICA,
}
resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def rotas(rs, vistas=None) -> list[tuple[str, str]]:
    """(método, caminho) de todas as rotas da API, entrando nos routers incluídos."""
    saida = []
    for r in rs:
        if isinstance(r, APIRoute):
            saida += [(m, r.path) for m in sorted(r.methods)]
        elif hasattr(r, "original_router"):
            saida += rotas(r.original_router.routes)
    return saida


with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_matriz CASCADE")
senhas = {e: s for _, e, s in semear()}
NOVA = "Lanterna-do-Farol-2026"


def pronto(email, senha=None):
    api_acesso._tentativas_ip.clear()
    c = TestClient(app, base_url="http://farol.teste")
    c.post("/api/entrar", json={"email": email, "senha": senha or senhas[email]})
    c.post("/api/senha", json={"atual": senha or senhas[email], "nova": NOVA})
    return c


clientes = {FAROL: pronto("admin@farol.example"), ADM: pronto("admin@emg.example"), OP: pronto("operador@emg.example"),
            CON: pronto("consulta@emg.example")}
anon = TestClient(app, base_url="http://farol.teste")
# um aviso e um usuário descartável da EMG, para as rotas com número
planilha = planilhas_teste.planilha("CF-0066").head(40).to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")
conf = clientes[OP].post("/api/planilha", files={"arquivo": ("p.csv", planilha)}, data={"data": "12/11", "horario": "8h"}).json()
aviso = clientes[OP].post("/api/avisos", json={"pacote": conf["pacote"], "data": "12/11", "horario": "8h", "conferi": True}).json()
alvo = clientes[ADM].post("/api/usuarios", json={"nome": "Alvo da Matriz", "email": "alvo@emg.example", "perfil": "consulta"}).json()
radio = clientes[ADM].post("/api/radios", json={"nome": "Rádio da Matriz (demonstração)", "email": "radio@example.com",
                                                "alcance": {"municipios": ["3138401"]}, "valor_padrao": "100"}).json()["radio"]
r = clientes[FAROL].post("/api/empresas", json={"nome": "Outra Empresa", "sigla": "OUT", "dominio": "out.example",
                                                "admin_nome": "Admin Outra", "admin_email": "admin@out.example"})
outra = pronto("admin@out.example", r.json()["senha_temporaria"])


def caminho(path: str) -> str:
    ids = {"/api/usuarios": alvo["usuario"]["id"], "/api/radios": radio["id"], "/api/envios": 1, "/api/empresas": 999999,
           "/api/relatorios/vias": 999999}
    p = path.replace("{id_}", str(next((v for k, v in ids.items() if path.startswith(k)), aviso["id"])))
    p = p.replace("{tipo}", "pdf").replace("{token}", "x" * 43).replace("{formato}", "csv").replace("{uf}", "MG")
    return p.replace("{codigo}", "FRL-0000-0000-0000" if "verificar" in p else "3138401")


todas = rotas(app.routes)
sem_regra = [f"{m} {p}" for m, p in todas if (m, p) not in MATRIZ]
conferir("toda rota da API tem regra na matriz", not sem_regra, "; ".join(sem_regra))
sobrando = [f"{m} {p}" for m, p in MATRIZ if (m, p) not in todas]
conferir("a matriz não tem rota que não existe mais", not sobrando, "; ".join(sobrando))

erros = []
for metodo, path in todas:
    if (metodo, path) not in MATRIZ:
        continue
    regra, url = MATRIZ[(metodo, path)], caminho(path)
    app_mod._envios.clear()
    st = anon.request(metodo, url).status_code
    if regra == PUBLICA:
        if st in (401, 403):
            erros.append(f"sem login {metodo} {path}: {st} (devia ser pública)")
        continue
    if st != 401:
        erros.append(f"sem login {metodo} {path}: {st} (devia ser 401)")
    for perfil, c in clientes.items():
        app_mod._envios.clear()
        st = c.request(metodo, url).status_code
        pode = perfil in regra
        if pode and st in (401, 403) or not pode and st != 403:
            erros.append(f"{perfil} {metodo} {path}: {st} ({'devia passar' if pode else 'devia ser 403'})")
conferir(f"matriz: {sum(1 for m, p in todas if MATRIZ.get((m, p), PUBLICA) != PUBLICA)} rotas fechadas x 4 perfis + sem login",
         not erros, "\n  " + "\n  ".join(erros))

# isolamento: o admin de outra empresa não consegue nada nas rotas com o número de um aviso ou usuário da EMG
vazou = []
for metodo, path in todas:
    if "{id_}" in path and MATRIZ.get((metodo, path)) not in (PUBLICA, None):
        corpo = {"motivo": "teste da matriz"} if path.endswith("cancelar") else {"data": "1/1", "horario": "8h"} if path.endswith("/data") \
            else {"texto": "x"} if path.endswith(("texto", "pdf")) else {"perfil": "consulta", "status": "ativo"} if path.startswith("/api/usuarios") \
            else {"nome": "Invasora", "email": "x@example.com"} if path.startswith("/api/radios") \
            else {"municipio": "3138401", "radio_id": radio["id"], "canal": "copia", "texto": "x", "valor": "1", "cobranca": "fechado"} \
            if path.endswith("envios") and metodo == "POST" else None
        st = outra.request(metodo, caminho(path), json=corpo).status_code
        if 200 <= st < 300:
            vazou.append(f"{metodo} {path}: {st}")
conferir("outra empresa: nenhuma rota com número de aviso ou usuário da EMG responde 2xx", not vazou, "; ".join(vazou))
conferir("outra empresa: o aviso da EMG continua não cancelado", clientes[CON].get(f"/api/historico/{aviso['id']}").json()["status"] == "gerado")

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_matriz CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
