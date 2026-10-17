"""Página de entrada do Norte (saida/index.html): abertura, o mapa do Brasil e a escolha da área.

Lista os municípios já processados, lendo os resumo_mapa.json que cada mapa grava ao lado
(só nome, UF, código IBGE e contagens). O mapa (Leaflet embutido) mostra as UFs, o contorno da
área de concessão e os municípios dentro dela: os já processados abrem o mapa do Norte, os outros
aparecem como "ainda não processado". Os links são relativos, para funcionar aberta como arquivo,
sem servidor. O script é liberado pelo hash na CSP, como no mapa, e os cartões continuam abaixo
do mapa (funcionam também sem script).

Uso: py -m uv run python -m comunidades.apresentacao.entrada (o pipeline já roda no fim)
"""

import json
from html import escape
from pathlib import Path

import geopandas as gpd
import shapely

from .. import config as C
from ..fontes import concessao
from .mapa import ARQ_RESUMO, LEAFLET, SAIDA_RAIZ, _fontes_embutidas, favicon, logo_com_feixe, politica_seguranca

TEMPLATE = Path(__file__).with_name("entrada_template.html")
ARQ_ENTRADA = SAIDA_RAIZ / "index.html"
# simplificação (em graus) e casas decimais de cada camada: o bastante para a escala de cada uma
SIMPLIFICAR = {"ufs": (0.01, 3), "concessao": (0.0005, 4), "municipios": (0.001, 4)}


def municipios() -> list[dict]:
    """Resumos dos mapas já gerados: saida/ (o primeiro município) e saida/<municipio>/, em ordem alfabética."""
    arquivos = [SAIDA_RAIZ / ARQ_RESUMO.name, *sorted(SAIDA_RAIZ.glob(f"*/{ARQ_RESUMO.name}"))]
    lista = [json.loads(a.read_text(encoding="utf-8")) for a in arquivos if a.exists()]
    return sorted((m for m in lista if (SAIDA_RAIZ / m["mapa"]).exists()), key=lambda m: C.sem_acento(m["municipio"]))


def _n(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def _cartao(m: dict) -> str:
    nome, uf = escape(m["municipio"]), escape(m["uf"])
    return f"""
      <li class="cartao">
        <div class="cartao-cab"><h2>{nome}</h2><span class="uf">{uf}</span></div>
        <dl class="numeros">
          <div><dt>clientes</dt><dd>{_n(m["clientes"])}</dd></div>
          <div><dt>comunidades</dt><dd>{_n(m["comunidades"])}</dd></div>
          <div><dt>chaves</dt><dd>{_n(m["chaves"])}</dd></div>
        </dl>
        <a class="abrir" href="{escape(m["mapa"])}" aria-label="Abrir {nome}/{uf}">Abrir</a>
      </li>"""


def _geo(g, props: list[str], camada: str) -> dict:
    tolerancia, casas = SIMPLIFICAR[camada]
    g = g.to_crs(C.CRS_WEB)
    g["geometry"] = shapely.set_precision(g.geometry.simplify(tolerancia, preserve_topology=True).values, 10 ** -casas)
    return json.loads(g[props + ["geometry"]].to_json(drop_id=True))


def _chave(nome: str, uf: str) -> tuple[str, str]:
    return C.sem_acento(nome).upper(), uf.upper()


def dados_mapa(ms: list[dict]) -> dict:
    """O que o mapa da entrada desenha: UFs, contorno da concessão e os municípios dentro dela.
    Dos municípios processados vão só o link do mapa e as contagens do resumo."""

    area, u = concessao.contorno(), concessao.ufs()
    mun = concessao.municipios(area, u)
    por_codigo = {str(m["codigo_ibge"]): m for m in ms if m.get("codigo_ibge")}
    por_nome = {_chave(m["municipio"], m["uf"]): m for m in ms}
    pronto = [por_codigo.get(c) or por_nome.get(_chave(n, s)) for c, n, s in zip(mun["CD_MUN"], mun["NM_MUN"], mun["SIGLA_UF"])]
    mun["MAPA"] = [p["mapa"] if p else "" for p in pronto]
    for campo in ("clientes", "comunidades", "chaves"):
        mun[campo.upper()] = [int(p[campo]) if p else 0 for p in pronto]
    ponto = mun.geometry.representative_point()
    u["LAT"], u["LON"] = u.geometry.representative_point().y.round(3), u.geometry.representative_point().x.round(3)
    return {
        "ufs": _geo(u, ["SIGLA_UF", "NM_UF"], "ufs"),
        "concessao": {"sigla": concessao.SIGLA, "n": len(mun),
                      "geo": _geo(gpd.GeoDataFrame(geometry=[area], crs=C.CRS_GEO), [], "concessao")},
        "municipios": _geo(mun, ["CD_MUN", "NM_MUN", "SIGLA_UF", "MAPA", "CLIENTES", "COMUNIDADES", "CHAVES"], "municipios"),
        # ponto de cada município processado, para aparecer também na escala do país
        "prontos": [[round(p.y, 4), round(p.x, 4), i] for i, (p, m) in enumerate(zip(ponto, mun["MAPA"])) if m],
        "rotulosUF": [[r.LAT, r.LON, r.SIGLA_UF] for r in u.itertuples()],
    }


def construir() -> Path:
    ms = municipios()
    cartoes = (f'<ul class="cartoes">{"".join(_cartao(m) for m in ms)}\n    </ul>' if ms
               else '<p class="vazio">Nenhuma área gerada ainda. Rode o Norte para um município.</p>')
    try:
        dados = dados_mapa(ms)
    except (OSError, ValueError) as e:  # sem internet na primeira vez ou KML inválido: entrada só com os cartões
        print(f"  aviso: mapa da entrada sem a concessão ({e})")
        dados = None
    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("<!--__LOGO__-->", logo_com_feixe())
            .replace("__FAVICON__", favicon())
            .replace("/*__FONTES__*/", _fontes_embutidas())
            .replace("/*__LEAFLET_CSS__*/", (LEAFLET / "leaflet.css").read_text(encoding="utf-8"))
            .replace("/*__LEAFLET_JS__*/", (LEAFLET / "leaflet.js").read_text(encoding="utf-8"))
            .replace("/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
            .replace("<!--__CARTOES__-->", cartoes)
            # Link para a área administrativa (protótipo), quando ela já foi gerada
            .replace("<!--__ADMIN__-->", '<p class="admin"><a href="admin.html">Área administrativa (protótipo)</a></p>'
                     if (SAIDA_RAIZ / "admin.html").exists() else ""))
    html = html.replace("/*__CSP__*/", politica_seguranca(html))
    ARQ_ENTRADA.write_text(html, encoding="utf-8", newline="\n")
    return ARQ_ENTRADA


if __name__ == "__main__":
    p = construir()
    print(f"Entrada: {p} ({len(municipios())} áreas, {p.stat().st_size / 1e6:.1f} MB)")
