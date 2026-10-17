"""Área de concessão da distribuidora (contorno real, em KML) e os municípios do IBGE dentro dela.

Do KML só sai a geometria: nomes, descrições e propriedades são descartados (um KML pode trazer
HTML e scripts nas descrições). A malha das UFs e dos municípios vem da API de malhas do IBGE e
fica em data/raw/malhas, baixada uma vez.

Uso: py -m uv run python -m comunidades.fontes.concessao (lista os municípios da concessão)
"""

import gzip
import json
import shutil
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import Polygon

from .. import config as C

ARQ_KML = C.DISTRIBUIDORAS / "concessao" / "EMG.kml"
SIGLA = "EMG"                      # sigla da concessão no KML (Energisa, Zona da Mata mineira e divisa com o RJ)
PASTA = C.RAW / "malhas"
API = "https://servicodados.ibge.gov.br/api"
MALHA = API + "/v3/malhas/{local}?intrarregiao={nivel}&formato=application/vnd.geo%2Bjson&qualidade={qualidade}"
CRS_AREA = "EPSG:5880"             # Brasil Policônico (SIRGAS 2000): áreas comparáveis no país inteiro
MIN_DENTRO = 0.5                   # município da concessão: pelo menos metade da área dentro do contorno
# (o traçado do KML e o da malha do IBGE não coincidem na divisa: vizinhos aparecem com 1% a 24% dentro)


def _baixar(url: str, destino: Path) -> Path:
    """Baixa uma vez para data/raw/malhas. A API do IBGE responde em gzip mesmo sem pedir."""
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"  baixando {destino.name}...", flush=True)
    tmp = destino.with_suffix(".parcial")
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, length=1 << 20)
    except urllib.error.URLError as e:
        # o Python não reconhece a cadeia de certificados do IBGE em algumas máquinas: o curl do sistema (que usa os
        # certificados do Windows) baixa com a verificação ligada; nunca se desliga a verificação
        curl = shutil.which("curl")
        if not curl or "CERTIFICATE" not in str(e).upper():
            raise
        subprocess.run([curl, "-sS", "--fail", "--compressed", "--max-time", "300", "-o", str(tmp), url], check=True)
    bruto = tmp.read_bytes()
    if bruto[:2] == b"\x1f\x8b":
        tmp.write_bytes(gzip.decompress(bruto))
    json.loads(tmp.read_text(encoding="utf-8"))  # resposta que não é JSON não fica no cache
    tmp.replace(destino)
    return destino


def contorno(arq: Path = ARQ_KML):
    """Polígonos do KML (EPSG:4674), só as coordenadas: anel externo e buracos de cada Polygon."""
    ns = "{http://www.opengis.net/kml/2.2}"
    anel = lambda el: [tuple(map(float, p.split(",")[:2])) for p in el.text.split()]
    partes = []
    for pol in ET.parse(arq).getroot().iter(f"{ns}Polygon"):
        externo = pol.find(f"{ns}outerBoundaryIs/{ns}LinearRing/{ns}coordinates")
        buracos = pol.findall(f"{ns}innerBoundaryIs/{ns}LinearRing/{ns}coordinates")
        partes.append(Polygon(anel(externo), [anel(b) for b in buracos]))
    if not partes:
        raise ValueError(f"{arq.name}: nenhum polígono no KML")
    return shapely.make_valid(shapely.union_all(partes))


def ufs() -> gpd.GeoDataFrame:
    """As 27 UFs (malha simplificada do IBGE): CD_UF, SIGLA_UF, NM_UF."""
    malha = _baixar(MALHA.format(local="paises/BR", nivel="UF", qualidade="minima"), PASTA / "ufs_BR.json")
    nomes = _baixar(f"{API}/v1/localidades/estados", PASTA / "nomes_ufs.json")
    info = {str(u["id"]): u for u in json.loads(nomes.read_text(encoding="utf-8"))}
    g = gpd.read_file(malha).rename(columns={"codarea": "CD_UF"})
    g["SIGLA_UF"] = g["CD_UF"].map(lambda c: info[c]["sigla"])
    g["NM_UF"] = g["CD_UF"].map(lambda c: info[c]["nome"])
    return g.set_crs(C.CRS_GEO, allow_override=True)[["CD_UF", "SIGLA_UF", "NM_UF", "geometry"]]


def _municipios_uf(sigla: str) -> gpd.GeoDataFrame:
    malha = _baixar(MALHA.format(local=f"estados/{sigla}", nivel="municipio", qualidade="intermediaria"),
                    PASTA / f"municipios_{sigla}.json")
    nomes = _baixar(f"{API}/v1/localidades/estados/{sigla}/municipios", PASTA / f"nomes_{sigla}.json")
    nome = {str(m["id"]): m["nome"] for m in json.loads(nomes.read_text(encoding="utf-8"))}
    g = gpd.read_file(malha).rename(columns={"codarea": "CD_MUN"})
    g["NM_MUN"], g["SIGLA_UF"] = g["CD_MUN"].map(nome), sigla
    return g.set_crs(C.CRS_GEO, allow_override=True)[["CD_MUN", "NM_MUN", "SIGLA_UF", "geometry"]]


def municipios(area=None, u: gpd.GeoDataFrame | None = None) -> gpd.GeoDataFrame:
    """Municípios com pelo menos MIN_DENTRO da área dentro da concessão (DENTRO = fração dentro),
    em ordem alfabética."""
    area = contorno() if area is None else area
    u = ufs() if u is None else u
    siglas = u[u.intersects(area)]["SIGLA_UF"].tolist()
    g = pd.concat([_municipios_uf(s) for s in siglas], ignore_index=True)
    m = g.to_crs(CRS_AREA).geometry
    g["DENTRO"] = m.intersection(gpd.GeoSeries([area], crs=C.CRS_GEO).to_crs(CRS_AREA).iloc[0]).area / m.area
    g = g[g["DENTRO"] >= MIN_DENTRO]
    return g.sort_values(["NM_MUN", "SIGLA_UF"], key=lambda s: s.map(C.sem_acento)).reset_index(drop=True)


if __name__ == "__main__":
    ms = municipios()
    print(f"Concessão {SIGLA}: {len(ms)} municípios com pelo menos {MIN_DENTRO:.0%} da área dentro")
    for r in ms.itertuples():
        print(f"  {r.CD_MUN}  {r.NM_MUN}/{r.SIGLA_UF}  {r.DENTRO:.0%}")
