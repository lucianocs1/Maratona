"""Prazo do aviso (REN ANEEL 1.000/2021, art. 436): 72 horas antes, ou 5 dias úteis se há equipamento vital. Puro.

O momento do aviso é o primeiro envio à rádio registrado (e-mail, WhatsApp ou cópia): é quando a
comunidade passa a poder ser avisada. Sem envio registrado, o aviso não entra na conta do prazo
(aparece à parte, "sem envio"). Dias úteis: segunda a sexta (feriados não entram nesta versão).
"""

import re
from datetime import datetime, time, timedelta, timezone

from .painel import data_do_desligamento

BRASILIA = timezone(timedelta(hours=-3))


def inicio(data_texto: str, horario_texto: str, gerado_em: datetime) -> datetime | None:
    """O começo do desligamento ('20/11' e '8h às 14h' -> 20/11 às 8h, no horário de Brasília)."""
    d = data_do_desligamento(data_texto, gerado_em.astimezone(BRASILIA))
    m = re.match(r"\s*(\d{1,2})\s*h\s*(\d{2})?", str(horario_texto or ""))
    if d is None or not m or int(m.group(1)) > 23:
        return None
    return datetime.combine(d, time(int(m.group(1)), int(m.group(2) or 0)), BRASILIA)


def dias_uteis_antes(momento: datetime, n: int) -> datetime:
    """O momento n dias úteis antes (pula sábado e domingo)."""
    d = momento
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def limite(comeco: datetime, vital: bool, horas: int = 72, dias_uteis: int = 5) -> datetime:
    """Até quando o aviso tem de sair."""
    return dias_uteis_antes(comeco, dias_uteis) if vital else comeco - timedelta(hours=horas)


def situacao(comeco: datetime | None, avisado_em: datetime | None, vital: bool, horas: int = 72, dias_uteis: int = 5) -> dict:
    """no_prazo (True/False/None), o limite e quanto faltou (horas) quando saiu atrasado."""
    if comeco is None or avisado_em is None:
        return {"no_prazo": None, "limite": None, "atraso_horas": None}
    lim = limite(comeco, vital, horas, dias_uteis)
    atraso = (avisado_em - lim).total_seconds() / 3600
    return {"no_prazo": atraso <= 0, "limite": lim, "atraso_horas": round(max(atraso, 0), 1)}


def regra(vital: bool, horas: int = 72, dias_uteis: int = 5) -> str:
    return f"{dias_uteis} dias úteis (equipamento vital)" if vital else f"{horas} horas"
