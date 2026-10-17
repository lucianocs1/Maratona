"""Mapa interativo (HTML autônomo, Leaflet): camadas reais + fictícias + resultado,
com painel para simular o desligamento de qualquer chave."""

import base64
import hashlib
import json
import os
import re
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely

from .. import config as C
from ..fontes import grafia, osm
from ..nucleo.algoritmo import territorios_voronoi
from ..nucleo.desligamento import CABECALHO_ANTIGO, codigos_locais, duracao_s, locais_antigos, palavras_do_e, simular
from .. import distribuidora as dist_
from ..nucleo import idiomas
from ..nucleo.abrangencia import MARGEM_DIVISA_M, fatores_metros
from ..nucleo.area import CASAS, MAX_VERTICES
from ..nucleo.impacto import perfis_para_mapa
from ..nucleo.nomes import classificar, exibir, normalizar
from ..validacao.avaliacao import avaliar

TEMPLATE = Path(__file__).with_name("mapa_template.html")
ARQ_SAIDA = C.SAIDA / "mapa_comunidades.html"
SAIDA_RAIZ = C.RAIZ / "saida"                              # onde fica a página de entrada (index.html)
ARQ_RESUMO = C.SAIDA / "resumo_mapa.json"                  # só contagens, para o cartão do município na entrada
LEAFLET = Path(__file__).with_name("vendor") / "leaflet"   # Leaflet 1.9.4 embutido (sem CDN)
PLEX = Path(__file__).with_name("vendor") / "ibm-plex"     # fontes IBM Plex embutidas (OFL)
MARCA = Path(__file__).with_name("marca")                  # logo do Norte
FONTES = [("IBM Plex Sans", "ibm-plex-sans-latin-400-normal.woff2", 400),
          ("IBM Plex Sans", "ibm-plex-sans-latin-500-normal.woff2", 500),
          ("IBM Plex Sans", "ibm-plex-sans-latin-600-normal.woff2", 600),
          ("IBM Plex Mono", "ibm-plex-mono-latin-500-normal.woff2", 500)]
FUNDO_MAPA = "https://server.arcgisonline.com"            # único servidor externo: fundos da Esri


def _gj(gdf: gpd.GeoDataFrame, props: list[str], simplificar_m: float = 0) -> dict:
    g = gdf.to_crs(C.CRS_METRICO)
    if simplificar_m:
        g["geometry"] = g.geometry.simplify(simplificar_m)
    g = g.to_crs(C.CRS_WEB)
    g["geometry"] = shapely.set_precision(g.geometry.values, 1e-5)
    return json.loads(g[props + ["geometry"]].to_json(drop_id=True))


def _territorios_reais(pontos: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    mun = gpd.read_file(C.INTERIM / "municipio.gpkg").to_crs(C.CRS_METRICO).union_all()
    t = territorios_voronoi(pontos, "COMUNIDADE", mun).rename(columns={"COMUNIDADE": "NOME"})
    return t.join(pontos.groupby("COMUNIDADE").size().rename("N_UC"), on="NOME")


def construir(dist=None):
    dist = dist or dist_.carregar()
    atividades = list(dist.perfis)
    df, por_uc, _, cen = avaliar(dist)  # df: UCs com previsão + gabarito (só para a camada de validação)
    gab = pd.read_csv(C.SINTETICO / "gabarito_uc.csv", dtype={"UC": str}).set_index("UC")
    df = df.join(gab[["LAT_REAL", "LON_REAL"]], on="UC")

    tr = gpd.read_file(C.SINTETICO / "transformadores.gpkg")
    ch = gpd.read_file(C.SINTETICO / "chaves.gpkg")
    mt = gpd.read_file(C.SINTETICO / "rede_mt.gpkg")
    se = gpd.read_file(C.SINTETICO / "subestacao.gpkg")

    # Trechos de MT a jusante de cada chave
    T = nx.DiGraph(list(zip(mt["NO_DE"], mt["NO_PARA"])))
    trecho_por_no = {n: i for i, n in enumerate(mt["NO_PARA"])}
    mt_chave = {}
    for _, r in ch.iterrows():
        mt_chave[r["COD_CHAVE"]] = [trecho_por_no[n] for n in nx.dfs_preorder_nodes(T, r["NO_PARA"])
                                    if n in trecho_por_no]

    # Índices compactos
    trafo_idx = {c: i for i, c in enumerate(tr["COD_TRAFO"])}
    com_prev = sorted(df["COMUNIDADE_PREVISTA"].unique())
    acentos = grafia.carregar()
    df["COMUNIDADE"] = df["COMUNIDADE"].map(lambda n: exibir(n, acentos))  # grafia com acentos para exibição
    com_real = sorted(df["COMUNIDADE"].unique())
    ip, ir = {c: i for i, c in enumerate(com_prev)}, {c: i for i, c in enumerate(com_real)}
    origem = {"cadastro": 0, "trafo (sem coordenada)": 1, "trafo (coordenada incoerente)": 2}

    # LGPD: o HTML não leva titular, número da UC nem endereço; só classe, comunidade e dados técnicos
    classes = sorted(df["CLASSE"].unique())
    # texto digitado no campo localidade; o que é nome de imóvel (o mesmo critério da votação) não vai
    # para o HTML: essas UCs recebem -1 e o popup mostra "(nome de imóvel)"
    imovel = lambda l: classificar(normalizar(l)) == "propriedade"
    loc_cad = sorted(l for l in df["BAIRRO_LOCALIDADE"].fillna("").astype(str).unique() if not imovel(l))
    ic, il = {c: i for i, c in enumerate(classes)}, {c: i for i, c in enumerate(loc_cad)}
    # desligamento por área: distrito (para o aviso) e atividade (para a janela e as cargas sensíveis),
    # só como códigos; atividade fora dos perfis da distribuidora = -1 (não entra na contagem)
    distritos_uc = sorted(df["DISTRITO"].unique())
    idist, iativ = {d: i for i, d in enumerate(distritos_uc)}, {a: i for i, a in enumerate(atividades)}
    # tamanho do aviso de hoje na área: o local de cada UC só como código (-1 = não entra) e as
    # palavras de cada local; os nomes de imóveis e ruas não vão para o HTML
    cod_local, palavras_local = codigos_locais(df)
    ucs = [[round(r.LAT_REAL, 5), round(r.LON_REAL, 5), trafo_idx[r.COD_TRAFO], ip[r.COMUNIDADE_PREVISTA],
            ir[r.COMUNIDADE], int(r.CONFIANCA * 100), int(r.ACERTO), origem[r.ORIGEM_COORD],
            1 if r.CLASSE == "Rural" else 0, ic[r.CLASSE], -1 if imovel(str(r.BAIRRO_LOCALIDADE or "")) else il[str(r.BAIRRO_LOCALIDADE or "")],
            idist[r.DISTRITO], iativ.get(r.ATIVIDADE, -1), cl]
           for r, cl in zip(df.itertuples(), cod_local)]

    # Cenários pré-calculados (mesma lógica do módulo desligamento)
    trafos_por_chave = {}
    for i, lista in enumerate(tr["CHAVES_MONTANTE"].fillna("")):
        for c in filter(None, lista.split(";")):
            trafos_por_chave.setdefault(c, []).append(i)
    cen = cen.set_index("CHAVE")
    cenarios = {}
    for _, r in ch.iterrows():
        cod = r["COD_CHAVE"]
        if cod not in cen.index:
            continue
        d = simular(df, cod, dist.regras)
        e = cen.loc[cod]
        cenarios[cod] = {
            "alim": r["ALIMENTADOR"], "n": len(d.ucs), "rural": round(float(e["RURAL"]), 2),
            "trafos": trafos_por_chave.get(cod, []), "mt": mt_chave.get(cod, []),
            "com": [[c.COMUNIDADE_PREVISTA, int(c.UC_AFETADAS), int(c.UC_TOTAL), bool(c.PARCIAL),
                     round(float(c.CONFIANCA), 2), bool(c.FRAGMENTO), c.DISTRITO]
                    for c in d.comunidades.itertuples()],
            "real": d.ucs["COMUNIDADE"].value_counts().reset_index().values.tolist(),
            "antigo": d.aviso_antigo, "novo": d.aviso_novo, "nLocais": len(locais_antigos(d.ucs)),
            "sAntes": round(duracao_s(d.aviso_antigo)), "sDepois": round(duracao_s(d.aviso_novo)),
            "prec": round(float(e["PRECISAO"]), 2), "cob": round(float(e["COBERTURA"]), 2),
            "cobUC": round(float(e["COBERTURA_UC"]), 3),
            # UCs afetadas por atividade (só contagens), na ordem dos perfis da distribuidora
            "ativ": [int(n) for n in d.ucs["ATIVIDADE"].value_counts().reindex(atividades, fill_value=0)],
        }

    # Camadas geográficas
    pts_real = gpd.GeoDataFrame(df[["COMUNIDADE", "COD_TRAFO"]], crs=C.CRS_GEO,
                                geometry=gpd.points_from_xy(df["LON_REAL"], df["LAT_REAL"]))
    prev = gpd.read_file(C.SAIDA / "comunidades.gpkg")
    camadas = {
        "municipio": _gj(gpd.read_file(C.INTERIM / "municipio.gpkg"), ["NM_MUN"], 20),
        "distritos": _gj(gpd.read_file(C.INTERIM / "distritos.gpkg"), ["NM_DIST"], 20),
        "setores": _gj(gpd.read_file(C.INTERIM / "setores.gpkg"), ["CD_SETOR", "SITUACAO"], 10),
        "localidades": _gj(gpd.read_file(C.INTERIM / "localidades_oficiais.gpkg"), ["NM_LOCALIDADE", "CT_LOCALIDADE"]),
        "gabarito": _gj(_territorios_reais(pts_real), ["NOME", "N_UC"], 15),
        "vias": _gj(gpd.read_file(osm.ARQ_VIAS).assign(
            MAIOR=lambda g: g["highway"].str.contains("trunk|primary|secondary|tertiary").astype(int)
        ), ["MAIOR"], 8),
        "previstas": _gj(prev.rename(columns={"COMUNIDADE": "NOME"}), ["NOME", "N_UC", "CONFIANCA_MEDIA"], 15),
        "se": _gj(se, ["NOME"]),
        "mt": _gj(mt, ["ALIMENTADOR"], 3),
        "chaves": _gj(ch, ["COD_CHAVE", "ALIMENTADOR", "UC_JUSANTE"]),
    }
    trw = tr.to_crs(C.CRS_WEB)
    trafos = [[round(p.y, 5), round(p.x, 5), c, int(n), a]
              for p, c, n, a in zip(trw.geometry, trw["COD_TRAFO"], trw["N_UC"], trw["ALIMENTADOR"])]

    rural = cen[cen["RURAL"] >= 0.8]
    metricas = {
        "acertoRuralCadastro": round(float(por_uc.loc["Rural", "ACERTO_CADASTRO"]) * 100, 1),
        "acertoRural": round(float(por_uc.loc["Rural", "ACERTO"]) * 100, 1),
        "acertoUrbanoCadastro": round(float(por_uc.loc["Urbana", "ACERTO_CADASTRO"]) * 100, 1),
        "acertoUrbano": round(float(por_uc.loc["Urbana", "ACERTO"]) * 100, 1),
        "cobertura": round(float(cen["COBERTURA"].mean()) * 100, 1),
        "coberturaUC": round(float(cen["COBERTURA_UC"].mean()) * 100, 1),
        "precisao": round(float(cen["PRECISAO"].mean()) * 100, 1),
        "segAntes": round(float(rural["SEG_ANTES"].mean())), "segDepois": round(float(rural["SEG_DEPOIS"].mean())),
        "nCenarios": len(cen), "nUC": len(df), "nComunidades": len(com_prev), "nTrafos": len(tr),
        "nChaves": len(ch), "kmMT": round(float(mt.to_crs(C.CRS_METRICO).length.sum() / 1000)),
    }

    dados = {"camadas": camadas, "ucs": ucs, "classes": classes, "locCad": loc_cad, "trafos": trafos,
             "comPrev": com_prev, "comReal": com_real, "cenarios": cenarios, "metricas": metricas,
             "perfis": perfis_para_mapa(dist.perfis, dist.expediente, dist.razao_muito_pior),
             "distribuidora": dist.para_mapa(), "idiomas": idiomas.para_mapa(),
             # ponto da obra: fatores graus -> metros (centro do município) e clientes por alimentador (só contagens)
             "rede": dict(zip(("kx", "ky"), fatores_metros(gpd.read_file(C.INTERIM / "municipio.gpkg").to_crs(C.CRS_GEO).union_all().centroid.y)),
                          margemDivisaM=MARGEM_DIVISA_M, clientesPorAlimentador={a: int(n) for a, n in df["ALIMENTADOR"].value_counts().sort_index().items()}),
             "alimentadores": sorted(mt["ALIMENTADOR"].unique()),
             # desligamento por área: as mesmas regras de desligamento.resumir e os limites do contorno
             "distritosUC": distritos_uc,
             "regrasAviso": {"limiarTotal": dist.regras.limiar_total, "limiteFragmento": dist.regras.limite_fragmento,
                             "limiteParticipacao": dist.regras.limite_participacao},
             "avisoHoje": {"cabecalho": CABECALHO_ANTIGO.replace("{assinatura}", dist.regras.assinatura_aviso_atual),
                           "palavrasLocal": palavras_local, "palavrasE": palavras_do_e()},
             "area": {"maxVertices": MAX_VERTICES, "casas": CASAS, "maxBytes": 5 * 1024 * 1024}}
    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("<!--__LOGO__-->", (MARCA / "farol.svg").read_text(encoding="utf-8").strip())
            .replace("<!--__LOGO_ABERTURA__-->", logo_com_feixe())
            .replace("__ENTRADA__", Path(os.path.relpath(SAIDA_RAIZ / "index.html", C.SAIDA)).as_posix())  # "Trocar área"
            .replace("__FAVICON__", favicon())
            .replace("/*__FONTES__*/", _fontes_embutidas())
            .replace("/*__LEAFLET_CSS__*/", (LEAFLET / "leaflet.css").read_text(encoding="utf-8"))
            .replace("/*__LEAFLET_JS__*/", (LEAFLET / "leaflet.js").read_text(encoding="utf-8"))
            .replace("/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
    html = html.replace("/*__CSP__*/", politica_seguranca(html))
    ARQ_SAIDA.write_text(html, encoding="utf-8", newline="\n")
    # Cartão do município na página de entrada: nome, UF e contagens (nada de dados de clientes)
    ARQ_RESUMO.write_text(json.dumps({
        "municipio": dist.municipio, "uf": dist.uf, "codigo_ibge": C.COD_MUNICIPIO, "mapa": ARQ_SAIDA.relative_to(SAIDA_RAIZ).as_posix(),
        "clientes": metricas["nUC"], "comunidades": metricas["nComunidades"], "chaves": metricas["nChaves"],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return ARQ_SAIDA


def favicon() -> str:
    return f"data:image/svg+xml;base64,{base64.b64encode((MARCA / 'farol-pequeno.svg').read_bytes()).decode()}"


def logo_com_feixe() -> str:
    """Logo do Norte com os dois feixes num grupo (class="feixe"), para a abertura girar só o feixe.
    O desenho é o mesmo do farol.svg."""
    svg = (MARCA / "farol.svg").read_text(encoding="utf-8").strip()
    feixes = re.findall(r'\n\s*<path [^>]*opacity="0\.45"/>', svg)
    if len(feixes) != 2:
        raise ValueError("farol.svg mudou: não achei os dois feixes (opacity 0.45)")
    for f in feixes:
        svg = svg.replace(f, "")
    return svg.replace('fill="none">', 'fill="none">\n  <g class="feixe">' + "".join(feixes) + "\n  </g>", 1)


def _fontes_embutidas() -> str:
    """@font-face das fontes IBM Plex, embutidas como data: (sem servidor de fontes)."""
    regras = []
    for familia, arquivo, peso in FONTES:
        b64 = base64.b64encode((PLEX / arquivo).read_bytes()).decode()
        regras.append(f"@font-face{{font-family:'{familia}';font-style:normal;font-weight:{peso};font-display:swap;"
                      f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "\n".join(regras)


def politica_seguranca(html: str, fundo_mapa: bool = True) -> str:
    """Content Security Policy do mapa: só roda os scripts embutidos (pelo hash SHA-256 de cada um)
    e só carrega imagens dos fundos de mapa da Esri. Nenhuma outra conexão externa.
    Sem fundo_mapa (área administrativa), nem as imagens da Esri: só as embutidas."""
    hashes = " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(s.encode('utf-8')).digest()).decode()}'"
                      for s in re.findall(r"<script>(.*?)</script>", html, flags=re.S)) or "'none'"  # sem script: nenhum roda
    return "; ".join([
        "default-src 'none'",
        f"script-src {hashes}",
        "style-src 'unsafe-inline'",
        f"img-src {FUNDO_MAPA} data:" if fundo_mapa else "img-src data:",  # data: = imagem embutida (o Leaflet usa para cancelar blocos), sem conexão
        "font-src data:",  # só as fontes embutidas no próprio arquivo, sem servidor
        "connect-src 'none'", "media-src 'none'", "object-src 'none'",
        "frame-src 'none'", "worker-src 'none'", "base-uri 'none'", "form-action 'none'",
    ])


if __name__ == "__main__":
    p = construir()
    print(f"Mapa: {p} ({p.stat().st_size / 1e6:.1f} MB)")
