"""Une, no banco, as comunidades de mesmo nome do mesmo município que o IBGE cortou em distritos diferentes.

Antes (18/10/2026), o mesmo nome em dois distritos virava duas comunidades, "Cagado (Aracati de Minas)" e "Cagado (Cataguases)",
e o aviso citava a comunidade duas vezes. Agora é uma só ("Cagado"), sem limite de distância: o distrito mostrado é o do
pedaço com mais endereços, a contagem é a soma e os endereços de referência passam ao nome único. Só renomeia e soma:
depois de rodar, refaça o desenho com `uv run python -m comunidades.territorio_concessao` e reinicie a API.
O base_concessao já grava assim (fontes/base_territorial.py não separa mais os homônimos).

Também une a comunidade que é o começo do nome da sede do distrito ("Aracati" e "Aracati de Minas"; eh_sede_do_curto).

Uso: uv run python -m comunidades.unificar_homonimos [--so cod1,cod2]
"""

import re
import sys
import unicodedata

from .banco.conexao import conectar


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()).strip()


def eh_sede_do_curto(longo: str, curto: str, distrito: str, municipio: str) -> bool:
    """O nome longo é o da "sede" e o curto é o começo dele ("Aracati" e "Aracati de Minas"): vale quando o longo é o
    nome do próprio distrito ou o curto mais "de/do/da" e o distrito ou o município. Só isso: "Antônio" e "Antônio
    Garoni", "Barra" e "Barra dos Couto" ou "Jardim" e "Jardim Bandeirantes" são lugares diferentes e ficam separados."""
    nl, nc = _norm(longo), _norm(curto)
    if not nl.startswith(nc + " "):
        return False
    alvos = {_norm(distrito), _norm(municipio)}
    resto = nl[len(nc) + 1:]
    return nl in alvos or any(resto == f"{p} {x}" for x in alvos for p in ("de", "do", "da"))


def _base(nome: str, distrito: str) -> str:
    """O nome sem o sufixo " (distrito)" que o homônimo ganhava (só esse sufixo exato)."""
    sufixo = f" ({distrito})"
    return nome[:-len(sufixo)] if distrito and nome.endswith(sufixo) else nome


def unificar(cur, cod: str) -> tuple[int, int]:
    """(grupos unidos, comunidades que sumiram) do município."""
    cur.execute("SELECT nome, distrito, enderecos FROM comunidade WHERE codigo_ibge = %s", (cod,))
    grupos: dict[str, list[tuple[str, str, int]]] = {}
    for nome, dist, n in cur.fetchall():
        grupos.setdefault(_base(nome, dist), []).append((nome, dist, n))
    unidos = sumiram = 0
    for base, itens in grupos.items():
        if len(itens) < 2:
            continue
        itens.sort(key=lambda x: -x[2])
        ganha, perdem = itens[0], itens[1:]
        total = sum(x[2] for x in itens)
        nomes = [x[0] for x in itens]
        cur.execute("UPDATE endereco_referencia SET comunidade = %s WHERE codigo_ibge = %s AND comunidade = ANY(%s)", (base, cod, nomes))
        cur.execute("DELETE FROM comunidade WHERE codigo_ibge = %s AND nome = ANY(%s)", (cod, [x[0] for x in perdem]))
        cur.execute("UPDATE comunidade SET nome = %s, enderecos = %s WHERE codigo_ibge = %s AND nome = %s", (base, total, cod, ganha[0]))
        cur.execute("UPDATE municipio SET comunidades = (SELECT count(*) FROM comunidade WHERE codigo_ibge = %s) WHERE codigo_ibge = %s", (cod, cod))
        unidos += 1
        sumiram += len(perdem)
    # sede e seu começo ("Aracati" + "Aracati de Minas"), no mesmo distrito: uma só, com o nome mais completo
    cur.execute("SELECT nome FROM municipio WHERE codigo_ibge = %s", (cod,))
    nome_mun = cur.fetchone()[0]
    cur.execute("SELECT nome, distrito, enderecos FROM comunidade WHERE codigo_ibge = %s", (cod,))
    todas = cur.fetchall()
    for longo, dist_l, n_l in todas:
        for curto, dist_c, n_c in todas:
            if curto == longo or dist_c != dist_l or not eh_sede_do_curto(longo, curto, dist_l or "", nome_mun):
                continue
            cur.execute("SELECT 1 FROM comunidade WHERE codigo_ibge = %s AND nome = %s", (cod, curto))
            if not cur.fetchone():
                continue   # já absorvida numa volta anterior
            cur.execute("UPDATE endereco_referencia SET comunidade = %s WHERE codigo_ibge = %s AND comunidade = %s", (longo, cod, curto))
            cur.execute("DELETE FROM comunidade WHERE codigo_ibge = %s AND nome = %s", (cod, curto))
            cur.execute("UPDATE comunidade SET enderecos = enderecos + %s WHERE codigo_ibge = %s AND nome = %s", (n_c, cod, longo))
            unidos += 1
            sumiram += 1
    cur.execute("UPDATE municipio SET comunidades = (SELECT count(*) FROM comunidade WHERE codigo_ibge = %s) WHERE codigo_ibge = %s", (cod, cod))
    return unidos, sumiram


def main(argv: list[str]) -> int:
    so = set(argv[argv.index("--so") + 1].split(",")) if "--so" in argv else None
    with conectar() as c, c.cursor() as cur:   # tudo numa transação: ou une todos ou nenhum
        cur.execute("SELECT codigo_ibge, nome FROM municipio ORDER BY codigo_ibge")
        alvos = [(a, b) for a, b in cur.fetchall() if so is None or a in so]
        tg = ts = 0
        for cod, nome in alvos:
            g, s = unificar(cur, cod)
            if g:
                print(f"{cod} {nome}: {g} grupos unidos ({s} comunidades a menos)")
            tg, ts = tg + g, ts + s
        cur.execute("SELECT count(*) FROM comunidade")
        print(f"Total: {tg} grupos unidos, {ts} comunidades a menos; restam {cur.fetchone()[0]}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
