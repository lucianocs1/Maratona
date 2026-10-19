"""Une, no banco, as comunidades de mesmo nome do mesmo município que o IBGE cortou em distritos diferentes.

Antes (18/10/2026), o mesmo nome em dois distritos virava duas comunidades, "Cagado (Aracati de Minas)" e "Cagado (Cataguases)",
e o aviso citava a comunidade duas vezes. Agora é uma só ("Cagado"), sem limite de distância: o distrito mostrado é o do
pedaço com mais endereços, a contagem é a soma e os endereços de referência passam ao nome único. Só renomeia e soma:
depois de rodar, refaça o desenho com `uv run python -m comunidades.territorio_concessao` e reinicie a API.
O base_concessao já grava assim (fontes/base_territorial.py não separa mais os homônimos).

Uso: uv run python -m comunidades.unificar_homonimos [--so cod1,cod2]
"""

import sys

from .banco.conexao import conectar


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
