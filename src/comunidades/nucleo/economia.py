"""Custo do envio à rádio e economia. Puro, em centavos (Decimal), e nunca inventa número.

- Por minuto no ar: custo = segundos do aviso do Norte x valor por minuto / 60. Se há o aviso de hoje
  (fazenda a fazenda, da coluna local da planilha), a economia é CALCULADA:
  (segundos do aviso de hoje - segundos do aviso do Norte) x valor por minuto / 60.
  Sem o aviso de hoje, só se a pessoa informar quanto custaria do jeito antigo (economia INFORMADA).
- Valor fechado pelo aviso: custo = o valor; economia só se a pessoa informar o custo antigo (INFORMADA).
- O tempo de ar economizado (segundos) aparece sempre que há o aviso de hoje.
- A economia pode sair negativa (o aviso do Norte mais longo): mostra como é, sem esconder.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

COBRANCAS = {"fechado": "valor fechado pelo aviso", "minuto": "por minuto no ar"}
MAX_VALOR = Decimal("100000")
CENTAVO = Decimal("0.01")


def reais(v) -> Decimal | None:
    """'1.234,56', '1234.56', 1234.5 -> Decimal('1234.56'); None se vazio. ValueError se inválido."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        raise ValueError("valor inválido")
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("valor inválido") from None
    if not d.is_finite() or d < 0 or d > MAX_VALOR:
        raise ValueError(f"valor fora da faixa (de 0 a R$ {MAX_VALOR:,.2f})".replace(",", "."))
    return d.quantize(CENTAVO, ROUND_HALF_UP)


def calcular(cobranca: str, valor: Decimal, segundos_farol: int, segundos_hoje: int | None = None,
             custo_antigo: Decimal | None = None) -> dict:
    """Custo, economia (calculada ou informada, ou nenhuma) e o tempo de ar economizado."""
    if cobranca not in COBRANCAS:
        raise ValueError("forma de cobrança inválida")
    tempo = (segundos_hoje - segundos_farol) if segundos_hoje is not None else None
    if cobranca == "minuto":
        custo = (valor * segundos_farol / 60).quantize(CENTAVO, ROUND_HALF_UP)
        if segundos_hoje is not None:
            eco, tipo = ((segundos_hoje - segundos_farol) * valor / 60).quantize(CENTAVO, ROUND_HALF_UP), "calculada"
        elif custo_antigo is not None:
            eco, tipo = (custo_antigo - custo).quantize(CENTAVO, ROUND_HALF_UP), "informada"
        else:
            eco, tipo = None, None
    else:
        custo = valor
        eco, tipo = ((custo_antigo - valor).quantize(CENTAVO, ROUND_HALF_UP), "informada") if custo_antigo is not None else (None, None)
    return {"custo": custo, "economia": eco, "economia_tipo": tipo, "tempo_economizado": tempo}
