"""Relatórios (Fase H): mensal, custos por rádio, comunidades, prazos, auditoria, acessos e a ficha da comunidade.

Cada relatório é um documento (nucleo/relatorios.py) que vira tela (JSON), PDF (apresentacao/pdf_relatorio.py)
e CSV protegido contra fórmula. Regras de todos (H0):
- Permissões: Admin da empresa e Operador geram, baixam e enviam; Consulta só gera e baixa; auditoria só o
  Admin da empresa; acessos de todas as empresas só o Admin do Norte (sem envio: ele não tem domínio de empresa).
- Toda geração (tela, PDF, CSV), download de segunda via e envio vira linha da auditoria, com quem, o tipo, os
  filtros, os destinatários e o SHA-256 do PDF. O código de verificação (FRL-...) sai do hash da linha "gerou".
- Segunda via: cada PDF fica guardado cifrado (AES-256-GCM, a mesma chave dos arquivos das rádios); baixar a via
  confere o SHA-256 antes de entregar.
- Enviar: e-mail com o PDF, só para endereços do domínio da empresa, até 5, com limite por hora.
- Filtros: período (mês, ano ou intervalo), município, tipo, rádio, pessoa.
O comprovante do aviso continua como era (mesmas rotas, mesmo PDF).
"""

import hashlib
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import cofre, correio
from ..apresentacao import email_relatorio, pdf_relatorio, rotulos, traducao
from ..banco import acesso as banco_acesso
from ..banco import base_territorial as banco_territorio
from ..banco import radios as banco_radios
from ..banco import relatorios as banco
from ..nucleo import relatorio as R
from ..nucleo import relatorios as RH
from ..nucleo import selecao
from ..nucleo import simulador as SIM
from ..nucleo.acesso import PERFIS, pode, problema_email
from ..nucleo.auditoria import codigo_verificacao
from ..nucleo.radios import alcanca
from ..nucleo.tipos_desligamento import ROTULOS
from .acesso import exigir, usuario_atual
from .comum import AVISO_FICTICIO, BRASILIA, DIST, config_empresa, erro

rotas = APIRouter()
MAX_DIAS = 400
ACESSOS = ("entrou", "saiu", "senha errada", "senha errada (conta bloqueada por 15 min)", "login recusado (conta em bloqueio temporário)",
           "login recusado (usuário bloqueado ou empresa suspensa)", "trocou a senha", "gerou senha temporária",
           "semente: nova senha temporária")
STATUS = {"preparando": "preparando", "enviado": "enviado", "entregue": "entregue", "falhou": "falhou", "confirmado": "confirmado"}
TIPOS = {   # tipo -> (ação exigida, nome, pode enviar)
    "mensal": ("ver_historico", "relatório mensal", True),
    "custos": ("ver_historico", "custos por rádio", True),
    "comunidades": ("ver_historico", "comunidades mais afetadas", True),
    "prazos": ("ver_historico", "prazos", True),
    "comunidade": ("ver_historico", "ficha da comunidade", True),
    "auditoria": ("relatorio_auditoria", "relatório de auditoria", True),
    "acessos": ("auditoria_geral", "auditoria geral de acessos", False),
    "simulador": ("ver_historico", "simulador de economia", False),   # só o Admin da empresa altera os valores (api/radio.py)
}
MAX_DESTINATARIOS, LIMITE_ENVIOS_REL, JANELA = 5, 10, 3600
_envios: dict[int, deque] = defaultdict(deque)


def _hoje() -> date:
    return datetime.now(BRASILIA).date()


def _quem(u: dict, idioma: str = "pt-BR") -> str:
    return f"{u['nome']} ({rotulos.perfil(idioma, u['perfil'])})"


# ---------- filtros e período ----------
def filtros(mes: str | None = Query(None, max_length=7), ano: int | None = Query(None, ge=2000, le=2100),
            inicio: str | None = Query(None, max_length=10), fim: str | None = Query(None, max_length=10),
            municipio: str | None = Query(None, max_length=7), tipo: str | None = Query(None, max_length=40),
            radio: str | None = Query(None, max_length=12), pessoa: str | None = Query(None, max_length=120),
            nome: str | None = Query(None, max_length=120), distrito: str | None = Query(None, max_length=120),
            so_acessos: bool = False, empresa: str | None = Query(None, max_length=10),
            categoria: str | None = Query(None, max_length=20)) -> dict:
    return {k: v for k, v in dict(mes=mes, ano=ano, inicio=inicio, fim=fim, municipio=municipio, tipo=tipo, radio=radio, pessoa=pessoa,
                                  nome=nome, distrito=distrito, so_acessos=so_acessos or None, empresa=empresa, categoria=categoria).items()
            if v not in (None, "")}


CHAVES_FILTRO = {"mes": 7, "ano": 4, "inicio": 10, "fim": 10, "municipio": 7, "tipo": 40, "radio": 12, "pessoa": 120, "nome": 120,
                 "distrito": 120, "so_acessos": 5, "empresa": 10, "categoria": 20}


def limpar_filtros(d: dict) -> dict:
    """Os filtros que vêm no corpo do "Enviar": só as chaves conhecidas, em texto curto."""
    saida = {}
    for k, v in (d or {}).items():
        if k in CHAVES_FILTRO and v not in (None, "", False):
            s = str(v).strip()
            if len(s) > CHAVES_FILTRO[k]:
                raise HTTPException(422, f"Filtro {k}: texto longo demais.")
            saida[k] = int(s) if k == "ano" and s.isdigit() else (True if k == "so_acessos" else s)
    return saida


def periodo(f: dict, padrao: str) -> tuple[date, date, str, bool]:
    """(início, fim, modo, fechado). modo: mes | ano | intervalo; fechado: o período já acabou."""
    hoje = _hoje()
    try:
        if f.get("inicio") or f.get("fim"):
            i, fim = date.fromisoformat(f.get("inicio") or f["fim"]), date.fromisoformat(f.get("fim") or f["inicio"])
            modo = "intervalo"
        elif f.get("ano") or (padrao == "ano" and not f.get("mes")):
            a = int(f.get("ano") or hoje.year)
            i, fim, modo = date(a, 1, 1), date(a, 12, 31), "ano"
        else:
            i, fim = R.periodo_do_mes(f.get("mes") or f"{hoje:%Y-%m}")
            modo = "mes"
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, "Período: use mes=AAAA-MM, ano=AAAA ou inicio e fim (AAAA-MM-DD).") from None
    if fim < i or (fim - i).days > MAX_DIAS:
        raise HTTPException(422, f"Período: o fim depois do início, até {MAX_DIAS} dias.")
    return i, fim, modo, fim < hoje


def _rotulo(i: date, fim: date, modo: str) -> str:
    return str(i.year) if modo == "ano" else R.rotulo_periodo(i, fim)


def idioma_tela(request: Request) -> str:
    """O idioma da tela de quem pede (cabeçalho X-Farol-Idioma): o relatório sai nele (Fase K)."""
    return traducao.idioma_do_pedido(request.headers.get("x-farol-idioma"))


_NOMES_FILTROS = {
    "pt-BR": {"municipio": "município", "tipo": "tipo", "radio": "rádio", "pessoa": "pessoa", "nome": "comunidade", "distrito": "distrito",
              "so_acessos": "só acessos", "empresa": "empresa", "categoria": "tipo de ação"},
    "en": {"municipio": "municipality", "tipo": "type", "radio": "radio station", "pessoa": "person", "nome": "community", "distrito": "district",
           "so_acessos": "sign-ins only", "empresa": "company", "categoria": "action type"},
    "es": {"municipio": "municipio", "tipo": "tipo", "radio": "radio", "pessoa": "persona", "nome": "comunidad", "distrito": "distrito",
           "so_acessos": "solo accesos", "empresa": "empresa", "categoria": "tipo de acción"},
}


SIM_NAO = {"pt-BR": ("não", "sim"), "en": ("no", "yes"), "es": ("no", "sí")}


def _filtros_texto(f: dict, idioma: str = "pt-BR") -> str:
    partes = []
    for k, rot in _NOMES_FILTROS.get(idioma, _NOMES_FILTROS["pt-BR"]).items():
        if f.get(k):
            v = traducao.texto(ROTULOS.get(f[k], f[k]), idioma) if k == "tipo" else f[k]
            if isinstance(v, bool) or str(v).lower() in ("true", "false"):   # nunca "True"/"False" para quem lê
                v = SIM_NAO[idioma if idioma in SIM_NAO else "pt-BR"][str(v).lower() == "true"]
            partes.append(f"{rot}: {v}")
    return ", ".join(partes) or traducao.texto("sem filtros", idioma)


# ---------- os documentos ----------
def _cobertura(radios: list[dict], avisos: list[dict]) -> dict:
    cob = {}
    for a in avisos:
        for m in a["municipios"]:
            for c in m["comunidades"]:
                k = (RH.nome_comunidade(c, m), m["nome"])
                if k not in cob:
                    cob[k] = [r["nome"] for r in radios if r["ativa"] and alcanca(r, m["codigo_ibge"], c["nome"], c.get("distrito"))]
    return cob


def _comparacoes(emp: int, i: date, fim: date) -> tuple[list, list]:
    """Avisos e envios do mesmo mês do ano anterior (e de dezembro do ano anterior, se o mês é janeiro)."""
    try:
        ia, fa = i.replace(year=i.year - 1), fim.replace(year=fim.year - 1)
    except ValueError:
        ia, fa = i.replace(year=i.year - 1, day=28), fim.replace(year=fim.year - 1, day=28)
    av = banco.avisos(emp, ia, fa)
    if i.month == 1:
        av += banco.avisos(emp, date(i.year - 1, 12, 1), date(i.year - 1, 12, 31))
    return av, banco.envios(emp, [a["id"] for a in av])


def construir(u: dict, tipo: str, f: dict, idioma: str = "pt-BR") -> tuple[dict, dict, str]:
    """(documento, campos a mais do JSON, subtítulo), no idioma de quem pede (as contas não mudam)."""
    emp, hoje, H, D = u["empresa_id"], _hoje(), DIST.prazo_legal_horas, DIST.prazo_vital_dias_uteis
    cfg = config_empresa(emp) if emp else {}
    extra = {}
    filtros_avisos = {k: f.get(k) for k in ("municipio", "tipo", "radio", "pessoa")}
    if tipo == "mensal":
        i, fim, modo, fechado = periodo(f, "mes")
        av_ano = banco.avisos(emp, date(fim.year, 1, 1), fim)
        en_ano = banco.envios(emp, [a["id"] for a in av_ano])
        av_c, en_c = _comparacoes(emp, i, fim) if modo == "mes" else ([], [])
        regs = banco.registros(emp, date(fim.year, 1, 1), fim + timedelta(days=1))
        doc = RH.mensal(av_ano, en_ano, av_c, en_c, regs, i, fim, filtros_avisos, hoje, H, D, fechado)
        av_p = [a for a in av_ano if i <= a["criado_em"].astimezone(BRASILIA).date() <= fim]
        legado = R.mensal(av_p, en_ano, i, fim, filtros_avisos, H, D)   # os campos de antes, para quem já os usa
        extra = {k: legado[k] for k in ("periodo", "filtros", "resumo", "por_tipo", "por_radio", "por_comunidade", "fora_do_prazo",
                                         "sem_envio", "lista", "como_calculado")}
        extra["opcoes"] = _opcoes(av_ano, en_ano)
    elif tipo == "custos":
        i, fim, modo, fechado = periodo(f, "ano")
        ano = fim.year
        mes_ref = 12 if fim < date(hoje.year, hoje.month, 1) else hoje.month if modo == "ano" else fim.month
        fech = fechado or (modo == "mes" and fim < hoje)
        av = banco.avisos(emp, date(ano, 1, 1), date(ano, 12, 31))
        av_ant = banco.avisos(emp, date(ano - 1, 1, 1), date(ano - 1, 12, 31))
        doc = RH.custos(av, banco.envios(emp, [a["id"] for a in av]), av_ant, banco.envios(emp, [a["id"] for a in av_ant]), ano, mes_ref,
                        fech, filtros_avisos, cfg)
        extra["opcoes"] = _opcoes(av, banco.envios(emp, [a["id"] for a in av]))
    elif tipo == "comunidades":
        i, fim, modo, _ = periodo(f, "ano")
        av = banco.avisos(emp, i, fim)
        en = banco.envios(emp, [a["id"] for a in av])
        doc = RH.comunidades(av, en, _cobertura(banco_radios.radios(emp, so_ativas=False), av), i, fim, filtros_avisos, cfg)
        extra["opcoes"] = _opcoes(av, en)
    elif tipo == "prazos":
        i, fim, modo, _ = periodo(f, "mes")
        av = banco.avisos(emp, i, fim)
        en = banco.envios(emp, [a["id"] for a in av])
        if modo == "mes":
            ant_i = (i - timedelta(days=1)).replace(day=1)
            av_c = banco.avisos(emp, ant_i, i - timedelta(days=1))
            av_aa, _ = _comparacoes(emp, i, fim)
            av_c += av_aa
        else:
            av_c = []
        fut = banco.avisos_futuros(emp, hoje)
        doc = RH.prazos(av, en, av_c, banco.envios(emp, [a["id"] for a in av_c]), i, fim, filtros_avisos, hoje, fut,
                        banco.envios(emp, [a["id"] for a in fut]), H, D, mes=modo == "mes")
        extra["opcoes"] = _opcoes(av, en)
    elif tipo in ("auditoria", "acessos"):
        geral = tipo == "acessos"
        i, fim, modo, _ = periodo(f, "mes")
        rs = banco.registros(None if geral else emp, i, fim, pessoa=f.get("pessoa"), acoes=ACESSOS if f.get("so_acessos") else None,
                             empresa_sigla=f.get("empresa") if geral else None)
        linhas = _linhas(rs)
        if f.get("categoria"):
            linhas = [x for x in linhas if RH.categoria(x["acao"]) == f["categoria"]]
        v = banco_acesso.verificar_registro()
        doc = RH.auditoria(linhas, v if geral else {"ok": v["ok"], "motivo": None if v["ok"] else "não confere"}, geral, _rotulo(i, fim, modo))
        if not linhas and f.get("so_acessos"):   # 0 acessos: dizer se há outras ações com os mesmos filtros
            outras = len(banco.registros(None if geral else emp, i, fim, pessoa=f.get("pessoa"), acoes=None,
                                         empresa_sigla=f.get("empresa") if geral else None))
            if outras:
                doc.setdefault("alertas", []).append(f"Nenhum acesso no período. Há {outras} ação(ões) de outro tipo; "
                                                     "desmarque \"Só acessos\" para vê-las.")
        extra = {"periodo": {"inicio": i.isoformat(), "fim": fim.isoformat(), "rotulo": _rotulo(i, fim, modo)}, "linhas": linhas,
                 "total": len(linhas), "pessoas": sorted({x["usuario"] for x in linhas if x["usuario"]}),
                 "categorias": list(RH.CATEGORIAS) + ["outros"],
                 "filtros": {k: v for k, v in {"pessoa": f.get("pessoa"), "empresa": f.get("empresa") if geral else None,
                                               "só acessos": "sim" if f.get("so_acessos") else None}.items() if v}}
    elif tipo == "comunidade":
        if not (f.get("municipio") and f.get("nome")):
            raise HTTPException(422, "Ficha da comunidade: informe municipio (código IBGE) e nome.")
        i, fim = hoje - timedelta(days=365), hoje + timedelta(days=60)
        av = banco.avisos(emp, i - timedelta(days=30), hoje)
        en = banco.envios(emp, [a["id"] for a in av])
        radios = [r["nome"] for r in banco_radios.radios(emp) if alcanca(r, f["municipio"], f["nome"], f.get("distrito"))]
        enderecos = banco_territorio.enderecos_da_comunidade(f["municipio"], f["nome"], f.get("distrito"))
        fic = RH.ficha((f["municipio"], f["nome"], f.get("distrito") or ""), av, en, radios, enderecos, hoje, H, D)
        doc = RH.ficha_documento(fic)
        extra["ficha"] = fic
        modo = "intervalo"
        i, fim = hoje - timedelta(days=365), hoje
    elif tipo == "simulador":
        i, fim, modo, _ = periodo(f, "ano")
        av = banco.avisos(emp, i, fim)
        en = banco.envios(emp, [a["id"] for a in av])
        valores = cfg.get("simulador") or {}
        doc = SIM.documento(valores, av, en, filtros_avisos)
        extra = {"valores": {k: None if v is None else str(v) for k, v in valores.items()}, "pode_editar": pode(u["perfil"], "configurar_empresa"),
                 "opcoes": _opcoes(av, en)}
    else:
        raise HTTPException(404, "Relatório desconhecido.")
    T = lambda x: traducao.texto(x, idioma)
    sub = (f"{u.get('empresa_nome') or T('Todas as empresas')} · {T(_rotulo(i, fim, modo)) if tipo != 'comunidade' else T('últimos 12 meses')}"
           f" · {_filtros_texto(f, idioma)}")
    return traducao.documento(doc, idioma), extra, sub


def _opcoes(avisos: list[dict], envios: list[dict]) -> dict:
    return {"municipios": sorted({(m["codigo_ibge"], f"{m['nome']}/{m['uf']}") for a in avisos for m in a["municipios"]}, key=lambda x: x[1]),
            "tipos": sorted({a["tipo"] for a in avisos if a.get("tipo")}), "rotulos_tipos": ROTULOS,
            "radios": sorted({(e["radio_id"], e["radio_nome"]) for e in envios}, key=lambda x: x[1]),
            "pessoas": sorted({a["usuario"] for a in avisos if a.get("usuario")})}


def _linhas(rs: list[dict]) -> list[dict]:
    return [{"quando": r["quando"].astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M:%S"), "usuario": r["usuario"],
             "perfil": PERFIS.get(r["perfil"], r["perfil"] or ""), "empresa": r["empresa"], "acao": r["acao"], "detalhe": r["detalhe"],
             "codigo": codigo_verificacao(r["hash"]) if r["hash"] else None} for r in rs]


# ---------- geração, segunda via e envio ----------
def _registrar(u: dict, acao: str, detalhe: str) -> str:
    return codigo_verificacao(banco_acesso.registrar(acao, detalhe[:500], u["id"], u["empresa_id"])["hash"])


def gerar_pdf(u: dict, tipo: str, f: dict, idioma: str = "pt-BR") -> tuple[bytes, str, str, dict]:
    """O PDF do relatório: a linha "gerou" (o código), o PDF com o rodapé e a segunda via cifrada, com o SHA-256 na auditoria."""
    doc, _, sub = construir(u, tipo, f, idioma)
    codigo = _registrar(u, f"gerou relatório {tipo} (PDF)", f"{doc['titulo']}; {sub}")
    pdf = pdf_relatorio.documento_completo(doc, sub, _quem(u, idioma), codigo, datetime.now(BRASILIA), AVISO_FICTICIO, idioma=idioma)
    sha = hashlib.sha256(pdf).hexdigest()
    if not cofre.disponivel():
        raise HTTPException(503, "Sem a chave do cofre (FAROL_CHAVE_ARQUIVOS): a segunda via não seria guardada.")
    via_id = banco.guardar_via(u["empresa_id"], u["id"], u["nome"], tipo, doc["titulo"], sub, codigo, sha, len(pdf),
                               cofre.cifrar(pdf, u["empresa_id"] or 0, 0, f"relatorio:{codigo}"))
    banco_acesso.registrar("guardou a via do relatório", f"{codigo} (via {via_id}): sha256 {sha}", u["id"], u["empresa_id"])
    return pdf, codigo, sha, doc


def _nome_arquivo(tipo: str, codigo: str, formato: str) -> str:
    return f"farol-{tipo}-{codigo}.{formato}"


def _rota_json(tipo: str, acao: str):
    def rota(f: dict = Depends(filtros), u: dict = Depends(exigir(acao)), idioma: str = Depends(idioma_tela)) -> dict:
        doc, extra, sub = construir(u, tipo, f, idioma)
        banco_acesso.registrar(f"gerou relatório {tipo} (tela)", f"{doc['titulo']}; {sub}"[:500], u["id"], u["empresa_id"])
        return {**extra, "documento": doc, "subtitulo": sub,
                "projecao": None if not doc.get("projecao") else {k: str(v) if isinstance(v, Decimal) else v for k, v in doc["projecao"].items()}}
    rota.__name__ = f"relatorio_{tipo}"
    return rota


def _rota_arquivo(tipo: str, acao: str):
    def rota(formato: str, f: dict = Depends(filtros), u: dict = Depends(exigir(acao)), idioma: str = Depends(idioma_tela)) -> Response:
        if formato == "pdf":
            pdf, codigo, sha, _ = gerar_pdf(u, tipo, f, idioma)
            return Response(pdf, media_type="application/pdf", headers={
                "Content-Disposition": f'attachment; filename="{_nome_arquivo(tipo, codigo, "pdf")}"', "X-Codigo": codigo, "X-Sha256": sha})
        if formato == "csv":
            doc, _, sub = construir(u, tipo, f, idioma)
            codigo = _registrar(u, f"gerou relatório {tipo} (CSV)", f"{doc['titulo']}; {sub}")
            return Response("﻿" + RH.csv_documento(doc, sub, _quem(u, idioma), codigo), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{_nome_arquivo(tipo, codigo, "csv")}"', "X-Codigo": codigo})
        raise HTTPException(404, "Formato: pdf ou csv.")
    rota.__name__ = f"relatorio_{tipo}_arquivo"
    return rota


class PedidoEnvio(BaseModel):
    filtros: dict = Field(default_factory=dict)
    destinatarios: list[str] = Field(max_length=MAX_DESTINATARIOS * 2)


def _limite(usuario_id: int) -> None:
    agora, fila = time.monotonic(), _envios[usuario_id]
    while fila and agora - fila[0] > JANELA:
        fila.popleft()
    if len(fila) >= LIMITE_ENVIOS_REL:
        raise HTTPException(429, f"Limite de {LIMITE_ENVIOS_REL} envios de relatório por hora atingido.")
    fila.append(agora)


def _rota_enviar(tipo: str, acao: str):
    def rota(dados: PedidoEnvio, u: dict = Depends(exigir(acao)), _e: dict = Depends(exigir("enviar_relatorio")),
             idioma: str = Depends(idioma_tela)) -> dict:
        emp = banco_acesso.empresa(u["empresa_id"])
        destinos = list(dict.fromkeys(str(d).strip().lower() for d in dados.destinatarios if str(d).strip()))
        if not 1 <= len(destinos) <= MAX_DESTINATARIOS:
            raise erro(422, f"Destinatários: de 1 a {MAX_DESTINATARIOS} e-mails.", "destinatarios")
        ruins = [d for d in destinos if problema_email(d, emp["dominio"])]
        if ruins:
            raise erro(422, f"Só e-mails @{emp['dominio']} podem receber relatórios: {', '.join(ruins)}.", "destinatarios")
        if not correio.ligado():
            raise HTTPException(503, "O envio por e-mail está desligado neste servidor.")
        _limite(u["id"])
        f = limpar_filtros(dados.filtros)
        pdf, codigo, sha, doc = gerar_pdf(u, tipo, f, idioma)
        msg = email_relatorio.mensagem(remetente=correio.remetente(), destinos=destinos, titulo=doc["titulo"], codigo=codigo,
                                       gerado_por=_quem(u, idioma), empresa=emp["nome"], pdf=(_nome_arquivo(tipo, codigo, "pdf"), pdf),
                                       aviso_ficticio=traducao.aviso_ficticio(idioma, AVISO_FICTICIO), idioma=idioma)
        try:
            correio.enviar(msg)
        except correio.FalhaEnvio as e:
            banco_acesso.registrar(f"envio do relatório {tipo} falhou", f"{codigo} para {', '.join(destinos)}: {e}", u["id"], u["empresa_id"])
            raise HTTPException(502, f"O e-mail não foi entregue: {e}.") from None
        banco_acesso.registrar(f"enviou relatório {tipo} por e-mail", f"{codigo} para {', '.join(destinos)}; sha256 {sha}", u["id"], u["empresa_id"])
        return {"ok": True, "codigo": codigo, "destinatarios": destinos, "sha256": sha}
    rota.__name__ = f"relatorio_{tipo}_enviar"
    return rota


for _tipo, (_acao, _nome, _envia) in TIPOS.items():
    rotas.add_api_route(f"/api/relatorios/{_tipo}", _rota_json(_tipo, _acao), methods=["GET"])
    rotas.add_api_route(f"/api/relatorios/{_tipo}.{{formato}}", _rota_arquivo(_tipo, _acao), methods=["GET"])
    if _envia:
        rotas.add_api_route(f"/api/relatorios/{_tipo}/enviar", _rota_enviar(_tipo, _acao), methods=["POST"])


def _tipos_do_perfil(u: dict) -> tuple[str, ...]:
    return tuple(t for t, (acao, _, _) in TIPOS.items() if pode(u["perfil"], acao))


@rotas.get("/api/relatorios/vias")
def vias(u: dict = Depends(usuario_atual)) -> dict:
    """As segundas vias dos relatórios que o perfil pode ver (da própria empresa)."""
    return {"vias": [{"id": v["id"], "tipo": v["tipo"], "titulo": v["titulo"], "filtros": v["filtros"], "codigo": v["codigo"], "sha256": v["sha256"],
                      "tamanho": v["tamanho"], "por": v["usuario_nome"], "criado_em": v["criado_em"].isoformat()}
                     for v in banco.vias(u["empresa_id"], _tipos_do_perfil(u))]}


@rotas.get("/api/relatorios/vias/{id_}.pdf")
def baixar_via(id_: int, u: dict = Depends(usuario_atual)) -> Response:
    """A mesma via do relatório, decifrada; o SHA-256 é conferido com o guardado antes de entregar."""
    v = banco.via(id_, u["empresa_id"])
    if not v or v["tipo"] not in _tipos_do_perfil(u):
        raise HTTPException(404, "Via não encontrada.")
    try:
        pdf = cofre.decifrar(v["cifrado"], u["empresa_id"] or 0, 0, f"relatorio:{v['codigo']}")
    except cofre.SemChave:
        raise HTTPException(503, "Sem a chave do cofre neste servidor.") from None
    except cofre.Violado:
        banco_acesso.registrar("segunda via não confere (cofre)", v["codigo"], u["id"], u["empresa_id"])
        raise HTTPException(409, "A via guardada não confere (alterada). Nada foi entregue.") from None
    if hashlib.sha256(pdf).hexdigest() != v["sha256"]:
        banco_acesso.registrar("segunda via não confere (sha256)", v["codigo"], u["id"], u["empresa_id"])
        raise HTTPException(409, "A via guardada não confere com o SHA-256. Nada foi entregue.")
    banco_acesso.registrar("baixou a segunda via do relatório", f"{v['codigo']} (via {id_}): sha256 {v['sha256']} conferido",
                           u["id"], u["empresa_id"])
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{_nome_arquivo(v["tipo"], v["codigo"], "pdf")}"', "X-Codigo": v["codigo"],
        "X-Sha256": v["sha256"]})


# ---------- Comprovante de um aviso (como era) ----------
def _comprovante(id_: int, u: dict) -> dict:
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    return R.comprovante(a, banco.envios(u["empresa_id"], [id_]), DIST.prazo_legal_horas, DIST.prazo_vital_dias_uteis)


@rotas.get("/api/historico/{id_}/comprovante")
def comprovante(id_: int, u: dict = Depends(exigir("ver_historico"))) -> dict:
    return _comprovante(id_, u)


def _brl(v) -> str:
    return RH.brl(v)


def _tempo(s) -> str:
    return RH.tempo(s)


@rotas.get("/api/historico/{id_}/comprovante.pdf")
def comprovante_pdf(id_: int, u: dict = Depends(exigir("ver_historico"))) -> Response:
    c = _comprovante(id_, u)
    idioma = (banco_acesso.aviso(id_, u["empresa_id"]) or {}).get("idioma") or "pt-BR"   # o comprovante sai no idioma do aviso
    codigo = _registrar(u, "gerou comprovante do aviso (PDF)", f"aviso {id_} ({c['codigo']})")
    criado = datetime.fromisoformat(c["criado_em"]).astimezone(BRASILIA)
    p = c["prazo"]
    sec = [("titulo", "O desligamento"), ("numeros", [
        ("Aviso", f"nº {c['aviso']} - código {c['codigo'] or '-'}"), ("Situação", c["status"]),
        ("Solicitado por", f"{c['por']} ({PERFIS.get(c['perfil'], '')})"), ("Quando", f"{criado:%d/%m/%Y às %H:%M}"),
        ("Desligamento", f"{c['data']}, {c['horario']}"), ("Tipo", f"{c['tipo']} ({c['motivo']})"),
        ("Quem será desligado", selecao.descrever_resumo(c["escolha"], idioma) if c.get("escolha") else "-"),
        ("UCs no aviso", str(c["ucs"])), ("Com equipamento vital (só a contagem)", str(c["equipamento_vital"])),
        ("Prazo", f"{p['regra']}: " + ("sem envio registrado" if p["no_prazo"] is None else "no prazo" if p["no_prazo"] else f"fora do prazo ({p['atraso_horas']} h)")),
        ("Custo", _brl(c["custo"])), ("Economia calculada", _brl(c["economia_calculada"])), ("Economia informada", _brl(c["economia_informada"]))])]
    for m in c["municipios"]:
        sec += [("titulo", f"{m['nome']}: {m['ucs']} UCs, {m['equipamento_vital']} com equipamento vital"), ("texto", ", ".join(m["comunidades"]))]
    sec += [("titulo", "Envios às rádios"), ("tabela", ["Rádio", "Canal", "Quando", "Situação", "Confirmado em", "Valor", "Custo", "Economia", "Por"],
                                              [[e["radio"], e["canal"], datetime.fromisoformat(e["quando"]).astimezone(BRASILIA).strftime("%d/%m %H:%M"),
                                                STATUS.get(e["status"], e["status"]),
                                                datetime.fromisoformat(e["confirmado_em"]).astimezone(BRASILIA).strftime("%d/%m %H:%M") if e["confirmado_em"] else "-",
                                                _brl(e["valor"]), _brl(e["custo"]),
                                                f"{_brl(e['economia'])} ({e['economia_tipo']})" if e["economia"] is not None else "-", e["por"]]
                                               for e in c["envios"]], (3.2, 1.2, 1.4, 1.5, 1.4, 1.3, 1.3, 2, 1.8))]
    T = lambda x: traducao.texto(x, idioma) if isinstance(x, str) else x
    sec = [(s[0], T(s[1])) if s[0] in ("titulo", "texto") else (s[0], [(T(r), T(v)) for r, v in s[1]]) if s[0] == "numeros"
           else (s[0], [T(x) for x in s[1]], [[T(x) for x in ln] for ln in s[2]], *s[3:]) for s in sec]
    pdf = pdf_relatorio.documento(T(f"Comprovante do aviso nº {c['aviso']}"), T(f"{u.get('empresa_nome') or ''} - desligamento de {c['data']}, {c['horario']}"),
                                  _quem(u, idioma), codigo, sec, AVISO_FICTICIO, datetime.now(BRASILIA), idioma=idioma)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="farol-comprovante-aviso-{id_}.pdf"', "X-Codigo": codigo})


def painel_do_mes(empresa_id: int, hoje: date) -> dict:
    """Os números do mês corrente para o dashboard: gasto, economizado, avisos e % no prazo."""
    i, f = R.periodo_do_mes(f"{hoje:%Y-%m}")
    avisos = banco.avisos(empresa_id, i, f)
    r = R.mensal(avisos, banco.envios(empresa_id, [a["id"] for a in avisos]), i, f, {}, DIST.prazo_legal_horas,
                 DIST.prazo_vital_dias_uteis)["resumo"]
    return {"mes": R.rotulo_periodo(i, f), "gasto": r["custo"], "economia_calculada": r["economia_calculada"],
            "economia_informada": r["economia_informada"], "tempo_economizado": r["tempo_economizado"], "desligamentos": r["desligamentos"],
            "envios": r["envios"], "confirmados": r["confirmados"], "pct_no_prazo": r["pct_no_prazo"], "com_envio": r["com_envio"]}


# ---------- H7: ficha da comunidade e mapa de calor (só leitura, sem arquivo: não vai para a auditoria) ----------
@rotas.get("/api/comunidades/ficha")
def ficha_comunidade(municipio: str = Query(..., pattern=r"^\d{7}$"), nome: str = Query(..., min_length=1, max_length=120),
                     distrito: str | None = Query(None, max_length=120), u: dict = Depends(exigir("ver_historico"))) -> dict:
    """O painel da comunidade no mapa: contagens, rádios que alcançam e os desligamentos dos últimos 12 meses."""
    _, extra, _ = construir(u, "comunidade", {"municipio": municipio, "nome": nome, "distrito": distrito})
    return extra["ficha"]


@rotas.get("/api/comunidades/calor")
def calor(u: dict = Depends(exigir("ver_historico"))) -> dict:
    """Desligamentos por comunidade nos últimos 12 meses (chave: código IBGE|nome sem sufixo|distrito), para o mapa de calor."""
    hoje = _hoje()
    contagem = defaultdict(int)
    for a in banco.avisos(u["empresa_id"], hoje - timedelta(days=365), hoje):
        if a.get("status") == "cancelado":
            continue
        for m in a["municipios"]:
            for c in m["comunidades"]:
                contagem[f"{m['codigo_ibge']}|{str(c['nome']).split(' (')[0]}|{c.get('distrito') or ''}"] += 1
    return {"desde": (hoje - timedelta(days=365)).isoformat(), "comunidades": contagem, "maximo": max(contagem.values(), default=0)}
