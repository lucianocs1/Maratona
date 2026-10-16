"""Custo do aviso no ar: a rádio cobra por inserção (spot) de 30 segundos, não por segundo.

Puro (sem rede, banco ou arquivos). Um aviso de 100 segundos ocupa 4 spots de 30 s; um de 20 s, 1 spot.
O preço do spot NÃO é um dado deste projeto: vem da configuração da distribuidora (distribuidoras/*.toml,
seção [radio]) como valor de referência, a confirmar com a emissora, e a tela deixa o operador mudá-lo.
O histórico guarda só os segundos (de onde saem os spots); o valor em reais nunca é gravado.
"""

import math
from dataclasses import dataclass

SPOT_SEGUNDOS = 30


@dataclass(frozen=True)
class TabelaRadio:
    spot_segundos: int = SPOT_SEGUNDOS
    preco_spot: float = 0.0       # reais por spot (referência a confirmar com a emissora)
    veiculacoes: int = 1          # quantas vezes o aviso vai ao ar
    fonte: str = ""               # de onde vem o preço de referência

    def para_tela(self) -> dict:
        return {"spot_segundos": self.spot_segundos, "preco_spot": self.preco_spot,
                "veiculacoes": self.veiculacoes, "fonte": self.fonte}


def spots(segundos: float, spot_segundos: int = SPOT_SEGUNDOS) -> int:
    """Quantos spots o texto ocupa: 0 se não há tempo, senão o inteiro de cima (a rádio cobra o spot inteiro)."""
    return math.ceil(segundos / spot_segundos) if segundos and segundos > 0 else 0


def custo(segundos: float, preco_spot: float, veiculacoes: int = 1, spot_segundos: int = SPOT_SEGUNDOS) -> float:
    """Reais para levar o aviso ao ar, nas veiculações indicadas."""
    return round(spots(segundos, spot_segundos) * preco_spot * veiculacoes, 2)
