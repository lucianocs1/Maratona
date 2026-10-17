"""Agrupamento das UCs da planilha por transformador e por circuito (alimentador). Puro.

Só os códigos da rede (texto curto da planilha, já limpo pelo tradutor) e contagens: nada de UC,
coordenada ou nome. Serve para a pessoa conferir se o desligamento bate com a parte da rede que vai
ser desligada (um circuito inteiro, alguns transformadores).
"""

from collections import Counter

LIMITE = 30


def por_codigo(codigos: list, limite: int = LIMITE) -> dict:
    """{"grupos": [{"codigo", "ucs"}...] (os maiores primeiro), "total": quantos códigos, "sem_codigo": UCs sem código}."""
    c = Counter(str(x) for x in codigos if x)
    sem = sum(1 for x in codigos if not x)
    grupos = [{"codigo": k, "ucs": n} for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:limite]]
    return {"grupos": grupos, "total": len(c), "sem_codigo": sem}
