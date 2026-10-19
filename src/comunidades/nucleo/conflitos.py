"""Conflito de data de desligamento: outro aviso da empresa, não cancelado, com horário que se sobrepõe ao do novo e
que atinge o mesmo município ou as mesmas comunidades. Puro (recebe os avisos já lidos do histórico).

Dois níveis: "comunidade" (alguma comunidade em comum: o mesmo aviso de rádio falaria da mesma gente duas vezes ou em
horários que se atropelam) e "município" (só o município em comum: vale conferir, mas pode ser outra parte da cidade).
Data e horário vêm como texto do formulário ('20/11' e '8h às 14h'); sem horário legível, a comparação é pelo dia todo.
"""

import re
from datetime import datetime, time, timedelta

from .painel import data_do_desligamento
from .prazo import BRASILIA

MAX_CONFLITOS = 20


def janela(data_texto: str, horario_texto: str, referencia: datetime) -> tuple[datetime, datetime] | None:
    """(começo, fim) do desligamento no horário de Brasília; None se a data não for dd/mm. Sem horário: o dia todo.
    `referencia`: quando o aviso foi gerado (decide o ano da data)."""
    d = data_do_desligamento(str(data_texto or ""), referencia.astimezone(BRASILIA))
    if d is None:
        return None
    horas = re.findall(r"(\d{1,2})\s*h\s*(\d{2})?", str(horario_texto or ""))
    if len(horas) >= 2 and all(int(h) <= 23 for h, _ in horas[:2]):
        (h1, m1), (h2, m2) = horas[:2]
        comeco = datetime.combine(d, time(int(h1), int(m1 or 0)), BRASILIA)
        fim = datetime.combine(d, time(int(h2), int(m2 or 0)), BRASILIA)
        return comeco, fim if fim > comeco else fim + timedelta(days=1)
    comeco = datetime.combine(d, time(0), BRASILIA)
    return comeco, comeco + timedelta(days=1)


def _comunidades(municipio: dict) -> set[str]:
    return {f"{c.get('nome')}|{c.get('distrito') or ''}" for c in municipio.get("comunidades", [])}


def achar(novo: dict, existentes: list[dict], agora: datetime) -> list[dict]:
    """Os avisos de `existentes` em conflito com `novo`.

    novo: {data, horario, municipios: [{codigo_ibge, nome, comunidades: [{nome, distrito}]}]};
    existentes: as linhas do histórico (data, horario, criado_em, status, codigo, id, municipios).
    Cada conflito: id, codigo, data, horario, nivel ('comunidade' ou 'municipio') e, por município em comum, o nome e as
    comunidades em comum. Os de nível 'comunidade' vêm primeiro; depois, o horário mais próximo."""
    meu = janela(novo["data"], novo["horario"], agora)
    if meu is None:
        return []
    meus = {m["codigo_ibge"]: m for m in novo["municipios"]}
    achados = []
    for a in existentes:
        if a.get("status") == "cancelado":
            continue
        j = janela(a["data"], a["horario"], a["criado_em"])
        if j is None or not (meu[0] < j[1] and j[0] < meu[1]):
            continue
        em_comum = []
        for m in a.get("municipios") or []:
            if m.get("codigo_ibge") not in meus:
                continue
            nomes = sorted(c.split("|")[0] for c in _comunidades(m) & _comunidades(meus[m["codigo_ibge"]]))
            em_comum.append({"codigo_ibge": m["codigo_ibge"], "nome": m.get("nome"), "comunidades": nomes})
        if not em_comum:
            continue
        achados.append({"id": a["id"], "codigo": a.get("codigo"), "data": a["data"], "horario": a["horario"],
                        "nivel": "comunidade" if any(m["comunidades"] for m in em_comum) else "municipio",
                        "municipios": em_comum, "_ordem": abs((j[0] - meu[0]).total_seconds())})
    achados.sort(key=lambda x: (x["nivel"] != "comunidade", x["_ordem"]))
    for x in achados:
        del x["_ordem"]
    return achados[:MAX_CONFLITOS]
