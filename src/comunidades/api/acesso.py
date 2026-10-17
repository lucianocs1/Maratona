"""Login, sessão e permissões da API.

- Senha: Argon2id (senhas.py); a mensagem de erro é a mesma para e-mail desconhecido, senha
  errada e conta em bloqueio, e o tempo também (o hash é conferido mesmo sem usuário). 5 erros
  seguidos bloqueiam a conta por 15 minutos; cada IP tem um limite de tentativas por janela de tempo.
- Sessão: token aleatório num cookie HttpOnly, SameSite=Strict (Secure em produção); o banco
  guarda só o hash. Acaba com 8 h sem uso ou 24 h no total, ao sair, ao trocar a senha (as
  outras sessões) e ao bloquear o usuário.
- Toda rota confere a sessão e a permissão no servidor (nucleo/acesso.py). Quem precisa trocar a
  senha só consegue trocá-la, ver quem é e sair.
- Requisições que mudam dados vindas de outra origem são recusadas (além do SameSite).
"""

import os
import re
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import senhas
from ..banco import acesso as banco
from ..nucleo import acesso as regras
from ..nucleo import auditoria
from ..senhas import HASH_FALSO, hash_senha, senha_temporaria
from .comum import erro

COOKIE = "farol_sessao"
PRODUCAO = os.environ.get("FAROL_PRODUCAO", "") == "1"   # no Render: cookie só por HTTPS
LIMITE_IP, JANELA_IP = 30, 600                           # tentativas de login por IP a cada 10 minutos
_tentativas_ip: dict[str, deque] = defaultdict(deque)
# a mesma para e-mail desconhecido, senha errada e conta em bloqueio temporário: não revela se o e-mail existe
ERRO_LOGIN = "E-mail ou senha incorretos. Após 5 tentativas erradas o acesso fica suspenso por 15 minutos."

rotas = APIRouter(prefix="/api")


def _publico(u: dict) -> dict:
    """O que a tela pode saber do usuário (nada de hash, tentativas ou bloqueio)."""
    return {"id": u["id"], "nome": u["nome"], "email": u["email"], "perfil": u["perfil"],
            "perfil_nome": regras.PERFIS[u["perfil"]], "empresa_id": u["empresa_id"], "empresa": u.get("empresa_nome"),
            "empresa_sigla": u.get("empresa_sigla"), "trocar_senha": u["trocar_senha"], "acoes": regras.acoes(u["perfil"]),
            "preferencias": u.get("preferencias") or {}}


# ---------- Dependências: sessão e permissão ----------
def _origem_confere(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    # só o host: atrás do proxy de produção o servidor vê http, e o navegador manda a origem em https
    origem = request.headers.get("origin")
    if origem and urlsplit(origem).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "Origem não permitida.")


def sessao_atual(request: Request) -> dict:
    _origem_confere(request)
    token = request.cookies.get(COOKIE)
    u = banco.sessao(token, regras.SESSAO_INATIVA, regras.SESSAO_MAXIMA) if token else None
    if not u or u["status"] != "ativo" or u.get("empresa_status") == "suspensa":
        raise HTTPException(401, "Entre com o seu e-mail e senha.")
    return u


def usuario_atual(u: dict = Depends(sessao_atual)) -> dict:
    """Sessão válida e senha já trocada (a temporária só serve para trocar)."""
    if u["trocar_senha"]:
        raise HTTPException(403, "Troque a senha temporária antes de continuar.")
    return u


def exigir(acao: str):
    def conferir(u: dict = Depends(usuario_atual)) -> dict:
        if not regras.pode(u["perfil"], acao):
            raise HTTPException(403, "Seu perfil não tem acesso a isto.")
        return u
    return conferir


# ---------- Login, saída, senha ----------
class Entrada(BaseModel):
    email: str
    senha: str


class TrocaSenha(BaseModel):
    atual: str
    nova: str


def _limite_ip(ip: str) -> None:
    agora, fila = time.monotonic(), _tentativas_ip[ip]
    while fila and agora - fila[0] > JANELA_IP:
        fila.popleft()
    if len(fila) >= LIMITE_IP:
        raise HTTPException(429, "Tentativas demais deste endereço. Espere alguns minutos.")
    fila.append(agora)


def _conferir_senha(hash_: str, senha: str) -> bool:
    return senhas.conferir(hash_, senha)


@rotas.post("/entrar")
def entrar(dados: Entrada, request: Request, response: Response) -> dict:
    _origem_confere(request)
    _limite_ip(request.client.host if request.client else "?")
    email = regras.normalizar_email(dados.email)
    u = banco.usuario_por_email(email) if len(email) <= 254 else None
    senha_ok = _conferir_senha(u["senha_hash"] if u else HASH_FALSO, dados.senha[:regras.SENHA_MAX])
    if not u:
        raise HTTPException(401, ERRO_LOGIN)
    if u["bloqueado_ate"] and u["bloqueado_ate"].timestamp() > time.time():
        banco.registrar("login recusado (conta em bloqueio temporário)", "", u["id"], u["empresa_id"])
        raise HTTPException(401, ERRO_LOGIN)
    if not senha_ok:
        f = banco.registrar_falha(u["id"], regras.MAX_TENTATIVAS, regras.BLOQUEIO)
        banco.registrar("senha errada" + (" (conta bloqueada por 15 min)" if f["bloqueado_ate"] else ""), "", u["id"], u["empresa_id"])
        raise HTTPException(401, ERRO_LOGIN)
    if u["status"] != "ativo" or u.get("empresa_status") == "suspensa":
        banco.registrar("login recusado (usuário bloqueado ou empresa suspensa)", "", u["id"], u["empresa_id"])
        raise HTTPException(403, "Acesso desativado. Fale com o administrador da sua empresa.")
    # hash de parâmetros antigos (ex.: o padrão de 64 MiB): refeito com os atuais, com a mesma senha conferida
    senha = dados.senha[:regras.SENHA_MAX]
    banco.registrar_acesso(u["id"], hash_senha(senha) if senhas.precisa_refazer(u["senha_hash"]) else None)
    token = secrets.token_urlsafe(32)
    banco.criar_sessao(u["id"], token)
    response.set_cookie(COOKIE, token, httponly=True, secure=PRODUCAO, samesite="strict", path="/",
                        max_age=int(regras.SESSAO_MAXIMA.total_seconds()))
    banco.registrar("entrou", "", u["id"], u["empresa_id"])
    return {"usuario": _publico(u)}


@rotas.post("/sair")
def sair(request: Request, response: Response) -> dict:
    _origem_confere(request)
    token = request.cookies.get(COOKIE)
    if token:
        u = banco.sessao(token, regras.SESSAO_INATIVA, regras.SESSAO_MAXIMA)
        banco.encerrar_sessao(token)
        if u:
            banco.registrar("saiu", "", u["id"], u["empresa_id"])
    response.delete_cookie(COOKIE, path="/", samesite="strict", secure=PRODUCAO, httponly=True)
    return {"ok": True}


@rotas.get("/eu")
def eu(u: dict = Depends(sessao_atual)) -> dict:
    return {"usuario": _publico(u)}


@rotas.post("/senha")
def trocar_senha(dados: TrocaSenha, request: Request, u: dict = Depends(sessao_atual)) -> dict:
    completo = banco.usuario(u["id"])
    if not _conferir_senha(completo["senha_hash"], dados.atual[:regras.SENHA_MAX]):
        raise erro(422, "A senha atual não confere.", "atual")
    problema = regras.problema_senha(dados.nova, u["email"])
    if problema:
        raise erro(422, problema, "nova")
    if dados.nova == dados.atual:
        raise erro(422, "A senha nova tem de ser diferente da atual.", "nova")
    banco.definir_senha(u["id"], hash_senha(dados.nova), trocar_senha=False)
    banco.encerrar_sessoes(u["id"], exceto_token=request.cookies.get(COOKIE))
    banco.registrar("trocou a senha", "", u["id"], u["empresa_id"])
    return {"usuario": _publico({**u, "trocar_senha": False})}


# ---------- Preferências da tela (Fase K e I6): idioma e acessibilidade, do próprio usuário ----------
ACESSIBILIDADE = {"texto": (90, 100, 125, 150, 200), "contraste": (False, True), "movimento": (False, True), "dislexia": (False, True),
                  "espacamento": (False, True), "foco": (False, True), "vibrar": (False, True), "painel": (False, True),
                  "links": (False, True), "guia": (False, True), "simples": (False, True)}


class Preferencias(BaseModel):
    idioma: str | None = Field(None, max_length=10)
    acessibilidade: dict | None = None


@rotas.put("/eu/preferencias")
def salvar_preferencias(dados: Preferencias, u: dict = Depends(sessao_atual)) -> dict:
    """O idioma da tela e as opções de acessibilidade do próprio usuário. Só valores da lista fechada: nada sobre
    deficiência nem motivo. A auditoria registra que mudou, sem o conteúdo."""
    prefs = dict(u.get("preferencias") or {})
    if dados.idioma is not None:
        if dados.idioma not in ("pt-BR", "en", "es"):
            raise erro(422, "Idioma: pt-BR, en ou es.", "idioma")
        prefs["idioma"] = dados.idioma
    if dados.acessibilidade is not None:
        ruins = [k for k, v in dados.acessibilidade.items() if k not in ACESSIBILIDADE or v not in ACESSIBILIDADE[k]]
        if ruins:
            raise erro(422, "Opção de acessibilidade inválida.", "acessibilidade")
    prefs = banco.mesclar_preferencias(u["id"], dados.idioma, dados.acessibilidade)
    # a auditoria diz só que mudou: quais opções de acessibilidade a pessoa usa pode indicar deficiência (dado sensível,
    # LGPD art. 11); as opções ficam só no perfil dela, e nenhum relatório nem Admin as vê
    if dados.acessibilidade is not None:
        banco.registrar("alterou as preferências de acessibilidade", "", u["id"], u["empresa_id"])
    if dados.idioma is not None:
        banco.registrar("alterou o idioma da tela", "", u["id"], u["empresa_id"])
    return {"preferencias": prefs}


# ---------- Relato de problema de acessibilidade (Declaração de acessibilidade) ----------
class Relato(BaseModel):
    texto: str = Field(max_length=1000)
    tela: str = Field("", max_length=40)


@rotas.post("/acessibilidade/relato")
def relatar_acessibilidade(dados: Relato, u: dict = Depends(usuario_atual)) -> dict:
    """Qualquer perfil relata um problema de acessibilidade; vai para a auditoria (o Admin do Norte vê na auditoria geral).
    Sem dado pessoal: texto com e-mail, telefone ou número longo é recusado."""
    texto = " ".join("".join(c if c.isprintable() else " " for c in dados.texto).split())
    if len(texto) < 10:
        raise erro(422, "Descreva o problema (pelo menos 10 caracteres).", "texto")
    if re.search(r"@|\d[\d .-]{7,}\d|https?://|www\.", texto):
        raise erro(422, "Sem dado pessoal: tire e-mail, telefone, número longo e endereço de site.", "texto")
    tela = re.sub(r"[^a-z0-9_-]", "", dados.tela.lower())[:40]
    linha = banco.registrar("relatou problema de acessibilidade", f"[{tela or 'tela'}] {texto}", u["id"], u["empresa_id"])
    return {"ok": True, "codigo": auditoria.codigo_verificacao(linha["hash"])}


# ---------- Usuários da empresa (Admin da empresa) ----------
class NovoUsuario(BaseModel):
    nome: str
    email: str
    perfil: str
    municipios: list[str] = Field(default_factory=list, max_length=200)


class AlteraUsuario(BaseModel):
    perfil: str
    status: str
    municipios: list[str] | None = Field(None, max_length=200)
    nome: str | None = Field(None, max_length=200)


def _municipios(codigos: list[str] | None) -> list[str] | None:
    """Os municípios em que o usuário atua: códigos IBGE da concessão (sem repetir)."""
    if codigos is None:
        return None
    from ..banco import base_territorial
    validos = {c for c, _, _, _ in base_territorial.contornos("EPSG:4674")}
    saida = sorted({str(c) for c in codigos})
    if any(c not in validos for c in saida):
        raise erro(422, "Municípios: use códigos IBGE de municípios da concessão.", "municipios")
    return saida


def _linha_usuario(x: dict) -> dict:
    return {"id": x["id"], "nome": x["nome"], "email": x["email"], "perfil": x["perfil"], "perfil_nome": regras.PERFIS[x["perfil"]],
            "status": x["status"], "trocar_senha": x["trocar_senha"], "municipios": x.get("municipios") or [],
            "ultimo_acesso": x["ultimo_acesso"].isoformat() if x["ultimo_acesso"] else None}


def _nome(nome: str, campo: str = "nome") -> str:
    n = " ".join(str(nome).split())
    if not 2 <= len(n) <= 120:
        raise erro(422, "Nome: de 2 a 120 caracteres.", campo)
    return n


@rotas.get("/usuarios")
def listar_usuarios(u: dict = Depends(exigir("gerenciar_usuarios"))) -> dict:
    return {"usuarios": [_linha_usuario(x) for x in banco.usuarios(u["empresa_id"])],
            "perfis": {p: regras.PERFIS[p] for p in regras.PERFIS_EMPRESA}}


@rotas.post("/usuarios")
def criar_usuario(dados: NovoUsuario, u: dict = Depends(exigir("gerenciar_usuarios"))) -> dict:
    emp = banco.empresa(u["empresa_id"])
    email, nome = regras.normalizar_email(dados.email), _nome(dados.nome)
    if (p := regras.problema_email(email, emp["dominio"])):
        raise erro(422, p, "email")
    if dados.perfil not in regras.PERFIS_EMPRESA:
        raise erro(422, "Perfil inválido.", "perfil")
    if banco.usuario_por_email(email):
        raise erro(409, "Já existe um usuário com este e-mail.", "email")
    municipios = _municipios(dados.municipios)
    temporaria = senha_temporaria()
    try:
        novo = banco.criar_usuario(u["empresa_id"], email, nome, dados.perfil, hash_senha(temporaria), municipios=municipios)
    except banco.errors.UniqueViolation:   # clique duplo: a outra requisição gravou primeiro
        raise erro(409, "Já existe um usuário com este e-mail.", "email") from None
    banco.registrar("cadastrou usuário", f"{nome} ({regras.PERFIS[dados.perfil]})", u["id"], u["empresa_id"])
    # a senha temporária aparece só nesta resposta, para o admin passar ao usuário
    return {"usuario": _linha_usuario(banco.usuario(novo["id"])), "senha_temporaria": temporaria}


def _da_empresa(id_: int, u: dict) -> dict:
    alvo = banco.usuario(id_)
    if not alvo or alvo["empresa_id"] != u["empresa_id"]:
        raise HTTPException(404, "Usuário não encontrado nesta empresa.")
    return alvo


@rotas.patch("/usuarios/{id_}")
def alterar_usuario(id_: int, dados: AlteraUsuario, u: dict = Depends(exigir("gerenciar_usuarios"))) -> dict:
    alvo = _da_empresa(id_, u)
    if dados.perfil not in regras.PERFIS_EMPRESA:
        raise erro(422, "Perfil inválido.", "perfil")
    if dados.status not in ("ativo", "bloqueado"):
        raise erro(422, "Situação: ativo ou bloqueado.", "status")
    nome = _nome(dados.nome) if dados.nome is not None else alvo["nome"]
    antes = alvo["perfil"] == "admin_empresa" and alvo["status"] == "ativo"
    depois = dados.perfil == "admin_empresa" and dados.status == "ativo"
    if regras.deixa_sem_admin(banco.admins_ativos(u["empresa_id"]), antes, depois):
        raise erro(409, "Este é o último admin ativo da empresa: cadastre outro admin antes de mudar o perfil ou bloquear.",
                   "status" if dados.status != "ativo" else "perfil")
    municipios = _municipios(dados.municipios)
    mudou = auditoria.diferencas(
        {"nome": alvo["nome"], "perfil": regras.PERFIS[alvo["perfil"]], "status": alvo["status"],
         "municipios": ", ".join(alvo.get("municipios") or []) or "todos"},
        {"nome": nome, "perfil": regras.PERFIS[dados.perfil], "status": dados.status,
         "municipios": (", ".join(municipios) or "todos") if municipios is not None else ", ".join(alvo.get("municipios") or []) or "todos"},
        {"nome": "nome", "perfil": "perfil", "status": "situação", "municipios": "municípios"})
    banco.alterar_usuario(id_, dados.perfil, dados.status, municipios, nome)
    banco.registrar("alterou usuário", f"{alvo['nome']}: {mudou}", u["id"], u["empresa_id"])
    return {"usuario": _linha_usuario(banco.usuario(id_))}


@rotas.post("/usuarios/{id_}/senha-temporaria")
def nova_temporaria(id_: int, u: dict = Depends(exigir("gerenciar_usuarios"))) -> dict:
    alvo = _da_empresa(id_, u)
    temporaria = senha_temporaria()
    banco.definir_senha(id_, hash_senha(temporaria), trocar_senha=True)
    banco.encerrar_sessoes(id_)
    banco.registrar("gerou senha temporária", alvo["nome"], u["id"], u["empresa_id"])
    return {"senha_temporaria": temporaria}


# ---------- Empresas (Admin do Norte) e registro ----------
class NovaEmpresa(BaseModel):
    nome: str
    sigla: str
    dominio: str
    admin_nome: str
    admin_email: str
    cnpj: str | None = Field(None, max_length=30)


class AlteraEmpresa(BaseModel):
    """Situação (suspender ou reativar) ou os dados da empresa (nome, domínio, CNPJ); o que não vier fica como está."""
    status: str | None = None
    nome: str | None = Field(None, max_length=200)
    dominio: str | None = Field(None, max_length=120)
    cnpj: str | None = Field(None, max_length=30)


@rotas.get("/empresas")
def listar_empresas(u: dict = Depends(exigir("gerenciar_empresas"))) -> dict:
    return {"empresas": [{"id": e["id"], "nome": e["nome"], "sigla": e["sigla"], "dominio": e["dominio"], "status": e["status"],
                          "cnpj": regras.formatar_cnpj(e["cnpj"]) if e.get("cnpj") else None,
                          "usuarios": e["usuarios"], "avisos": e["avisos"]} for e in banco.empresas()]}


def _dominio(dominio: str) -> str:
    d = str(dominio or "").strip().lower()
    if regras.problema_email(f"x@{d}"):
        raise erro(422, "Domínio de e-mail inválido (ex.: empresa.com.br).", "dominio")
    return d


def _cnpj(cnpj: str | None, exceto: int | None = None) -> str | None:
    c = regras.normalizar_cnpj(cnpj) or None
    if c and not regras.cnpj_valido(c):
        raise erro(422, "CNPJ inválido: confira os dígitos verificadores (aceita o alfanumérico).", "cnpj")
    if c and (outra := banco.empresa_por_cnpj(c)) and outra["id"] != exceto:
        raise erro(409, "Já existe uma empresa com este CNPJ.", "cnpj")
    return c


@rotas.patch("/empresas/{id_}")
def mudar_empresa(id_: int, dados: AlteraEmpresa, u: dict = Depends(exigir("gerenciar_empresas"))) -> dict:
    """Suspende ou reativa a empresa (suspensa: ninguém dela entra, e as sessões abertas acabam), ou altera o nome,
    o domínio dos e-mails e o CNPJ (os e-mails já cadastrados não mudam). Antes e depois na auditoria."""
    e = banco.empresa(id_)
    if not e:
        raise HTTPException(404, "Empresa não encontrada.")
    if dados.status is not None:
        if dados.status not in ("ativa", "suspensa"):
            raise erro(422, "Situação: ativa ou suspensa.", "status")
        if dados.status == e["status"]:
            raise erro(409, f"A empresa já está {dados.status}.", "status")
        banco.mudar_status_empresa(id_, dados.status)
        banco.registrar("suspendeu empresa" if dados.status == "suspensa" else "reativou empresa",
                        f"{e['nome']} ({e['sigla']}): situação {e['status']} → {dados.status}", u["id"], id_)
        return {"empresa": {"id": id_, "status": dados.status}}
    nome = _nome(dados.nome) if dados.nome is not None else e["nome"]
    dominio = _dominio(dados.dominio) if dados.dominio is not None else e["dominio"]
    cnpj = _cnpj(dados.cnpj, id_) if dados.cnpj is not None else e.get("cnpj")
    novo = {"nome": nome, "dominio": dominio, "cnpj": regras.formatar_cnpj(cnpj) if cnpj else "—"}
    antes = {"nome": e["nome"], "dominio": e["dominio"], "cnpj": regras.formatar_cnpj(e["cnpj"]) if e.get("cnpj") else "—"}
    if novo == antes:
        raise erro(409, "Nada mudou nos dados da empresa.")
    banco.alterar_empresa(id_, nome, dominio, cnpj)
    banco.registrar("alterou empresa", f"{e['nome']} ({e['sigla']}): " + auditoria.diferencas(antes, novo, {
        "nome": "nome", "dominio": "domínio", "cnpj": "CNPJ"}), u["id"], id_)
    return {"empresa": {"id": id_, "nome": nome, "dominio": dominio, "status": e["status"]}}


@rotas.post("/empresas")
def criar_empresa(dados: NovaEmpresa, u: dict = Depends(exigir("gerenciar_empresas"))) -> dict:
    nome, sigla = _nome(dados.nome), dados.sigla.strip().upper()
    if not (2 <= len(sigla) <= 10 and sigla.isalnum()):
        raise erro(422, "Sigla: de 2 a 10 letras ou números.", "sigla")
    dominio = _dominio(dados.dominio)
    admin_nome = _nome(dados.admin_nome, "admin_nome")
    email = regras.normalizar_email(dados.admin_email)
    if (p := regras.problema_email(email, dominio)):
        raise erro(422, p, "admin_email")
    if banco.empresa_por_sigla(sigla):
        raise erro(409, "Já existe uma empresa com esta sigla.", "sigla")
    if banco.usuario_por_email(email):
        raise erro(409, "Já existe um usuário com este e-mail.", "admin_email")
    cnpj = _cnpj(dados.cnpj)
    temporaria = senha_temporaria()
    try:   # a empresa e o primeiro admin juntos: nunca uma empresa sem admin
        e = banco.criar_empresa_com_admin(nome, sigla, dominio, cnpj, email, admin_nome, hash_senha(temporaria), u["nome"])
    except banco.errors.UniqueViolation:   # clique duplo: a outra requisição gravou primeiro
        raise erro(409, "Já existe uma empresa com esta sigla.", "sigla") from None
    banco.registrar("cadastrou empresa", f"{nome} ({sigla}) e o primeiro admin", u["id"], e["id"])
    return {"empresa": {"id": e["id"], "nome": nome, "sigla": sigla}, "senha_temporaria": temporaria}


@rotas.get("/registro")
def registro(u: dict = Depends(exigir("ver_registro"))) -> dict:
    """A auditoria: o Admin do Norte vê a de todas as empresas; o Admin da empresa, só a dela.
    Quem fez aparece com o nome e o perfil de quando fez (copiados na linha); o código sai do hash."""
    linhas = banco.registros(None if u["perfil"] == "admin_farol" else u["empresa_id"])
    return {"registro": [{"quando": r["quando"].isoformat(), "acao": r["acao"], "detalhe": r["detalhe"],
                          "usuario": r["usuario"], "perfil": regras.PERFIS.get(r["perfil"], ""), "empresa": r["empresa"],
                          "codigo": auditoria.codigo_verificacao(r["hash"]) if r["hash"] else None} for r in linhas]}


@rotas.get("/auditoria/verificar")
def verificar_auditoria(u: dict = Depends(exigir("ver_registro"))) -> dict:
    """Refaz a conta da corrente inteira (nucleo/auditoria.verificar). O Admin da empresa vê só se está
    íntegra; onde quebrou (o número da linha) só o Admin do Norte vê."""
    v = banco.verificar_registro()
    banco.registrar("conferiu a integridade da auditoria", "íntegra" if v["ok"] else "QUEBRADA", u["id"], u["empresa_id"])
    if u["perfil"] == "admin_farol":
        return {k: v[k] for k in ("ok", "linhas", "conferidas", "quebra_id", "motivo")}
    return {"ok": v["ok"], "motivo": None if v["ok"] else "A auditoria não confere. Avise o Admin do Norte."}
