"""Identificação automática de comunidades a partir do cadastro da distribuidora.

Usa SOMENTE o que a distribuidora tem: cadastro de UCs (coordenada, texto de
localidade) e posição dos transformadores. O gabarito do IBGE não é lido aqui.

Etapas:
1. Coordenadas: ausentes ou incoerentes com o transformador -> posição do trafo.
2. Texto: normaliza o campo de localidade e descarta vazios e nomes de sítio/fazenda.
3. Vocabulário: agrupa variantes e erros de digitação (fuzzy) num nome canônico.
4. Votação espacial: cada UC recebe o nome predominante entre os vizinhos.
5. Homônimos: o mesmo nome em lugares distantes vira comunidades distintas.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from rapidfuzz import fuzz, process
from sklearn.cluster import DBSCAN
from shapely.strtree import STRtree
from sklearn.neighbors import KDTree

from .. import config as C
from .nomes import classificar, exibir, normalizar

DIST_MAX_TRAFO_M = 600   # UC mais longe que isso do próprio trafo -> coordenada suspeita
MIN_OCORRENCIAS = 3      # variante com menos ocorrências não vira nome canônico sozinha
SIMILARIDADE_TYPO = 88
K_VIZINHOS = 15
RAIO_VOTO_M = 1500
PESO_MESMO_TRAFO = 4.0
EPS_HOMONIMO_M = 2000
MIN_UC_INSTANCIA = 8
MIN_UC_COMUNIDADE = 3  # abaixo disso é fragmento de voto, não comunidade


def corrigir_coordenadas(ucs: gpd.GeoDataFrame, trafos: gpd.GeoDataFrame) -> pd.DataFrame:
    tr = trafos.to_crs(C.CRS_METRICO).set_index("COD_TRAFO").geometry
    txy = np.c_[tr.x, tr.y]
    pos = pd.Series(range(len(tr)), index=tr.index)
    t = txy[pos[ucs["COD_TRAFO"]].to_numpy()]

    m = ucs.to_crs(C.CRS_METRICO)
    x, y = m.geometry.x.to_numpy(), m.geometry.y.to_numpy()
    sem = np.isnan(x)
    dist = np.hypot(x - t[:, 0], y - t[:, 1])
    longe = ~sem & (dist > DIST_MAX_TRAFO_M)
    usar_trafo = sem | longe
    # pequeno espalhamento determinístico para não empilhar UCs no mesmo ponto
    rng = np.random.default_rng(C.SEMENTE)
    x = np.where(usar_trafo, t[:, 0] + rng.normal(0, 15, len(x)), x)
    y = np.where(usar_trafo, t[:, 1] + rng.normal(0, 15, len(y)), y)
    origem = np.select([sem, longe], ["trafo (sem coordenada)", "trafo (coordenada incoerente)"], "cadastro")
    return pd.DataFrame({"X": x, "Y": y, "ORIGEM_COORD": origem}, index=ucs.index)


def vocabulario(nomes: pd.Series) -> dict:
    """Mapeia cada variante normalizada para um nome canônico."""
    cont = nomes.value_counts()
    canonicos, mapa = [], {}
    for nome, n in cont.items():
        alvo = process.extractOne(nome, canonicos, scorer=fuzz.ratio) if canonicos else None
        if alvo and alvo[1] >= SIMILARIDADE_TYPO:
            mapa[nome] = alvo[0]
        elif n >= MIN_OCORRENCIAS:
            canonicos.append(nome)
            mapa[nome] = nome
        else:
            mapa[nome] = None  # variante rara e sem par: não vota
    return mapa


def votar(xy: np.ndarray, votos: np.ndarray, trafo: np.ndarray):
    """Nome predominante entre os vizinhos (peso pela distância) e a confiança do voto.

    Vizinhos no mesmo transformador pesam mais: estão no mesmo lugar físico, e isso
    evita que bairros urbanos densos "engulam" as UCs rurais da borda da cidade.
    """
    validos = np.where(pd.notna(votos))[0]
    arvore = KDTree(xy[validos])
    dist, idx = arvore.query(xy, k=min(K_VIZINHOS, len(validos)))
    nome_final = np.empty(len(xy), dtype=object)
    confianca = np.zeros(len(xy))
    for i in range(len(xy)):
        ok = dist[i] <= RAIO_VOTO_M
        if not ok.any():
            nome_final[i] = None
            continue
        viz = validos[idx[i][ok]]
        rotulos = votos[viz]
        pesos = 1.0 / (dist[i][ok] + 30.0) * np.where(trafo[viz] == trafo[i], PESO_MESMO_TRAFO, 1.0)
        placar = pd.Series(pesos).groupby(rotulos).sum()
        nome_final[i] = placar.idxmax()
        confianca[i] = placar.max() / placar.sum()
    return nome_final, confianca


def separar_homonimos(df: pd.DataFrame) -> pd.Series:
    """Mesmo nome em áreas distantes -> instâncias distintas ('Vista Alegre (Piacatuba)')."""
    inst = pd.Series(index=df.index, dtype=object)
    for nome, d in df.groupby("NOME"):
        lab = DBSCAN(eps=EPS_HOMONIMO_M, min_samples=1).fit_predict(d[["X", "Y"]].to_numpy())
        tamanhos = pd.Series(lab).value_counts()
        grandes = tamanhos[tamanhos >= MIN_UC_INSTANCIA].index
        if len(grandes) <= 1:
            inst[d.index] = nome
            continue
        # componentes pequenos vão para o componente grande mais próximo
        cent = {g: d[lab == g][["X", "Y"]].mean().to_numpy() for g in grandes}
        for g in np.unique(lab):
            membros = d.index[lab == g]
            if g not in grandes:
                c = d.loc[membros, ["X", "Y"]].mean().to_numpy()
                g2 = min(grandes, key=lambda k: np.hypot(*(cent[k] - c)))
            else:
                g2 = g
            inst[membros] = g2
        # Blocos no mesmo distrito são a mesma comunidade; só distritos diferentes viram homônimos
        distrito = {g: d.loc[inst[d.index] == g, "DISTRITO"].mode().iat[0] for g in grandes}
        if len(set(distrito.values())) == 1:
            inst[d.index] = nome
        else:
            inst[d.index] = inst[d.index].map(lambda g: f"{nome} ({distrito[g]})")
    return inst


def absorver_fragmentos(df: pd.DataFrame) -> pd.Series:
    """Comunidades com pouquíssimas UCs (ruído do voto) passam para a vizinha mais próxima."""
    rot = df["COMUNIDADE_PREVISTA"].copy()
    tam = rot.value_counts()
    pequenas = rot.isin(tam[tam < MIN_UC_COMUNIDADE].index).to_numpy()
    if pequenas.any() and (~pequenas).any():
        xy = df[["X", "Y"]].to_numpy()
        _, idx = KDTree(xy[~pequenas]).query(xy[pequenas], k=1)
        rot.iloc[np.where(pequenas)[0]] = rot.iloc[np.where(~pequenas)[0][idx[:, 0]]].to_numpy()
    return rot


def identificar(ucs: gpd.GeoDataFrame, trafos: gpd.GeoDataFrame, acentos: dict | None = None) -> gpd.GeoDataFrame:
    """acentos: grafia dos nomes vinda das fontes do município (ver nomes.exibir)."""
    df = ucs.drop(columns="geometry").copy()
    df = df.join(corrigir_coordenadas(ucs, trafos))

    df["LOC_NORM"] = df["BAIRRO_LOCALIDADE"].map(normalizar)
    df["LOC_TIPO"] = df["LOC_NORM"].map(classificar)
    nomes_validos = df.loc[df["LOC_TIPO"] == "nome", "LOC_NORM"]
    mapa = vocabulario(nomes_validos)
    df["VOTO"] = df["LOC_NORM"].map(mapa).where(df["LOC_TIPO"] == "nome")

    xy = df[["X", "Y"]].to_numpy()
    nome, conf = votar(xy, df["VOTO"].to_numpy(dtype=object), df["COD_TRAFO"].to_numpy())
    df["NOME"] = [exibir(n, acentos) if n else "Sem identificação" for n in nome]
    df["CONFIANCA"] = conf.round(3)
    df["COMUNIDADE_PREVISTA"] = separar_homonimos(df)
    df["COMUNIDADE_PREVISTA"] = absorver_fragmentos(df)

    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["X"], df["Y"]), crs=C.CRS_METRICO)
    return g


def territorios_voronoi(pontos: gpd.GeoDataFrame, coluna: str, municipio: shapely.Geometry,
                        margem_m: float = 1000, crs: str = C.CRS_METRICO) -> gpd.GeoDataFrame:
    """Território de cada comunidade, para desenho no mapa.

    Células de Voronoi por transformador (rótulo = comunidade majoritária das suas UCs),
    unidas por comunidade e recortadas ao município e a uma margem em volta das casas.
    Usar o trafo, e não a UC, evita ilhas de uma casa só nas fronteiras.
    `municipio`: contorno do município já em `crs` (padrão C.CRS_METRICO; quem chama lê o arquivo)."""
    m = pontos.to_crs(crs)
    mun = municipio
    limite = shapely.intersection(mun, m.geometry.buffer(margem_m, quad_segs=4).union_all())
    tr = m.assign(_x=m.geometry.x, _y=m.geometry.y).groupby("COD_TRAFO").agg(
        _x=("_x", "mean"), _y=("_y", "mean"), **{coluna: (coluna, lambda s: s.mode().iat[0])})
    tr = gpd.GeoDataFrame(tr, geometry=gpd.points_from_xy(tr["_x"], tr["_y"]), crs=crs)
    tr = tr[~tr.geometry.duplicated()]
    celulas = shapely.voronoi_polygons(shapely.MultiPoint(tr.geometry.to_list()), extend_to=mun.envelope)
    cel = gpd.GeoDataFrame(geometry=list(celulas.geoms), crs=crs)
    cel = gpd.sjoin(cel, tr[[coluna, "geometry"]], predicate="contains", how="inner")
    t = cel.dissolve(by=coluna, as_index=False)[[coluna, "geometry"]]
    # buffer de ida e volta funde as frestas numéricas entre células vizinhas
    t["geometry"] = t.geometry.buffer(1, quad_segs=2).buffer(-1, quad_segs=2).intersection(limite)
    return t[~t.geometry.is_empty]


ILHA_FRACAO, ILHA_MAX_M2, ILHA_CASAS = 0.12, 2_000_000, 20   # ilha: menos de 12% da comunidade e de 2 km2, ou até 20 casas dela (era 10; mapa mais limpo)


def absorver_ilhas(t: gpd.GeoDataFrame, coluna: str, pontos: gpd.GeoDataFrame | None = None) -> gpd.GeoDataFrame:
    """Passa as ilhas pequenas de cada comunidade (só desenho) para a comunidade que mais as cerca.

    Em cada comunidade fica o pedaço maior; um pedaço menor só some se for pequeno (menos de ILHA_FRACAO da área da
    comunidade e de ILHA_MAX_M2) ou se tiver poucas casas dela (até ILHA_CASAS, quando se passam as `pontos`, na mesma
    projeção): vira da vizinha com mais divisa com ele. Pedaços povoados e distantes ficam, porque em geral são dois
    lugares de mesmo nome. `t` em projeção métrica, uma linha por comunidade."""
    p = t.explode(index_parts=False).reset_index(drop=True)
    p["_a"] = p.geometry.area
    maior, total = p.groupby(coluna)["_a"].transform("max"), p.groupby(coluna)["_a"].transform("sum")
    pequena = (p["_a"] < ILHA_FRACAO * total) & (p["_a"] < ILHA_MAX_M2)
    if pontos is not None:
        j = gpd.sjoin(pontos[[coluna, "geometry"]], p[[coluna, "geometry"]].rename(columns={coluna: "_c"}), predicate="within")
        casas = j[j[coluna] == j["_c"]].groupby("index_right").size().reindex(p.index, fill_value=0)
        pequena |= casas <= ILHA_CASAS
    pequenas = p.index[(p["_a"] < maior) & pequena]
    if not len(pequenas):
        return t
    arvore = STRtree(p.geometry.to_numpy())
    dono = p[coluna].to_numpy(dtype=object).copy()
    for i in sorted(pequenas, key=lambda k: p.at[k, "_a"]):
        borda = p.geometry[i].buffer(2)
        melhor, area = None, 0.0
        for j in arvore.query(borda, predicate="intersects"):
            if dono[j] != dono[i]:
                a = borda.intersection(p.geometry[j]).area
                if a > area:
                    melhor, area = j, a
        if melhor is not None:
            dono[i] = dono[melhor]
    p[coluna] = dono
    r = p.dissolve(by=coluna, as_index=False)[[coluna, "geometry"]]
    r["geometry"] = r.geometry.buffer(1, quad_segs=2).buffer(-1, quad_segs=2)
    return r


VAZIO_MAX_M2 = 1_000_000   # buraco entre territórios de menos de 1 km2 é tapado pela vizinha


def tapar_vazios(t: gpd.GeoDataFrame, coluna: str, municipio: shapely.Geometry) -> gpd.GeoDataFrame:
    """Fecha os buracos pequenos entre os territórios (restos do alisamento e da limpeza de ilhas): cada buraco vira
    da vizinha com mais divisa com ele. Sem isso, a divisa grossa do mapa desenha um pontinho em volta de cada buraco."""
    vazio = shapely.difference(municipio, shapely.union_all(t.geometry.to_numpy()))
    buracos = [g for g in getattr(vazio, "geoms", [vazio]) if g.geom_type == "Polygon" and 0 < g.area < VAZIO_MAX_M2]
    if not buracos:
        return t
    arvore = STRtree(t.geometry.to_numpy())
    extra: dict[int, list] = {}
    for b in buracos:
        borda = b.buffer(2)
        melhor, area = None, 0.0
        for j in arvore.query(borda, predicate="intersects"):
            a = borda.intersection(t.geometry.iloc[j]).area
            if a > area:
                melhor, area = int(j), a
        if melhor is not None:
            extra.setdefault(melhor, []).append(b.buffer(0.5))
    g = t.geometry.copy()
    for j, partes in extra.items():
        g.iloc[j] = shapely.union_all([t.geometry.iloc[j], *partes]).buffer(1, quad_segs=2).buffer(-1, quad_segs=2)
    return t.assign(geometry=g)


def _limpar(t: gpd.GeoDataFrame, coluna: str, pontos: gpd.GeoDataFrame, municipio: shapely.Geometry) -> gpd.GeoDataFrame:
    """Passa as ilhas pequenas à vizinha e tapa os buracos; tapar os buracos pode deixar um restinho solto, então repete."""
    for _ in range(3):
        t = tapar_vazios(absorver_ilhas(t, coluna, pontos), coluna, municipio)
    return t


def territorios_cobrindo(pontos: gpd.GeoDataFrame, coluna: str, municipio: shapely.Geometry,
                         celula_m: float = 150) -> gpd.GeoDataFrame:
    """Território de cada comunidade cobrindo o município inteiro, sem vazios nem sobreposição (só desenho).

    Cada pedaço do município fica com a comunidade das casas mais próximas (Voronoi de células de `celula_m`,
    rótulo = comunidade majoritária da célula), recortado ao contorno do município, com as frestas fechadas e as
    pontas de menos de ~80 m alisadas e as ilhas pequenas passadas para a vizinha (absorver_ilhas). É uma estimativa: não há limite oficial de comunidade.
    `pontos` e `municipio` na mesma projeção métrica."""
    m = pontos.assign(COD_TRAFO=((pontos.geometry.x // celula_m).astype(int).astype(str) + "_"
                                 + (pontos.geometry.y // celula_m).astype(int).astype(str)))
    t = territorios_voronoi(m, coluna, municipio, margem_m=1e7, crs=pontos.crs)
    liso = t.geometry.buffer(-40, quad_segs=4).buffer(40, quad_segs=4)
    t["geometry"] = liso.where(~liso.is_empty, t.geometry)
    t = t[~t.geometry.is_empty]
    # comunidade que nunca foi a maioria de uma célula (poucas casas entre vizinhas grandes) não ficou com área:
    # leva a região das próprias casas (Voronoi por casa), tirada das vizinhas
    sem = sorted(set(pontos[coluna]) - set(t[coluna]))
    if not sem:
        return _limpar(t, coluna, pontos, municipio)
    xy = pontos[["geometry"]].assign(c=pontos[coluna].to_numpy()).drop_duplicates("geometry")
    celulas = shapely.voronoi_polygons(shapely.MultiPoint(xy.geometry.to_list()), extend_to=municipio.envelope)
    cel = gpd.GeoDataFrame(geometry=list(celulas.geoms), crs=pontos.crs)
    cel = gpd.sjoin(cel, gpd.GeoDataFrame(xy[["c"]], geometry=xy.geometry.to_numpy(), crs=pontos.crs),
                    predicate="contains", how="inner")
    novas = cel[cel["c"].isin(sem)].dissolve(by="c", as_index=False)[["c", "geometry"]]
    novas["geometry"] = novas.geometry.intersection(municipio)
    novas = novas[~novas.geometry.is_empty].rename(columns={"c": coluna})
    ocupado = shapely.union_all(novas.geometry.to_numpy())
    t = t.assign(geometry=t.geometry.difference(ocupado))
    return _limpar(pd.concat([t[~t.geometry.is_empty], novas], ignore_index=True), coluna, pontos, municipio)


def territorios(g: gpd.GeoDataFrame, municipio: shapely.Geometry) -> gpd.GeoDataFrame:
    t = territorios_voronoi(g, "COMUNIDADE_PREVISTA", municipio).rename(columns={"COMUNIDADE_PREVISTA": "COMUNIDADE"})
    resumo = g.groupby("COMUNIDADE_PREVISTA").agg(
        N_UC=("UC", "count"), DISTRITO=("DISTRITO", lambda s: s.mode().iat[0]), CONFIANCA_MEDIA=("CONFIANCA", "mean"))
    t = t.join(resumo, on="COMUNIDADE")
    t["CONFIANCA_MEDIA"] = t["CONFIANCA_MEDIA"].round(3)
    return t
