"""Localidades oficiais do IBGE (Censo 2022) dos municípios da concessão no banco.

Lê os arquivos que o projeto já usa (data/raw/localidades/<UF>/<UF>_localidades_2022.gpkg: MG e RJ) e grava, para cada
município que já está na base territorial (base_concessao.py), as localidades dele: código, nome, categoria e ponto.
O pessoal de negócio mandou os mesmos arquivos em shapefile (conferidos linha a linha: idênticos); por isso a fonte
é a do projeto, que o git ignora e o pipeline já baixa. Dado público; nenhum cliente. O IBGE lista cinco comunidades quilombolas duas vezes nesses municípios; ficam uma só.

Uso:
  uv run python -m comunidades.localidades_oficiais
"""

import sys

from . import config as C
from .banco import base_territorial as banco_base
from .banco import localidades as banco

UFS = ("MG", "RJ")


def executar() -> int:
    import geopandas as gpd

    banco.criar_esquema()
    ms = banco_base.municipios_gravados()
    linhas, faltam = [], []
    for uf in UFS:
        arq = C.RAW / "localidades" / uf / f"{uf}_localidades_2022.gpkg"
        if not arq.exists():
            faltam.append(str(arq))
            continue
        g = gpd.read_file(arq).to_crs(C.CRS_GEO)
        g = g[g["CD_MUN"].isin(ms)]
        linhas += [(r.CD_MUN, str(r.CD_LOCALIDADE), str(r.NM_LOCALIDADE).strip(), str(r.CT_LOCALIDADE), r.geometry) for r in g.itertuples()]
    # o IBGE lista algumas comunidades quilombolas duas vezes (mesmo código, nome e ponto; uma como "Localidade Quilombola" e
    # outra como povoado ou lugarejo): fica uma linha só, a quilombola, para não aparecer em dobro no mapa e no relatório
    unicas = {}
    for l in linhas:
        chave = (l[0], l[1], l[2], l[4].wkt)
        if chave not in unicas or ("Quilombola" in l[3] and "Quilombola" not in unicas[chave][3]):
            unicas[chave] = l
    repetidas = len(linhas) - len(unicas)
    linhas = list(unicas.values())
    if faltam:
        print("Arquivos do IBGE não encontrados (rode o pipeline para baixar):", *faltam, sep="\n  ")
    if not linhas:
        return 1
    n = banco.gravar(linhas)
    com = {l[0] for l in linhas}
    print(f"{n} localidades oficiais em {len(com)} dos {len(ms)} municípios da base territorial ({repetidas} listadas duas vezes pelo IBGE foram juntadas).")
    for cat, q in banco.totais(sorted(com))["categorias"].items():
        print(f"  {cat}: {q}")
    return 0


if __name__ == "__main__":
    sys.exit(executar())
