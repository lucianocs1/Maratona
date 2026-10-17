"""Dashboard da empresa: números do histórico de avisos (só o que o histórico já guarda, só agregados).

Regra pura: recebe os avisos (como o banco os devolve) e a data de hoje; não lê arquivo nem banco.
A data do desligamento é guardada como o aviso a fala ("20/11"); o ano sai da data em que o aviso
foi gerado (um "05/01" gerado em dezembro é do ano seguinte).
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from .custo import SPOT_SEGUNDOS, spots

TOP = 8            # municípios e comunidades que mais aparecem
MESES = 12         # avisos por mês: os últimos 12 meses
PROXIMOS = 8       # próximos desligamentos listados


def data_do_desligamento(texto: str, gerado_em: datetime) -> date | None:
    """'20/11' -> a data, com o ano de quando o aviso foi gerado (ou o seguinte); None se não for dd/mm."""
    try:
        dia, mes = (int(x) for x in texto.strip().split("/")[:2])
        d = date(gerado_em.year, mes, dia)
    except (ValueError, TypeError):
        return None
    return d if d >= gerado_em.date() - timedelta(days=31) else date(gerado_em.year + 1, mes, dia)


def _meses(hoje: date) -> list[str]:
    ano, mes, saida = hoje.year, hoje.month, []
    for _ in range(MESES):
        saida.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    return saida[::-1]


def resumir(avisos: list[dict], hoje: date, spot_segundos: int = SPOT_SEGUNDOS) -> dict:
    """Totais, avisos por mês, municípios e comunidades que mais aparecem, próximos desligamentos e
    o número de avisos por município (para o mapa). No comparativo, os spots de rádio (a rádio cobra por
    inserção de spot_segundos) são somados município a município: cada aviso ocupa spots inteiros."""
    ucs = segundos_soma = segundos_n = finais = cartoes = com_vital = recentes = 0
    comp = {"municipios": 0, "segundos_hoje": 0, "segundos_farol": 0, "palavras_hoje": 0, "palavras_farol": 0,
            "locais": 0, "comunidades": 0, "spots_hoje": 0, "spots_farol": 0}
    comunidades, mun = set(), {}
    mun_avisos, mun_ucs = Counter(), Counter()
    com_vezes, com_ucs, com_mun = Counter(), Counter(), {}
    por_mes = defaultdict(lambda: {"avisos": 0, "ucs": 0})
    proximos = []
    for a in avisos:
        criado = a["criado_em"]
        ms = a["municipios"] or []
        ucs_aviso = sum(int(m.get("ucs", 0)) for m in ms)
        ucs += ucs_aviso
        if criado.date() >= hoje - timedelta(days=30):
            recentes += 1
        chave_mes = f"{criado.year:04d}-{criado.month:02d}"
        por_mes[chave_mes]["avisos"] += 1
        por_mes[chave_mes]["ucs"] += ucs_aviso
        if any(int((m.get("equipamento_vital") or {}).get("sim", 0)) for m in ms):
            com_vital += 1
        for m in ms:
            cod = m["codigo_ibge"]
            mun[cod] = {"codigo_ibge": cod, "nome": m["nome"], "uf": m["uf"]}
            mun_avisos[cod] += 1
            mun_ucs[cod] += int(m.get("ucs", 0))
            cartoes += 1
            finais += bool(m.get("texto_final"))
            # o tempo no ar do que vai à rádio: a mensagem pelo modelo da empresa, se houver; senão o aviso do algoritmo
            seg_farol = m.get("segundos_mensagem") if m.get("segundos_mensagem") is not None else m.get("segundos")
            texto_farol = m.get("mensagem") or m.get("aviso", "")
            if seg_farol is not None:
                segundos_soma += float(seg_farol)
                segundos_n += 1
            if m.get("hoje"):   # o comparativo: só os municípios cuja planilha trouxe a coluna local
                comp["municipios"] += 1
                comp["segundos_hoje"] += int(m["hoje"]["segundos"])
                comp["segundos_farol"] += int(seg_farol or 0)
                comp["spots_hoje"] += spots(int(m["hoje"]["segundos"]), spot_segundos)
                comp["spots_farol"] += spots(int(seg_farol or 0), spot_segundos)
                comp["palavras_hoje"] += int(m["hoje"]["palavras"])
                comp["palavras_farol"] += len(str(texto_farol).split())
                comp["locais"] += int(m["hoje"]["locais"])
                comp["comunidades"] += len(m.get("comunidades", []))
            for c in m.get("comunidades", []):
                k = (cod, c["nome"])
                comunidades.add(k)
                com_vezes[k] += 1
                com_ucs[k] += int(c.get("afetadas", 0))
                com_mun[k] = m["nome"]
        d = data_do_desligamento(a["data"], criado)
        if d and d >= hoje:
            proximos.append({"id": a["id"], "data": d.isoformat(), "horario": a["horario"],
                             "municipios": [m["nome"] for m in ms], "ucs": ucs_aviso})
    proximos.sort(key=lambda p: (p["data"], p["id"]))
    ordem_mun = sorted(mun_avisos, key=lambda c: (-mun_avisos[c], -mun_ucs[c], mun[c]["nome"]))
    ordem_com = sorted(com_vezes, key=lambda k: (-com_vezes[k], -com_ucs[k], k[1]))
    return {
        "totais": {"avisos": len(avisos), "ultimos_30_dias": recentes, "ucs": ucs, "comunidades": len(comunidades),
                   "municipios": len(mun), "com_equipamento_vital": com_vital,
                   "segundos_medio": round(segundos_soma / segundos_n) if segundos_n else 0,
                   "textos_finais": finais, "avisos_municipio": cartoes},
        "por_mes": [{"mes": k, **por_mes.get(k, {"avisos": 0, "ucs": 0})} for k in _meses(hoje)],
        "municipios": [{**mun[c], "avisos": mun_avisos[c], "ucs": mun_ucs[c]} for c in ordem_mun[:TOP]],
        "comunidades": [{"nome": k[1], "municipio": com_mun[k], "avisos": com_vezes[k], "ucs": com_ucs[k]} for k in ordem_com[:TOP]],
        "proximos": proximos[:PROXIMOS],
        "por_municipio": {c: mun_avisos[c] for c in ordem_mun},
        "comparativo": comp,
    }
