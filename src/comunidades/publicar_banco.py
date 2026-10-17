"""Leva a base pública do banco local para o banco de produção (Neon, Render ou outro Postgres com PostGIS).

Copia só dados públicos, já prontos no banco local (base_concessao.py e rede_concessao.py): municípios,
comunidades, endereços de referência do CNEFE e a rede elétrica FICTÍCIA. Nada de usuário, sessão,
registro ou aviso: o acesso de produção nasce da semente (comunidades.semente), com senhas novas.
Substitui o que o destino já tiver dessas tabelas, numa transação só, e confere as contagens.

A conexão do destino vem de FAROL_DESTINO_URL ou da linha DATABASE_URL do arquivo .env.producao na raiz
(ignorado pelo git). Nunca no código nem na linha de comando.
Uso: uv run python -m comunidades.publicar_banco
"""

import os
import sys
import time

import psycopg

from . import config as C
from .banco import base_territorial, clientes, localidades, municipios_ibge, rede
from .banco.conexao import conectar

ARQ = C.RAIZ / ".env.producao"
TABELAS = ("municipio", "comunidade", "endereco_referencia",
           "rede_subestacao", "rede_trecho", "rede_chave", "rede_trafo",   # na ordem das chaves estrangeiras
           "cliente_ficticio",   # um cliente fictício por endereço (clientes_concessao.py): ~600 mil linhas
           "localidade_oficial",   # localidades oficiais do IBGE (localidades_oficiais.py): ~480 linhas
           "municipio_ibge")   # os municípios do Brasil (malha do IBGE), para a área de atuação das empresas


def destino() -> str:
    if os.environ.get("FAROL_DESTINO_URL"):
        return os.environ["FAROL_DESTINO_URL"]
    if ARQ.exists():
        for linha in ARQ.read_text(encoding="utf-8").splitlines():
            nome, _, valor = linha.strip().partition("=")
            if nome.strip() == "DATABASE_URL" and valor.strip():
                return valor.strip().strip('"').strip("'")
    raise SystemExit(f"Defina FAROL_DESTINO_URL ou crie {ARQ.name} com DATABASE_URL=... (a conexão do banco de produção).")


def _colunas(cur, tabela: str) -> list[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s"
                " ORDER BY ordinal_position", (tabela,))
    return [r[0] for r in cur.fetchall()]


def publicar() -> int:
    url = destino()
    t0 = time.time()
    with conectar() as origem, psycopg.connect(url) as dst:
        with dst.cursor() as cur:
            cur.execute("SELECT current_database(), version()")
            banco, versao = cur.fetchone()
            print(f"Destino: banco {banco} ({versao.split(',')[0]})", flush=True)
            cur.execute(base_territorial.ESQUEMA)   # inclui CREATE EXTENSION postgis
            cur.execute(rede.ESQUEMA)
            cur.execute(clientes.ESQUEMA)
            cur.execute(localidades.ESQUEMA)
            cur.execute(municipios_ibge.ESQUEMA)
            cur.execute("TRUNCATE " + ", ".join(TABELAS))
        for t in TABELAS:
            with origem.cursor() as co, dst.cursor() as cd:
                cols = ", ".join(_colunas(co, t))
                with co.copy(f"COPY {t} ({cols}) TO STDOUT") as saida, cd.copy(f"COPY {t} ({cols}) FROM STDIN") as entrada:
                    for bloco in saida:
                        entrada.write(bloco)
                co.execute(f"SELECT count(*) FROM {t}")
                n_origem = co.fetchone()[0]
                cd.execute(f"SELECT count(*) FROM {t}")
                n_destino = cd.fetchone()[0]
            print(f"  {t}: {n_destino:,} linhas".replace(",", "."), flush=True)
            if n_origem != n_destino:
                raise SystemExit(f"{t}: {n_origem} na origem e {n_destino} no destino; nada foi gravado.")
        dst.commit()
    with psycopg.connect(url, autocommit=True) as dst:
        dst.execute("ANALYZE")
        tam = dst.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    print(f"Pronto em {time.time() - t0:.0f} s. Tamanho do banco de produção: {tam}.")
    return 0


if __name__ == "__main__":
    sys.exit(publicar())
