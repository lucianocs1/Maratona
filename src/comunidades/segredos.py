"""Segredos do Norte (endereço do banco, chaves, SMTP): só em variável de ambiente.

Ordem: a variável de ambiente; se não houver, a linha NOME=valor do arquivo .env na raiz do projeto
(ignorado pelo git; FAROL_ENV escolhe outro, ex.: .env.producao). Nenhum segredo fica no código.
"""

import os

from . import config as C

ARQ_ENV = C.RAIZ / (os.environ.get("FAROL_ENV") or ".env")


def segredo(nome: str) -> str | None:
    if os.environ.get(nome):
        return os.environ[nome]
    if ARQ_ENV.exists():
        for linha in ARQ_ENV.read_text(encoding="utf-8").splitlines():
            n, _, valor = linha.strip().partition("=")
            if n.strip() == nome and valor.strip():
                return valor.strip().strip('"').strip("'")
    return None
