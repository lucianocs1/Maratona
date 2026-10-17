"""Área de atuação das empresas: os municípios (códigos do IBGE) onde cada empresa pode criar avisos.

Puro: não lê banco nem arquivo do disco. Recebe os códigos e, na importação, os bytes do KML/GeoJSON que a pessoa
enviou; quem grava é banco/empresas_area.py e quem confere a permissão é a API. O arquivo importado nunca é guardado:
dele saem só os polígonos, e do banco, os códigos dos municípios que eles cobrem.
"""

import json
import re

import shapely
from defusedxml import ElementTree as ET
from shapely.geometry import MultiPolygon, Polygon, shape

MAX_ARQUIVO = 5 * 1024 * 1024        # 5 MB: o KML da EMG tem ~0,3 MB
MAX_VERTICES = 500_000
MAX_POLIGONOS = 5_000
# Brasil com folga (ilhas oceânicas incluídas): longitude e latitude em graus, SIRGAS 2000
BRASIL = (-75.0, -35.0, -28.0, 6.0)
CODIGO = re.compile(r"^[0-9]{7}$")
MAX_MUNICIPIOS = 6_000
PERIGOSOS = re.compile(rb"<\s*script|javascript:|<!ENTITY|<!DOCTYPE|<\?xml-stylesheet", re.I)


class AreaInvalida(ValueError):
    """Arquivo ou lista de municípios recusados; a mensagem é para a pessoa ler (sem nada do conteúdo)."""


def normalizar_codigos(codigos) -> list[str]:
    """Códigos do IBGE (7 dígitos), sem repetidos, em ordem."""
    if not isinstance(codigos, (list, tuple, set)):
        raise AreaInvalida("Envie a lista de municípios.")
    lista = sorted({str(c).strip() for c in codigos})
    if len(lista) > MAX_MUNICIPIOS:
        raise AreaInvalida(f"No máximo {MAX_MUNICIPIOS} municípios.")
    ruins = [c for c in lista if not CODIGO.match(c)]
    if ruins:
        raise AreaInvalida("Código de município inválido (use os 7 dígitos do IBGE).")
    return lista


def resumo(antes, depois, outras: dict[str, set] | None = None) -> dict:
    """O que muda ao salvar: X municípios, Y novos, Z removidos e W em sobreposição com outra empresa.
    outras: sigla -> municípios de cada outra empresa."""
    antes, depois = set(antes), set(depois)
    sobre = {}
    for sigla, ms in (outras or {}).items():
        for c in depois & set(ms):
            sobre.setdefault(c, []).append(sigla)
    return {"municipios": len(depois), "novos": sorted(depois - antes), "removidos": sorted(antes - depois),
            "sobreposicao": [{"codigo_ibge": c, "empresas": sorted(e)} for c, e in sorted(sobre.items())],
            "mudou": antes != depois}


def sobreposicoes(areas: dict[str, set]) -> dict[str, list[str]]:
    """Município -> siglas, só dos que estão na área de mais de uma empresa."""
    por = {}
    for sigla, ms in areas.items():
        for c in ms:
            por.setdefault(c, []).append(sigla)
    return {c: sorted(s) for c, s in sorted(por.items()) if len(s) > 1}


def _anel(texto: str) -> list[tuple[float, float]]:
    pts = []
    for p in (texto or "").split():
        partes = p.split(",")
        if len(partes) < 2:
            raise AreaInvalida("Coordenadas do KML ilegíveis.")
        pts.append((float(partes[0]), float(partes[1])))
    return pts


def _do_kml(dados: bytes) -> list:
    try:
        raiz = ET.fromstring(dados, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception:
        raise AreaInvalida("O arquivo não é um KML válido.") from None
    if not raiz.tag.endswith("kml"):
        raise AreaInvalida("O arquivo não é um KML válido.")
    ns = raiz.tag[:-3]   # "{http://www.opengis.net/kml/2.2}" ou ""
    tipos = {el.tag.replace(ns, "") for el in raiz.iter()}
    if tipos & {"Point", "LineString"} and "Polygon" not in tipos:
        raise AreaInvalida("O arquivo tem só pontos ou linhas: a área precisa de polígonos.")
    partes = []
    for pol in raiz.iter(f"{ns}Polygon"):
        ext = pol.find(f"{ns}outerBoundaryIs/{ns}LinearRing/{ns}coordinates")
        if ext is None:
            continue
        buracos = [_anel(b.text) for b in pol.findall(f"{ns}innerBoundaryIs/{ns}LinearRing/{ns}coordinates")]
        partes.append(Polygon(_anel(ext.text), buracos))
    return partes


def _do_geojson(dados: bytes) -> list:
    try:
        g = json.loads(dados.decode("utf-8-sig"))
    except Exception:
        raise AreaInvalida("O arquivo não é um GeoJSON válido.") from None
    if not isinstance(g, dict):
        raise AreaInvalida("O arquivo não é um GeoJSON válido.")
    geoms = []
    if g.get("type") == "FeatureCollection":
        geoms = [f.get("geometry") for f in g.get("features") or [] if isinstance(f, dict)]
    elif g.get("type") == "Feature":
        geoms = [g.get("geometry")]
    else:
        geoms = [g]
    partes = []
    for x in geoms:
        if not isinstance(x, dict):
            continue
        if x.get("type") not in ("Polygon", "MultiPolygon"):
            raise AreaInvalida("Só polígonos: o arquivo tem pontos, linhas ou outro tipo de geometria.")
        try:
            s = shape(x)
        except Exception:
            raise AreaInvalida("Geometria ilegível no GeoJSON.") from None
        partes.extend(s.geoms if isinstance(s, MultiPolygon) else [s])
    return partes


def geometria_do_arquivo(nome: str, dados: bytes):
    """Valida o KML/GeoJSON da concessão e devolve um MultiPolygon (EPSG:4674): tamanho máximo, sem scripts nem
    DTD/entidades, só polígonos, todos dentro do Brasil. O arquivo não é guardado."""
    nome = (nome or "").lower()
    if len(dados) > MAX_ARQUIVO:
        raise AreaInvalida(f"Arquivo grande demais (máximo {MAX_ARQUIVO // (1024 * 1024)} MB).")
    if not dados.strip():
        raise AreaInvalida("Arquivo vazio.")
    if PERIGOSOS.search(dados[:MAX_ARQUIVO]):
        raise AreaInvalida("O arquivo tem script, DTD ou entidade: recusado por segurança.")
    if nome.endswith(".kml"):
        partes = _do_kml(dados)
    elif nome.endswith((".geojson", ".json")):
        partes = _do_geojson(dados)
    else:
        raise AreaInvalida("Envie um arquivo .kml ou .geojson.")
    if not partes:
        raise AreaInvalida("Nenhum polígono no arquivo.")
    if len(partes) > MAX_POLIGONOS or sum(len(p.exterior.coords) + sum(len(i.coords) for i in p.interiors) for p in partes) > MAX_VERTICES:
        raise AreaInvalida("Polígonos demais no arquivo.")
    x0, y0, x1, y1 = BRASIL
    for p in partes:
        a, b, c, d = p.bounds
        if a < x0 or b < y0 or c > x1 or d > y1:
            raise AreaInvalida("Há polígono fora do Brasil (confira se as coordenadas estão em longitude, latitude).")
    g = shapely.make_valid(shapely.union_all(partes))
    polis = [g] if g.geom_type == "Polygon" else [q for q in getattr(g, "geoms", []) if q.geom_type == "Polygon"] \
        + [r for q in getattr(g, "geoms", []) if q.geom_type == "MultiPolygon" for r in q.geoms]
    if g.geom_type == "MultiPolygon":
        polis = list(g.geoms)
    if not polis or sum(p.area for p in polis) <= 0:
        raise AreaInvalida("Os polígonos do arquivo não têm área.")
    return MultiPolygon(polis)
