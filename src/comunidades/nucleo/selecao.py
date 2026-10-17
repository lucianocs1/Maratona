"""Escolha de quem será desligado: a planilha pode ser a BASE DE CLIENTES (como a da Energisa), não a lista
de um desligamento. O operador diz quem fica sem luz e só essas UCs seguem para as travas e o aviso.

Puro: recebe o JSON validado da planilha (nucleo/esquema_planilha.py), o critério e a comunidade de cada
linha (que a API calcula pela base territorial, nucleo/afetados.localizar) e devolve as linhas escolhidas
e a conta. O navegador repete as mesmas regras para o contador ao vivo; quem decide é o servidor.

O critério (Criterio) é o que fica registrado: nunca a lista de UCs.
- modo "planilha": a planilha já é a lista do desligamento (vem do sistema de manobras);
- modo "escolha": filtros por circuito, conjunto, transformador e bairro (caixas de marcar) e, no mapa,
  polígonos desenhados e comunidades clicadas. Dentro de um filtro vale qualquer um dos valores marcados;
  entre filtros diferentes, a UC tem de atender a todos. O mapa (polígonos e comunidades, juntos) conta como
  mais um filtro: a UC entra se estiver dentro de algum polígono ou numa das comunidades.
- inativas (SITUACAO = INATIVO...) ficam fora, salvo com incluir_inativas.
Linha sem coordenada (rejeitada) não tem como estar dentro do mapa; se tiver equipamento vital e atender aos
outros filtros, entra assim mesmo (não dá para saber se está na área) e a trava de equipamento vital bloqueia.
A conta fecha sempre: lidas = inativas fora + não escolhidas + escolhidas; escolhidas = ok + corrigidas + rejeitadas.
O ponto é testado no polígono com 5 casas decimais, as mesmas do mapa da tela.
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import area as area_
from .esquema_planilha import PlanilhaJSON, Resumo, Vital
from .planilha import inativa

FILTROS = ("circuito", "conjunto", "transformador", "bairro")
NOMES_FILTRO = {"circuito": ("circuito", "circuitos"), "conjunto": ("conjunto", "conjuntos"),
                "transformador": ("transformador", "transformadores"), "bairro": ("bairro", "bairros")}
MAX_VALORES = 2000          # valores marcados num filtro
MAX_COMUNIDADES = 2000
MAX_POLIGONOS = 50
CASAS_PONTO = 5             # as mesmas do mapa da tela (api/app.CASAS_PONTO)
MAX_CITADOS = 8             # valores citados por filtro na descrição (o resto vira "+N")
_CRITERIO = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

Anel = tuple[tuple[float, float], ...]


class ComunidadeEscolhida(BaseModel):
    model_config = _CRITERIO
    municipio: str = Field(pattern=r"^\d{7}$")       # código IBGE
    nome: str = Field(min_length=1, max_length=120)


class Criterio(BaseModel):
    """Quem será desligado. Recusa campo a mais; canonico() deixa a mesma escolha sempre igual."""
    model_config = _CRITERIO
    modo: Literal["planilha", "escolha"]
    circuito: tuple[str, ...] = Field((), max_length=MAX_VALORES)
    conjunto: tuple[str, ...] = Field((), max_length=MAX_VALORES)
    transformador: tuple[str, ...] = Field((), max_length=MAX_VALORES)
    bairro: tuple[str, ...] = Field((), max_length=MAX_VALORES)
    poligonos: tuple[tuple[Anel, ...], ...] = Field((), max_length=MAX_POLIGONOS)   # [lon, lat], como no GeoJSON
    comunidades: tuple[ComunidadeEscolhida, ...] = Field((), max_length=MAX_COMUNIDADES)
    incluir_inativas: bool = False

    @model_validator(mode="after")
    def _coerente(self):
        for f in FILTROS:
            if any(not v or len(v) > 60 for v in getattr(self, f)):
                raise ValueError(f"{f}: valor vazio ou com mais de 60 caracteres")
        tem = self.tem_filtro()
        if self.modo == "planilha" and tem:
            raise ValueError("a planilha inteira não leva filtros nem mapa")
        if self.modo == "escolha" and not tem:
            raise ValueError("escolha pelo menos um filtro, uma comunidade ou uma área no mapa")
        for p in self.poligonos:
            if not p or any(len(anel) < 4 or anel[0] != anel[-1] for anel in p):
                raise ValueError("polígono: cada anel com pelo menos 3 pontos e fechado")
            if any(not (-180 <= x <= 180 and -90 <= y <= 90) for anel in p for x, y in anel):
                raise ValueError("polígono fora dos limites de latitude e longitude")
        if area_.n_vertices(self.poligonos_lista()) > area_.MAX_VERTICES:
            raise ValueError(f"a área tem mais de {area_.MAX_VERTICES} vértices")
        return self

    def tem_filtro(self) -> bool:
        return any(getattr(self, f) for f in FILTROS) or bool(self.poligonos or self.comunidades)

    def tem_mapa(self) -> bool:
        return bool(self.poligonos or self.comunidades)

    def poligonos_lista(self) -> list:
        return [[[list(v) for v in anel] for anel in p] for p in self.poligonos]


def canonico(c: Criterio) -> Criterio:
    """A mesma escolha sempre do mesmo jeito: valores sem repetição e em ordem, área com 6 casas."""
    return Criterio(modo=c.modo, incluir_inativas=c.incluir_inativas,
                    **{f: tuple(sorted(set(getattr(c, f)))) for f in FILTROS},
                    poligonos=tuple(tuple(tuple(tuple(v) for v in anel) for anel in p) for p in area_.arredondar(c.poligonos_lista())),
                    comunidades=tuple(ComunidadeEscolhida(municipio=m, nome=n)
                                      for m, n in sorted({(x.municipio, x.nome) for x in c.comunidades})))


def texto_canonico(c: Criterio) -> str:
    """O critério canônico em texto: o que o pacote assinado leva e o que o sha256 identifica."""
    return json.dumps(canonico(c).model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256(c: Criterio) -> str:
    return hashlib.sha256(texto_canonico(c).encode("utf-8")).hexdigest()


# ---------- a escolha ----------
@dataclass(frozen=True)
class Escolha:
    modelo: PlanilhaJSON        # só as linhas escolhidas (o resumo refeito sobre elas); o arquivo é o mesmo
    conta: dict                 # lidas, inativas_fora, nao_escolhidas, escolhidas, ok, corrigidas, rejeitadas
    inativas: dict              # inativas fora, contadas por bairro e por circuito (nunca a UC)
    linhas: tuple[int, ...]     # as linhas escolhidas (números de linha da planilha, para os testes)


def _dentro(pontos, poligonos: list) -> set[int]:
    """Linhas dentro de algum polígono, com as coordenadas arredondadas como no mapa."""
    com = [p for p in pontos if p.lat is not None]
    idx = area_.ucs_na_area([round(p.lat, CASAS_PONTO) for p in com], [round(p.lon, CASAS_PONTO) for p in com], poligonos)
    return {com[i].linha for i in idx}


def escolhidas(m: PlanilhaJSON, c: Criterio, comunidade: dict[int, tuple[str, str]]) -> tuple[list, list]:
    """(linhas escolhidas, linhas inativas que ficaram fora), pelos pontos do JSON, na ordem da planilha.
    comunidade: linha -> (código IBGE, nome) das linhas localizadas numa comunidade."""
    na_area = _dentro(m.pontos, c.poligonos_lista()) if c.poligonos else set()
    comunidades = {(x.municipio, x.nome) for x in c.comunidades}
    valores = {f: set(getattr(c, f)) for f in FILTROS if getattr(c, f)}
    entram, inativas = [], []
    for pt in m.pontos:
        if inativa(pt.situacao) and not c.incluir_inativas:
            inativas.append(pt)
            continue
        if c.modo == "planilha":
            entram.append(pt)
            continue
        if any(getattr(pt, f) not in v for f, v in valores.items()):
            continue
        if c.tem_mapa():
            no_mapa = pt.linha in na_area or comunidade.get(pt.linha) in comunidades
            sem_posicao_vital = pt.lat is None and pt.equipamento_vital is True
            if not (no_mapa or sem_posicao_vital):
                continue
        entram.append(pt)
    return entram, inativas


def _resumo(pontos) -> Resumo:
    conta = Counter(p.status for p in pontos)
    vital = Counter("a_confirmar" if p.equipamento_vital is None else "sim" if p.equipamento_vital else "nao"
                    for p in pontos if p.status != "rejeitada")
    return Resumo(total=len(pontos), ok=conta["ok"], corrigidas=conta["corrigida"], rejeitadas=conta["rejeitada"],
                  avisos=sum(len(p.avisos) for p in pontos),
                  equipamento_vital=Vital(sim=vital["sim"], nao=vital["nao"], a_confirmar=vital["a_confirmar"]))


def aplicar(m: PlanilhaJSON, c: Criterio, comunidade: dict[int, tuple[str, str]]) -> Escolha:
    """O JSON só com as linhas escolhidas (as travas e o aviso valem sobre elas) e a conta da escolha."""
    entram, inativas = escolhidas(m, canonico(c), comunidade)
    r = _resumo(entram)
    conta = {"lidas": m.resumo.total, "inativas_fora": len(inativas), "nao_escolhidas": m.resumo.total - len(inativas) - len(entram),
             "escolhidas": len(entram), "ok": r.ok, "corrigidas": r.corrigidas, "rejeitadas": r.rejeitadas}
    if not (conta["lidas"] == conta["inativas_fora"] + conta["nao_escolhidas"] + conta["escolhidas"]
            and conta["escolhidas"] == r.ok + r.corrigidas + r.rejeitadas):
        raise ValueError("a conta da escolha não fecha")
    sem = "não informado"
    por = {"bairro": dict(sorted(Counter(p.bairro or sem for p in inativas).items())),
           "circuito": dict(sorted(Counter(p.circuito or sem for p in inativas).items()))}
    return Escolha(m.model_copy(update={"pontos": tuple(entram), "resumo": r}), conta, por, tuple(p.linha for p in entram))


# ---------- o que fica registrado (auditoria, histórico e PDF): o critério, nunca as UCs ----------
# as palavras da descrição em cada idioma (o PDF do comprovante sai no idioma do aviso); singular e plural
PALAVRAS = {
    "pt-BR": {"planilha": "a planilha inteira (lista do desligamento)", "area": ("área desenhada", "polígono", "polígonos", "vértices"),
              "comunidade": ("comunidade", "comunidades"), "circuito": ("circuito", "circuitos"), "conjunto": ("conjunto", "conjuntos"),
              "transformador": ("transformador", "transformadores"), "bairro": ("bairro", "bairros"), "uc": ("UC", "UCs"),
              "e": " e ", "inativas": " (inativas incluídas)"},
    "en": {"planilha": "the whole spreadsheet (outage list)", "area": ("drawn area", "polygon", "polygons", "vertices"),
           "comunidade": ("community", "communities"), "circuito": ("circuit", "circuits"), "conjunto": ("set", "sets"),
           "transformador": ("transformer", "transformers"), "bairro": ("neighborhood", "neighborhoods"), "uc": ("UC", "UCs"),
           "e": " and ", "inativas": " (inactive included)"},
    "es": {"planilha": "toda la planilla (lista del corte)", "area": ("área dibujada", "polígono", "polígonos", "vértices"),
           "comunidade": ("comunidad", "comunidades"), "circuito": ("circuito", "circuitos"), "conjunto": ("conjunto", "conjuntos"),
           "transformador": ("transformador", "transformadores"), "bairro": ("barrio", "barrios"), "uc": ("UC", "UC"),
           "e": " y ", "inativas": " (inactivas incluidas)"},
}


def _lista(valores, citados: int = MAX_CITADOS) -> str:
    v = list(valores)
    return ", ".join(v[:citados]) + (f" (+{len(v) - citados})" if len(v) > citados else "")


def descrever_resumo(r: dict, idioma: str = "pt-BR") -> str:
    """A descrição a partir do que o histórico guarda (resumo()), no idioma pedido (sem ele, em português)."""
    w = PALAVRAS.get(idioma, PALAVRAS["pt-BR"])
    um = lambda par, n: par[0] if n == 1 else par[1]
    partes = [w["planilha"]] if r["modo"] == "planilha" else []
    if r["poligonos"]:
        a = w["area"]
        partes.append(f"{a[0]} ({r['poligonos']} {a[1] if r['poligonos'] == 1 else a[2]}, {r['vertices']} {a[3]})")
    if r["comunidades"]:
        partes.append(f"{um(w['comunidade'], len(r['comunidades']))} {_lista(r['comunidades'])}")
    for f in FILTROS:
        if r[f]:
            partes.append(f"{um(w[f], len(r[f]))} {_lista(r[f])}")
    ucs, com = r["conta"]["escolhidas"], r["comunidades_no_aviso"]
    texto = w["e"].join(partes) + f", {ucs} {um(w['uc'], ucs)}, {com} {um(w['comunidade'], com)}"
    return (texto + (w["inativas"] if r["incluir_inativas"] else ""))[:600]


def resumo(c: Criterio, conta: dict, comunidades: int) -> dict:
    """O que o histórico guarda da escolha: o critério (contagens da área e os valores marcados, nunca as UCs), a conta,
    o sha256 do critério canônico e o texto (em português, como vai para a auditoria)."""
    c = canonico(c)
    r = {"modo": c.modo, "sha256": sha256(c), "poligonos": len(c.poligonos), "vertices": area_.n_vertices(c.poligonos_lista()),
         "comunidades": [x.nome for x in c.comunidades], **{f: list(getattr(c, f)) for f in FILTROS},
         "incluir_inativas": c.incluir_inativas, "conta": dict(conta), "comunidades_no_aviso": comunidades}
    return {**r, "texto": descrever_resumo(r)}


def descrever(c: Criterio, ucs: int, comunidades: int, idioma: str = "pt-BR") -> str:
    """'área desenhada (1 polígono, 5 vértices), 42 UCs, 3 comunidades' ou 'circuitos CIR147, CIR771, 96 UCs, 2 comunidades'."""
    return descrever_resumo(resumo(c, {"escolhidas": ucs}, comunidades), idioma)
