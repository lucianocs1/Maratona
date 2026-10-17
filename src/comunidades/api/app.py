"""API do Norte (FastAPI): recebe a planilha de UCs afetadas e devolve municípios, comunidades e aviso.

Controller: lê o arquivo (api/leitura.py), traduz as linhas para o JSON validado (nucleo/planilha.py),
confere de novo por uma rotina independente (api/conferencia.py), busca no banco a base territorial
dos municípios que as coordenadas tocam (banco/base_territorial.py) e chama o núcleo
(nucleo/afetados.py). A planilha fica só em memória e é descartada: nada de número de UC na resposta,
no banco ou no log, e nada de coordenada no banco ou no log. Os problemas citam só o número da linha.
A resposta traz os pontos das UCs (só latitude, longitude e comunidade, sem o número) para o mapa de
quem enviou; eles não entram no histórico.

Dois passos: /api/planilha (Conferir) devolve a conferência, as travas (nucleo/travas.py) e o pacote
assinado (api/pacote.py); /api/avisos (Gerar) só aceita esse pacote, com a confirmação humana, e grava.
Entre os dois, a escolha de quem será desligado (nucleo/selecao.py): a planilha pode ser a base de clientes.
/api/planilha devolve também o pacote "base" e o que a tela precisa para escolher (linha a linha, sem a UC);
/api/planilha/escolha recebe o critério e devolve a conferência só das escolhidas, com o pacote "escolha"
(o critério assinado junto). O pacote de /api/planilha já vale como "a planilha inteira" (inativas fora).

Toda rota, menos /api/saude e /api/entrar, exige login (api/acesso.py), e a permissão é conferida
no servidor. Cada planilha processada fica no histórico da empresa só como agregado.
Uso: uv run uvicorn comunidades.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
"""

import functools
import hashlib
import mimetypes
import logging
import secrets
import time
import traceback
from collections import Counter, OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import shapely
from pyproj import Transformer

from .. import semente, senhas
from ..config import sem_acento
from ..apresentacao import audio, copiloto, traducao
from ..banco import acesso as banco_acesso
from ..banco import base_territorial as banco
from ..banco import clientes as banco_clientes
from ..banco import localidades as banco_localidades
from ..banco import rede as banco_rede
from ..banco import radios as banco_radios
from ..banco import relatorios as banco_relatorios
from ..fontes.base_territorial import CRS_BASE
from .. import correio
from ..nucleo import agrupamento, auditoria, consultas, esquema_planilha, idiomas, mensagem, painel, selecao, travas, verificador
from ..nucleo import tipos_desligamento as tipos
from ..nucleo.afetados import BaseMunicipio, afetados, localizar, municipio_de
from ..nucleo.desligamento import PALAVRAS_POR_SEGUNDO, aviso_antigo_de_locais, locais_de
from ..nucleo import planilha
from ..nucleo.acesso import PERFIS
from ..nucleo.coordenadas import Area
from ..nucleo.motivos import TEXTOS, Motivo
from ..nucleo.planilha import MAX_LINHAS, PlanilhaInvalida, modelo_csv
from . import conferencia, leitura
from . import pacote as pacote_
from .comum import AUDIO, AVISO_FICTICIO, BRASILIA, DIST, MAX_TEXTO, config_empresa, erro, segundos
from .comum import texto_do_aviso as _texto_do_aviso
from .area_atuacao import rotas as area_rotas
from .radio import rotas as radio_rotas
from .relatorios import painel_do_mes
from .relatorios import rotas as relatorio_rotas
from .acesso import PRODUCAO, exigir, rotas, usuario_atual
from .proxy import ProxyConfiavel

MAX_PROBLEMAS = 200          # problemas listados um a um na resposta (o total vem sempre)
CASAS_PONTO = 5              # casas decimais dos pontos no mapa (cerca de 1 m)
MAX_AVISOS_PAINEL = 5000      # avisos considerados no dashboard (os mais recentes)
GEO_PARA_BASE = Transformer.from_crs("EPSG:4674", CRS_BASE, always_xy=True)

@asynccontextmanager
async def _ao_subir(app):
    """Ao subir: o banco que já existe recebe as tabelas e colunas novas (só acréscimos; nada é apagado). Sem banco
    configurado (testes sem banco) ou sem permissão, a API sobe assim mesmo e o log diz o que fazer."""
    try:
        _log.warning("%s", banco_acesso.atualizar_esquema())
        if semente.semear_area_demo():   # banco de antes da área de atuação: a EMG recebe a concessão já carregada
            _log.warning("área de atuação da EMG (demonstração) carregada")
    except Exception as e:   # sem DATABASE_URL ou banco fora do ar: as rotas que usam o banco respondem com o erro delas
        _log.warning("esquema do banco não conferido ao subir (%s)", type(e).__name__)
    yield


# em produção, sem a documentação interativa (é a única parte sem CSP: carrega o Swagger de fora)
app = FastAPI(title="Norte", version="0.1.0", docs_url=None if PRODUCAO else "/api/docs",
              openapi_url=None if PRODUCAO else "/api/openapi.json", redoc_url=None, lifespan=_ao_subir)
app.include_router(rotas)
app.include_router(area_rotas)
app.include_router(radio_rotas)
app.include_router(relatorio_rotas)
if PRODUCAO:  # IP e esquema de quem acessa, pelo proxy do Render (api/proxy.py)
    app.add_middleware(ProxyConfiavel)


_log = logging.getLogger("farol.api")


@app.exception_handler(StarletteHTTPException)
async def _erro_http(request, e: StarletteHTTPException):
    """As mensagens de erro da API no idioma da tela de quem pediu (cabeçalho X-Farol-Idioma; Fase K)."""
    idioma = traducao.idioma_do_pedido(request.headers.get("x-farol-idioma"))
    if idioma != traducao.PADRAO and isinstance(e.detail, str):
        e = StarletteHTTPException(e.status_code, traducao.texto(e.detail, idioma), headers=e.headers)
    return await http_exception_handler(request, e)


@app.exception_handler(Exception)
def _erro_inesperado(request, erro: Exception) -> JSONResponse:
    """Erro não previsto: nada é gerado nem gravado (o histórico só é gravado no fim de tudo) e a
    pessoa recebe um código para o suporte. O log técnico leva só o tipo do erro e onde ele ocorreu
    (arquivo e linha), nunca a mensagem nem valores: assim nenhum dado da planilha vai para o log."""
    codigo = f"ERR-{secrets.token_hex(3).upper()}"
    onde = " <- ".join(f"{Path(q.filename).name}:{q.lineno}" for q in traceback.extract_tb(erro.__traceback__)[-4:][::-1])
    _log.error("%s %s %s em %s", codigo, request.url.path, type(erro).__name__, onde)
    texto = traducao.texto(f"Ocorreu um erro e nada foi gerado (código {codigo}).", request.headers.get("x-farol-idioma"))
    return JSONResponse({"detail": texto}, status_code=500)


_PYDANTIC = {   # tipo do erro de validação -> como a pessoa lê (a mensagem original vem em inglês)
    "missing": lambda c: "preencha este campo.", "string_too_long": lambda c: f"no máximo {c.get('max_length')} caracteres.",
    "string_too_short": lambda c: f"pelo menos {c.get('min_length')} caracteres.", "too_long": lambda c: f"no máximo {c.get('max_length')} itens.",
    "less_than_equal": lambda c: f"no máximo {c.get('le')}.", "greater_than_equal": lambda c: f"no mínimo {c.get('ge')}.",
    "less_than": lambda c: f"menor que {c.get('lt')}.", "greater_than": lambda c: f"maior que {c.get('gt')}.",
    "int_parsing": lambda c: "tem de ser um número inteiro.", "float_parsing": lambda c: "tem de ser um número.",
    "int_from_float": lambda c: "tem de ser um número inteiro.", "literal_error": lambda c: "valor fora das opções.",
    "string_pattern_mismatch": lambda c: "formato inválido.", "bool_parsing": lambda c: "sim ou não.",
}


@app.exception_handler(RequestValidationError)
def _validacao(request, e: RequestValidationError) -> JSONResponse:
    """Dado com formato errado (número fora da faixa, campo faltando…): a mensagem em português e o
    campo no cabeçalho X-Farol-Campo, para a tela marcar o erro nele. O valor digitado não volta."""
    primeiro = (e.errors() or [{}])[0]
    campo = next((str(x) for x in reversed(primeiro.get("loc", ())) if isinstance(x, str) and x not in ("body", "query", "path")), "")
    texto = _PYDANTIC.get(primeiro.get("type"), lambda c: "valor inválido.")(primeiro.get("ctx") or {})
    detalhe = traducao.texto(f"Confira o campo {campo or 'informado'}: {texto}", request.headers.get("x-farol-idioma"))
    return JSONResponse({"detail": detalhe, "campo": campo or None}, status_code=422,
                        headers={"X-Farol-Campo": campo} if campo else None)


@app.exception_handler(senhas.Ocupado)
def _ocupado(request, erro: senhas.Ocupado) -> JSONResponse:
    """Hashes de senha demais ao mesmo tempo (memória do servidor): recusa e pede para tentar de novo."""
    return JSONResponse({"detail": str(erro)}, status_code=503, headers={"Retry-After": "5"})


APRESENTACAO = Path(__file__).resolve().parents[1] / "apresentacao"
TELA = APRESENTACAO / "app"            # a tela (index.html, app.js, app.css)
# A tela só fala com a própria API e só busca de fora os fundos de mapa da Esri
CSP = "; ".join([
    "default-src 'none'", "script-src 'self'", "style-src 'self'", "font-src 'self'", "connect-src 'self'",
    "img-src 'self' data: https://server.arcgisonline.com", "manifest-src 'self'",
    "media-src 'self' blob:",  # o tocador do áudio do aviso (o MP3 vem da API e toca de um blob local)
    "base-uri 'none'", "form-action 'none'", "frame-ancestors 'none'", "object-src 'none'",
])
SEM_CSP = ("/api/docs", "/api/openapi.json")  # documentação interativa (desenvolvimento): carrega o Swagger de fora


@app.middleware("http")
async def cabecalhos(request, chamar):
    r = await chamar(request)
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Referrer-Policy"] = "no-referrer"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    if not request.url.path.startswith(SEM_CSP) and "content-security-policy" not in r.headers:
        r.headers["Content-Security-Policy"] = CSP
    r.headers.setdefault("Cache-Control", "no-store")  # resultados de planilha nunca ficam em cache
    if PRODUCAO:  # só HTTPS daqui para a frente (o Render serve em HTTPS)
        r.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return r


@app.get("/", include_in_schema=False)
def tela() -> FileResponse:
    return FileResponse(TELA / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/config")
def config(request: Request, u: dict = Depends(usuario_atual)) -> dict:
    """O que a tela precisa da configuração da distribuidora (nada secreto). Os tipos de desligamento vêm no idioma da
    tela (cabeçalho X-Farol-Idioma); o idioma padrão do aviso é o da empresa (Fase K)."""
    tela = traducao.idioma_do_pedido(request.headers.get("x-farol-idioma"))
    cfg = config_empresa(u["empresa_id"]) if u.get("empresa_id") else {}
    return {"distribuidora": DIST.nome, "telefone": DIST.telefone, "aviso_ficticio": AVISO_FICTICIO,
            "idiomas": {k: v["nome"] for k, v in idiomas.IDIOMAS.items()}, "idioma_padrao": cfg.get("idioma_padrao") or DIST.idioma_padrao,
            "audio_idiomas": audio.idiomas_com_voz() if AUDIO else [], "idioma_tela": tela,
            "prazo_legal_horas": DIST.prazo_legal_horas, "prazo_vital_dias_uteis": DIST.prazo_vital_dias_uteis,
            "norma": DIST.norma, "palavras_por_segundo": PALAVRAS_POR_SEGUNDO,
            "limites": {"bytes": leitura.MAX_BYTES, "linhas": MAX_LINHAS}, "audio": AUDIO, "radio": DIST.radio.para_tela(),
            "ia": {"ativa": copiloto.ativo(), "provedor": copiloto.nome_do_provedor(),
                   "pedidos": {k: v[0] for k, v in copiloto.PEDIDOS.items()}, "max_livre": copiloto.MAX_LIVRE,
                   "perguntas_exemplo": consultas.EXEMPLOS, "max_pergunta": consultas.MAX_PERGUNTA},
            "tipos": tipos.rotulos(tela), "tipo_padrao": tipos.PADRAO, "max_outro": tipos.MAX_OUTRO, "email": correio.ligado()}


def _na_area(u: dict, codigo: str) -> None:
    """O mapa operacional: só os perfis da empresa e só os municípios da área de atuação dela. O Admin do Norte não
    vê o mapa operacional (o dele é o mapa das empresas)."""
    if u["perfil"] == "admin_farol":
        raise HTTPException(403, "Seu perfil não tem acesso a isto.")
    if codigo not in banco_acesso.area(u["empresa_id"]):
        raise HTTPException(404, "Município fora da área de atuação da empresa.")


@app.get("/api/concessao")
def concessao(u: dict = Depends(usuario_atual)) -> JSONResponse:
    """Contorno dos municípios da base (dados públicos do IBGE), para o mapa da tela: para os perfis da empresa, só
    os da área de atuação dela."""
    g = banco.concessao_geojson()
    if u["perfil"] != "admin_farol":
        area = banco_acesso.area(u["empresa_id"])
        g = {**g, "features": [f for f in g["features"] if f["properties"]["codigo_ibge"] in area]}
    return JSONResponse(g, headers={"Cache-Control": "private, no-cache"})


@app.get("/api/municipios/{codigo}/comunidades")
def comunidades(codigo: str, u: dict = Depends(usuario_atual)) -> JSONResponse:
    """Território de cada comunidade do município (dados públicos), para o mapa da tela."""
    if not (len(codigo) == 7 and codigo.isdigit()):
        raise HTTPException(422, "codigo: use o código IBGE do município (7 dígitos).")
    _na_area(u, codigo)
    g = banco.comunidades_geojson(codigo)
    if g is None:
        raise HTTPException(404, "Município fora da base da concessão.")
    return JSONResponse(g, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/municipios/{codigo}/rede")
def rede(codigo: str, u: dict = Depends(usuario_atual)) -> JSONResponse:
    """Rede elétrica FICTÍCIA do município (demonstração): média tensão, subestação, chaves e trafos."""
    if not (len(codigo) == 7 and codigo.isdigit()):
        raise HTTPException(422, "codigo: use o código IBGE do município (7 dígitos).")
    _na_area(u, codigo)
    r = banco_rede.rede_mapa(codigo)
    if r is None and codigo not in {c for c, _, _, _ in banco.contornos(CRS_BASE)}:
        raise HTTPException(404, "Município fora da base da concessão.")
    # município da concessão ainda sem a rede fictícia: null (resposta normal; um 404 sujaria o console a cada movimento do mapa)
    return JSONResponse(r, headers={"Cache-Control": "private, max-age=3600"})


def _area_do_mapa(u: dict) -> list[str]:
    """Os municípios cujos clientes fictícios e localidades oficiais o perfil pode ver: só os da área de atuação da empresa; o Admin do Norte
    não vê o mapa operacional."""
    if u["perfil"] == "admin_farol":
        raise HTTPException(403, "Seu perfil não tem acesso a isto.")
    return sorted(banco_acesso.area(u["empresa_id"]))


@app.get("/api/localidades-oficiais")
def localidades_oficiais(u: dict = Depends(usuario_atual)) -> JSONResponse:
    """Localidades oficiais do IBGE (Censo 2022) da área da empresa, para a camada do mapa: [lat, lon, nome, categoria,
    município]. Dado público; os três perfis da empresa veem, o Admin do Norte não (mapa operacional)."""
    return JSONResponse({"fonte": "IBGE, Censo 2022", "localidades": banco_localidades.para_o_mapa(_area_do_mapa(u))},
                        headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/clientes/resumo")
def clientes_resumo(u: dict = Depends(exigir("gerar_aviso"))) -> JSONResponse:
    """Contagens dos clientes FICTÍCIOS da área da empresa (total, por classe, vitais e inativas): só números. Só quem gera
    aviso (o Consulta não vê pontos de cliente, como já é com as UCs da planilha)."""
    return JSONResponse({"ficticio": True, **banco_clientes.totais(_area_do_mapa(u))}, headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/clientes")
def clientes(sul: float, oeste: float, norte: float, leste: float, zoom: int, u: dict = Depends(exigir("gerar_aviso"))) -> JSONResponse:
    """Clientes FICTÍCIOS na janela do mapa: de longe a densidade em quadradinhos; de perto (zoom 15 ou mais) os pontos
    com classe, vital e ativa. Nunca número de UC, titular ou endereço."""
    codigos = _area_do_mapa(u)
    if not (-90 <= sul < norte <= 90 and -180 <= oeste < leste <= 180 and 5 <= zoom <= 20):
        raise HTTPException(422, "Janela do mapa inválida (sul, oeste, norte, leste e zoom de 5 a 20).")
    r = banco_clientes.consultar(codigos, sul, oeste, norte, leste, zoom)
    return JSONResponse({"ficticio": True, **r}, headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/saude")
def saude() -> dict:
    return {"ok": True, "municipios": len(banco.contornos(CRS_BASE))}


@app.get("/api/modelo-planilha")
def modelo(u: dict = Depends(usuario_atual)) -> Response:
    banco_acesso.registrar("baixou o modelo da planilha", "modelo_planilha_farol.csv", u["id"], u["empresa_id"])
    # com BOM, para o Excel abrir os acentos certos
    return Response("﻿" + modelo_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="modelo_planilha_farol.csv"'})


def _bases(xy: np.ndarray, area: set[str] | None = None) -> tuple[list[BaseMunicipio], np.ndarray]:
    """Só as bases dos municípios que as UCs tocam (os contornos de todos decidem quais são) e dentro da área de
    atuação da empresa. Devolve também, por UC, se ela caiu num município fora dessa área."""
    todos = banco.contornos(CRS_BASE)
    vazio = np.empty((0, 2))
    leves = [BaseMunicipio(c, n, u, g, vazio, np.array([], dtype=object), np.array([], dtype=object))
             for c, n, u, g in todos]
    qual = municipio_de(xy, leves)
    fora_area = np.zeros(len(xy), dtype=bool)
    if area is not None:
        fora_area = np.array([q >= 0 and todos[q][0] not in area for q in qual], dtype=bool)
    usados = sorted(set(qual[~fora_area]) - {-1})
    bases = []
    for i in usados:
        c, n, u, g = todos[i]
        exy, com, dis = banco.enderecos(c, CRS_BASE)
        bases.append(BaseMunicipio(c, n, u, g, exy, com, dis))
    return bases, fora_area


def _pontos(ucs, comunidades=None, ordem=()) -> list[list]:
    """Pontos das UCs para o mapa de quem enviou a planilha: [lat, lon] ou [lat, lon, comunidade].
    Nunca o número da UC; não vão para o histórico (_guardar escolhe os campos que grava)."""
    lat, lon = ucs["LAT"].round(CASAS_PONTO).tolist(), ucs["LON"].round(CASAS_PONTO).tolist()
    if comunidades is None:
        return [[a, o] for a, o in zip(lat, lon)]
    posicao = {nome: i for i, nome in enumerate(ordem)}
    return [[a, o, posicao.get(c, -1)] for a, o, c in zip(lat, lon, comunidades)]


def _aviso_hoje(locais, data: str, horario: str) -> dict | None:
    """O aviso como é hoje (imóvel por imóvel, rua por rua), com os locais citados, as palavras e o tempo no ar.
    Pode listar imóveis e ruas (é o comunicado público que já vai ao rádio); nunca pessoas, UCs nem coordenadas.
    None se nenhuma UC do município tem local (não há o que comparar)."""
    if not locais_de(locais):
        return None
    texto = aviso_antigo_de_locais(locais, data, horario, DIST.regras)
    palavras = len(texto.split())
    # "lista": os locais, para _mensagens remontar o aviso de hoje com o mesmo modelo da empresa (não vai para o histórico)
    return {"texto": texto, "locais": len(locais_de(locais)), "palavras": palavras,
            "segundos": round(palavras / PALAVRAS_POR_SEGUNDO), "lista": locais_de(locais)}


def _prazo(vital: Counter, cfg: dict) -> dict:
    if vital["sim"]:
        regra = f"{DIST.prazo_vital_dias_uteis} dias úteis (há unidades com equipamento vital)"
    elif vital["a_confirmar"]:
        regra = f"{DIST.prazo_vital_dias_uteis} dias úteis até confirmar as unidades sem a informação de equipamento vital"
    else:
        regra = f"{DIST.prazo_legal_horas} horas"
    return {"antecedencia_minima": regra, "norma": DIST.norma, "planejamento_interno_dias": cfg["antecedencia_dias"]}


@functools.lru_cache(maxsize=1)
def _area() -> Area:
    """A área da concessão (os contornos dos municípios do banco) com a margem de 50 m, para o tradutor."""
    return Area(shapely.union_all([g for _, _, _, g in banco.contornos("EPSG:4674")]))


def _parametros(cfg: dict) -> planilha.Parametros:
    """Os parâmetros do tradutor: o fuso UTM é o da empresa; o resto, o da distribuidora."""
    c = DIST.planilha
    return planilha.Parametros(dentro=_area(), epsg_utm=cfg["epsg_utm"], isolado_km=c.ponto_isolado_km,
                               muitas_ucs=c.muitas_ucs_mesma_coordenada)


def _nome_arquivo(nome: str | None) -> str:
    """O nome do arquivo enviado, limpo: sem pasta, sem caracteres de controle, até 100 caracteres."""
    base = str(nome or "planilha").replace("\\", "/").rsplit("/", 1)[-1]
    return (planilha.limpar(base) or "planilha")[:100]


def _traduzir(conteudo: bytes, nome: str | None, aba: str | None, u: dict):
    """Arquivo -> JSON padronizado validado (nucleo/planilha.montar). O arquivo não é guardado."""
    tabela = leitura.ler_tabela(conteudo, aba)
    if not tabela.linhas:
        raise PlanilhaInvalida("A planilha não tem nenhuma linha de dados.")
    modelo = planilha.montar(
        tabela.campos, tabela.cabecalho, tabela.linhas, _parametros(config_empresa(u["empresa_id"])),
        arquivo={"nome": _nome_arquivo(nome), "sha256": hashlib.sha256(conteudo).hexdigest(), "formato": tabela.formato,
                 "aba": tabela.aba, "colunas_ignoradas": tabela.colunas_ignoradas},
        empresa=(u.get("empresa_nome") or "")[:120], gerado_em=datetime.now(BRASILIA).strftime("%Y-%m-%dT%H:%M"),
        gerado_por=f"{u['nome']} ({PERFIS[u['perfil']]})"[:160])
    try:   # dupla conferência: rotina independente relê o arquivo (api/conferencia.py)
        conferencia.conferir(conteudo, modelo)
    except conferencia.Divergencia as e:
        banco_acesso.registrar("planilha bloqueada pela conferência independente", str(e)[:200], u["id"], u["empresa_id"])
        raise PlanilhaInvalida(f"Nada foi gerado: {e}. Confira a planilha e envie de novo.") from None
    return modelo


def _traducao(m) -> dict:
    """O que a tela mostra da tradução: arquivo, colunas reconhecidas, resumo e o que foi corrigido (sem UC)."""
    return {"arquivo": {k: getattr(m.arquivo, k) for k in ("nome", "formato", "aba", "linhas", "colunas_ignoradas")},
            "colunas": list(m.colunas), "resumo": m.resumo.model_dump(), "versao": m.tradutor,
            "corrigidas": [{"linha": pt.linha, "codigo": pt.correcao.value, "correcao": TEXTOS[pt.correcao]}
                           for pt in m.pontos if pt.status == "corrigida"][:MAX_PROBLEMAS],
            "avisos": [{"linha": pt.linha, "avisos": [a.value for a in pt.avisos]}
                       for pt in m.pontos if pt.avisos][:MAX_PROBLEMAS],
            "textos": {k.value: v for k, v in TEXTOS.items()}}


LIMITE_ENVIOS, JANELA_ENVIOS = 20, 3600       # planilhas por usuário por hora
_envios: dict[int, deque] = defaultdict(deque)


def _limite_envios(usuario_id: int) -> None:
    """No máximo LIMITE_ENVIOS planilhas por usuário em JANELA_ENVIOS segundos (cada uma custa CPU e memória)."""
    agora, fila = time.monotonic(), _envios[usuario_id]
    while fila and agora - fila[0] > JANELA_ENVIOS:
        fila.popleft()
    if len(fila) >= LIMITE_ENVIOS:
        raise HTTPException(429, f"Limite de {LIMITE_ENVIOS} planilhas por hora atingido. Tente de novo mais tarde.")
    fila.append(agora)


class PedidoAviso(BaseModel):
    """2º passo: o pacote assinado da conferência, a data e o horário, a confirmação e a justificativa."""
    pacote: str = Field(max_length=pacote_.MAX_PACOTE)
    data: str = Field(max_length=200)
    horario: str = Field(max_length=200)
    idioma: str = Field(idiomas.PADRAO, max_length=10)
    conferi: bool = False
    justificativa: str | None = Field(None, max_length=2000)
    tipo: str = Field(tipos.PADRAO, max_length=40)
    tipo_outro: str | None = Field(None, max_length=1000)


def _formulario(data: str, horario: str, idioma: str) -> tuple[str, str, str]:
    data, horario = _texto_do_aviso("data", data), _texto_do_aviso("horário", horario)
    if idioma not in idiomas.IDIOMAS:
        raise erro(422, f"idioma: use um de {', '.join(idiomas.IDIOMAS)}.", "idioma")
    return data, horario, idioma


def _motivo(tipo: str, outro: str | None, idioma: str = idiomas.PADRAO) -> tuple[str, str]:
    """O tipo de desligamento (lista fechada ou "Outro" curto e sem dado pessoal) e o texto do motivo no idioma do aviso."""
    try:
        return tipos.motivo(tipo, outro, idioma)
    except ValueError as e:
        raise erro(422, f"Tipo de desligamento: {e}", "tipo_outro" if tipo == "outro" else "tipo") from None


class _PedeAba(Exception):
    def __init__(self, mensagem: str, abas: list[str]):
        super().__init__(mensagem)
        self.abas = abas


@app.exception_handler(_PedeAba)
def _pede_aba(request, e: _PedeAba) -> JSONResponse:
    """Mais de uma aba serve: 409 com a lista, para a pessoa escolher."""
    return JSONResponse({"detail": str(e), "abas": e.abas}, status_code=409)


async def _ler_e_traduzir(arquivo: UploadFile, aba: str | None, u: dict):
    """O arquivo enviado -> JSON validado; o arquivo sai da memória aqui. 409 pede a aba; 422 recusa."""
    _limite_envios(u["id"])
    conteudo = await arquivo.read(leitura.MAX_BYTES + 1)
    try:
        return _traduzir(conteudo, arquivo.filename, aba or None, u)
    except leitura.EscolhaDeAba as e:
        raise _PedeAba(str(e), e.abas) from None
    except PlanilhaInvalida as e:
        raise HTTPException(422, str(e)) from None
    finally:
        del conteudo


def _resultado(modelo, data: str, horario: str, idioma: str, cfg: dict, area: set[str] | None = None, lido=None) -> dict:
    """Do JSON validado (nunca da planilha bruta): municípios, comunidades, avisos, pontos e as travas.
    lido: o JSON do arquivo inteiro, para a tradução (modelo pode ser só as linhas escolhidas)."""
    v = planilha.validas(modelo)
    rejeitadas = [pt for pt in modelo.pontos if pt.status == "rejeitada"]
    fora_planilha = [pt for pt in rejeitadas if pt.motivo == Motivo.FORA_DA_CONCESSAO]
    resposta = {"aviso_ficticio": AVISO_FICTICIO,
                "planilha": {"linhas": modelo.resumo.total, "validas": len(v), "total_problemas": len(rejeitadas),
                             "problemas_por_motivo": dict(Counter(TEXTOS[pt.motivo] for pt in rejeitadas)),
                             "problemas": [{"linha": pt.linha, "codigo": pt.motivo.value, "motivo": TEXTOS[pt.motivo]}
                                           for pt in rejeitadas[:MAX_PROBLEMAS]]},
                "traducao": _traducao(lido or modelo),
                "fora_da_concessao": {"ucs": len(fora_planilha), "linhas": [pt.linha for pt in fora_planilha[:MAX_PROBLEMAS]]},
                "municipios": [], "prazo": _prazo(Counter(), cfg),
                "pontos_fora": [[round(pt.lat, CASAS_PONTO), round(pt.lon, CASAS_PONTO)] for pt in fora_planilha],
                # as corrigidas, com cor própria no mapa (só latitude e longitude, sem a UC)
                "pontos_corrigidos": [[round(pt.lat, CASAS_PONTO), round(pt.lon, CASAS_PONTO)]
                                      for pt in modelo.pontos if pt.status == "corrigida"]}
    resposta["fora_da_area"] = {"ucs": 0, "linhas": []}
    linhas_fora, linhas_fora_area, por_municipio = set(), set(), {}
    if not v.empty:
        x, y = GEO_PARA_BASE.transform(v["LON"].to_numpy(), v["LAT"].to_numpy())
        xy = np.c_[x, y]
        bases, fora_area = _bases(xy, area)
        if fora_area.any():   # município fora da área de atuação da empresa: a linha é rejeitada (nunca entra no aviso)
            linhas_fora_area = {int(l) for l in v["LINHA"][fora_area]}
            resposta["fora_da_area"] = {"ucs": len(linhas_fora_area), "linhas": sorted(linhas_fora_area)[:MAX_PROBLEMAS]}
            resposta["pontos_fora"] += _pontos(v[fora_area])
            texto = TEXTOS[Motivo.FORA_DA_AREA]
            p = resposta["planilha"]
            p["total_problemas"] += len(linhas_fora_area)
            p["problemas_por_motivo"][texto] = len(linhas_fora_area)
            p["problemas"] = sorted(p["problemas"] + [{"linha": l, "codigo": Motivo.FORA_DA_AREA.value, "motivo": texto}
                                                      for l in sorted(linhas_fora_area)], key=lambda x: x["linha"])[:MAX_PROBLEMAS]
            v, xy = v[~fora_area].reset_index(drop=True), xy[~fora_area]
        # o aviso do algoritmo com a data e o horário no formato do idioma (em português, como vieram)
        r = afetados(xy, bases, DIST.regras, *idiomas.localizar(data, horario, idioma), idioma) if bases else None
        fora = r.fora if r else np.arange(len(v))
        if len(fora):   # dentro da área com a margem, mas fora dos contornos dos municípios (na divisa da concessão)
            linhas_fora = {int(l) for l in v["LINHA"].iloc[fora]}
            resposta["fora_da_concessao"]["ucs"] += int(len(fora))
            resposta["fora_da_concessao"]["linhas"] = sorted(resposta["fora_da_concessao"]["linhas"] + sorted(linhas_fora))[:MAX_PROBLEMAS]
            resposta["pontos_fora"] += _pontos(v.iloc[fora])
        vital_total = Counter()
        for m in (r.municipios if r else []):
            ucs = v.iloc[m.ucs.index]
            por_municipio[f"{m.nome}/{m.uf}"] = [int(l) for l in ucs["LINHA"]]
            vital = Counter("a_confirmar" if f is None else "sim" if bool(f) else "nao" for f in ucs["VITAL"])
            vital_total += vital
            resposta["municipios"].append({
                "codigo_ibge": m.codigo, "nome": m.nome, "uf": m.uf, "ucs": len(m.ucs),
                "comunidades": [{"nome": c.COMUNIDADE_PREVISTA, "distrito": c.DISTRITO, "afetadas": int(c.UC_AFETADAS),
                                 "total": int(c.UC_TOTAL), "parcial": bool(c.PARCIAL), "fragmento": bool(c.FRAGMENTO),
                                 "confianca": round(float(c.CONFIANCA), 2)} for c in m.comunidades.itertuples()],
                "aviso": m.aviso, "segundos": m.segundos,
                # o aviso de hoje (fazenda a fazenda), se a planilha trouxe a coluna local: só para o comparativo
                "hoje": _aviso_hoje(ucs["LOCAL"], data, horario) if "local" in modelo.colunas else None,
                # [lat, lon, posição da comunidade na lista acima (-1 = sem comunidade)], sem o número da UC
                "pontos": _pontos(ucs, m.ucs["COMUNIDADE_PREVISTA"], [c.COMUNIDADE_PREVISTA for c in m.comunidades.itertuples()]),
                "equipamento_vital": {k: vital[k] for k in ("sim", "nao", "a_confirmar")},
                # só contagens; a classe é texto livre da planilha, então vai cortada
                "classes": dict(Counter((c or "não informada")[:MAX_TEXTO] for c in ucs["CLASSE"])),
            })
        resposta["prazo"] = _prazo(vital_total, cfg)
    # por transformador e por circuito (só os códigos da rede e contagens), se a planilha trouxe as colunas
    resposta["rede"] = {campo: agrupamento.por_codigo(v[campo.upper()].tolist()) for campo in ("circuito", "transformador")
                        if campo in modelo.colunas}
    ms = resposta["municipios"]
    resposta["conferencia"] = {
        "vital_bloqueio": travas.vital_bloqueio(modelo, linhas_fora, linhas_fora_area),
        "rejeicao": travas.rejeicao(modelo, cfg["limite_rejeicao"], len(linhas_fora_area)),
        "suspeitos": travas.suspeitos(modelo, por_municipio),
        "arquivo": modelo.arquivo.nome, "sha256": modelo.arquivo.sha256,
        "numeros": {"clientes": sum(m["ucs"] for m in ms), "municipios": len(ms),
                    "comunidades": sum(len(m["comunidades"]) for m in ms),
                    "equipamento_vital": sum(m["equipamento_vital"]["sim"] for m in ms),
                    "vital_a_confirmar": sum(m["equipamento_vital"]["a_confirmar"] for m in ms),
                    "corrigidas": modelo.resumo.corrigidas, "rejeitadas": modelo.resumo.rejeitadas,
                    "fora_da_concessao": resposta["fora_da_concessao"]["ucs"], "fora_da_area": resposta["fora_da_area"]["ucs"]}}
    return resposta


MAX_LOCALIZACOES = 8
_localizacoes: OrderedDict = OrderedDict()


def _localizacao(modelo, area: set[str]) -> tuple[dict[int, tuple[str, str]], dict[tuple[str, str], str]]:
    """Linha -> (código IBGE, comunidade) de cada linha válida localizada (a mesma regra do aviso, nucleo/afetados.localizar)
    e o distrito de cada comunidade. Fica num cache pequeno do processo, pela posição das linhas e pela área: só números de
    linha e nomes de comunidade, nunca UC nem coordenada."""
    v = planilha.validas(modelo)
    chave = hashlib.sha256(repr((tuple(zip(v["LINHA"].tolist(), v["LAT"].tolist(), v["LON"].tolist())),
                                 sorted(area))).encode()).hexdigest()
    if chave in _localizacoes:
        _localizacoes.move_to_end(chave)
        return _localizacoes[chave]
    comunidade, distritos = {}, {}
    if not v.empty:
        x, y = GEO_PARA_BASE.transform(v["LON"].to_numpy(), v["LAT"].to_numpy())
        xy = np.c_[x, y]
        bases, fora_area = _bases(xy, area)
        if bases:
            loc = localizar(xy[~fora_area], bases)
            for linha, q, nome, distrito in zip(v["LINHA"].to_numpy()[~fora_area], loc["MUNICIPIO"], loc["COMUNIDADE_PREVISTA"],
                                                loc["DISTRITO"]):
                if q >= 0 and nome is not None:
                    comunidade[int(linha)] = (bases[q].codigo, nome)
                    distritos.setdefault((bases[q].codigo, nome), distrito)
    _localizacoes[chave] = (comunidade, distritos)
    while len(_localizacoes) > MAX_LOCALIZACOES:
        _localizacoes.popitem(last=False)
    return comunidade, distritos


def _base_escolha(modelo, comunidade: dict, distritos: dict) -> dict:
    """O que a tela precisa para escolher quem será desligado (só na memória do navegador, como os pontos do mapa):
    linha a linha, a posição (5 casas, ou null), a comunidade e o circuito, o conjunto, o transformador e o bairro como
    índices nas listas de valores, se está inativa e, só nas linhas sem posição, se tem equipamento vital (a regra de
    nucleo/selecao.py). Nunca o número da UC nem o endereço."""
    valores = {f: sorted({getattr(p, f) for p in modelo.pontos if getattr(p, f)}) for f in selecao.FILTROS}
    posicao = {f: {x: i for i, x in enumerate(vs)} for f, vs in valores.items()}
    nomes = {c: (n, uf) for c, n, uf, _ in banco.contornos(CRS_BASE)}
    municipios = sorted({c for c, _ in comunidade.values()})
    comunidades = sorted(set(comunidade.values()))
    i_mun, i_com = {c: i for i, c in enumerate(municipios)}, {c: i for i, c in enumerate(comunidades)}
    linhas = {"lat": [], "lon": [], "com": [], **{f: [] for f in selecao.FILTROS}, "inativa": [], "vital_sem_posicao": []}
    for p in modelo.pontos:
        tem = p.lat is not None
        linhas["lat"].append(round(p.lat, CASAS_PONTO) if tem else None)
        linhas["lon"].append(round(p.lon, CASAS_PONTO) if tem else None)
        linhas["com"].append(i_com.get(comunidade.get(p.linha), -1))
        for f in selecao.FILTROS:
            linhas[f].append(posicao[f].get(getattr(p, f), -1))
        linhas["inativa"].append(int(planilha.inativa(p.situacao)))
        linhas["vital_sem_posicao"].append(int(not tem and p.equipamento_vital is True))
    return {"lidas": modelo.resumo.total, "valores": valores, "linhas": linhas,
            "municipios": [{"codigo_ibge": c, "nome": nomes.get(c, (c, ""))[0], "uf": nomes.get(c, ("", ""))[1]} for c in municipios],
            "comunidades": [{"municipio": i_mun[c], "nome": n, "distrito": distritos.get((c, n))} for c, n in comunidades],
            "colunas": [f for f in selecao.FILTROS if f in modelo.colunas] + (["situacao"] if "situacao" in modelo.colunas else [])}


def _conferir_escolha(modelo, criterio, comunidade: dict, data: str, horario: str, idioma: str, cfg: dict, area: set[str]) -> dict:
    """A conferência só das linhas escolhidas: as travas (vital, suspeitos, limite de rejeição, fora da área) valem sobre
    elas. Devolve também a escolha: o critério, a conta fechada (lidas, inativas fora, não escolhidas, escolhidas) e as
    inativas contadas por bairro e por circuito."""
    e = selecao.aplicar(modelo, criterio, comunidade)
    resposta = _resultado(e.modelo, data, horario, idioma, cfg, area, lido=modelo)
    n = resposta["conferencia"]["numeros"]
    resposta["escolha"] = {**selecao.resumo(criterio, e.conta, n["comunidades"]), "inativas": e.inativas}
    resposta["conferencia"]["conta"] = e.conta
    return resposta


def _area_da_empresa(u: dict) -> set[str]:
    """A área de atuação da empresa de quem gera o aviso; sem área cadastrada, nenhum aviso (o servidor recusa)."""
    area = banco_acesso.area(u["empresa_id"])
    if not area:
        raise HTTPException(422, "A área de atuação da empresa não está cadastrada: nenhum aviso pode ser criado. Peça ao Admin do Norte.")
    return area


@app.post("/api/planilha")
async def conferir_planilha(arquivo: UploadFile = File(...), data: str = Form(...), horario: str = Form(...),
                            idioma: str = Form(idiomas.PADRAO), aba: str | None = Form(None, max_length=leitura.MAX_NOME_ABA),
                            tipo: str = Form(tipos.PADRAO, max_length=40), tipo_outro: str | None = Form(None, max_length=1000),
                            u: dict = Depends(exigir("gerar_aviso"))) -> JSONResponse:
    """1º passo (Conferir): traduz a planilha e mostra o resultado e as travas. Nada vai para o histórico.
    Devolve o pacote assinado (UCs opacas, 15 minutos) que o 2º passo usa para gerar o aviso."""
    data, horario, idioma = _formulario(data, horario, idioma)
    tipo, motivo = _motivo(tipo, tipo_outro, idioma)
    modelo = await _ler_e_traduzir(arquivo, aba, u)
    cfg, area = config_empresa(u["empresa_id"]), _area_da_empresa(u)
    comunidade, distritos = _localizacao(modelo, area)
    planilha_inteira = selecao.Criterio(modo="planilha")
    resposta = _conferir_escolha(modelo, planilha_inteira, comunidade, data, horario, idioma, cfg, area)
    resposta["base"] = _base_escolha(modelo, comunidade, distritos)
    resposta["desligamento"] = {"tipo": tipo, "rotulo": tipos.ROTULOS[tipo], "motivo": motivo}
    _mensagens(resposta["municipios"], cfg, data, horario, idioma, motivo)
    _alerta_repeticao(resposta, u, cfg)
    opaco = travas.ucs_opacas(modelo)
    # o pacote "base" serve para escolher quem será desligado; o "escolha" já é a planilha inteira (sem as inativas)
    resposta["pacote_base"], _ = pacote_.assinar(opaco, u["id"], u["empresa_id"], fase="base")
    resposta["pacote"], vence = pacote_.assinar(opaco, u["id"], u["empresa_id"], criterio=planilha_inteira)
    resposta["pacote_vence"] = datetime.fromtimestamp(vence, BRASILIA).isoformat(timespec="seconds")
    r = modelo.resumo
    banco_acesso.registrar("importou planilha", f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256}): {r.total} linhas, "
                           f"{r.ok} ok, {r.corrigidas} corrigidas, {r.rejeitadas} rejeitadas", u["id"], u["empresa_id"])
    return JSONResponse(resposta)


class PedidoEscolha(BaseModel):
    """Entre os dois passos: o pacote "base" da planilha lida, o critério de quem será desligado e o formulário."""
    pacote: str = Field(max_length=pacote_.MAX_PACOTE)
    criterio: selecao.Criterio
    data: str = Field(max_length=200)
    horario: str = Field(max_length=200)
    idioma: str = Field(idiomas.PADRAO, max_length=10)
    tipo: str = Field(tipos.PADRAO, max_length=40)
    tipo_outro: str | None = Field(None, max_length=1000)


LIMITE_ESCOLHAS = 120         # conferências de escolha por usuário por hora (cada uma roda o algoritmo)
_escolhas: dict[int, deque] = defaultdict(deque)


@app.post("/api/planilha/escolha")
def conferir_escolha(dados: PedidoEscolha, u: dict = Depends(exigir("gerar_aviso"))) -> JSONResponse:
    """Escolher quem será desligado (nucleo/selecao.py): com o pacote "base" e o critério, a conferência só das escolhidas
    e o pacote "escolha" (o critério assinado junto), que o 2º passo usa para gerar o aviso. Nada vai para o histórico."""
    data, horario, idioma = _formulario(dados.data, dados.horario, dados.idioma)
    tipo, motivo = _motivo(dados.tipo, dados.tipo_outro, idioma)
    agora, fila = time.monotonic(), _escolhas[u["id"]]
    while fila and agora - fila[0] > JANELA_ENVIOS:
        fila.popleft()
    if len(fila) >= LIMITE_ESCOLHAS:
        raise HTTPException(429, f"Limite de {LIMITE_ESCOLHAS} conferências por hora atingido. Tente de novo mais tarde.")
    fila.append(agora)
    try:
        modelo = pacote_.abrir(dados.pacote, u["id"], u["empresa_id"], fase="base")
    except pacote_.PacoteRecusado as e:
        raise HTTPException(422, str(e)) from None
    cfg, area = config_empresa(u["empresa_id"]), _area_da_empresa(u)
    criterio = selecao.canonico(dados.criterio)
    resposta = _conferir_escolha(modelo, criterio, _localizacao(modelo, area)[0], data, horario, idioma, cfg, area)
    resposta["desligamento"] = {"tipo": tipo, "rotulo": tipos.ROTULOS[tipo], "motivo": motivo}
    _mensagens(resposta["municipios"], cfg, data, horario, idioma, motivo)
    _alerta_repeticao(resposta, u, cfg)
    resposta["pacote"], vence = pacote_.assinar(modelo, u["id"], u["empresa_id"], criterio=criterio)
    resposta["pacote_vence"] = datetime.fromtimestamp(vence, BRASILIA).isoformat(timespec="seconds")
    banco_acesso.registrar("conferiu a escolha de quem será desligado", f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256}): "
                           f"{resposta['escolha']['texto']}"[:500], u["id"], u["empresa_id"])
    return JSONResponse(resposta)


@app.post("/api/avisos")
def gerar_aviso(dados: PedidoAviso, u: dict = Depends(exigir("gerar_aviso"))) -> JSONResponse:
    """2º passo (Gerar aviso): só com o pacote da conferência válido, a caixa "Conferi" marcada, nenhuma
    trava de equipamento vital e, acima do limite de rejeição, a justificativa. Grava no histórico."""
    data, horario, idioma = _formulario(dados.data, dados.horario, dados.idioma)
    tipo, motivo = _motivo(dados.tipo, dados.tipo_outro, idioma)
    pacote_hash = hashlib.sha256(dados.pacote.encode()).hexdigest()
    if (ja := banco_acesso.aviso_do_pacote(u["empresa_id"], pacote_hash)):   # clique duplo ou reenvio: um aviso só
        raise HTTPException(409, f"Este aviso já foi gerado com esta conferência (aviso nº {ja}). Para outro aviso, confira a planilha de novo.")
    try:
        modelo, criterio = pacote_.abrir_escolha(dados.pacote, u["id"], u["empresa_id"])
    except pacote_.PacoteRecusado as e:
        raise HTTPException(422, str(e)) from None
    cfg, area = config_empresa(u["empresa_id"]), _area_da_empresa(u)
    # a mesma escolha que foi conferida (o critério veio assinado): as travas valem sobre as escolhidas
    resposta = _conferir_escolha(modelo, criterio, _localizacao(modelo, area)[0], data, horario, idioma, cfg, area)
    _mensagens(resposta["municipios"], cfg, data, horario, idioma, motivo)
    rep = _alerta_repeticao(resposta, u, cfg)
    c, arq = resposta["conferencia"], f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256})"
    problema = travas.problema_para_gerar(c, dados.conferi, dados.justificativa)
    if problema:
        if c["vital_bloqueio"]:
            banco_acesso.registrar("geração bloqueada (equipamento vital)", f"{arq}: linha(s) "
                                   + ", ".join(str(x["linha"]) for x in c["vital_bloqueio"][:20]), u["id"], u["empresa_id"])
        raise HTTPException(422, problema)
    if rep:
        banco_acesso.registrar("alerta de repetição", f"{arq}: {rep}"[:500], u["id"], u["empresa_id"])
    banco_acesso.registrar("escolheu quem será desligado", f"{arq}: {resposta['escolha']['texto']}"[:700], u["id"], u["empresa_id"])
    banco_acesso.registrar("conferiu os números e o mapa", f"{arq}: {c['numeros']['clientes']} clientes, "
                           f"{c['numeros']['comunidades']} comunidades", u["id"], u["empresa_id"])
    if c["rejeicao"]["acima"]:
        banco_acesso.registrar("justificou rejeições acima do limite", f"{c['rejeicao']['rejeitadas']} de {c['rejeicao']['total']} "
                               f"linhas: {travas.limpar_justificativa(dados.justificativa)}", u["id"], u["empresa_id"])
    resposta["desligamento"] = {"tipo": tipo, "rotulo": tipos.ROTULOS[tipo], "motivo": motivo}
    try:
        return JSONResponse(_guardar(resposta, u, data, horario, idioma, tipo, motivo, cfg, pacote_hash))
    except banco_acesso.AvisoRepetido as e:
        raise HTTPException(409, f"Este aviso já foi gerado com esta conferência (aviso nº {e.args[0]}). "
                            "Para outro aviso, confira a planilha de novo.") from None


@app.post("/api/planilha/json")
async def baixar_json(arquivo: UploadFile = File(...), aba: str | None = Form(None, max_length=leitura.MAX_NOME_ABA),
                      u: dict = Depends(exigir("baixar_json"))) -> Response:
    """O JSON padronizado completo, com os números de UC: só num pedido explícito, reenviando o mesmo
    arquivo (a tradução é reprodutível) e registrado na auditoria."""
    modelo = await _ler_e_traduzir(arquivo, aba, u)
    banco_acesso.registrar("baixou o JSON da planilha (com números de UC)",
                           f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256}), {modelo.resumo.total} linhas", u["id"], u["empresa_id"])
    nome = "".join(ch for ch in sem_acento(modelo.arquivo.nome.rsplit(".", 1)[0]) if ch.isalnum() or ch in "-_")[:60] or "planilha"
    return Response(esquema_planilha.texto(modelo), media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="farol-{nome}.json"'})


class PedidoRelatorio(BaseModel):
    pacote: str = Field(max_length=pacote_.MAX_PACOTE)


@app.post("/api/planilha/relatorio")
def relatorio_planilha(dados: PedidoRelatorio, u: dict = Depends(exigir("gerar_aviso"))) -> Response:
    """Relatório da tradução (CSV): linha, situação, motivo ou correção e avisos. Sem UC nem coordenada."""
    try:
        modelo = pacote_.abrir(dados.pacote, u["id"], u["empresa_id"])
    except pacote_.PacoteRecusado as e:
        raise HTTPException(422, str(e)) from None
    banco_acesso.registrar("baixou o relatório da planilha (CSV)", f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256})", u["id"], u["empresa_id"])
    return Response("﻿" + travas.relatorio_csv(modelo), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="farol-relatorio-planilha.csv"'})


def _alerta_repeticao(resposta: dict, u: dict, cfg: dict) -> str | None:
    """Comunidades deste aviso que já tiveram desligamentos nos últimos D dias (com este, N ou mais): aviso amarelo, não bloqueia."""
    n, dias = cfg["repeticao_n"], cfg["repeticao_dias"]
    hoje = datetime.now(BRASILIA).date()
    anteriores = Counter()
    for a in banco_relatorios.avisos(u["empresa_id"], hoje - timedelta(days=dias), hoje):
        if a.get("status") == "cancelado":
            continue
        for m in a["municipios"]:
            for c in m["comunidades"]:
                anteriores[(m["codigo_ibge"], c["nome"], c.get("distrito"))] += 1
    repetidas = sorted({f"{c['nome'].split(' (')[0]} ({m['nome']}): {anteriores[(m['codigo_ibge'], c['nome'], c.get('distrito'))] + 1}"
                        for m in resposta["municipios"] for c in m["comunidades"]
                        if anteriores[(m["codigo_ibge"], c["nome"], c.get("distrito"))] + 1 >= n})
    if not repetidas:
        return None
    texto = f"Repetição: com este, {n} ou mais desligamentos em {dias} dias"
    resposta["conferencia"]["suspeitos"].append({"tipo": "repeticao", "texto": texto, "ucs": len(repetidas), "linhas": [],
                                                 "comunidades": repetidas})
    return f"{texto}: {', '.join(repetidas)}"


def _mensagens(municipios: list[dict], cfg: dict, data: str, horario: str, idioma: str, motivo: str, codigo: str = "") -> None:
    """A mensagem da rádio de cada município, pelo modelo da empresa (nucleo/mensagem.py), e o tempo no ar.
    Um modelo por idioma (Fase K): o do idioma do aviso, com a data e as horas no formato dele."""
    for m in municipios:
        m["mensagem"] = mensagem.montar(cfg["modelos"].get(idioma, cfg["modelo_mensagem"]), mensagem.valores_do_municipio(
            m, distribuidora=cfg["nome_mensagem"], data=data, horario=horario, motivo=motivo, telefone=cfg["telefone"], codigo=codigo,
            idioma=idioma))
        m["segundos_mensagem"] = segundos(m["mensagem"])
        hoje = m.get("hoje")
        if hoje and hoje.get("lista"):
            # comparação justa: o aviso de hoje com o MESMO modelo, só a lista muda (locais no lugar das comunidades)
            hoje["texto"] = mensagem.montar(cfg["modelos"].get(idioma, cfg["modelo_mensagem"]), mensagem.valores_do_municipio(
                {**m, "comunidades": []}, distribuidora=cfg["nome_mensagem"], data=data, horario=horario, motivo=motivo,
                telefone=cfg["telefone"], codigo=codigo, idioma=idioma) | {"comunidades": mensagem.lista_falada(hoje["lista"], idioma)})
            hoje["palavras"], hoje["segundos"] = len(hoje["texto"].split()), segundos(hoje["texto"])
            # nunca maior: com poucos locais (ex.: 1 UC), a lista por local é a mais curta e o Norte usa ela
            m["mesmo_tamanho"] = m["segundos_mensagem"] > hoje["segundos"]
            if m["mesmo_tamanho"]:
                m["mensagem"], m["segundos_mensagem"] = hoje["texto"], hoje["segundos"]


def _guardar(resposta: dict, u: dict, data: str, horario: str, idioma: str, tipo: str, motivo: str, cfg: dict,
             pacote_hash: str | None = None) -> dict:
    """Grava no histórico da empresa só o agregado (sem as linhas com problema), com a linha "gerou aviso"
    na auditoria na mesma transação, e devolve a resposta com o id, o código de verificação e quem pediu."""
    p = resposta["planilha"]
    resumo = {"linhas": p["linhas"], "validas": p["validas"], "problemas": p["total_problemas"],
              "fora_da_concessao": resposta["fora_da_concessao"]["ucs"], "prazo": resposta["prazo"],
              "corrigidas": resposta["conferencia"]["numeros"]["corrigidas"], "arquivo_sha256": resposta["conferencia"]["sha256"]}
    if resposta.get("escolha"):   # o critério de quem foi desligado e a conta (nunca as UCs)
        resumo["escolha"] = {k: v for k, v in resposta["escolha"].items() if k != "inativas"}
    # do aviso de hoje, só as contagens (o texto lista imóveis e ruas e não precisa ficar guardado)
    municipios = [{**{k: m[k] for k in ("codigo_ibge", "nome", "uf", "ucs", "comunidades", "aviso", "segundos", "equipamento_vital",
                                         "mensagem", "segundos_mensagem")},
                   "mesmo_tamanho": bool(m.get("mesmo_tamanho")),
                   "hoje": {k: m["hoje"][k] for k in ("locais", "palavras", "segundos")} if m.get("hoje") else None}
                  for m in resposta["municipios"]]
    nomes = ", ".join(m["nome"] for m in municipios) or "nenhum município"
    g = banco_acesso.gravar_aviso(u["empresa_id"], u["id"], data, horario, idioma, resumo, municipios, tipo, motivo,
                                  lambda id_: f"aviso {id_}: {nomes} ({p['linhas']} linhas), {tipos.ROTULOS[tipo].lower()}",
                                  pacote_hash)
    resposta.update(id=g["id"], codigo=g["codigo"], criado_em=g["criado_em"].isoformat(), usuario=g["solicitante"],
                    usuario_perfil=PERFIS.get(g["solicitante_perfil"], ""), status="gerado")
    if "{codigo}" in cfg["modelos"].get(idioma, cfg["modelo_mensagem"]):   # o código só existe depois de gravado: a mensagem é refeita com ele
        _mensagens(resposta["municipios"], cfg, data, horario, idioma, motivo, g["codigo"])
        for guardado, m in zip(municipios, resposta["municipios"]):   # o guardado não tem a lista de locais: copia
            guardado.update(mensagem=m["mensagem"], segundos_mensagem=m["segundos_mensagem"], mesmo_tamanho=bool(m.get("mesmo_tamanho")),
                            hoje={k: m["hoje"][k] for k in ("locais", "palavras", "segundos")} if m.get("hoje") else None)
        banco_acesso.atualizar_municipios(g["id"], u["empresa_id"], municipios)
    return resposta


# ---------- Histórico de avisos da empresa ----------
class TextoFinal(BaseModel):
    texto: str


class PedidoAudio(BaseModel):
    # o limite do texto é conferido de novo, com o tamanho de cada caso, ao gerar (audio.mp3)
    texto: str = Field(max_length=audio.MAX_CARACTERES_COMPARATIVO)
    idioma: str = Field(idiomas.PADRAO, max_length=10)
    municipio: str = Field("", max_length=100)   # só para o nome do arquivo e o registro
    comparativo: bool = False  # o aviso de hoje no comparativo: pode ser bem mais longo


@app.post("/api/audio")
def gerar_audio(dados: PedidoAudio, u: dict = Depends(exigir("gerar_aviso"))) -> Response:
    """MP3 do aviso falado (voz sintetizada no próprio servidor, sem enviar o texto para fora)."""
    if not AUDIO:
        raise HTTPException(503, "O áudio do aviso está desligado neste servidor.")
    try:
        mp3, segundos = audio.mp3(dados.texto, dados.idioma,
                                  max_caracteres=audio.MAX_CARACTERES_COMPARATIVO if dados.comparativo else audio.MAX_CARACTERES)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    municipio = "".join(ch for ch in dados.municipio if ch.isalnum() or ch in " -")[:60].strip() or "aviso"
    arquivo = "-".join(sem_acento(municipio).lower().encode("ascii", "ignore").decode().split()) or "aviso"
    banco_acesso.registrar("gerou MP3 do aviso" + (" de hoje (comparativo)" if dados.comparativo else ""),
                           f"{municipio}, {segundos:.0f} s", u["id"], u["empresa_id"])
    return Response(mp3, media_type="audio/mpeg", headers={
        "Content-Disposition": f'attachment; filename="farol-aviso-{arquivo}.mp3"',
        "X-Duracao-Segundos": f"{segundos:.1f}"})


def _aviso_publico(a: dict) -> dict:
    tipo = a.get("tipo") or None
    return {"id": a["id"], "criado_em": a["criado_em"].isoformat(), "data": a["data"], "horario": a["horario"],
            "idioma": a["idioma"], "usuario": a["usuario"], "usuario_perfil": PERFIS.get(a.get("usuario_perfil"), ""),
            "resumo": a["resumo"], "municipios": a["municipios"], "status": a.get("status") or "gerado", "codigo": a.get("codigo"),
            "desligamento": {"tipo": tipo, "rotulo": tipos.ROTULOS.get(tipo, ""), "motivo": a.get("motivo")} if tipo else None}


@app.get("/api/historico")
def historico(u: dict = Depends(exigir("ver_historico"))) -> dict:
    return {"avisos": [_aviso_publico(a) for a in banco_acesso.avisos(u["empresa_id"])]}


@app.get("/api/historico/{id_}")
def historico_um(id_: int, u: dict = Depends(exigir("ver_historico"))) -> dict:
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    return _aviso_publico(a)


def _avisos_do_painel(u: dict) -> list[dict]:
    """Os avisos mais recentes da empresa do usuário, no horário de Brasília (só do histórico dele)."""
    return [{**a, "criado_em": a["criado_em"].astimezone(BRASILIA)}
            for a in banco_acesso.avisos(u["empresa_id"], MAX_AVISOS_PAINEL)]


@app.get("/api/painel")
def dashboard(u: dict = Depends(exigir("ver_historico"))) -> dict:
    """Dashboard da empresa: só agregados do histórico (nucleo/painel.py), no horário de Brasília."""
    hoje = datetime.now(BRASILIA).date()
    return {**painel.resumir(_avisos_do_painel(u), hoje, DIST.radio.spot_segundos),
            "mes": painel_do_mes(u["empresa_id"], hoje)}


class PerguntaAoPainel(BaseModel):
    pergunta: str


@app.post("/api/painel/perguntar")
def perguntar_ao_painel(dados: PerguntaAoPainel, u: dict = Depends(exigir("ver_historico"))) -> dict:
    """Pergunte ao painel: a IA escolhe uma consulta fixa (nucleo/consultas.py) e o código calcula em cima
    do histórico da própria empresa; a resposta escrita só vale se todos os números estão nos dados.
    A IA nunca vê o histórico inteiro nem escreve SQL; ao provedor vão a pergunta e, se ele redige, a tabela
    agregada. No registro de atividade vai só o nome da consulta, nunca a pergunta."""
    if not copiloto.ativo():
        raise HTTPException(503, "O copiloto está desligado neste servidor.")
    pergunta = " ".join(dados.pergunta.split())
    if not 3 <= len(pergunta) <= consultas.MAX_PERGUNTA:
        raise HTTPException(422, f"Pergunta: de 3 a {consultas.MAX_PERGUNTA} caracteres.")
    avisos = _avisos_do_painel(u)
    conhecidos = sorted({m["nome"] for a in avisos for m in (a["municipios"] or [])})
    try:
        escolha = copiloto.escolher_consulta(pergunta, conhecidos)
        nome, params = escolha if escolha else (None, {})
        params = consultas.normalizar_parametros(nome, params) if nome else {}
    except copiloto.CopilotoIndisponivel as e:
        raise HTTPException(503, str(e)) from None
    except ValueError:
        nome, params = None, {}   # a IA escolheu uma consulta ou um parâmetro que não existe: trata como não entendida
    provedor = copiloto.nome_do_provedor()
    if not nome:
        banco_acesso.registrar("perguntou ao painel", "sem consulta", u["id"], u["empresa_id"])
        return {"entendida": False, "provedor": provedor, "exemplos": consultas.EXEMPLOS,
                "resposta": "Não consegui ligar essa pergunta a nenhuma consulta do histórico. Tente uma destas:"}
    tabela = consultas.executar(nome, params, avisos, datetime.now(BRASILIA).date(), DIST.radio.spot_segundos)
    resposta, por = consultas.texto_padrao(nome, params, tabela), "padrao"
    try:
        escrita = copiloto.redigir_resposta(pergunta, tabela)
    except copiloto.CopilotoIndisponivel:
        escrita = None
    if escrita and consultas.conferir_resposta(escrita, pergunta, params, tabela):
        resposta, por = escrita.strip(), "ia"
    banco_acesso.registrar("perguntou ao painel", f"consulta {nome}, resposta {por}", u["id"], u["empresa_id"])
    return {"entendida": True, "consulta": nome, "rotulo": consultas.CATALOGO[nome][0], "parametros": params,
            "resposta": resposta, "resposta_por": por, "tabela": tabela, "provedor": provedor}


class PedidoReescrita(BaseModel):
    texto: str               # o texto atual da caixa (o operador pode ter editado)
    pedido: str              # curto, whatsapp, sms, acolhedor ou livre
    livre: str = ""          # o pedido escrito pelo operador (só com pedido = livre)


@app.post("/api/historico/{id_}/municipios/{codigo}/reescrever")
def reescrever_aviso(id_: int, codigo: str, dados: PedidoReescrita, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Copiloto do aviso: a IA reescreve e o verificador confere contra o aviso original do banco.

    Se a conferência falhar, o texto reescrito é descartado (verificado = false) e a tela mantém o atual.
    No registro de atividade vai só o resultado, nunca o texto."""
    if not copiloto.ativo():
        raise HTTPException(503, "O copiloto do aviso está desligado neste servidor.")
    texto = dados.texto.strip()
    if not 1 <= len(texto) <= verificador.MAX_CARACTERES:
        raise HTTPException(422, f"Texto do aviso: de 1 a {verificador.MAX_CARACTERES} caracteres.")
    try:
        _, limite = copiloto.instrucao(dados.pedido, dados.livre)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    a = banco_acesso.aviso(id_, u["empresa_id"])
    m = next((x for x in (a["municipios"] if a else []) if x["codigo_ibge"] == codigo), None)
    if not m:
        raise HTTPException(404, "Aviso ou município não encontrado nesta empresa.")
    try:
        candidato = copiloto.reescrever(texto, dados.pedido, dados.livre)
    except copiloto.CopilotoIndisponivel as e:
        raise HTTPException(503, str(e)) from None
    r = verificador.verificar(m.get("mensagem") or m["aviso"], candidato, [c["nome"] for c in m["comunidades"]], m["nome"],
                              limite or verificador.MAX_CARACTERES, set(DIST.nome.split()))
    banco_acesso.registrar("reescreveu o aviso com IA", f"aviso {id_}, município {codigo}, pedido {dados.pedido}: "
                           + ("aprovado" if r.ok else "recusado pelo verificador"), u["id"], u["empresa_id"])
    return {"texto": candidato if r.ok else texto, "verificado": r.ok, "motivos": r.motivos,
            "provedor": copiloto.nome_do_provedor()}


@app.put("/api/historico/{id_}/municipios/{codigo}/texto")
def guardar_texto_final(id_: int, codigo: str, dados: TextoFinal, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """O texto que foi para a rádio (depois da edição), gravado ao baixar o PDF ou copiar."""
    texto = dados.texto.strip()
    if not 1 <= len(texto) <= 3000:
        raise HTTPException(422, "Texto do aviso: de 1 a 3.000 caracteres.")
    a = banco_acesso.aviso(id_, u["empresa_id"])
    gerado_ = next((m.get("aviso") for m in (a or {}).get("municipios", []) if m.get("codigo_ibge") == codigo), None)
    if not banco_acesso.texto_final(id_, u["empresa_id"], codigo, texto):
        raise HTTPException(404, "Aviso ou município não encontrado nesta empresa.")
    if gerado_ is not None and texto != gerado_:
        banco_acesso.registrar("editou a mensagem", f"aviso {id_}, município {codigo}: {len(gerado_.split())} -> "
                               f"{len(texto.split())} palavras", u["id"], u["empresa_id"])
    banco_acesso.registrar("guardou o texto final", f"aviso {id_}, município {codigo}", u["id"], u["empresa_id"])
    return {"ok": True}


class Cancelamento(BaseModel):
    motivo: str = Field(max_length=1000)


class NovaData(BaseModel):
    data: str = Field(max_length=200)
    horario: str = Field(max_length=200)


def _aviso_da_empresa(id_: int, u: dict) -> dict:
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    if a.get("status") == "cancelado":
        raise HTTPException(409, "Este aviso já foi cancelado.")
    return a


@app.post("/api/historico/{id_}/cancelar")
def cancelar(id_: int, dados: Cancelamento, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Cancela o desligamento: o aviso fica no histórico, marcado, e o motivo vai para a auditoria."""
    _aviso_da_empresa(id_, u)
    motivo = tipos.limpar(dados.motivo)
    if (p := tipos.problema_outro(motivo)):
        raise HTTPException(422, f"Motivo do cancelamento: {p}")
    banco_acesso.cancelar_aviso(id_, u["empresa_id"])
    banco_acesso.registrar("cancelou o aviso", f"aviso {id_}: {motivo}", u["id"], u["empresa_id"])
    return _aviso_publico(banco_acesso.aviso(id_, u["empresa_id"]))


@app.post("/api/historico/{id_}/data")
def mudar_data(id_: int, dados: NovaData, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Muda a data ou o horário do desligamento; o antes e o depois vão para a auditoria."""
    a = _aviso_da_empresa(id_, u)
    data, horario = _texto_do_aviso("data", dados.data), _texto_do_aviso("horário", dados.horario)
    if (data, horario) == (a["data"], a["horario"]):   # clique duplo ou nada mudou: nenhuma linha a mais na auditoria
        raise erro(409, f"O aviso já está com a data {data}, {horario}.", "data")
    banco_acesso.mudar_data(id_, u["empresa_id"], data, horario)
    banco_acesso.registrar("mudou a data do aviso", f"aviso {id_}: de {a['data']}, {a['horario']} para {data}, {horario}",
                           u["id"], u["empresa_id"])
    return _aviso_publico(banco_acesso.aviso(id_, u["empresa_id"]))


@app.get("/api/historico/{id_}/linha-do-tempo")
def linha_do_tempo(id_: int, u: dict = Depends(exigir("ver_historico"))) -> dict:
    """Tudo o que aconteceu com o aviso, em ordem, com o nome e o perfil de quem fez (da auditoria)."""
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    envios = [e["id"] for e in banco_radios.envios(u["empresa_id"], id_)]
    linhas = banco_acesso.linhas_do_aviso(u["empresa_id"], id_, envios, (a.get("resumo") or {}).get("arquivo_sha256"))
    return {"aviso": id_, "linhas": [{"quando": r["quando"].isoformat(), "usuario": r["usuario"], "perfil": PERFIS.get(r["perfil"], ""),
                                      "acao": r["acao"], "detalhe": r["detalhe"], "codigo": auditoria.codigo_verificacao(r["hash"])}
                                     for r in linhas]}


@app.get("/api/verificar/{codigo}")
def verificar_codigo(codigo: str, u: dict = Depends(usuario_atual)) -> dict:
    """Confere um código de verificação (FRL-XXXX-XXXX-XXXX): a linha da auditoria que ele aponta, da
    própria empresa (o Admin do Norte vê de todas), e se a corrente da auditoria está íntegra."""
    h = "".join(ch for ch in codigo.upper().removeprefix("FRL") if ch.isalnum())
    if len(h) != 12 or any(ch not in "0123456789ABCDEF" for ch in h):
        raise HTTPException(422, "Código de verificação: use o formato FRL-XXXX-XXXX-XXXX.")
    ln = banco_acesso.linha_por_hash(h)
    if not ln or (u["perfil"] != "admin_farol" and ln["empresa_id"] != u["empresa_id"]):
        raise HTTPException(404, "Código não encontrado na auditoria desta empresa.")
    return {"codigo": auditoria.codigo_verificacao(ln["hash"]), "quando": ln["quando"].isoformat(), "acao": ln["acao"],
            "detalhe": ln["detalhe"], "por": ln["usuario"], "perfil": PERFIS.get(ln["perfil"], ""),
            "auditoria_integra": banco_acesso.verificar_registro()["ok"],
            "sha256_pdf": (banco_relatorios.via_por_codigo(auditoria.codigo_verificacao(ln["hash"])) or {}).get("sha256")}


# Arquivos da tela: o app, o Leaflet e as fontes embutidas no projeto (vendor/) e o logo. Nada de CDN.
# o manifest do app instalável (sem service worker: nada da API fica guardado no aparelho)
mimetypes.add_type("application/manifest+json", ".webmanifest")
app.mount("/assets/app", StaticFiles(directory=TELA), name="app")
app.mount("/assets/vendor", StaticFiles(directory=APRESENTACAO / "vendor"), name="vendor")
app.mount("/assets/marca", StaticFiles(directory=APRESENTACAO / "marca"), name="marca")
