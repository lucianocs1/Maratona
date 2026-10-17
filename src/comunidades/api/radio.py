"""Rádios, configuração da empresa, PDF do roteiro e envio do aviso (e-mail, WhatsApp, cópia), com confirmação.

- Configuração da empresa (modelo da mensagem, nome falado, telefone, limite de rejeição, fuso UTM,
  antecedência): só o Admin da empresa.
- Rádios: só o Admin da empresa cadastra, altera, desativa e define o valor padrão (Fase J). Se falta uma
  rádio, o Operador pede o cadastro (nome, cidade, contato da rádio e observação); o Admin atende (cadastra a
  rádio a partir do pedido, na mesma transação) ou recusa com motivo.
- Envio: quem gera aviso escolhe a rádio, informa o valor (gravado no envio) e manda. Por e-mail, o
  servidor gera o PDF e o MP3, guarda os dois cifrados (cofre.py), manda pelo SMTP configurado e põe
  no e-mail o link "Confirmar recebimento" (token de uso único, 7 dias, só o hash no banco).
- Confirmação: página pública, sem login. Abrir o link só mostra a página; confirmar é um POST (um
  leitor de e-mail que abre o link sozinho não confirma nada).
Tudo o que alguém faz vai para a auditoria com o nome de quem fez (do login).
"""

import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from .. import cofre, correio
from ..apresentacao import audio, confirmacao, email_radio, pdf_radio, rotulos
from ..nucleo import idiomas
from ..nucleo.tipos_desligamento import rotulos as rotulos_tipos
from ..banco import acesso as banco_acesso
from ..banco import base_territorial as banco_territorio
from ..banco import radios as banco
from ..config import sem_acento
from ..nucleo import economia, mensagem
from ..nucleo import radios as alcance_
from ..nucleo.acesso import PERFIS, problema_email
from ..nucleo.auditoria import diferencas
from ..nucleo.tipos_desligamento import _EMAIL, _NUMEROS, _SITE, limpar
from ..segredos import segredo
from .acesso import exigir
from .comum import AUDIO, AVISO_FICTICIO, BRASILIA, config_empresa, erro, segundos

rotas = APIRouter()
LIMITE_EMAILS, JANELA_EMAILS = 30, 3600          # e-mails para rádios por usuário por hora
_emails: dict[int, deque] = defaultdict(deque)
_NUMEROS = re.compile(r"\d[\d.\-/ ]{4,}\d")
CSP_PAGINA = ("default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'; "
              "frame-ancestors 'none'; object-src 'none'")


def _municipios_concessao() -> set[str]:
    return {c for c, _, _, _ in banco_territorio.contornos("EPSG:4674")}


def _dinheiro(d: Decimal | None) -> str | None:
    return None if d is None else f"{Decimal(d):.2f}"


# ---------- Configuração da empresa ----------
class Configuracao(BaseModel):
    modelo_mensagem: str = Field(max_length=mensagem.MAX_MODELO)
    nome_mensagem: str = Field(max_length=120)
    telefone: str = Field("", max_length=40)
    limite_rejeicao: float = Field(ge=0, le=0.5)
    epsg_utm: int = Field(ge=31960, le=31985)
    antecedencia_dias: int = Field(ge=1, le=90)
    orcamento_radio: float | None = Field(None, ge=0, le=100_000_000)   # orçamento anual de rádio (R$)
    alerta_preco: float = Field(0.20, ge=0, le=5)                       # alerta quando o envio custa mais que isso acima da média
    repeticao_n: int = Field(3, ge=2, le=50)                            # repetição: N desligamentos...
    repeticao_dias: int = Field(30, ge=7, le=365)                       # ...dentro de D dias
    modelo_mensagem_en: str | None = Field(None, max_length=mensagem.MAX_MODELO)   # Fase K: o modelo em inglês e em espanhol
    modelo_mensagem_es: str | None = Field(None, max_length=mensagem.MAX_MODELO)
    idioma_padrao: Literal["pt-BR", "en", "es"] = "pt-BR"


@rotas.get("/api/empresa/configuracao")
def ver_configuracao(u: dict = Depends(exigir("configurar_empresa"))) -> dict:
    return {**config_empresa(u["empresa_id"]), "campos": list(mensagem.CAMPOS), "modelo_padrao": mensagem.PADRAO,
            "modelos_padrao": mensagem.PADROES}


@rotas.put("/api/empresa/configuracao")
def salvar_configuracao(dados: Configuracao, u: dict = Depends(exigir("configurar_empresa"))) -> dict:
    for campo in ("modelo_mensagem", "modelo_mensagem_en", "modelo_mensagem_es"):
        if getattr(dados, campo) is not None and (p := mensagem.problema_modelo(getattr(dados, campo))):
            raise erro(422, p, campo)
    nome = limpar(dados.nome_mensagem)
    if len(nome) < 2:
        raise erro(422, "Nome da empresa na mensagem: de 2 a 120 caracteres.", "nome_mensagem")
    antes = config_empresa(u["empresa_id"])
    antes = {**antes, "modelo_mensagem_en": antes["modelos"]["en"], "modelo_mensagem_es": antes["modelos"]["es"]}
    novo = {"modelo_mensagem": dados.modelo_mensagem.strip(), "nome_mensagem": nome, "telefone": limpar(dados.telefone),
            "limite_rejeicao": round(dados.limite_rejeicao, 4), "epsg_utm": dados.epsg_utm, "antecedencia_dias": dados.antecedencia_dias,
            "orcamento_radio": round(dados.orcamento_radio, 2) if dados.orcamento_radio is not None else None,
            "alerta_preco": round(dados.alerta_preco, 4), "repeticao_n": dados.repeticao_n, "repeticao_dias": dados.repeticao_dias,
            "modelo_mensagem_en": (dados.modelo_mensagem_en or "").strip() or antes["modelos"]["en"],
            "modelo_mensagem_es": (dados.modelo_mensagem_es or "").strip() or antes["modelos"]["es"], "idioma_padrao": dados.idioma_padrao}
    banco.salvar_config(u["empresa_id"], u["id"], novo)
    banco_acesso.registrar("alterou a configuração da empresa", diferencas(antes, novo, {
        "modelo_mensagem": "modelo da mensagem", "nome_mensagem": "nome na mensagem", "telefone": "telefone", "limite_rejeicao": "limite de rejeição",
        "epsg_utm": "fuso UTM", "antecedencia_dias": "antecedência (dias)", "orcamento_radio": "orçamento de rádio", "alerta_preco": "alerta de preço",
        "repeticao_n": "repetição (N)", "repeticao_dias": "repetição (dias)", "modelo_mensagem_en": "modelo em inglês",
        "modelo_mensagem_es": "modelo em espanhol", "idioma_padrao": "idioma padrão"}), u["id"], u["empresa_id"])
    return ver_configuracao(u)


class Simulador(BaseModel):
    gasto_min: Decimal = Field(ge=0, le=1_000_000_000)                  # gasto mensal com rádio (R$), ou o mínimo da faixa
    gasto_max: Decimal | None = Field(None, ge=0, le=1_000_000_000)     # o máximo da faixa (opcional)
    pct_tempo: Decimal = Field(Decimal("100"), ge=0, le=100)            # % do gasto cobrado por tempo no ar
    nota: str | None = Field(None, max_length=200)                      # origem dos valores (ex.: "valores informados pela Energisa")


@rotas.put("/api/empresa/configuracao/simulador")
def salvar_simulador(dados: Simulador, u: dict = Depends(exigir("configurar_empresa"))) -> dict:
    """Os valores do simulador de economia (Relatórios): só o Admin da empresa; o antes e o depois vão para a auditoria."""
    gmin = dados.gasto_min.quantize(Decimal("0.01"))
    gmax = dados.gasto_max.quantize(Decimal("0.01")) if dados.gasto_max is not None else None
    if gmax is not None and gmax < gmin:
        raise erro(422, "Gasto máximo: igual ou maior que o mínimo.", "gasto_max")
    nota = limpar(dados.nota or "") or None
    if nota and (len(nota) > 120 or problema_nota(nota)):
        raise erro(422, "Origem dos valores: até 120 caracteres, sem e-mail, site nem número longo.", "nota")
    antes = config_empresa(u["empresa_id"])["simulador"]
    novo = {"gasto_min": gmin, "gasto_max": gmax, "pct_tempo": dados.pct_tempo.quantize(Decimal("0.01")), "nota": nota}
    banco.salvar_simulador(u["empresa_id"], u["id"], novo["gasto_min"], novo["gasto_max"], novo["pct_tempo"], nota)
    banco_acesso.registrar("alterou o simulador de economia", diferencas(texto_simulador(antes), texto_simulador(novo), ROTULOS_SIMULADOR),
                           u["id"], u["empresa_id"])
    return {"simulador": texto_simulador(config_empresa(u["empresa_id"])["simulador"])}


ROTULOS_SIMULADOR = {"gasto_min": "gasto mensal (mínimo)", "gasto_max": "gasto mensal (máximo)", "pct_tempo": "% cobrado por tempo",
                     "nota": "origem dos valores"}


def texto_simulador(v: dict) -> dict:
    """Os valores do simulador como texto (dinheiro com 2 casas), para a auditoria e a resposta."""
    return {k: (None if x is None else x if k == "nota" else _dinheiro(x)) for k, x in v.items()}


def problema_nota(texto: str) -> bool:
    return bool(_NUMEROS.search(texto) or _EMAIL.search(texto) or _SITE.search(texto))


# ---------- Rádios ----------
class DadosRadio(BaseModel):
    nome: str = Field(max_length=200)
    email: str | None = Field(None, max_length=254)
    whatsapp: str | None = Field(None, max_length=40)
    alcance: dict = Field(default_factory=dict)
    valor_padrao: str | float | None = None
    cobranca: Literal["fechado", "minuto"] = "fechado"
    ativa: bool = True
    pedido_id: int | None = None   # cadastro que atende um pedido de rádio do Operador


def _radio_publica(r: dict) -> dict:
    return {"id": r["id"], "nome": r["nome"], "email": r["email"], "whatsapp": r["whatsapp"], "alcance": r["alcance"],
            "valor_padrao": _dinheiro(r["valor_padrao"]), "cobranca": r["cobranca"], "ativa": r["ativa"],
            "valor_sugerido": _dinheiro(r["ultimo_valor"] if r["ultimo_valor"] is not None else r["valor_padrao"]),
            "cobranca_sugerida": r["ultima_cobranca"] or r["cobranca"]}


def _validar_radio(d: DadosRadio) -> dict:
    nome = limpar(d.nome)
    if not 2 <= len(nome) <= 80:
        raise erro(422, "Nome da rádio: de 2 a 80 caracteres.", "nome")
    email = (d.email or "").strip().lower() or None
    if email and (p := problema_email(email)):
        raise erro(422, f"E-mail da rádio: {p}", "email")
    whats = re.sub(r"\D", "", d.whatsapp or "") or None
    if whats and not 10 <= len(whats) <= 13:
        raise erro(422, "WhatsApp da rádio: de 10 a 13 algarismos, com o DDD (e o 55 do Brasil, se quiser).", "whatsapp")
    if not email and not whats:
        raise erro(422, "Informe o e-mail ou o WhatsApp da rádio.", "email")
    try:
        valor = economia.reais(d.valor_padrao)
    except ValueError as e:
        raise erro(422, f"Valor padrão: {e}.", "valor_padrao") from None
    try:
        alcance = alcance_.normalizar_alcance(d.alcance, _municipios_concessao())
    except ValueError as e:
        raise erro(422, f"Alcance da rádio: {e}.", "alcance") from None
    return {"nome": nome, "email": email, "whatsapp": whats, "alcance": alcance, "valor_padrao": valor, "cobranca": d.cobranca,
            "ativa": d.ativa}


@rotas.get("/api/radios")
def listar_radios(u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    return {"radios": [_radio_publica(r) for r in banco.radios(u["empresa_id"], so_ativas=u["perfil"] != "admin_empresa")]}


@rotas.post("/api/radios")
def criar_radio(dados: DadosRadio, u: dict = Depends(exigir("gerenciar_radios"))) -> dict:
    """Cadastra uma rádio da empresa (só o Admin da empresa); com pedido_id, atende o pedido do Operador."""
    d = _validar_radio(dados)
    d["ativa"] = True
    if banco.radio_com_nome(u["empresa_id"], d["nome"]):
        raise erro(409, "Já existe uma rádio com este nome nesta empresa.", "nome")
    pedido = None
    if dados.pedido_id is not None:
        pedido = banco.pedido(dados.pedido_id, u["empresa_id"])
        if not pedido or pedido["status"] != "aberto":
            raise erro(409, "Este pedido de rádio já foi atendido ou recusado.")
    try:
        id_ = banco.criar_radio(u["empresa_id"], u["id"], d, dados.pedido_id, u["nome"])
    except banco.PedidoResolvido:
        raise erro(409, "Este pedido de rádio já foi atendido ou recusado.") from None
    banco_acesso.registrar("cadastrou rádio", f"{d['nome']} ({len(d['alcance']['municipios'])} município(s), "
                           f"{len(d['alcance']['comunidades'])} comunidade(s))", u["id"], u["empresa_id"])
    if pedido:
        banco_acesso.registrar("atendeu pedido de rádio", f"pedido {pedido['id']}: {pedido['nome']} ({pedido['cidade']}), pedido por "
                               f"{pedido['criado_por_nome']}; cadastrada como {d['nome']}", u["id"], u["empresa_id"])
    return {"radio": _radio_publica(banco.radio(id_, u["empresa_id"]))}


@rotas.patch("/api/radios/{id_}")
def alterar_radio(id_: int, dados: DadosRadio, u: dict = Depends(exigir("gerenciar_radios"))) -> dict:
    antes = banco.radio(id_, u["empresa_id"])
    if not antes:
        raise HTTPException(404, "Rádio não encontrada nesta empresa.")
    d = _validar_radio(dados)
    if banco.radio_com_nome(u["empresa_id"], d["nome"], exceto=id_):
        raise erro(409, "Já existe outra rádio com este nome nesta empresa.", "nome")
    resumo_alcance = lambda a: f"{len(a.get('municipios') or [])} município(s), {len(a.get('comunidades') or [])} comunidade(s)"
    campos = {"nome": "nome", "email": "e-mail", "whatsapp": "WhatsApp", "alcance": "alcance", "valor_padrao": "valor padrão",
              "cobranca": "cobrança"}
    comparavel = lambda r: {k: (resumo_alcance(r[k]) if k == "alcance" else _dinheiro(r[k]) if k == "valor_padrao" else r[k]) for k in campos}
    mudou = diferencas(comparavel(antes), comparavel(d), campos) if comparavel(antes) != comparavel(d) else ""
    if not mudou and d["ativa"] == antes["ativa"]:   # nada mudou: nenhuma linha a mais na auditoria
        return {"radio": _radio_publica(antes), "nada_mudou": True}
    banco.alterar_radio(id_, u["empresa_id"], d)
    if mudou:
        banco_acesso.registrar("alterou cadastro de rádio", f"{antes['nome']}: {mudou}", u["id"], u["empresa_id"])
    if d["ativa"] != antes["ativa"]:
        banco_acesso.registrar("reativou rádio" if d["ativa"] else "desativou rádio", d["nome"], u["id"], u["empresa_id"])
    return {"radio": _radio_publica(banco.radio(id_, u["empresa_id"]))}


# ---------- Pedidos de cadastro de rádio (Operador pede; Admin da empresa atende ou recusa) ----------
class PedidoRadio(BaseModel):
    nome: str = Field(max_length=200)
    cidade: str = Field(max_length=200)
    contato: str = Field("", max_length=200)
    observacao: str = Field("", max_length=1000)


class Recusa(BaseModel):
    motivo: str = Field(max_length=1000)


def _texto_livre(texto: str, rotulo: str, campo: str, minimo: int, maximo: int) -> str:
    """Texto digitado (observação, motivo): tamanho e nada que pareça dado pessoal (número longo, e-mail, site)."""
    t = limpar(texto)
    if not minimo <= len(t) <= maximo:
        raise erro(422, f"{rotulo}: de {minimo} a {maximo} caracteres." if minimo else f"{rotulo}: até {maximo} caracteres.", campo)
    if _NUMEROS.search(t) or "@" in t or re.search(r"https?://|www\.", t, re.I):
        raise erro(422, f"{rotulo}: sem números longos (UC, CPF, telefone de cliente), e-mail nem site.", campo)
    return t


def _pedido_publico(p: dict) -> dict:
    return {"id": p["id"], "nome": p["nome"], "cidade": p["cidade"], "contato": p["contato"], "observacao": p["observacao"],
            "status": p["status"], "motivo_recusa": p["motivo_recusa"], "radio_id": p["radio_id"], "por": p["criado_por_nome"],
            "criado_em": p["criado_em"].isoformat(), "resolvido_por": p["resolvido_por_nome"],
            "resolvido_em": p["resolvido_em"].isoformat() if p["resolvido_em"] else None}


@rotas.post("/api/radios/pedidos")
def pedir_radio(dados: PedidoRadio, u: dict = Depends(exigir("pedir_radio"))) -> dict:
    """O Operador pede ao Admin da empresa o cadastro de uma rádio (contato da rádio, nunca de cliente)."""
    nome = limpar(dados.nome)
    if not 2 <= len(nome) <= 80:
        raise erro(422, "Nome da rádio: de 2 a 80 caracteres.", "nome")
    cidade = limpar(dados.cidade)
    if not 2 <= len(cidade) <= 80:
        raise erro(422, "Cidade da rádio: de 2 a 80 caracteres.", "cidade")
    contato = limpar(dados.contato)
    if contato and problema_email(contato.lower()) and not 10 <= len(re.sub(r"\D", "", contato)) <= 13:
        raise erro(422, "Contato da rádio: o e-mail ou o telefone da rádio, com o DDD.", "contato")
    if len(contato) > 120:
        raise erro(422, "Contato da rádio: até 120 caracteres.", "contato")
    observacao = _texto_livre(dados.observacao, "Observação", "observacao", 0, 300)
    if banco.pedido_aberto_igual(u["empresa_id"], nome, cidade):
        raise erro(409, "Já existe um pedido aberto para esta rádio nesta cidade.", "nome")
    id_ = banco.criar_pedido(u["empresa_id"], u["id"], u["nome"], {"nome": nome, "cidade": cidade, "contato": contato,
                                                                    "observacao": observacao})
    banco_acesso.registrar("pediu cadastro de rádio", f"{nome} ({cidade}), pedido {id_}", u["id"], u["empresa_id"])
    return {"pedido": _pedido_publico(banco.pedido(id_, u["empresa_id"]))}


@rotas.get("/api/radios/pedidos")
def listar_pedidos(u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """O Admin da empresa vê os pedidos da empresa; o Operador, os que ele fez."""
    so_meus = None if u["perfil"] == "admin_empresa" else u["id"]
    return {"pedidos": [_pedido_publico(p) for p in banco.pedidos(u["empresa_id"], so_meus)]}


@rotas.post("/api/radios/pedidos/{id_}/recusar")
def recusar_pedido(id_: int, dados: Recusa, u: dict = Depends(exigir("gerenciar_radios"))) -> dict:
    p = banco.pedido(id_, u["empresa_id"])
    if not p:
        raise HTTPException(404, "Pedido não encontrado nesta empresa.")
    motivo = _texto_livre(dados.motivo, "Motivo da recusa", "motivo", 3, 300)
    if not banco.recusar_pedido(id_, u["empresa_id"], motivo, u["nome"]):
        raise erro(409, "Este pedido de rádio já foi atendido ou recusado.")
    banco_acesso.registrar("recusou pedido de rádio", f"pedido {id_}: {p['nome']} ({p['cidade']}), pedido por {p['criado_por_nome']}: {motivo}",
                           u["id"], u["empresa_id"])
    return {"pedido": _pedido_publico(banco.pedido(id_, u["empresa_id"]))}


# ---------- Aviso: rádios sugeridas, PDF e envios ----------
def _aviso(id_: int, u: dict, ativo: bool = False) -> dict:
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    if ativo and a.get("status") == "cancelado":
        raise HTTPException(409, "Este desligamento foi cancelado: nada é enviado.")
    return a


def _municipio(a: dict, codigo: str) -> dict:
    m = next((m for m in a["municipios"] if m.get("codigo_ibge") == codigo), None)
    if not m:
        raise HTTPException(404, "Município não encontrado neste aviso.")
    return m


@rotas.get("/api/historico/{id_}/radios")
def sugerir_radios(id_: int, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Para cada município do aviso: as rádios que alcançam as comunidades afetadas e as comunidades sem rádio."""
    a = _aviso(id_, u)
    radios = banco.radios(u["empresa_id"])
    return {"radios": [_radio_publica(r) for r in radios],
            "municipios": [{"codigo_ibge": m["codigo_ibge"], "nome": m["nome"], **alcance_.cobertura(radios, m)} for m in a["municipios"]]}


def _texto_seguro(texto: str, cfg: dict, a: dict) -> str:
    """O texto que vai para a rádio: de 1 a 3.000 caracteres, sem número longo (UC, CPF), e-mail nem site.
    O telefone de atendimento e o código do aviso são permitidos."""
    t = " ".join(str(texto).replace("\r", "").split())
    if not 1 <= len(t) <= mensagem.MAX_MENSAGEM:
        raise erro(422, "Texto do aviso: de 1 a 3.000 caracteres.", "texto")
    resto = t
    for permitido in (cfg["telefone"], a.get("codigo") or ""):
        if permitido:
            resto = resto.replace(permitido, " ")
    if _NUMEROS.search(resto) or "@" in resto or re.search(r"https?://|www\.", resto, re.I):
        raise erro(422, "O texto não pode ter números longos (UC, CPF, telefone de cliente), e-mail nem site.", "texto")
    return t


def _gerar_pdf(a: dict, m: dict, texto: str, u: dict, cfg: dict) -> tuple[str, bytes]:
    situacao = lambda c: "vizinha" if c.get("fragmento") else "parte" if c.get("parcial") else "inteira"
    nome = lambda c: f"{alcance_.nome_base(c['nome'])} ({'Sede' if c.get('distrito') == m['nome'] else c.get('distrito')})"
    grupos = {s: [nome(c) for c in m["comunidades"] if situacao(c) == s] for s in ("inteira", "parte", "vizinha")}
    q, i = a["criado_em"].astimezone(BRASILIA), a.get("idioma") or "pt-BR"
    solicitado = rotulos.t(i, "solicitado", nome=a["usuario"], perfil=rotulos.perfil(i, a.get("usuario_perfil")),
                           quando=rotulos.t(i, "quando", d=q), codigo=a.get("codigo") or "-")
    data, horario = idiomas.localizar(a["data"], a["horario"], i)
    prazo = rotulos.prazo(i, f"{a['resumo']['prazo']['antecedencia_minima']} ({a['resumo']['prazo']['norma']})")
    pdf = pdf_radio.roteiro(municipio=m["nome"], uf=m["uf"], empresa=cfg["nome_mensagem"], data=data, horario=horario,
                            tipo=a.get("motivo") or "", texto=texto, inteiras=grupos["inteira"], parciais=grupos["parte"],
                            vizinhas=grupos["vizinha"], prazo=prazo,
                            vital_sim=m["equipamento_vital"]["sim"], vital_a_confirmar=m["equipamento_vital"]["a_confirmar"],
                            solicitado=solicitado, aviso_id=a["id"], aviso_ficticio=AVISO_FICTICIO, gerado_por=u["nome"],
                            gerado_em=datetime.now(BRASILIA), idioma=i)
    base = "-".join(sem_acento(m["nome"]).lower().split()) or "municipio"
    return f"farol-aviso-{base}-{a['data'].replace('/', '-')}.pdf", pdf


class PedidoPdf(BaseModel):
    texto: str = Field(max_length=mensagem.MAX_MENSAGEM + 500)


@rotas.post("/api/historico/{id_}/municipios/{codigo}/pdf")
def baixar_pdf(id_: int, codigo: str, dados: PedidoPdf, u: dict = Depends(exigir("gerar_aviso"))) -> Response:
    """O PDF do roteiro para a rádio, gerado no servidor com o texto (editado) do município; fica na auditoria."""
    a = _aviso(id_, u)
    m, cfg = _municipio(a, codigo), config_empresa(u["empresa_id"])
    nome, pdf = _gerar_pdf(a, m, _texto_seguro(dados.texto, cfg, a), u, cfg)
    banco_acesso.registrar("gerou PDF", f"aviso {id_}, município {codigo}", u["id"], u["empresa_id"])
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nome}"'})


class PedidoEnvio(BaseModel):
    municipio: str = Field(pattern=r"^\d{7}$")
    radio_id: int
    canal: Literal["email", "whatsapp", "copia"]
    texto: str = Field(max_length=mensagem.MAX_MENSAGEM + 500)
    valor: str | float = Field(...)
    cobranca: Literal["fechado", "minuto"]
    custo_antigo: str | float | None = None


def _envio_publico(e: dict) -> dict:
    return {"id": e["id"], "aviso_id": e["aviso_id"], "municipio": e["municipio"], "municipio_nome": e["municipio_nome"],
            "radio_id": e["radio_id"], "radio_nome": e["radio_nome"], "canal": e["canal"], "destino": e["destino"],
            "status": e["status"], "valor": _dinheiro(e["valor"]), "cobranca": e["cobranca"], "custo": _dinheiro(e["custo"]),
            "custo_antigo": _dinheiro(e["custo_antigo"]), "economia": _dinheiro(e["economia"]), "economia_tipo": e["economia_tipo"],
            "segundos": e["segundos"], "segundos_hoje": e["segundos_hoje"], "tempo_economizado": e["tempo_economizado"],
            "por": e["criado_por_nome"], "criado_em": e["criado_em"].isoformat(),
            "confirmado_em": e["confirmado_em"].isoformat() if e["confirmado_em"] else None, "arquivos": list(e["arquivos"] or [])}


def _limite_emails(usuario_id: int) -> None:
    agora, fila = time.monotonic(), _emails[usuario_id]
    while fila and agora - fila[0] > JANELA_EMAILS:
        fila.popleft()
    if len(fila) >= LIMITE_EMAILS:
        raise HTTPException(429, f"Limite de {LIMITE_EMAILS} e-mails para rádios por hora atingido. Tente mais tarde.")
    fila.append(agora)


def url_publica() -> str:
    """O endereço público do Norte para o link do e-mail (FAROL_URL_PUBLICA); nunca o Host do pedido."""
    return (segredo("FAROL_URL_PUBLICA") or "http://127.0.0.1:8000").rstrip("/")


@rotas.post("/api/historico/{id_}/envios")
def enviar(id_: int, dados: PedidoEnvio, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Envia o aviso de um município para uma rádio (e-mail, WhatsApp ou cópia), com o valor gravado no envio."""
    a = _aviso(id_, u, ativo=True)
    m, cfg = _municipio(a, dados.municipio), config_empresa(u["empresa_id"])
    r = banco.radio(dados.radio_id, u["empresa_id"])
    if not r or not r["ativa"]:
        raise HTTPException(404, "Rádio não encontrada nesta empresa.")
    destino = r["email"] if dados.canal == "email" else r["whatsapp"] if dados.canal == "whatsapp" else ""
    if dados.canal != "copia" and not destino:
        raise HTTPException(422, f"Esta rádio não tem {'e-mail' if dados.canal == 'email' else 'WhatsApp'} cadastrado.")
    texto = _texto_seguro(dados.texto, cfg, a)
    try:
        valor = economia.reais(dados.valor)
    except ValueError as e:
        raise erro(422, f"Valor: {e}.", "valor") from None
    try:
        custo_antigo = economia.reais(dados.custo_antigo)
    except ValueError as e:
        raise erro(422, f"Custo antigo: {e}.", "custo_antigo") from None
    if valor is None:
        raise erro(422, "Informe o valor do envio (R$).", "valor")
    if (ja := banco.envio_repetido({"aviso_id": a["id"], "municipio": m["codigo_ibge"], "radio_id": r["id"], "canal": dados.canal,
                                    "texto": texto, "valor": valor, "cobranca": dados.cobranca})):
        raise erro(409, f"Este envio acabou de ser registrado (envio nº {ja}). Para repetir, espere um minuto.")
    if dados.canal == "email":
        if not correio.ligado():
            raise HTTPException(503, "O envio por e-mail está desligado neste servidor. Use o WhatsApp ou copie a mensagem.")
        if not cofre.disponivel():
            raise HTTPException(503, "Sem a chave do cofre (FAROL_CHAVE_ARQUIVOS): o PDF e o MP3 enviados não seriam guardados.")
        _limite_emails(u["id"])
    seg, seg_hoje = segundos(texto), (m.get("hoje") or {}).get("segundos")
    eco = economia.calcular(dados.cobranca, valor, seg, seg_hoje, custo_antigo)
    envio_id = banco.criar_envio({
        "empresa_id": u["empresa_id"], "aviso_id": a["id"], "municipio": m["codigo_ibge"], "municipio_nome": m["nome"],
        "radio_id": r["id"], "radio_nome": r["nome"], "canal": dados.canal, "destino": destino or "", "texto": texto,
        "valor": valor, "cobranca": dados.cobranca, "custo": eco["custo"], "custo_antigo": custo_antigo, "economia": eco["economia"],
        "economia_tipo": eco["economia_tipo"], "segundos": seg, "segundos_hoje": seg_hoje, "tempo_economizado": eco["tempo_economizado"],
        "status": "preparando" if dados.canal == "email" else "enviado", "criado_por": u["id"], "criado_por_nome": u["nome"]})
    banco_acesso.registrar("informou o valor do envio", f"envio {envio_id} ({r['nome']}): R$ {valor:.2f}, "
                           f"{economia.COBRANCAS[dados.cobranca]}" + (f", custo antigo informado R$ {custo_antigo:.2f}" if custo_antigo is not None else "")
                           + (f", economia {eco['economia_tipo']} R$ {eco['economia']:.2f}" if eco["economia"] is not None else ""),
                           u["id"], u["empresa_id"])
    if m.get("texto_final") != texto:
        banco_acesso.texto_final(a["id"], u["empresa_id"], m["codigo_ibge"], texto)
    resposta = {}
    if dados.canal == "email":
        resposta = _por_email(a, m, r, texto, envio_id, u, cfg)
    elif dados.canal == "whatsapp":
        numero = destino if len(destino) > 11 else "55" + destino
        resposta["whatsapp_url"] = f"https://wa.me/{numero}?text={quote(texto)}"
        banco_acesso.registrar("enviou por WhatsApp", f"envio {envio_id}: aviso {a['id']}, {m['nome']} para {r['nome']}", u["id"], u["empresa_id"])
    else:
        banco_acesso.registrar("copiou a mensagem para a rádio", f"envio {envio_id}: aviso {a['id']}, {m['nome']} para {r['nome']}",
                               u["id"], u["empresa_id"])
    return {"envio": _envio_publico(banco.envio(envio_id, u["empresa_id"])), **resposta}


def _por_email(a: dict, m: dict, r: dict, texto: str, envio_id: int, u: dict, cfg: dict) -> dict:
    nome_pdf, pdf = _gerar_pdf(a, m, texto, u, cfg)
    mp3, i = None, a.get("idioma") or "pt-BR"
    if AUDIO and i in audio.idiomas_com_voz():   # idioma sem voz com licença adequada: o e-mail vai só com o PDF
        try:
            dados_mp3, _ = audio.mp3(texto, i)
            mp3 = (nome_pdf.replace(".pdf", ".mp3"), dados_mp3)
        except Exception:  # noqa: BLE001 (sem o MP3, o e-mail vai com o PDF e diz isso)
            mp3 = None
    for tipo, (nome, dados) in (("pdf", (nome_pdf, pdf)), ("mp3", mp3)) if mp3 else (("pdf", (nome_pdf, pdf)),):
        banco.guardar_arquivo(envio_id, u["empresa_id"], tipo, nome, len(dados), cofre.cifrar(dados, u["empresa_id"], envio_id, tipo))
    token = secrets.token_urlsafe(32)
    banco.definir_token(envio_id, token)
    data, horario = idiomas.localizar(a["data"], a["horario"], i)
    msg = email_radio.mensagem(remetente=correio.remetente(), destino=r["email"], municipio=m["nome"], uf=m["uf"], data=data,
                               horario=horario, empresa=cfg["nome_mensagem"], texto=texto, codigo=a.get("codigo") or "",
                               link_confirmar=f"{url_publica()}/confirmar/{token}", pdf=(nome_pdf, pdf), mp3=mp3,
                               aviso_ficticio=AVISO_FICTICIO, idioma=i)
    banco.mudar_status(envio_id, "enviado")
    banco_acesso.registrar("enviou por e-mail", f"envio {envio_id}: aviso {a['id']}, {m['nome']} para {r['nome']} ({r['email']})"
                           f", PDF{' e MP3' if mp3 else ''}", u["id"], u["empresa_id"])
    try:
        correio.enviar(msg)
    except correio.FalhaEnvio as e:
        banco.mudar_status(envio_id, "falhou")
        banco_acesso.registrar("envio por e-mail falhou", f"envio {envio_id}: {e}", u["id"], u["empresa_id"])
        return {"erro": f"O e-mail não foi entregue: {e}."}
    banco.mudar_status(envio_id, "entregue")
    banco_acesso.registrar("e-mail entregue ao servidor de e-mail", f"envio {envio_id} para {r['nome']}", u["id"], u["empresa_id"])
    return {}


@rotas.get("/api/historico/{id_}/envios")
def envios_do_aviso(id_: int, u: dict = Depends(exigir("ver_historico"))) -> dict:
    _aviso(id_, u)
    return {"envios": [_envio_publico(e) for e in banco.envios(u["empresa_id"], id_)]}


@rotas.get("/api/envios/{id_}/arquivos/{tipo}")
def baixar_arquivo(id_: int, tipo: Literal["pdf", "mp3"], u: dict = Depends(exigir("ver_historico"))) -> Response:
    """O PDF ou o MP3 que foi para a rádio, decifrado na hora (fica na auditoria)."""
    e = banco.envio(id_, u["empresa_id"])
    arq = banco.arquivo(id_, u["empresa_id"], tipo) if e else None
    if not arq:
        raise HTTPException(404, "Arquivo não encontrado nesta empresa.")
    try:
        dados = cofre.decifrar(arq["cifrado"], u["empresa_id"], id_, tipo)
    except cofre.SemChave:
        raise HTTPException(503, "Sem a chave do cofre neste servidor.") from None
    except cofre.Violado:
        banco_acesso.registrar("arquivo enviado não confere (cofre)", f"envio {id_}, {tipo}", u["id"], u["empresa_id"])
        raise HTTPException(409, "O arquivo guardado não confere (alterado). Nada foi entregue.") from None
    banco_acesso.registrar(f"baixou o {tipo.upper()} enviado", f"envio {id_} ({e['radio_nome']})", u["id"], u["empresa_id"])
    return Response(dados, media_type="application/pdf" if tipo == "pdf" else "audio/mpeg",
                    headers={"Content-Disposition": f'attachment; filename="{arq["nome"]}"'})


# ---------- Confirmação pela rádio (pública, sem login) ----------
def _pagina(html: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(html, status_code=status, headers={"Content-Security-Policy": CSP_PAGINA, "Cache-Control": "no-store"})


def _token_valido(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{40,60}", token or ""))


@rotas.get("/confirmar/{token}", include_in_schema=False)
def pagina_confirmar(token: str) -> HTMLResponse:
    """Só mostra (não confirma): o link pode ser aberto por um leitor de e-mail automático."""
    e = banco.envio_pelo_token(token) if _token_valido(token) else None
    if not e:
        return _pagina(confirmacao.pagina("Link inválido", "Este link de confirmação não existe."), 404)
    i, T = e.get("idioma") or "pt-BR", lambda chave, **v: rotulos.t(e.get("idioma"), chave, **v)
    if e["confirmado_em"]:
        return _pagina(confirmacao.pagina(T("conf_ja"), T("conf_ja_texto", municipio=e["municipio_nome"]), idioma=i))
    if e["token_expira"] < datetime.now(e["token_expira"].tzinfo):
        return _pagina(confirmacao.pagina(T("conf_vencido"), T("conf_vencido_texto"), idioma=i), 410)
    data, horario = idiomas.localizar(e["data"], e["horario"], i)
    return _pagina(confirmacao.pagina(T("conf_titulo"), T("conf_texto", radio=e["radio_nome"], municipio=e["municipio_nome"], data=data,
                                                          horario=horario), acao=f"/confirmar/{token}", idioma=i))


@rotas.post("/confirmar/{token}", include_in_schema=False)
def confirmar(token: str, request: Request) -> HTMLResponse:
    origem = request.headers.get("origin")
    if origem and origem != "null" and urlsplit(origem).netloc != request.headers.get("host", ""):
        return _pagina(confirmacao.pagina("Não confirmado", "Pedido de outra origem."), 403)
    e = banco.confirmar(token) if _token_valido(token) else None
    if not e:
        return _pagina(confirmacao.pagina("Não confirmado", "O link não vale mais (já usado, vencido ou inexistente)."), 410)
    banco_acesso.registrar("rádio confirmou o recebimento", f"envio {e['id']}: {e['radio_nome']}, aviso {e['aviso_id']} ({e['municipio_nome']})",
                           None, e["empresa_id"])
    i = (banco.envio_pelo_token(token) or {}).get("idioma") or "pt-BR"
    return _pagina(confirmacao.pagina(rotulos.t(i, "conf_ok"), rotulos.t(i, "conf_ok_texto", radio=e["radio_nome"]), idioma=i))
