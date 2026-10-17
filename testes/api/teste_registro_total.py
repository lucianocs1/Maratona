"""Teste do registro total (Fase H6): toda rota que muda algo, baixa um arquivo ou gera um relatório grava na auditoria.

Sem banco (só lê o código das rotas). Para cada rota da API:
- POST, PUT, PATCH e DELETE: o código da rota chama registrar (ou _registrar, ou gerar_pdf, que registra);
- GET de arquivo ou relatório (.pdf, .csv, .{formato}, /relatorios/, modelo da planilha): idem;
- os outros GET só mostram o que já existe e têm de estar em VISTAS. Rota nova fora das duas listas é falha:
  quem cria a rota tem de dizer se ela grava na auditoria ou só mostra.
O nome e o perfil de quem fez são copiados do login pelo banco (banco/acesso.registrar); o teste_relatorios_h
confere no banco que nenhuma linha com usuário fica sem nome ou perfil.

Uso (na raiz): uv run python -W ignore testes/api/teste_registro_total.py
"""

import inspect
import os
import re
import sys

os.environ.setdefault("FAROL_EMAIL", "0")

from fastapi.routing import APIRoute  # noqa: E402

from comunidades.api.app import app  # noqa: E402

# GET que só mostram (nada muda, nenhum arquivo sai): fora da auditoria por decisão (CHECKLIST, Fase H)
VISTAS = {
    "/", "/api/saude", "/api/config", "/api/concessao", "/api/eu", "/api/usuarios", "/api/empresas", "/api/registro",
    "/api/auditoria/verificar", "/api/empresa/configuracao", "/api/radios", "/api/radios/pedidos", "/api/historico", "/api/historico/{id_}",
    "/api/historico/{id_}/radios", "/api/historico/{id_}/envios", "/api/historico/{id_}/comprovante", "/api/historico/{id_}/linha-do-tempo",
    "/api/painel", "/api/verificar/{codigo}", "/api/municipios/{codigo}/comunidades", "/api/municipios/{codigo}/rede",
    "/api/clientes", "/api/clientes/resumo", "/api/localidades-oficiais",
    "/api/relatorios/vias", "/api/comunidades/ficha", "/api/comunidades/calor", "/confirmar/{token}",
    "/api/empresas/mapa", "/api/empresas/{id_}/ficha", "/api/municipios-ibge", "/api/municipios-ibge/{uf}/mapa",
}
ARQUIVO = re.compile(r"\.(pdf|csv|mp3|\{formato\})$|^/api/relatorios/|^/api/modelo-planilha$|/arquivos/")
# salvar_area grava a área e a linha da auditoria na mesma transação (banco/acesso.salvar_area)
GRAVA = re.compile(r"\b(_?registrar|gerar_pdf|salvar_area)\(")
resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def rotas(rs):
    for r in rs:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from rotas(r.original_router.routes)


gravam, vistas, sem_registro, sem_classe = [], [], [], []
for r in rotas(app.routes):
    for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
        nome = f"{m} {r.path}"
        if m == "GET" and r.path in VISTAS:
            vistas.append(nome)
            continue
        if m == "GET" and not ARQUIVO.search(r.path):
            sem_classe.append(nome)
            continue
        try:
            fonte = inspect.getsource(r.endpoint)
        except (OSError, TypeError):
            fonte = ""
        (gravam if GRAVA.search(fonte) else sem_registro).append(nome)

conferir(f"{len(gravam)} rotas que mudam, baixam ou geram gravam na auditoria", not sem_registro and len(gravam) > 30,
         "sem registro: " + ", ".join(sem_registro))
conferir(f"{len(vistas)} GET só de leitura, todos listados em VISTAS (rota nova sem classe é falha)", not sem_classe,
         "sem classe: " + ", ".join(sem_classe))
todas = {r.path for r in rotas(app.routes)}
conferir("VISTAS sem rota que não existe mais e sem arquivo (.pdf, .csv, .mp3)", VISTAS <= todas
         and not any(re.search(r"\.(pdf|csv|mp3|\{formato\})$", v) for v in VISTAS), ", ".join(sorted(VISTAS - todas)))
fonte_registrar = inspect.getsource(__import__("comunidades.banco.acesso", fromlist=["x"])._registrar)
conferir("o banco copia nome e perfil do login (não vêm do pedido)", "usuario_nome" in fonte_registrar and "perfil" in fonte_registrar)
# a regra pega mesmo uma rota que não registra
falsa = APIRoute("/api/x", lambda: None, methods=["POST"])
conferir("uma rota POST sem registrar seria apontada", not GRAVA.search(inspect.getsource(falsa.endpoint)))

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
