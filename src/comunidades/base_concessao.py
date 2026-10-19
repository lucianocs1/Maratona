"""Base territorial da área de concessão no banco: um município por vez, só dados públicos do IBGE.

Para cada município da concessão (fontes/concessao.py), num processo separado com o município
configurado (FAROL_DISTRIBUIDORA apontando para um .toml mínimo em data/concessao/): baixa o
CNEFE (setores e localidades da UF ficam em cache), limpa as comunidades (fontes/ibge.py, a
mesma limpeza do gabarito), monta a grafia sem o OSM, mede o acerto na amostra separada
(validacao/planilha.py) e grava no banco (banco/base_territorial.py). Sem OSM e sem rede fictícia.
Um município que falha não interrompe os outros: a falha é registrada e o resumo mostra.

Uso:
  uv run python -m comunidades.base_concessao             # os municípios que ainda faltam no banco
  uv run python -m comunidades.base_concessao --refazer   # todos de novo
  uv run python -m comunidades.base_concessao --so 3115300,3169901
"""

import json
import os
import subprocess
import sys
import time

from . import config as C

MARCA = "RESULTADO "           # linha que o processo de cada município imprime no fim
CELULA_TERRITORIO_M = 150      # território para desenho: Voronoi por célula desta largura


def _um_municipio() -> None:
    """Roda dentro do processo do município (config já aponta para ele)."""
    import geopandas as gpd
    import numpy as np

    from .banco import base_territorial as banco
    from .fontes import base_territorial as BT
    from .fontes import dados, grafia, ibge
    from .nucleo.algoritmo import territorios_cobrindo
    from .validacao.planilha import amostra_separada

    dados.garantir()
    if not (C.INTERIM / "enderecos_gabarito.gpkg").exists():
        ibge.construir()
    if not (C.INTERIM / "grafia.json").exists():
        grafia.construir()
    e = BT.enderecos()
    a = amostra_separada(e)
    validacao = {z: {"acerto": round(float(r.ACERTO), 3), "enderecos": int(r.ENDERECOS)} for z, r in a.iterrows()}

    # território de cada comunidade (só para desenho): cobre o município inteiro (Voronoi de células de ~150 m)
    mun = gpd.read_file(C.INTERIM / "municipio.gpkg")
    t = territorios_cobrindo(e.to_crs(C.CRS_METRICO), "COMUNIDADE", mun.to_crs(C.CRS_METRICO).union_all(),
                                CELULA_TERRITORIO_M)
    eg = e.to_crs(C.CRS_GEO)
    dentro = float(os.environ["FAROL_DENTRO"]) if os.environ.get("FAROL_DENTRO") else None
    banco.gravar_municipio(C.COD_MUNICIPIO, C.NOME_MUNICIPIO, C.UF, dentro, mun.to_crs(C.CRS_GEO).union_all(),
                           eg, t.to_crs(C.CRS_GEO), validacao)
    print(MARCA + json.dumps({"enderecos": len(e), "comunidades": int(e["COMUNIDADE"].nunique()),
                              "validacao": validacao, "rural": int(np.sum(e["ZONA"] == "Rural"))}), flush=True)


def _toml(cod: str, nome: str, uf: str):
    """Configuração mínima do município (só o que o config.py lê), em data/concessao/."""
    pasta = C.DADOS / "concessao"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"{cod}.toml"
    arq.write_text("# Gerado por base_concessao.py: só o município, para montar a base territorial.\n"
                   f"[distribuidora]\nmunicipio = {json.dumps(nome, ensure_ascii=False)}\nuf = {json.dumps(uf)}\n"
                   f"codigo_ibge = {json.dumps(cod)}\n", encoding="utf-8")
    return arq


def executar(argv: list[str]) -> int:
    from .banco import base_territorial as banco
    from .fontes import concessao

    banco.criar_esquema()
    ms = concessao.municipios()
    so = set(argv[argv.index("--so") + 1].split(",")) if "--so" in argv else None
    feitos = {} if "--refazer" in argv else banco.municipios_gravados()
    fila = [r for r in ms.itertuples() if (so is None or r.CD_MUN in so) and r.CD_MUN not in feitos]
    print(f"Concessão {concessao.SIGLA}: {len(ms)} municípios; no banco: {len(feitos)}; a processar: {len(fila)}", flush=True)
    falhas = []
    for i, r in enumerate(fila, 1):
        t0 = time.time()
        env = {**os.environ, "FAROL_DISTRIBUIDORA": str(_toml(r.CD_MUN, r.NM_MUN, r.SIGLA_UF)),
               "FAROL_DENTRO": f"{r.DENTRO:.4f}", "PYTHONIOENCODING": "utf-8"}
        p = subprocess.run([sys.executable, "-m", "comunidades.base_concessao", "--um"], env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        linha = next((l for l in p.stdout.splitlines() if l.startswith(MARCA)), None)
        rotulo = f"[{i}/{len(fila)}] {r.NM_MUN}/{r.SIGLA_UF} ({r.CD_MUN})"
        if p.returncode or not linha:
            erro = (p.stderr.strip().splitlines() or ["sem mensagem"])[-1]
            falhas.append((rotulo, erro))
            print(f"{rotulo}: FALHOU em {time.time() - t0:.0f} s: {erro}", flush=True)
            continue
        res = json.loads(linha[len(MARCA):])
        v = res["validacao"]
        acerto = " | ".join(f"{z.lower()} {d['acerto']:.1%} ({d['enderecos']})" for z, d in v.items())
        print(f"{rotulo}: {res['enderecos']} endereços, {res['comunidades']} comunidades | acerto {acerto} | "
              f"{time.time() - t0:.0f} s", flush=True)
    banco.colorir_mapa()
    print(f"\nNo banco:{len(banco.municipios_gravados())} de {len(ms)} municípios. Falhas nesta rodada: {len(falhas)}")
    for rotulo, erro in falhas:
        print(f"  {rotulo}: {erro}")
    return 1 if falhas else 0


if __name__ == "__main__":
    if "--um" in sys.argv:
        _um_municipio()
    else:
        sys.exit(executar(sys.argv[1:]))
