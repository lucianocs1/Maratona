"""Referências para os testes JS × Python: avisos e janelas por chave, gerados pelo Python.

O navegador tem de reproduzir estes arquivos exatamente (mesmo texto, mesmas notas).
avisos.json: avisos pt-BR (Norte e aviso de hoje) e o aviso nos 3 idiomas, em 2 datas e horários.
janelas.json: 3 sugestões por chave, em 2 datas e 3 durações, com a nota do início às 8h.
tamanho_hoje.json: locais, palavras e segundos do aviso de hoje por chave, nas 2 datas e horários,
contados no texto montado (e conferidos com a conta pelos códigos de local, que o mapa usa no modo área).

Uso: py -m uv run python -m comunidades.validacao.referencias [pasta]
(padrão: saida/referencias_passo12; com FAROL_DISTRIBUIDORA, a saída do outro município)
"""

import json
import sys
from datetime import date
from pathlib import Path

from .. import config as C
from .. import distribuidora as dist_
from ..nucleo import idiomas
from ..nucleo.desligamento import (aviso_antigo, aviso_novo, codigos_locais, duracao_s, locais_antigos,
                                   simular, tamanho_aviso_antigo)
from ..nucleo.impacto import nota_dano, sugerir_janelas
from .avaliacao import avaliar

PASTA = C.SAIDA / "referencias_passo12"
# (dia, mês, início, fim) em minutos: o horário padrão do aviso e um com meia hora
DATAS_AVISO = ((12, 11, 8 * 60, 14 * 60), (5, 3, 8 * 60 + 30, 13 * 60 + 15))
DATAS_JANELA = (date(2026, 11, 12), date(2026, 11, 15))   # quinta-feira e domingo
DURACOES_MIN = (120, 240, 360)
INICIO_PADRAO = 8 * 60


def contagem_atividades(ucs, atividades: list) -> dict:
    return ucs["ATIVIDADE"].value_counts().reindex(atividades, fill_value=0).astype(int).to_dict()


def janelas_de(cod: str, cont: dict, perfis: dict, exp) -> list:
    linhas = []
    for d in DATAS_JANELA:
        for dur in DURACOES_MIN:
            sug = sugerir_janelas(cont, d, dur, perfis, exp)
            linhas.append([cod, d.isoformat(), dur, [[j["inicio"], j["nota"], j["explicacao"]] for j in sug],
                           nota_dano(cont, d, INICIO_PADRAO, dur, perfis)])
    return linhas


def avisos_idiomas_de(cod: str, resumo, dist) -> list:
    linhas = []
    for idioma in idiomas.IDIOMAS:
        for dia, mes, ini, fim in DATAS_AVISO:
            texto = aviso_novo(resumo, idiomas.formatar_data(dia, mes, idioma),
                               idiomas.formatar_horario(ini, fim, idioma), dist.regras, idioma)
            linhas.append([cod, idioma, dia, mes, ini, fim, idiomas.com_telefone(texto, dist.telefone, idioma)])
    return linhas


def tamanho_hoje_de(cod: str, ucs, codigos: list[int], palavras: list[int], regras) -> list:
    """Tamanho do aviso de hoje contado no texto, nas 2 datas e horários. Para se a conta pelos
    códigos de local (codigos: um por UC de ucs, do cadastro inteiro) der outro resultado."""
    linhas = []
    for dia, mes, ini, fim in DATAS_AVISO:
        data, horario = idiomas.formatar_data(dia, mes, "pt-BR"), idiomas.formatar_horario(ini, fim, "pt-BR")
        texto = aviso_antigo(ucs, data, horario, regras)
        pelo_texto = (len(locais_antigos(ucs)), len(texto.split()), round(duracao_s(texto)))
        pelos_codigos = tamanho_aviso_antigo(codigos, palavras, data, horario, regras)
        if pelo_texto != pelos_codigos:
            raise SystemExit(f"Tamanho do aviso de hoje diferente em {cod} ({data}): texto {pelo_texto}, códigos {pelos_codigos}")
        linhas.append([cod, dia, mes, ini, fim, *pelo_texto])
    return linhas


def gerar(dist=None) -> dict:
    dist = dist or dist_.carregar()
    atividades = list(dist.perfis)
    df, _, _, cen = avaliar(dist)
    codigos, palavras = codigos_locais(df)
    local = dict(zip(df.index, codigos))
    pt, outros, janelas, tamanhos = {}, [], [], []
    for cod in cen["CHAVE"]:
        d = simular(df, cod, dist.regras)
        pt[cod] = {"novo": d.aviso_novo, "antigo": d.aviso_antigo}
        outros += avisos_idiomas_de(cod, d.comunidades, dist)
        janelas += janelas_de(cod, contagem_atividades(d.ucs, atividades), dist.perfis, dist.expediente)
        tamanhos += tamanho_hoje_de(cod, d.ucs, [local[i] for i in d.ucs.index], palavras, dist.regras)
    return {"avisos": {"avisos_pt": pt, "avisos_idiomas": outros}, "janelas": janelas, "tamanho_hoje": tamanhos}


def gravar(pasta: Path, nome: str, dados) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / nome
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return arq


if __name__ == "__main__":
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else PASTA
    r = gerar()
    for nome, chave in (("avisos.json", "avisos"), ("janelas.json", "janelas"), ("tamanho_hoje.json", "tamanho_hoje")):
        print(f"Gravado: {gravar(pasta, nome, r[chave])}")
