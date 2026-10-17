"""Coordenada de uma linha da planilha: lê, confere e, só quando dá para ter certeza, corrige.

Puro: recebe os valores das células (como o leitor os entregou) e uma função dentro(lat, lon) que
diz se um ponto está na área da concessão (Area, com a margem). Não lê arquivo nem banco.

Formatos aceitos, nesta ordem de preferência (o primeiro que a linha trouxer):
- latitude e longitude em colunas separadas: número decimal com ponto ou vírgula, ou graus,
  minutos e segundos (21°31'49.6"S, com N/S/L/E/O/W ou sinal);
- latitude e longitude na mesma célula ("-21.53, -42.64", "-21,53; -42,64", "21°31'S 42°38'W");
- colunas só em graus, minutos e segundos (LAT_GMS e LONG_GMS);
- UTM (SIRGAS 2000; o fuso vem da configuração da empresa, padrão 23S, EPSG:31983).

Correção (nunca adivinhar): latitude e longitude trocadas, ou o sinal negativo faltando (valor
positivo que deveria ser negativo), só quando exatamente uma das alternativas cai dentro da área.
Duas ou mais alternativas dentro = rejeitada (correcao_ambigua); nenhuma = fora_da_concessao.
O resultado tem status ok, corrigida ou rejeitada, com motivo, correção e avisos das listas
fechadas de nucleo/motivos.py.
"""

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Callable

import shapely
from pyproj import Transformer
from shapely.ops import transform

from .motivos import Aviso, Correcao, FormulaSemValor, Motivo

EPSG_GEO = 4674              # SIRGAS 2000, graus
EPSG_UTM_PADRAO = 31983      # SIRGAS 2000 / UTM 23S (Zona da Mata mineira)
EPSG_METRICO = 5880          # SIRGAS 2000 / Brazil Polyconic: metros no Brasil inteiro (margem da área)
MARGEM_M = 50.0              # um ponto até 50 m fora do contorno ainda conta como dentro
CASAS_MINIMAS = 4            # menos que isso: aviso (4 casas ~ 11 m)
UTM_X, UTM_Y = (100_000.0, 900_000.0), (0.0, 10_000_000.0)   # faixas válidas de um fuso UTM

OK, CORRIGIDA, REJEITADA = "ok", "corrigida", "rejeitada"


@dataclass(frozen=True)
class Coordenada:
    status: str                                  # ok | corrigida | rejeitada
    lat: float | None = None
    lon: float | None = None
    motivo: Motivo | None = None                 # só na rejeitada
    correcao: Correcao | None = None             # só na corrigida
    original: tuple[float, float] | None = None  # (lat, lon) como veio, na corrigida
    origem: str | None = None                    # decimal | celula | gms | utm
    avisos: tuple[Aviso, ...] = ()
    lido: tuple[float, float] | None = None      # (lat, lon) lido, na rejeitada fora_da_concessao (para o mapa)


class _Recusa(Exception):
    def __init__(self, motivo: Motivo):
        self.motivo = motivo


# ---------- valores de uma célula ----------
def vazio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _conferir_tipo(v) -> None:
    """Tipos de célula que nunca são coordenada."""
    if isinstance(v, FormulaSemValor):
        raise _Recusa(Motivo.COORD_FORMULA)
    if isinstance(v, (datetime, date, time, timedelta)):
        raise _Recusa(Motivo.COORD_DATA)
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise _Recusa(Motivo.COORD_FORMATO)


_MENOS = str.maketrans({"−": "-", "–": "-", " ": " ", " ": " "})
_DECIMAL = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
_NAO_FINITOS = {"nan", "inf", "infinity"}


def decimal(v) -> tuple[float, int]:
    """Número decimal e quantas casas decimais ele trouxe. '-21,53' -> (-21.53, 2)."""
    _conferir_tipo(v)
    if isinstance(v, (int, float)):
        x = float(v)
        if not math.isfinite(x):
            raise _Recusa(Motivo.COORD_NAO_FINITA)
        return x, max(0, -Decimal(repr(x)).normalize().as_tuple().exponent)
    s = re.sub(r"^([+-])\s+", r"\1", v.translate(_MENOS).strip())   # "- 42.63" ok; "21 31 49" não é número
    if s.lstrip("+-").lower() in _NAO_FINITOS:
        raise _Recusa(Motivo.COORD_NAO_FINITA)
    if not any(c.isdigit() for c in s):
        raise _Recusa(Motivo.COORD_SEM_NUMERO)
    if not _DECIMAL.fullmatch(s):
        raise _Recusa(Motivo.COORD_FORMATO)
    s = s.replace(",", ".")
    return float(s), len(s.partition(".")[2])


_GMS = re.compile(r"""^\s*(?P<h1>[NSLEOW])?\s*(?P<sinal>[-+])?\s*
    (?P<g>\d{1,3}(?:[.,]\d+)?)\s*(?P<mg>[°º˚]|\s)\s*
    (?:(?P<m>\d{1,2}(?:[.,]\d+)?)\s*(?P<mm>['′’]|\s)\s*
       (?:(?P<s>\d{1,2}(?:[.,]\d+)?)\s*(?:"|″|''|’’|”)?\s*)?)?
    (?P<h2>[NSLEOW])?\s*$""", re.X | re.I)


def gms(v) -> float:
    """Graus, minutos e segundos -> graus decimais. "21°31'49.595"S" -> -21.530443..."""
    _conferir_tipo(v)
    if not isinstance(v, str):
        raise _Recusa(Motivo.COORD_FORMATO)
    m = _GMS.match(v.translate(_MENOS))
    if not m:
        raise _Recusa(Motivo.COORD_FORMATO if any(c.isdigit() for c in v) else Motivo.COORD_SEM_NUMERO)
    h1, h2 = m.group("h1"), m.group("h2")
    tem_marca = m.group("mg") in "°º˚" or (m.group("mm") or " ") in "'′’" or h1 or h2
    if not tem_marca or (h1 and h2):
        raise _Recusa(Motivo.COORD_FORMATO)
    num = lambda g: float(g.replace(",", ".")) if g else 0.0
    graus, minutos, segundos = num(m.group("g")), num(m.group("m")), num(m.group("s"))
    if minutos >= 60 or segundos >= 60 or (m.group("m") and not graus.is_integer()) \
            or (m.group("s") and not minutos.is_integer()):
        raise _Recusa(Motivo.COORD_FORMATO)
    hemisferio = (h1 or h2 or "").upper()
    negativo = hemisferio in ("S", "O", "W")
    if m.group("sinal") == "-":
        if hemisferio:          # "-21°S": sinal e hemisfério juntos é ambíguo
            raise _Recusa(Motivo.COORD_FORMATO)
        negativo = True
    valor = graus + minutos / 60 + segundos / 3600
    return -valor if negativo else valor


def _um_valor(v) -> tuple[float, int | None]:
    """Uma célula de latitude ou longitude: decimal (com as casas) ou graus, minutos e segundos."""
    try:
        return decimal(v)
    except _Recusa as e:
        if e.motivo not in (Motivo.COORD_FORMATO, Motivo.COORD_SEM_NUMERO) or not isinstance(v, str):
            raise
        try:
            return gms(v), None
        except _Recusa:
            raise e from None


_PAR_DECIMAL = re.compile(r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*[,;\s|]\s*([+-]?\d+(?:[.,]\d+)?)\s*$")
_PAR_GMS = re.compile(r"^\s*(.+?[NSLEOW])\s*[,;/|]?\s*(.+?[NSLEOW])\s*$", re.I)


def par(v) -> tuple[tuple[float, int | None], tuple[float, int | None]]:
    """Latitude e longitude na mesma célula (a primeira é a latitude)."""
    _conferir_tipo(v)
    if not isinstance(v, str):
        raise _Recusa(Motivo.COORD_FORMATO)
    s = v.translate(_MENOS)
    m = _PAR_DECIMAL.match(s)
    if m:
        return decimal(m.group(1)), decimal(m.group(2))
    m = _PAR_GMS.match(s)
    if m:
        return (gms(m.group(1)), None), (gms(m.group(2)), None)
    if not any(c.isdigit() for c in s):
        raise _Recusa(Motivo.COORD_SEM_NUMERO)
    raise _Recusa(Motivo.COORD_FORMATO)


@lru_cache(maxsize=8)
def _utm_para_geo(epsg: int) -> Transformer:
    return Transformer.from_crs(epsg, EPSG_GEO, always_xy=True)


def utm(x: float, y: float, epsg: int = EPSG_UTM_PADRAO) -> tuple[float, float]:
    """UTM (metros) -> (lat, lon) em SIRGAS 2000."""
    lon, lat = _utm_para_geo(epsg).transform(x, y)
    return lat, lon


# ---------- área da concessão ----------
class Area:
    """O contorno da concessão (shapely, em graus SIRGAS 2000) com a margem: dentro(lat, lon) -> bool."""

    def __init__(self, contorno_geo, margem_m: float = MARGEM_M):
        self._para_m = Transformer.from_crs(EPSG_GEO, EPSG_METRICO, always_xy=True)
        self._g = transform(self._para_m.transform, contorno_geo).buffer(margem_m)
        shapely.prepare(self._g)

    def __call__(self, lat: float, lon: float) -> bool:
        x, y = self._para_m.transform(lon, lat)
        return math.isfinite(x) and math.isfinite(y) and bool(shapely.contains_xy(self._g, x, y))


# ---------- a coordenada da linha ----------
def _nos_limites(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def _alternativas(lat: float, lon: float) -> dict[tuple[float, float], Correcao]:
    """Pontos corrigidos possíveis: trocados e/ou com o sinal negativo que faltava (só positivo -> negativo)."""
    neg = lambda v: -v if v > 0 else None
    alt = {}
    for correcao, p in [
        (Correcao.TROCA, (lon, lat)),
        (Correcao.SINAL_LAT, (neg(lat), lon)), (Correcao.SINAL_LON, (lat, neg(lon))),
        (Correcao.SINAL_AMBOS, (neg(lat), neg(lon))),
        (Correcao.TROCA_E_SINAL, (neg(lon), lat)), (Correcao.TROCA_E_SINAL, (lon, neg(lat))),
        (Correcao.TROCA_E_SINAL, (neg(lon), neg(lat))),
    ]:
        if None not in p and p != (lat, lon):
            alt.setdefault(p, correcao)
    return alt


def _decidir(lat: float, lon: float, origem: str, avisos: tuple, dentro, alternativas) -> Coordenada:
    if _nos_limites(lat, lon) and (dentro is None or dentro(lat, lon)):
        return Coordenada(OK, lat, lon, origem=origem, avisos=avisos)
    if dentro is None:   # sem a área não há como saber se uma correção está certa: nada é corrigido
        return Coordenada(REJEITADA, motivo=Motivo.COORD_LIMITES)
    achadas = [(p, c) for p, c in alternativas.items() if _nos_limites(*p) and dentro(*p)]
    if len(achadas) == 1:
        (nlat, nlon), correcao = achadas[0]
        return Coordenada(CORRIGIDA, nlat, nlon, correcao=correcao, original=(lat, lon), origem=origem, avisos=avisos)
    if achadas:
        return Coordenada(REJEITADA, motivo=Motivo.CORRECAO_AMBIGUA)
    if _nos_limites(lat, lon):
        return Coordenada(REJEITADA, motivo=Motivo.FORA_DA_CONCESSAO, lido=(lat, lon))
    return Coordenada(REJEITADA, motivo=Motivo.COORD_LIMITES)


def _dois(a, b) -> None:
    """Uma das duas células vazia: confere o tipo da outra (fórmula e data têm motivo próprio) e recusa."""
    for v in (a, b):
        if not vazio(v):
            _conferir_tipo(v)
    raise _Recusa(Motivo.COORD_INCOMPLETA)


def interpretar(lat=None, lon=None, *, celula=None, lat_gms=None, lon_gms=None, x=None, y=None,
                epsg_utm: int = EPSG_UTM_PADRAO, dentro: Callable[[float, float], bool] | None = None) -> Coordenada:
    """A coordenada de uma linha a partir das células que a planilha trouxe (as ausentes ficam None)."""
    try:
        if not (vazio(lat) and vazio(lon)):
            if vazio(lat) or vazio(lon):
                _dois(lat, lon)
            (a, ca), (b, cb) = _um_valor(lat), _um_valor(lon)
            origem = "decimal" if ca is not None and cb is not None else "gms"
        elif not vazio(celula):
            (a, ca), (b, cb) = par(celula)
            origem = "celula"
        elif not (vazio(lat_gms) and vazio(lon_gms)):
            if vazio(lat_gms) or vazio(lon_gms):
                _dois(lat_gms, lon_gms)
            (a, ca), (b, cb) = (gms(lat_gms), None), (gms(lon_gms), None)
            origem = "gms"
        elif not (vazio(x) and vazio(y)):
            if vazio(x) or vazio(y):
                _dois(x, y)
            return _de_utm(decimal(x)[0], decimal(y)[0], epsg_utm, dentro)
        else:
            raise _Recusa(Motivo.COORD_VAZIA)
    except _Recusa as e:
        return Coordenada(REJEITADA, motivo=e.motivo)
    casas = [c for c in (ca, cb) if c is not None]
    avisos = (Aviso.POUCAS_CASAS,) if casas and min(casas) < CASAS_MINIMAS else ()
    return _decidir(a, b, origem, avisos, dentro, _alternativas(a, b))


def _de_utm(x: float, y: float, epsg: int, dentro) -> Coordenada:
    no_fuso = lambda e, n: UTM_X[0] <= e <= UTM_X[1] and UTM_Y[0] <= n <= UTM_Y[1]
    if no_fuso(x, y):
        lat, lon = utm(x, y, epsg)
        trocado = utm(y, x, epsg) if no_fuso(y, x) else None
        alternativas = {trocado: Correcao.UTM_TROCADO} if trocado else {}
        return _decidir(lat, lon, "utm", (), dentro, alternativas)
    if no_fuso(y, x) and dentro is not None:
        lat, lon = utm(y, x, epsg)
        if dentro(lat, lon):
            return Coordenada(CORRIGIDA, lat, lon, correcao=Correcao.UTM_TROCADO, original=None, origem="utm")
        return Coordenada(REJEITADA, motivo=Motivo.FORA_DA_CONCESSAO, lido=(lat, lon))
    return Coordenada(REJEITADA, motivo=Motivo.COORD_LIMITES)
