"""Relatório de conferência: as localidades oficiais do IBGE contra as comunidades que o app monta (CNEFE).

Feito para o pessoal de negócio revisar: dois CSVs (separador ";", abrem direto no Excel) com as colunas de decisão em
branco, e um resumo por município. Não muda nada do aviso: o casamento é só por nome (nucleo/localidades.py) e a posição
mostra se o par faz sentido (nomes se repetem). Só dado público: nada de cliente, UC ou endereço de pessoa.

Saídas em saida/localidades/:
- conferencia_localidades.csv: cada localidade do IBGE, a comunidade nossa de mesmo nome (se houver), se o ponto cai no
  território dela e em qual comunidade o ponto cai de fato; "decisao_negocio" para eles preencherem.
- comunidades_sem_nome_oficial.csv: as comunidades nossas sem localidade do IBGE de mesmo nome, das maiores para as
  menores, com a localidade oficial que cai dentro delas (candidata a nome oficial); "nome_oficial_sugerido" em branco.
- resumo_por_municipio.csv: os números por município.

Uso: uv run python -m comunidades.validacao.localidades
"""

import csv
import sys
from collections import defaultdict

from .. import config as C
from ..banco import localidades as banco
from ..nucleo import localidades as regra

GRAUS_POR_METRO = 1 / 111_320   # distância aproximada em metros, boa o bastante para "dentro", "a 200 m" ou "longe"
SAIDA = C.SAIDA / "localidades"


def _metros(graus: float) -> int:
    return round(graus / GRAUS_POR_METRO)


def conferir(oficiais: list[dict], comunidades: list[dict]) -> dict:
    """As linhas das três planilhas. oficiais: dicts do banco (com 'ponto'); comunidades: dicts do banco (com 'territorio')."""
    por_mun = defaultdict(list)
    for c in comunidades:
        por_mun[c["codigo_ibge"]].append(c)
    linhas, casadas, dentro = [], set(), defaultdict(list)
    for o in oficiais:
        lista = por_mun.get(o["codigo_ibge"], [])
        nomes = [regra.sem_sufixo(c["nome"]) for c in lista]
        veredito, i = regra.casar(o["nome"], nomes)
        par = lista[i] if i is not None else None
        if par:
            casadas.add((o["codigo_ibge"], i))
        contem = sorted((c for c in lista if c["territorio"] is not None and c["territorio"].contains(o["ponto"])), key=lambda c: c["territorio"].area)
        for c in contem:
            dentro[(c["codigo_ibge"], c["nome"], c["distrito"])].append(f"{o['nome']} ({o['categoria']})")
        atencao = []
        if par is None:
            posicao = "-"
            if o["categoria"] == "Cidade":
                atencao.append('sede municipal: no aviso o app a chama de "Sede"')
        elif par["territorio"] is None:
            posicao = "comunidade sem território desenhado"
            atencao.append("a comunidade não tem território desenhado")
        elif par["territorio"].contains(o["ponto"]):
            posicao = "dentro"
        else:
            d = _metros(par["territorio"].distance(o["ponto"]))
            posicao = f"fora, a {d} m"
            if d > 50:
                atencao.append("mesmo nome, mas o ponto está longe do território: pode ser outro lugar de nome repetido")
        if par is not None:
            repetidas = sum(1 for n in nomes if regra.normalizar(n) == regra.normalizar(nomes[i]))
            if repetidas > 1:
                atencao.append(f"há {repetidas} comunidades com este nome no município")
        if par is None and contem:
            atencao.append("o ponto cai numa comunidade de outro nome")
        linhas.append({
            "municipio": o["municipio"], "uf": o["uf"], "codigo_localidade": o["codigo"], "localidade_ibge": o["nome"],
            "categoria": o["categoria"], "casamento": veredito,
            "comunidade_nossa": nomes[i] if par else "", "enderecos_da_comunidade": par["enderecos"] if par else "",
            "ponto_no_territorio_dela": posicao,
            "comunidade_onde_o_ponto_cai": (regra.sem_sufixo(contem[0]["nome"]) if contem else "nenhuma"),
            "atencao": "; ".join(atencao), "decisao_negocio": "", "observacao_negocio": "",
        })
    sem_par = []
    for k, cs in por_mun.items():
        for i, c in enumerate(cs):
            if (k, i) in casadas:
                continue
            achadas = dentro.get((c["codigo_ibge"], c["nome"], c["distrito"]), [])
            sem_par.append({
                "municipio": c["municipio"], "comunidade_nossa": c["nome"], "distrito": c["distrito"], "enderecos": c["enderecos"],
                "territorio_desenhado": "sim" if c["territorio"] is not None else "não",
                "localidades_oficiais_dentro_dela": "; ".join(achadas), "nome_oficial_sugerido": "", "observacao_negocio": "",
            })
    sem_par.sort(key=lambda r: (-r["enderecos"], r["municipio"], r["comunidade_nossa"]))
    resumo = []
    for mun in sorted({o["municipio"] for o in oficiais}):
        ls = [l for l in linhas if l["municipio"] == mun]
        cs = [c for c in comunidades if c["municipio"] == mun]
        cod = next(c["codigo_ibge"] for c in cs) if cs else None
        idx = [i for i, c in enumerate(cs)]
        com_par = {i for (k, i) in casadas if k == cod}
        end_tot = sum(c["enderecos"] for c in cs)
        end_par = sum(cs[i]["enderecos"] for i in com_par)
        casam = sum(1 for l in ls if l["casamento"] != regra.SEM_PAR)
        resumo.append({
            "municipio": mun, "localidades_ibge": len(ls), "nome_igual": sum(1 for l in ls if l["casamento"] == regra.IGUAL),
            "nome_parecido": sum(1 for l in ls if l["casamento"] == regra.PARECIDO), "sem_par": len(ls) - casam,
            "pct_localidades_com_par": round(100 * casam / len(ls)) if ls else 0, "comunidades_nossas": len(cs),
            "comunidades_com_par_no_ibge": len(com_par), "enderecos_total": end_tot, "enderecos_em_comunidades_com_par": end_par,
            "pct_enderecos_com_par": round(100 * end_par / end_tot) if end_tot else 0,
        })
        del idx
    return {"conferencia": linhas, "sem_nome_oficial": sem_par, "resumo": resumo}


def _gravar(nome: str, linhas: list[dict]) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    with open(SAIDA / nome, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig: o Excel abre com acento
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=";")
        w.writeheader()
        w.writerows(linhas)


def executar() -> int:
    oficiais, comunidades = banco.todas(), banco.comunidades()
    if not oficiais:
        print("Sem localidades oficiais no banco: rode antes  uv run python -m comunidades.localidades_oficiais")
        return 1
    r = conferir(oficiais, comunidades)
    _gravar("conferencia_localidades.csv", r["conferencia"])
    _gravar("comunidades_sem_nome_oficial.csv", r["sem_nome_oficial"])
    _gravar("resumo_por_municipio.csv", r["resumo"])
    c = r["conferencia"]
    igual, parecido = sum(1 for l in c if l["casamento"] == regra.IGUAL), sum(1 for l in c if l["casamento"] == regra.PARECIDO)
    longe = sum(1 for l in c if "longe do território" in l["atencao"])
    print(f"{len(c)} localidades oficiais x {len(comunidades)} comunidades nossas")
    print(f"  nome igual: {igual} | nome parecido: {parecido} | sem par: {len(c) - igual - parecido}")
    print(f"  casadas por nome com o ponto longe do território (conferir): {longe}")
    print(f"  comunidades nossas sem nome oficial: {len(r['sem_nome_oficial'])}")
    print(f"Planilhas em {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(executar())
