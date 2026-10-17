"""Tradutor da planilha de UCs afetadas: as linhas lidas -> o JSON padronizado (nucleo/esquema_planilha.py).

Puro: recebe só as colunas do modelo (a leitura, em api/leitura.py, já descartou as outras) com os
valores como estavam nas células, e devolve os pontos e o resumo. Nenhuma parte do sistema usa a
planilha bruta: afetados, aviso, mapa e histórico consomem só o JSON validado (validas()).

Cada linha sai com status ok, corrigida ou rejeitada, motivo, correção e avisos das listas fechadas
(nucleo/motivos.py), nunca texto livre. A conta fecha sempre: linhas lidas = ok + corrigidas + rejeitadas.
Regras:
- célula com mais de 200 caracteres numa coluna mantida: a linha é rejeitada;
- UC vazia ou inválida: rejeitada; UC repetida: a primeira linha válida entra (com aviso), as
  seguintes são rejeitadas apontando a linha que entrou;
- coordenada: nucleo/coordenadas.py (formatos, correção só dentro da concessão, motivos);
- textos: Unicode normalizado (NFC), sem caracteres de controle e invisíveis, espaços juntados e
  cortados no limite do campo (40 para classe, transformador, circuito e conjunto; 60 para o bairro;
  20 para a situação; 80 para o local);
- local: de uma coluna de endereço, só o nome da rua (so_rua); URBANO/RURAL não é local;
- avisos de grupo: coordenada repetida, a mesma coordenada em muitas UCs, ponto isolado (longe de
  todos os outros da planilha).
"""

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.neighbors import KDTree

from . import coordenadas as K
from .esquema_planilha import FORMATO, VERSAO, PlanilhaJSON, validar_dados
from .motivos import Aviso, FormulaSemValor, Motivo

VERSAO_TRADUTOR = "2.1.0"   # muda quando a tradução de um mesmo arquivo puder mudar

# nomes de coluna aceitos para cada campo (depois de minúsculas, sem acento e com "_" no lugar de espaço)
SINONIMOS = {
    "uc": ("uc", "unidade_consumidora", "numero_uc", "num_uc", "n_uc", "codigo_uc", "instalacao", "numcdc"),
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lon", "long", "lng", "x"),
    "equipamento_vital": ("equipamento_vital", "vital", "equip_vital", "aparelho_vital"),
    "classe": ("classe", "classe_uc", "categoria"),
    # o que o aviso de hoje cita para a UC (o imóvel no rural, a rua no urbano): só para o comparativo
    # a ordem importa: na base da distribuidora a coluna LOCAL é URBANO/RURAL, não o imóvel; por isso
    # endereco vem antes de local (no modelo antigo, sem endereco, local continua valendo)
    "local": ("local_aviso", "imovel", "nome_imovel", "endereco", "local"),
    "transformador": ("transformador", "trafo", "cod_trafo", "codigo_trafo", "cod_transformador"),
    "circuito": ("circuito", "alimentador", "cod_circuito", "codigo_circuito"),
    # para escolher quem será desligado numa base de clientes (nucleo/selecao.py): conjunto, bairro e situação
    "conjunto": ("conjunto", "conjunto_eletrico", "cod_conjunto", "codigo_conjunto"),
    "bairro": ("bairro", "nome_bairro"),
    "situacao": ("situacao", "situacao_uc", "status_uc", "situacao_cliente"),
    # alternativas à latitude/longitude decimal (nucleo/coordenadas.py)
    "celula": ("coordenada", "coordenadas", "lat_lon", "latlon", "lat_long", "latitude_longitude", "gps"),
    "lat_gms": ("lat_gms", "latitude_gms"),
    "lon_gms": ("long_gms", "lon_gms", "longitude_gms"),
    "coord_x": ("coord_x", "utm_x", "x_utm", "easting"),
    "coord_y": ("coord_y", "utm_y", "y_utm", "northing"),
}
# só estas colunas são lidas; todas as outras (nome, número da casa, medidor, conta...) são descartadas
# logo depois de achar o cabeçalho, antes de qualquer processamento
MANTIDAS = tuple(SINONIMOS)
# uma fonte de coordenada basta (a primeira completa, na ordem de nucleo/coordenadas.interpretar)
FONTES_COORDENADA = (("latitude", "longitude"), ("celula",), ("lat_gms", "lon_gms"), ("coord_x", "coord_y"))
# colunas de endereço completo: delas o aviso de hoje leva só o nome da rua (so_rua)
ENDERECO = ("endereco",)
NAO_E_LOCAL = {"urbano", "urbana", "rural"}       # a coluna LOCAL da base da distribuidora
SIM = {"sim", "s", "1", "true", "verdadeiro", "x", "yes", "y"}
NAO = {"nao", "n", "0", "false", "falso", "no", ""}
MAX_LINHAS = 50_000
LIMITE_CELULA = 200          # caracteres de uma célula mantida (mais que isso: a linha é rejeitada)
MAX_UC = 40
LIMITES_TEXTO = {"classe": 40, "transformador": 40, "circuito": 40, "conjunto": 40, "bairro": 60, "situacao": 20, "local": 80}
# situação da UC na base de clientes que fica fora do aviso por padrão (outro valor ou vazio: ativa, avisada)
INATIVA = {"inativo", "inativa", "desligado", "desligada"}
CASAS_PONTO = 7              # casas decimais de lat/lon no JSON (~1 cm), o mesmo em qualquer máquina


class PlanilhaInvalida(ValueError):
    """A planilha inteira não pode ser usada (coluna obrigatória faltando, vazia, grande demais)."""


class ContaNaoFecha(RuntimeError):
    """Linhas lidas diferente de ok + corrigidas + rejeitadas: nada é entregue."""


@dataclass(frozen=True)
class Parametros:
    dentro: Callable[[float, float], bool] | None   # a área da concessão com a margem (coordenadas.Area)
    epsg_utm: int = K.EPSG_UTM_PADRAO               # fuso UTM da empresa
    isolado_km: float = 20.0                        # ponto mais longe que isso do vizinho mais próximo: aviso
    muitas_ucs: int = 10                            # a mesma coordenada em tantas UCs ou mais: aviso


# ---------- colunas ----------
def _chave(nome: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(nome)) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def colunas(cabecalho: list[str]) -> dict[str, str]:
    """Campo do modelo -> coluna da planilha que o traz (a primeira que bater com um sinônimo)."""
    return {campo: cabecalho[i] for campo, i in campos_por_indice(cabecalho).items()}


def campos_por_indice(cabecalho: list) -> dict[str, int]:
    """Campo do modelo -> posição da coluna que o traz (a primeira que bater, na ordem dos sinônimos).
    Colunas sem campo não aparecem: são as descartadas."""
    por_chave: dict[str, int] = {}
    for i, c in enumerate(cabecalho):
        if c is not None and str(c).strip():
            por_chave.setdefault(_chave(c), i)
    achadas = {}
    for campo, nomes in SINONIMOS.items():
        i = next((por_chave[n] for n in nomes if n in por_chave), None)
        if i is not None:
            achadas[campo] = i
    return achadas


def serve(campos) -> bool:
    """A aba tem o que é obrigatório: a UC e pelo menos uma fonte completa de coordenada."""
    return "uc" in campos and any(all(c in campos for c in fonte) for fonte in FONTES_COORDENADA)


# ---------- endereço -> só a rua ----------
_CEP = re.compile(r"\bCEP\b\.?:?\s*\d{2}\.?\d{3}-?\d{3}|\b\d{2}\.?\d{3}-\d{3}\b|\b\d{8}\b", re.I)
_CORTE = re.compile(r",|\s[-–—]\s|\s\(")   # depois da vírgula, do " - " ou do "(" vem número, bairro ou cidade
_NUMERO = re.compile(r"\s+(n[º°ºo]\.?|n\.|num\.?|n[úu]mero)\s*\d.*$", re.I)
_COMPLEMENTO = re.compile(r"\s+(casa|ap|apt|apto|apartamento|lote|lt|quadra|qd|bloco|bl|sala|loja|km|s/n|s\.n\.?|sn)"
                          r"(\.|\b|$).*$", re.I)
# um número solto no fim é o da casa, salvo quando é o nome da via ("Estrada 267") ou de uma rodovia ("BR 116")
_TIPO_VIA = {"rua", "r", "avenida", "av", "travessa", "tv", "alameda", "al", "praca", "pc", "estrada", "est",
             "rodovia", "rod", "beco", "vila", "largo", "ladeira", "acesso", "via", "viela", "servidao"}
_RODOVIA = set("BR AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
_FIM_NUMERO = re.compile(r"^(?P<antes>.*?)\s+(?P<num>\d+[a-zA-Z]?)$")


def e_so_tipo_de_via(texto: str) -> bool:
    """'Rua', 'Av.', 'Beco': só o tipo, sem o nome (o que vem depois dele é o nome da via)."""
    p = str(texto).split()
    return len(p) == 1 and _chave(p[0]) in _TIPO_VIA


def so_rua(endereco: str) -> str:
    """'Rua das Flores, 123, casa 2 - CEP 36700-000' -> 'Rua das Flores'; 'Av. Brasil nº 45' -> 'Av. Brasil'.

    Tira o CEP, o que vem depois da vírgula ou do " - " (número, bairro, cidade), o "nº 45" e o
    complemento (casa, apto, lote...). Um nome sem nada disso ("Fazenda Boa Vista") fica igual.
    Vazio quando não sobra nome de rua."""
    s = _CEP.sub(" ", " ".join(str(endereco).split()))
    s = _CORTE.split(s, maxsplit=1)[0]
    sem_numero = _NUMERO.sub("", s)
    if not e_so_tipo_de_via(sem_numero):   # "Beco Número 399" (CNEFE) é o nome da via, não o número da casa
        s = sem_numero
    s = _COMPLEMENTO.sub("", s)
    m = _FIM_NUMERO.match(s.strip())
    if m:
        antes = m.group("antes").split()
        so_o_tipo = e_so_tipo_de_via(m.group("antes"))
        rodovia = antes[-1].upper() in _RODOVIA   # Rodovia BR 116, Estrada MG 120
        # "Beco Número 399": se o "número" sobrou até aqui, é parte do nome da via (o _NUMERO não o tirou)
        numero_da_via = _chave(antes[-1]) in {"numero", "n", "no", "num"}
        if not (so_o_tipo or rodovia or numero_da_via):
            s = m.group("antes")
    return s.strip(" .,;:-–—/")


# ---------- valores de uma célula ----------
def limpar(texto: str) -> str:
    """Unicode normalizado (NFC), sem caracteres de controle nem invisíveis, espaços juntados."""
    s = unicodedata.normalize("NFC", texto)
    s = "".join(c if unicodedata.category(c)[0] != "C" else " " for c in s)
    return " ".join(s.split())


def _como_texto(v) -> str:
    """Valor de célula -> texto (número inteiro sem ".0"; data no formato ISO)."""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, float) and v.is_integer() and math.isfinite(v):
        return str(int(v))
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return str(v)


def _longa(v) -> bool:
    return isinstance(v, str) and len(v) > LIMITE_CELULA


def _uc(v) -> tuple[str | None, Motivo | None]:
    if v is None or (isinstance(v, str) and not limpar(v)):
        return None, Motivo.UC_VAZIA
    if isinstance(v, (FormulaSemValor, bool, datetime, date, time, timedelta)) or \
            (isinstance(v, float) and not math.isfinite(v)):
        return None, Motivo.UC_INVALIDA
    s = limpar(_como_texto(v))
    if s.endswith(".0") and s[:-2].isdigit():   # número lido como decimal (csv exportado)
        s = s[:-2]
    if len(s) > MAX_UC:
        return None, Motivo.UC_INVALIDA
    return s, None


def _texto(v, limite: int, avisos: list) -> str | None:
    if v is None:
        return None
    if isinstance(v, FormulaSemValor):
        avisos.append(Aviso.CAMPO_FORMULA)
        return None
    s = limpar(_como_texto(v))
    if len(s) > limite:
        avisos.append(Aviso.TEXTO_CORTADO)
        s = s[:limite].rstrip()
    return s or None


def _vital(v, avisos: list) -> bool | None:
    if v is None:
        return False
    if isinstance(v, FormulaSemValor):
        avisos.append(Aviso.CAMPO_FORMULA)
        return None
    if isinstance(v, bool):
        return v
    txt = _chave(_como_texto(v))
    if txt in SIM:
        return True
    if txt in NAO:
        return False
    avisos.append(Aviso.VITAL_INVALIDO)
    return None


# ---------- a tradução ----------
def _ponto(numero: int, valores: list, campos: dict, p: Parametros, endereco: bool) -> dict:
    cel = lambda c: valores[campos[c]] if c in campos else None
    pt = {"linha": numero, "uc": None, "lat": None, "lon": None, "equipamento_vital": None, "classe": None, "local": None,
          "transformador": None, "circuito": None, "conjunto": None, "bairro": None, "situacao": None, "status": K.REJEITADA, "motivo": None, "correcao": None,
          "original": None, "repete_linha": None, "avisos": []}
    pt["uc"], motivo_uc = _uc(cel("uc")) if not _longa(cel("uc")) else (None, Motivo.UC_INVALIDA)
    if any(_longa(v) for v in valores):
        # a UC e o equipamento vital ficam registrados (conferência independente e alerta de vital)
        if "equipamento_vital" in campos and not _longa(cel("equipamento_vital")):
            pt["equipamento_vital"] = _vital(cel("equipamento_vital"), [])
        pt["motivo"] = Motivo.CELULA_LONGA
        return pt
    c = K.interpretar(cel("latitude"), cel("longitude"), celula=cel("celula"), lat_gms=cel("lat_gms"),
                      lon_gms=cel("lon_gms"), x=cel("coord_x"), y=cel("coord_y"), epsg_utm=p.epsg_utm, dentro=p.dentro)
    redondo = lambda v: round(v, CASAS_PONTO)
    ponto = (c.lat, c.lon) if c.lat is not None else c.lido
    if ponto is not None:
        pt["lat"], pt["lon"] = redondo(ponto[0]), redondo(ponto[1])
    avisos = list(c.avisos)
    # sem a coluna: "a confirmar"; com a coluna e a célula vazia: não (como no modelo da planilha)
    pt["equipamento_vital"] = _vital(cel("equipamento_vital"), avisos) if "equipamento_vital" in campos else None
    for campo in ("classe", "transformador", "circuito", "conjunto", "bairro", "situacao"):
        pt[campo] = _texto(cel(campo), LIMITES_TEXTO[campo], avisos)
    local = cel("local")
    if isinstance(local, str) and endereco:
        local = so_rua(local)
    local = _texto(local, LIMITES_TEXTO["local"], avisos)
    pt["local"] = None if local and _chave(local) in NAO_E_LOCAL else local
    pt["avisos"] = avisos
    if motivo_uc:
        pt["motivo"] = motivo_uc
    elif c.status == K.REJEITADA:
        pt["motivo"] = c.motivo
    else:
        pt["status"], pt["correcao"] = c.status, c.correcao
        pt["original"] = (redondo(c.original[0]), redondo(c.original[1])) if c.original else None
    return pt


def _avisos_de_grupo(pontos: list[dict], p: Parametros) -> None:
    """UC repetida, coordenada repetida, a mesma coordenada em muitas UCs e ponto isolado."""
    primeira: dict[str, dict] = {}
    for pt in pontos:
        if pt["status"] == K.REJEITADA:
            continue
        if pt["uc"] in primeira:
            pt.update(status=K.REJEITADA, motivo=Motivo.UC_REPETIDA, correcao=None, original=None,
                      repete_linha=primeira[pt["uc"]]["linha"])
            if Aviso.UC_REPETIDA not in primeira[pt["uc"]]["avisos"]:
                primeira[pt["uc"]]["avisos"].append(Aviso.UC_REPETIDA)
        else:
            primeira[pt["uc"]] = pt
    aceitos = [pt for pt in pontos if pt["status"] != K.REJEITADA]
    por_ponto = defaultdict(list)
    for pt in aceitos:
        por_ponto[(pt["lat"], pt["lon"])].append(pt)
    for grupo in por_ponto.values():
        if len(grupo) > 1:
            for pt in grupo:
                pt["avisos"].append(Aviso.COORD_DUPLICADA)
                if len(grupo) >= p.muitas_ucs:
                    pt["avisos"].append(Aviso.COORD_MUITAS_UCS)
    if len(por_ponto) > 1:
        unicos = list(por_ponto)
        lat0 = math.radians(float(np.mean([u[0] for u in unicos])))
        xy = np.array([[u[1] * 111_320 * math.cos(lat0), u[0] * 110_574] for u in unicos])
        dist, _ = KDTree(xy).query(xy, k=2)
        for (u, d) in zip(unicos, dist[:, 1]):
            if d > p.isolado_km * 1000:
                for pt in por_ponto[u]:
                    pt["avisos"].append(Aviso.PONTO_ISOLADO)


def traduzir(campos: dict[str, int], linhas: list[tuple[int, list]], p: Parametros,
             endereco: bool = False) -> tuple[list[dict], dict]:
    """Os pontos (um por linha lida, na ordem) e o resumo. endereco: a coluna do local é de endereço."""
    pontos = [_ponto(n, valores, campos, p, endereco) for n, valores in linhas]
    _avisos_de_grupo(pontos, p)
    conta = Counter(pt["status"] for pt in pontos)
    aceitos = [pt for pt in pontos if pt["status"] != K.REJEITADA]
    vital = Counter("a_confirmar" if pt["equipamento_vital"] is None else "sim" if pt["equipamento_vital"] else "nao"
                    for pt in aceitos)
    resumo = {"total": len(linhas), "ok": conta[K.OK], "corrigidas": conta[K.CORRIGIDA], "rejeitadas": conta[K.REJEITADA],
              "avisos": sum(len(pt["avisos"]) for pt in pontos),
              "equipamento_vital": {k: vital[k] for k in ("sim", "nao", "a_confirmar")}}
    if resumo["total"] != resumo["ok"] + resumo["corrigidas"] + resumo["rejeitadas"]:   # nunca entrega conta aberta
        raise ContaNaoFecha("linhas lidas diferente de ok + corrigidas + rejeitadas")
    return pontos, resumo


def montar(campos: dict[str, int], cabecalho: list[str], linhas: list[tuple[int, list]], p: Parametros, *,
           arquivo: dict, empresa: str, gerado_em: str, gerado_por: str) -> PlanilhaJSON:
    """O JSON padronizado inteiro, já conferido pelo esquema (levanta erro se algo não bate)."""
    endereco = "local" in campos and _chave(cabecalho[campos["local"]]) in ENDERECO
    pontos, resumo = traduzir(campos, linhas, p, endereco)
    return validar_dados({
        "formato": FORMATO, "versao": VERSAO, "tradutor": VERSAO_TRADUTOR,
        "empresa": empresa, "gerado_em": gerado_em, "gerado_por": gerado_por,
        "arquivo": {**arquivo, "linhas": len(linhas)},
        "colunas": [c for c in SINONIMOS if c in campos],
        "pontos": pontos, "resumo": resumo,
    })


# ---------- o que o resto do sistema consome ----------
def inativa(situacao: str | None) -> bool:
    """A situação da base de clientes diz que a UC está inativa (fica fora do aviso por padrão)."""
    return situacao is not None and _chave(situacao) in INATIVA


def validas(m: PlanilhaJSON) -> pd.DataFrame:
    """As linhas que entram (ok e corrigidas), do JSON validado: LINHA, UC, LAT, LON, VITAL, CLASSE, LOCAL..."""
    return pd.DataFrame([(pt.linha, pt.uc, pt.lat, pt.lon, pt.equipamento_vital, pt.classe or "", pt.local,
                          pt.transformador, pt.circuito, pt.conjunto, pt.bairro, pt.situacao, pt.status)
                         for pt in m.pontos if pt.status != K.REJEITADA],
                        columns=["LINHA", "UC", "LAT", "LON", "VITAL", "CLASSE", "LOCAL", "TRANSFORMADOR", "CIRCUITO", "CONJUNTO",
                                 "BAIRRO", "SITUACAO", "STATUS"])


def modelo_csv() -> str:
    """O modelo para baixar: cabeçalho e duas linhas de exemplo (fictícias). local: o que o aviso de
    hoje cita para a UC (o imóvel no rural, a rua no urbano), opcional, só para o comparativo."""
    return ("uc;latitude;longitude;equipamento_vital;classe;local\n"
            "0000000001;-21,5321;-42,6412;não;residencial;Rua das Flores\n"
            "0000000002;-21,5410;-42,6503;sim;rural;Sítio Boa Vista\n")
