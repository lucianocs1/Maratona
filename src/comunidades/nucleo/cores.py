"""Cor de cada comunidade no mapa: duas comunidades que se encostam nunca levam a mesma cor.

Puro (só geometrias). Coloração DSATUR (a próxima é sempre a que já vê mais cores em volta); em mapas de divisas, 4 a 6 cores bastam. A cor é só um número (índice da paleta da tela): não diz nada sobre a comunidade.
"""

import shapely
from shapely.strtree import STRtree

N_CORES = 8
FOLGA_M = 5   # duas comunidades a menos disto uma da outra contam como vizinhas (frestas do desenho)


def colorir(geometrias: list, folga_m: float = FOLGA_M, n_cores: int = N_CORES) -> list[int]:
    """Índice de cor (0 a n_cores-1) de cada geometria, na mesma ordem; geometrias em projeção métrica."""
    n = len(geometrias)
    arvore = STRtree(geometrias)
    vizinhas = [set() for _ in range(n)]
    for i, g in enumerate(geometrias):
        for j in arvore.query(shapely.buffer(g, folga_m), predicate="intersects"):
            if j != i:
                vizinhas[i].add(int(j))
                vizinhas[int(j)].add(i)
    # DSATUR: sempre a que já vê mais cores diferentes em volta (desempate: mais vizinhas)
    cor = [-1] * n
    for _ in range(n):
        i = max((k for k in range(n) if cor[k] < 0), key=lambda k: (len({cor[j] for j in vizinhas[k]} - {-1}), len(vizinhas[k])))
        usadas = {cor[j] for j in vizinhas[i]}
        livres = [c for c in range(n_cores) if c not in usadas]
        # sem cor livre (raro): a menos usada entre as vizinhas
        cor[i] = livres[0] if livres else min(range(n_cores), key=lambda c: sum(cor[j] == c for j in vizinhas[i]))
    return cor
