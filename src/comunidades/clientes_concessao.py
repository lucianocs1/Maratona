"""Clientes FICTÍCIOS dos municípios da concessão no banco (a camada "Clientes" do mapa).

Para cada município que já tem base territorial e rede fictícia (base_concessao.py, rede_concessao.py), num processo
separado com o município configurado (data/concessao/<código>.toml): cada endereço do CNEFE vira um cliente com a
classe da espécie do endereço, ligado ao transformador mais próximo e ao circuito (alimentador) dele. Equipamento vital
(só entre residenciais e rurais) e UC inativa são sorteados com semente fixa (o código do município): rodar de novo
dá o mesmo resultado. Nada de número de UC, titular ou endereço: só o ponto e os atributos (banco/clientes.py).
Um município que falha não interrompe os outros.

Uso:
  uv run python -m comunidades.clientes_concessao             # os municípios que ainda não têm clientes
  uv run python -m comunidades.clientes_concessao --refazer   # todos de novo
  uv run python -m comunidades.clientes_concessao --so 3115300,3169901
"""

import json
import os
import subprocess
import sys
import time

from . import config as C

MARCA = "RESULTADO "
# espécie do endereço no CNEFE -> classe (1 residencial, 2 rural, 3 comercial, 4 poder público); o resto não é cliente
ESPECIE_CLASSE = {"1": 1, "2": 1, "3": 2, "4": 4, "5": 4, "6": 3, "8": 3}


def _um_municipio() -> None:
    """Roda dentro do processo do município (config já aponta para ele)."""
    import geopandas as gpd
    import numpy as np
    from scipy.spatial import cKDTree

    from .banco import clientes as banco

    cod = C.COD_MUNICIPIO
    g = gpd.read_file(C.INTERIM / "enderecos_gabarito.gpkg", columns=["COD_ESPECIE"])
    classe = g["COD_ESPECIE"].astype(str).map(ESPECIE_CLASSE)
    g = g[classe.notna().to_numpy()].reset_index(drop=True)
    classe = classe[classe.notna()].astype(int).to_numpy()
    if g.empty:
        raise SystemExit("sem endereços com espécie de cliente")

    trafos = banco.trafos_do_municipio(cod).to_crs(C.CRS_METRICO)
    trechos = banco.trechos_do_municipio(cod).to_crs(C.CRS_METRICO)
    if trafos.empty or trechos.empty:
        raise SystemExit("o município não tem rede no banco (rode rede_concessao)")
    # o circuito de cada trafo: o do trecho de média tensão mais próximo
    ali = gpd.sjoin_nearest(trafos[["COD_TRAFO", "geometry"]], trechos[["ALIMENTADOR", "geometry"]]).drop_duplicates("COD_TRAFO")
    circuito = dict(zip(ali["COD_TRAFO"], ali["ALIMENTADOR"]))

    xy = np.column_stack([g.to_crs(C.CRS_METRICO).geometry.x, g.to_crs(C.CRS_METRICO).geometry.y])
    txy = np.column_stack([trafos.geometry.x, trafos.geometry.y])
    _, i = cKDTree(txy).query(xy)
    cod_trafo = trafos["COD_TRAFO"].to_numpy()[i]

    rng = np.random.default_rng(int(cod))
    vital = np.isin(classe, (1, 2)) & (rng.random(len(g)) < banco.VITAL_PCT)
    ativa = rng.random(len(g)) >= banco.INATIVA_PCT
    pontos = g.to_crs(C.CRS_GEO).geometry.to_numpy()
    n = banco.gravar(cod, classe, vital, ativa, cod_trafo, [circuito[t] for t in cod_trafo], pontos)
    print(MARCA + json.dumps({"clientes": n, "vitais": int(vital.sum()), "inativas": int((~ativa).sum()),
                              "trafos": int(len(set(cod_trafo)))}), flush=True)


def executar(argv: list[str]) -> int:
    from .banco import base_territorial as banco_base
    from .banco import clientes as banco
    from .banco import rede as banco_rede

    banco.criar_esquema()
    ms = banco_base.municipios_gravados()
    so = set(argv[argv.index("--so") + 1].split(",")) if "--so" in argv else None
    com_rede = banco_rede.municipios_com_rede()
    feitos = set() if "--refazer" in argv else banco.municipios_com_clientes()
    fila = sorted((cod for cod in ms if (so is None or cod in so) and cod in com_rede and cod not in feitos), key=lambda c: ms[c]["nome"])
    print(f"Base territorial: {len(ms)} municípios; com rede: {len(com_rede & set(ms))}; com clientes: {len(feitos & set(ms))}; "
          f"a processar: {len(fila)}", flush=True)
    falhas = []
    for i, cod in enumerate(fila, 1):
        t0 = time.time()
        rotulo = f"[{i}/{len(fila)}] {ms[cod]['nome']}/{ms[cod]['uf']} ({cod})"
        toml = C.DADOS / "concessao" / f"{cod}.toml"
        if not toml.exists():
            falhas.append((rotulo, f"falta {toml.name} (rode o base_concessao)"))
            print(f"{rotulo}: FALHOU: falta {toml}", flush=True)
            continue
        env = {**os.environ, "FAROL_DISTRIBUIDORA": str(toml), "PYTHONIOENCODING": "utf-8"}
        p = subprocess.run([sys.executable, "-m", "comunidades.clientes_concessao", "--um"], env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        linha = next((l for l in p.stdout.splitlines() if l.startswith(MARCA)), None)
        if p.returncode or not linha:
            erro = (p.stderr.strip().splitlines() or p.stdout.strip().splitlines() or ["sem mensagem"])[-1]
            falhas.append((rotulo, erro))
            print(f"{rotulo}: FALHOU em {time.time() - t0:.0f} s: {erro}", flush=True)
            continue
        r = json.loads(linha[len(MARCA):])
        print(f"{rotulo}: {r['clientes']} clientes em {r['trafos']} transformadores, {r['vitais']} vitais, {r['inativas']} inativas "
              f"| {time.time() - t0:.0f} s", flush=True)
    print(f"\nCom clientes no banco: {len(banco.municipios_com_clientes() & set(ms))} de {len(ms)} municípios. "
          f"Falhas nesta rodada: {len(falhas)}")
    for rotulo, erro in falhas:
        print(f"  {rotulo}: {erro}")
    return 1 if falhas else 0


if __name__ == "__main__":
    if "--um" in sys.argv:
        _um_municipio()
    else:
        sys.exit(executar(sys.argv[1:]))
