"""Medição (só leitura): quanto os polígonos nomeados do IBGE (setores do Censo 2022) servem de contorno
das comunidades da concessão, em comparação com as comunidades que o CNEFE montou.

Para cada camada nomeada dos setores (aglomerado rural, núcleo urbano, bairro, subdistrito, favela) mede:
quantos polígonos existem, que parte dos endereços cai dentro de algum, e, por comunidade, o polígono
dominante, a pureza (parte dos endereços da comunidade dentro dele) e se o nome é o mesmo.
Nada é gravado no banco; o resultado vai para saida/poligonos/ (csv com ";" e BOM, para o Excel).

Uso: uv run python -m comunidades.validacao.poligonos
"""

import re

import geopandas as gpd
import pandas as pd

from .. import config as C
from ..banco.conexao import conectar
from ..nucleo.localidades import normalizar

CAMADAS = {"aglomerado rural": "NM_AGLOM", "núcleo urbano": "NM_NU", "bairro": "NM_BAIRRO",
           "subdistrito": "NM_SUBDIST", "favela/comunidade urbana": "NM_FCU"}
SAIDA = C.RAIZ / "saida" / "poligonos"


def _sem_distrito(nome: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", nome)


def enderecos_do_banco() -> gpd.GeoDataFrame:
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT codigo_ibge, comunidade, ST_X(ponto), ST_Y(ponto) FROM endereco_referencia")
        r = cur.fetchall()
    return gpd.GeoDataFrame({"mun": [x[0] for x in r], "comunidade": [x[1] for x in r]},
                            geometry=gpd.points_from_xy([x[2] for x in r], [x[3] for x in r]), crs="EPSG:4674")


def setores(municipios: set[str]) -> gpd.GeoDataFrame:
    partes = []
    for uf in ("MG", "RJ"):
        arq = C.RAW / f"setores_{uf.lower()}" / f"{uf}_setores_CD2022.shp"
        s = gpd.read_file(arq, columns=["SITUACAO", "CD_MUN", *CAMADAS.values()], where="1=1")
        partes.append(s[s["CD_MUN"].isin(municipios)])
    return pd.concat(partes).to_crs("EPSG:4674")


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    e = enderecos_do_banco()
    muns = set(e["mun"].unique())
    print(f"{len(e)} endereços de referência, {len(muns)} municípios, "
          f"{e['comunidade'].nunique()} nomes de comunidade", flush=True)
    s = setores(muns)
    print(f"{len(s)} setores nos municípios da concessão "
          f"({(s['SITUACAO'].str.startswith('Rural')).sum()} rurais)", flush=True)
    comunidades = e.groupby(["mun", "comunidade"]).size().rename("enderecos").reset_index()
    resumo, linhas = [], []
    for camada, col in CAMADAS.items():
        t = s[s[col].notna()].dissolve(by=["CD_MUN", col], as_index=False)[["CD_MUN", col, "geometry"]]
        t = t.rename(columns={"CD_MUN": "mun_pol", col: "poligono"})
        if t.empty:
            resumo.append({"camada": camada, "poligonos": 0, "enderecos_dentro_%": 0, "comunidades_pureza>=80%": 0,
                           "comunidades_mesmo_nome": 0})
            continue
        j = gpd.sjoin(e, t, how="left", predicate="within")
        j = j[~j.index.duplicated()]
        j["poligono"] = j["poligono"].where(j["mun"] == j["mun_pol"])
        dentro = j["poligono"].notna()
        por = (j.assign(n=1).groupby(["mun", "comunidade", "poligono"], dropna=True)["n"].sum().reset_index())
        dom = por.sort_values("n", ascending=False).drop_duplicates(["mun", "comunidade"])
        dom = comunidades.merge(dom, on=["mun", "comunidade"], how="left")
        dom["pureza"] = (dom["n"] / dom["enderecos"]).fillna(0)
        dom["mesmo_nome"] = [bool(p) and normalizar(_sem_distrito(c)) == normalizar(p)
                             for c, p in zip(dom["comunidade"], dom["poligono"].fillna(""))]
        dom["camada"] = camada
        linhas.append(dom)
        resumo.append({"camada": camada, "poligonos": len(t), "enderecos_dentro_%": round(100 * dentro.mean(), 1),
                       "comunidades_pureza>=80%": int((dom["pureza"] >= 0.8).sum()),
                       "comunidades_mesmo_nome": int(dom["mesmo_nome"].sum())})
    r = pd.DataFrame(resumo)
    print(f"\nComunidades do CNEFE no banco: {len(comunidades)}")
    print(r.to_string(index=False))
    r.to_csv(SAIDA / "resumo_camadas.csv", sep=";", index=False, encoding="utf-8-sig")
    if linhas:
        pd.concat(linhas).to_csv(SAIDA / "comunidade_x_poligono.csv", sep=";", index=False, encoding="utf-8-sig")
    print(f"\nArquivos em {SAIDA}")


if __name__ == "__main__":
    main()
