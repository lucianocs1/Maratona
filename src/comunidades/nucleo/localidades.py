"""Casar o nome de uma localidade oficial (IBGE) com as comunidades do app.

Puro: sem arquivo, sem banco, sem IBGE. Recebe nomes e devolve o veredito. O casamento é só por nome normalizado; quem
decide se o par vale é o negócio (o relatório de conferência mostra também a posição, porque nomes se repetem:
Bela Vista, Boa Vista, São Francisco existem em vários lugares do mesmo município).
"""

import difflib
import re
import unicodedata

CORTE_PARECIDO = 0.86   # parecença mínima (difflib) para "parecido"
# palavras que não distinguem uma localidade da outra ("Povoado Santa Rita" = "Santa Rita"); sao, santa e santo ficam
GENERICAS = {"povoado", "comunidade", "localidade", "vila", "bairro", "distrito", "de", "da", "do", "das", "dos", "rural",
             "sitio", "fazenda", "fazendinha"}

IGUAL, PARECIDO, SEM_PAR = "nome igual", "nome parecido", "sem par"


def sem_sufixo(nome: str) -> str:
    """O nome sem o distrito entre parênteses que o app põe nos homônimos: "Bela Vista (Sede)" -> "Bela Vista"."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", str(nome)).strip()


def normalizar(nome: str) -> str:
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(p for p in s.split() if p not in GENERICAS)


def casar(nome_oficial: str, nomes_das_comunidades: list[str]) -> tuple[str, int | None]:
    """(veredito, posição da comunidade na lista): nome igual, parecido ou sem par. O nome da comunidade pode trazer
    o distrito entre parênteses; ele é ignorado."""
    chave = normalizar(nome_oficial)
    if not chave:
        return SEM_PAR, None
    alvos = [normalizar(n) for n in nomes_das_comunidades]
    if chave in alvos:
        return IGUAL, alvos.index(chave)
    unicos = [a for a in dict.fromkeys(alvos) if a]
    perto = difflib.get_close_matches(chave, unicos, n=1, cutoff=CORTE_PARECIDO)
    return (PARECIDO, alvos.index(perto[0])) if perto else (SEM_PAR, None)
