"""Microrregiões do IBGE (MG e RJ) no banco: o mapa de "regiões" que a área de negócio pediu.

Baixa da API pública do IBGE (servicodados.ibge.gov.br, sem chave) a malha e os nomes das microrregiões de cada UF da
concessão, guarda os arquivos em data/raw/microrregioes/ e grava no banco as que tocam algum município da base territorial
(base_concessao.py). Dado público; nenhum cliente. Rode de novo para atualizar (a malha é refeita pelo IBGE só a cada
revisão da divisão territorial).

Uso:
  uv run python -m comunidades.microrregioes
"""

import gzip
import json
import sys
import urllib.request

import shapely

from . import config as C
from .banco import base_territorial as banco_base
from .banco import microrregioes as banco

UFS = {"MG": 31, "RJ": 33}
API = "https://servicodados.ibge.gov.br/api"
PASTA = C.RAW / "microrregioes"


def _baixar(url: str, destino) -> dict | list:
    if not destino.exists():
        PASTA.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as r:
            dados = r.read()
        destino.write_bytes(gzip.decompress(dados) if dados[:2] == bytes([0x1F, 0x8B]) else dados)   # o IBGE responde comprimido
    return json.loads(destino.read_text(encoding="utf-8"))


def executar() -> int:
    banco.criar_esquema()
    ms = banco_base.municipios_gravados()
    if not ms:
        print("Base territorial vazia: rode base_concessao antes.")
        return 1
    contornos = {c[0]: c[3] for c in banco_base.contornos(C.CRS_GEO)}
    pontos = [g.representative_point() for g in contornos.values()]
    linhas = []
    for uf, cod in UFS.items():
        malha = _baixar(f"{API}/v3/malhas/estados/{cod}?intrarregiao=microrregiao&formato=application/vnd.geo+json"
                        "&qualidade=intermediaria", PASTA / f"malha_{uf}.json")
        nomes = {str(x["id"]): x for x in _baixar(f"{API}/v1/localidades/estados/{cod}/microrregioes",
                                                  PASTA / f"nomes_{uf}.json")}
        for f in malha["features"]:
            g = shapely.from_geojson(json.dumps(f["geometry"]))
            c = f["properties"]["codarea"]
            if c in nomes and any(g.contains(p) for p in pontos):
                n = nomes[c]
                linhas.append((c, n["nome"], n["mesorregiao"]["nome"], uf, g))
    if not linhas:
        return 1
    print(f"{banco.gravar(linhas)} microrregiões do IBGE tocam os {len(ms)} municípios da base territorial:")
    for l in sorted(linhas, key=lambda x: x[1]):
        print(f"  {l[1]} ({l[3]}, {l[2]})")
    return 0


if __name__ == "__main__":
    sys.exit(executar())
