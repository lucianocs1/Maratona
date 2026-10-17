"""Relatórios da empresa: o mensal (ou de um período), o comprovante de um aviso e a auditoria. Puro.

Recebe os avisos e os envios como o banco os devolve (só agregados: municípios, comunidades, contagens,
valores dos envios) e devolve números e listas. Nada de UC, coordenada ou nome de cliente; as pessoas
que aparecem são as do login (quem pediu, quem enviou). Os números saem só do que está gravado:
economia "calculada" (pelo tempo no ar do aviso de hoje) e "informada" (custo antigo digitado) ficam
separadas, e o que não dá para saber fica de fora, nunca estimado.
"""

import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal

from . import prazo as P
from .tipos_desligamento import ROTULOS
from .travas import celula_segura

TOP_COMUNIDADES = 15
COMO_CALCULADO = [
    "Custo: o valor informado no envio. Por minuto no ar: valor por minuto x segundos da mensagem do Norte / 60; "
    "valor fechado: o próprio valor.",
    "Economia calculada: só com cobrança por minuto e com o aviso de hoje (fazenda a fazenda, da coluna local da planilha): "
    "(segundos do aviso de hoje - segundos da mensagem do Norte) x valor por minuto / 60.",
    "Economia informada: quando a pessoa que enviou digitou quanto custaria o aviso do jeito antigo: custo antigo - custo.",
    "Sem o aviso de hoje e sem o custo antigo, não há economia: o relatório não estima.",
    "Tempo economizado: segundos do aviso de hoje - segundos da mensagem do Norte, quando há o aviso de hoje.",
    "No prazo: o primeiro envio à rádio saiu pelo menos 72 horas antes do início (5 dias úteis com equipamento vital; "
    "feriados não entram). Aviso sem envio registrado fica fora dessa conta.",
]
MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
            "novembro", "dezembro"]


def _d(v) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal("0")


def rotulo_periodo(inicio: date, fim: date) -> str:
    if inicio.day == 1 and (fim.month != inicio.month or fim.day >= 28) and inicio.month == fim.month:
        return f"{MESES_PT[inicio.month - 1]} de {inicio.year}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def filtrar(avisos: list[dict], envios: list[dict], f: dict) -> tuple[list[dict], list[dict]]:
    """Filtros: municipio (código IBGE), tipo, radio (id), pessoa (nome de quem pediu)."""
    def aviso_ok(a):
        return ((not f.get("municipio") or any(m["codigo_ibge"] == f["municipio"] for m in a["municipios"]))
                and (not f.get("tipo") or a.get("tipo") == f["tipo"]) and (not f.get("pessoa") or a.get("usuario") == f["pessoa"]))
    av = [a for a in avisos if aviso_ok(a)]
    ids = {a["id"] for a in av}
    en = [e for e in envios if e["aviso_id"] in ids and (not f.get("municipio") or e["municipio"] == f["municipio"])
          and (not f.get("radio") or str(e["radio_id"]) == str(f["radio"]))]
    if f.get("radio"):   # só os avisos que foram para a rádio escolhida
        com_radio = {e["aviso_id"] for e in en}
        av = [a for a in av if a["id"] in com_radio]
    return av, en


def _vital(a: dict) -> int:
    return sum(int(m.get("equipamento_vital", {}).get("sim", 0)) for m in a["municipios"])


def _prazo_do_aviso(a: dict, envios_do_aviso: list[dict], horas: int, dias_uteis: int) -> dict:
    comeco = P.inicio(a["data"], a["horario"], a["criado_em"])
    primeiro = min((e["criado_em"] for e in envios_do_aviso), default=None)
    vital = _vital(a) > 0
    return {**P.situacao(comeco, primeiro, vital, horas, dias_uteis), "inicio": comeco, "avisado_em": primeiro,
            "regra": P.regra(vital, horas, dias_uteis)}


def mensal(avisos: list[dict], envios: list[dict], inicio: date, fim: date, filtros: dict | None = None,
           horas: int = 72, dias_uteis: int = 5) -> dict:
    """O relatório do período: resumo, por tipo, por rádio, por comunidade, fora do prazo, sem envio e a lista."""
    av, en = filtrar(avisos, envios, filtros or {})
    ativos = [a for a in av if a.get("status") != "cancelado"]
    por_aviso = defaultdict(list)
    for e in en:
        por_aviso[e["aviso_id"]].append(e)
    prazos = {a["id"]: _prazo_do_aviso(a, por_aviso[a["id"]], horas, dias_uteis) for a in ativos}
    no_prazo = sum(1 for p in prazos.values() if p["no_prazo"] is True)
    com_envio = sum(1 for p in prazos.values() if p["no_prazo"] is not None)
    comunidades = Counter()
    ucs_com = Counter()
    for a in ativos:
        for m in a["municipios"]:
            for c in m["comunidades"]:
                chave = (c["nome"], c.get("distrito") or "", m["nome"])
                comunidades[chave] += 1
                ucs_com[chave] += int(c.get("afetadas", 0))
    calc = sum((_d(e["economia"]) for e in en if e.get("economia_tipo") == "calculada"), Decimal("0"))
    inf = sum((_d(e["economia"]) for e in en if e.get("economia_tipo") == "informada"), Decimal("0"))
    resumo = {
        "desligamentos": len(ativos), "cancelados": len(av) - len(ativos),
        "avisos": sum(len(a["municipios"]) for a in ativos),
        "comunidades": len(comunidades), "ucs": sum(int(m.get("ucs", 0)) for a in ativos for m in a["municipios"]),
        "equipamento_vital": sum(_vital(a) for a in ativos),
        "envios": len(en), "confirmados": sum(1 for e in en if e["status"] == "confirmado"),
        "falharam": sum(1 for e in en if e["status"] == "falhou"),
        "segundos_no_ar": sum(int(e["segundos"]) for e in en),
        "custo": f"{sum((_d(e['custo']) for e in en), Decimal('0')):.2f}",
        "economia_calculada": f"{calc:.2f}", "economia_informada": f"{inf:.2f}",
        "tempo_economizado": sum(int(e["tempo_economizado"]) for e in en if e.get("tempo_economizado") is not None),
        "no_prazo": no_prazo, "com_envio": com_envio,
        "pct_no_prazo": round(100 * no_prazo / com_envio, 1) if com_envio else None,
    }
    tipos = defaultdict(lambda: {"desligamentos": 0, "ucs": 0})
    for a in ativos:
        t = tipos[a.get("tipo") or "sem_tipo"]
        t["desligamentos"] += 1
        t["ucs"] += sum(int(m.get("ucs", 0)) for m in a["municipios"])
    radios = defaultdict(lambda: {"envios": 0, "confirmados": 0, "custo": Decimal("0"), "economia": Decimal("0"), "segundos": 0})
    for e in en:
        r = radios[e["radio_nome"]]
        r["envios"] += 1
        r["confirmados"] += e["status"] == "confirmado"
        r["custo"] += _d(e["custo"])
        r["economia"] += _d(e["economia"])
        r["segundos"] += int(e["segundos"])
    fora = [{"aviso": a["id"], "data": a["data"], "horario": a["horario"], "municipios": ", ".join(m["nome"] for m in a["municipios"]),
             "regra": prazos[a["id"]]["regra"], "atraso_horas": prazos[a["id"]]["atraso_horas"],
             "avisado_em": prazos[a["id"]]["avisado_em"].isoformat() if prazos[a["id"]]["avisado_em"] else None}
            for a in ativos if prazos[a["id"]]["no_prazo"] is False]
    sem_envio = [{"aviso": a["id"], "data": a["data"], "municipios": ", ".join(m["nome"] for m in a["municipios"])}
                 for a in ativos if prazos[a["id"]]["no_prazo"] is None]
    lista = []
    for a in sorted(av, key=lambda x: x["criado_em"]):
        es = por_aviso[a["id"]]
        lista.append({"aviso": a["id"], "criado_em": a["criado_em"].isoformat(), "data": a["data"], "horario": a["horario"],
                      "tipo": ROTULOS.get(a.get("tipo"), "—"), "municipios": ", ".join(m["nome"] for m in a["municipios"]),
                      "comunidades": sum(len(m["comunidades"]) for m in a["municipios"]), "ucs": sum(int(m.get("ucs", 0)) for m in a["municipios"]),
                      "equipamento_vital": _vital(a), "status": a.get("status") or "gerado", "por": a.get("usuario") or "—",
                      "codigo": a.get("codigo"), "radios": ", ".join(sorted({e["radio_nome"] for e in es})) or "—",
                      "envios": len(es), "confirmados": sum(1 for e in es if e["status"] == "confirmado"),
                      "custo": f"{sum((_d(e['custo']) for e in es), Decimal('0')):.2f}",
                      "no_prazo": prazos.get(a["id"], {}).get("no_prazo")})
    return {
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "rotulo": rotulo_periodo(inicio, fim)},
        "filtros": {k: v for k, v in (filtros or {}).items() if v},
        "resumo": resumo,
        "por_tipo": [{"tipo": k, "rotulo": ROTULOS.get(k, "sem tipo"), **v} for k, v in sorted(tipos.items(), key=lambda kv: -kv[1]["desligamentos"])],
        "por_radio": [{"radio": k, "envios": v["envios"], "confirmados": v["confirmados"], "custo": f"{v['custo']:.2f}",
                       "economia": f"{v['economia']:.2f}", "segundos": v["segundos"]}
                      for k, v in sorted(radios.items(), key=lambda kv: (-kv[1]["envios"], kv[0]))],
        "por_comunidade": [{"comunidade": n, "distrito": d, "municipio": mu, "avisos": comunidades[(n, d, mu)], "ucs": ucs_com[(n, d, mu)]}
                           for (n, d, mu) in sorted(comunidades, key=lambda k: (-comunidades[k], -ucs_com[k], k))[:TOP_COMUNIDADES]],
        "fora_do_prazo": fora, "sem_envio": sem_envio, "lista": lista, "como_calculado": COMO_CALCULADO,
    }


COMPARAVEIS = ("desligamentos", "avisos", "ucs", "envios", "confirmados", "segundos_no_ar", "custo", "economia_calculada",
               "economia_informada", "tempo_economizado", "pct_no_prazo")


def comparar(atual: dict, anterior: dict) -> dict:
    """Diferença dos números do resumo para o período anterior (None quando um dos lados não tem o número)."""
    saida = {}
    for k in COMPARAVEIS:
        a, b = atual["resumo"].get(k), anterior["resumo"].get(k)
        if a is None or b is None:
            saida[k] = {"atual": a, "anterior": b, "diferenca": None}
        else:
            dif = Decimal(str(a)) - Decimal(str(b))
            saida[k] = {"atual": a, "anterior": b, "diferenca": f"{dif:.2f}" if isinstance(a, str) else float(dif) if k == "pct_no_prazo" else int(dif)}
    return saida


def comprovante(a: dict, envios: list[dict], horas: int = 72, dias_uteis: int = 5) -> dict:
    """Um aviso (um desligamento): quem pediu, quando, tipo, municípios, comunidades, contagens, envios e o prazo."""
    p = _prazo_do_aviso(a, envios, horas, dias_uteis)
    return {
        "aviso": a["id"], "codigo": a.get("codigo"), "status": a.get("status") or "gerado", "por": a.get("usuario"),
        "perfil": a.get("usuario_perfil"), "criado_em": a["criado_em"].isoformat(), "data": a["data"], "horario": a["horario"],
        "tipo": ROTULOS.get(a.get("tipo"), "—"), "motivo": a.get("motivo") or "",
        "municipios": [{"nome": f"{m['nome']}/{m['uf']}", "ucs": m.get("ucs", 0), "equipamento_vital": m.get("equipamento_vital", {}).get("sim", 0),
                        "comunidades": [f"{c['nome'].split(' (')[0]} ({'Sede' if c.get('distrito') == m['nome'] else c.get('distrito')})"
                                        for c in m["comunidades"]]} for m in a["municipios"]],
        "ucs": sum(int(m.get("ucs", 0)) for m in a["municipios"]), "equipamento_vital": _vital(a),
        # o critério de quem foi desligado (nucleo/selecao.resumo), nunca as UCs; aviso de antes da escolha: None
        "escolha": (a.get("resumo") or {}).get("escolha"),
        "prazo": {"regra": p["regra"], "no_prazo": p["no_prazo"], "atraso_horas": p["atraso_horas"],
                  "limite": p["limite"].isoformat() if p["limite"] else None},
        "envios": [{"radio": e["radio_nome"], "canal": e["canal"], "status": e["status"], "quando": e["criado_em"].isoformat(),
                    "confirmado_em": e["confirmado_em"].isoformat() if e.get("confirmado_em") else None, "por": e.get("criado_por_nome"),
                    "valor": f"{_d(e['valor']):.2f}", "cobranca": e["cobranca"], "custo": f"{_d(e['custo']):.2f}",
                    "economia": f"{_d(e['economia']):.2f}" if e.get("economia") is not None else None, "economia_tipo": e.get("economia_tipo"),
                    "tempo_economizado": e.get("tempo_economizado")} for e in envios],
        "custo": f"{sum((_d(e['custo']) for e in envios), Decimal('0')):.2f}",
        "economia_calculada": f"{sum((_d(e['economia']) for e in envios if e.get('economia_tipo') == 'calculada'), Decimal('0')):.2f}",
        "economia_informada": f"{sum((_d(e['economia']) for e in envios if e.get('economia_tipo') == 'informada'), Decimal('0')):.2f}",
    }


# ---------- CSV (protegido contra fórmula) ----------
def _csv(linhas: list[list]) -> str:
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    for ln in linhas:
        w.writerow([celula_segura(v) for v in ln])
    return saida.getvalue()


def mensal_csv(rel: dict, gerado_por: str, codigo: str) -> str:
    r = rel["resumo"]
    linhas = [["relatorio", f"Relatório do período: {rel['periodo']['rotulo']}"], ["gerado_por", gerado_por], ["codigo_verificacao", codigo],
              ["filtros", ", ".join(f"{k}={v}" for k, v in rel["filtros"].items()) or "nenhum"], []]
    linhas += [["resumo", "valor"]] + [[k, "" if v is None else v] for k, v in r.items()] + [[]]
    linhas.append(["aviso", "gerado_em", "data", "horario", "tipo", "municipios", "comunidades", "ucs", "equipamento_vital", "situacao",
                   "pedido_por", "radios", "envios", "confirmados", "custo", "no_prazo", "codigo"])
    for x in rel["lista"]:
        linhas.append([x["aviso"], x["criado_em"], x["data"], x["horario"], x["tipo"], x["municipios"], x["comunidades"], x["ucs"],
                       x["equipamento_vital"], x["status"], x["por"], x["radios"], x["envios"], x["confirmados"], x["custo"],
                       "" if x["no_prazo"] is None else "sim" if x["no_prazo"] else "não", x["codigo"] or ""])
    return _csv(linhas)


def auditoria_csv(linhas: list[dict], titulo: str, gerado_por: str, codigo: str) -> str:
    saida = [["relatorio", titulo], ["gerado_por", gerado_por], ["codigo_verificacao", codigo], [],
             ["quando", "quem", "perfil", "empresa", "acao", "detalhe", "codigo"]]
    saida += [[x["quando"], x["usuario"] or "", x["perfil"] or "", x["empresa"] or "", x["acao"], x["detalhe"], x["codigo"] or ""] for x in linhas]
    return _csv(saida)


def periodo_do_mes(mes: str) -> tuple[date, date]:
    """'2026-10' -> (1/10/2026, 31/10/2026). ValueError se não for AAAA-MM."""
    ano, m = (int(x) for x in mes.split("-"))
    inicio = date(ano, m, 1)
    fim = date(ano + (m == 12), 1 if m == 12 else m + 1, 1)
    return inicio, date.fromordinal(fim.toordinal() - 1)


def mes_anterior(inicio: date) -> str:
    return f"{inicio.year - (inicio.month == 1):04d}-{12 if inicio.month == 1 else inicio.month - 1:02d}"


def dentro(momento: datetime, inicio: date, fim: date) -> bool:
    d = momento.astimezone(P.BRASILIA).date()
    return inicio <= d <= fim
