"""Simulador de economia com rádio (Relatórios). Puro, em Decimal, e nunca inventa número.

- Redução do tempo no ar: a média real da empresa, dos avisos do período cuja planilha trouxe a coluna local
  (aviso de hoje, fazenda a fazenda): (soma dos segundos do aviso de hoje - soma dos segundos do aviso do Norte)
  / soma dos segundos do aviso de hoje. Sem esses avisos, a medição de validação (44 s -> 14 s, 68,2%), com o
  rótulo "medição de validação".
- Economia mensal = gasto mensal com rádio x parte cobrada por tempo x redução; anual = mensal x 12. Para o
  gasto mínimo e o máximo (a faixa), no cenário da empresa e no conservador (50% cobrado por tempo).
- Já economizado de fato: economia calculada + informada dos envios registrados no período.
O gasto e a parte cobrada por tempo vêm da configuração da empresa (só o Admin da empresa altera).
"""

from decimal import ROUND_HALF_UP, Decimal

from .relatorio import filtrar
from .relatorios import FORMULAS, _d, brl

CENTAVO = Decimal("0.01")
VALIDACAO = {"segundos_hoje": 44, "segundos_farol": 14}   # README: duração média do aviso no rádio, 44 s -> 14 s
CONSERVADOR = Decimal("50")
PCT_PADRAO = Decimal("100")
MAX_GASTO = Decimal("1000000000")


def pct(v) -> str:
    """Decimal('68.18') -> '68,2%'; 100 -> '100%'."""
    s = f"{Decimal(str(v)).quantize(Decimal('0.1'), ROUND_HALF_UP)}".replace(".", ",")
    return f"{s[:-2] if s.endswith(',0') else s}%"


def reducao(avisos: list[dict]) -> dict:
    """A redução do tempo no ar dos avisos (ativos) com o aviso de hoje; sem eles, a medição de validação."""
    hoje = farol = n = 0
    com_hoje = set()
    for a in avisos:
        if a.get("status") == "cancelado":
            continue
        for m in a["municipios"] or []:
            if not m.get("hoje"):
                continue
            seg = m.get("segundos_mensagem") if m.get("segundos_mensagem") is not None else m.get("segundos")
            hoje += int(m["hoje"]["segundos"])
            farol += int(seg or 0)
            n += 1
            com_hoje.add(a.get("id"))
    fonte = "empresa" if n and hoje > 0 else "validacao"
    if fonte == "validacao":
        hoje, farol, n, com_hoje = VALIDACAO["segundos_hoje"], VALIDACAO["segundos_farol"], 0, set()
    return {"fonte": fonte, "segundos_hoje": hoje, "segundos_farol": farol, "municipios": n, "avisos": len(com_hoje),
            "reducao": Decimal(hoje - farol) / Decimal(hoje)}


def economia(gasto: Decimal, pct_tempo: Decimal, red: Decimal) -> dict:
    """Economia mensal e anual (centavos) de um gasto mensal, com a parte cobrada por tempo (0 a 100) e a redução (fração)."""
    mensal = Decimal(gasto) * Decimal(pct_tempo) / 100 * red
    return {"mensal": mensal.quantize(CENTAVO, ROUND_HALF_UP), "anual": (mensal * 12).quantize(CENTAVO, ROUND_HALF_UP)}


def economizado(envios: list[dict]) -> dict:
    calc = sum((_d(e["economia"]) for e in envios if e.get("economia_tipo") == "calculada"), Decimal("0"))
    inf = sum((_d(e["economia"]) for e in envios if e.get("economia_tipo") == "informada"), Decimal("0"))
    return {"calculada": calc, "informada": inf, "total": calc + inf, "envios": len(envios)}


def fonte_texto(r: dict) -> str:
    """De onde vem a redução, em texto curto: "média real de 87 avisos da empresa" ou "medição de validação (Leopoldina)"."""
    if r["fonte"] != "empresa":
        return "medição de validação (Leopoldina)"
    return "média real de 1 aviso da empresa" if r["avisos"] == 1 else f"média real de {r['avisos']} avisos da empresa"


def cenarios(valores: dict, red: Decimal) -> list[dict]:
    """[{faixa, cenario, pct, gasto, mensal, anual}] para o mínimo e o máximo (se houver), nos dois cenários."""
    faixas = [("mínimo", valores.get("gasto_min")), ("máximo", valores.get("gasto_max"))]
    pct_emp = Decimal(str(valores.get("pct_tempo") if valores.get("pct_tempo") is not None else PCT_PADRAO))
    saida = []
    for faixa, gasto in faixas:
        if gasto is None:
            continue
        for cenario, p in (("da empresa", pct_emp), ("conservador", CONSERVADOR)):
            saida.append({"faixa": faixa, "cenario": cenario, "pct": p, "gasto": Decimal(str(gasto)), **economia(Decimal(str(gasto)), p, red)})
    return saida


def documento(valores: dict, avisos: list[dict], envios: list[dict], filtros: dict) -> dict:
    """O documento do simulador (o mesmo na tela, no PDF e no CSV). valores: gasto_min, gasto_max, pct_tempo e nota (origem dos valores)."""
    av, en = filtrar(avisos, envios, filtros or {})
    r = reducao(av)
    red, ja = r["reducao"], economizado(en)
    cs = cenarios(valores, red)
    pct_emp = Decimal(str(valores.get("pct_tempo") if valores.get("pct_tempo") is not None else PCT_PADRAO))
    gmin, gmax = valores.get("gasto_min"), valores.get("gasto_max")
    faixa = ("não informado" if gmin is None else brl(gmin) if gmax is None or Decimal(str(gmax)) == Decimal(str(gmin))
             else f"{brl(gmin)} a {brl(gmax)}")
    da_empresa = [c for c in cs if c["cenario"] == "da empresa"]
    conservador = [c for c in cs if c["cenario"] == "conservador"]
    intervalo = lambda xs, k: "—" if not xs else brl(xs[0][k]) if len(xs) == 1 else f"{brl(xs[0][k])} a {brl(xs[-1][k])}"
    fonte = fonte_texto(r)
    resumo = [
        {"rotulo": "Redução do tempo no ar", "valor": pct(red * 100), "comparacoes": []},
        {"rotulo": "De onde vem a redução", "valor": fonte, "comparacoes": []},
        {"rotulo": "Gasto mensal com rádio", "valor": faixa, "comparacoes": []},
        *([{"rotulo": "Origem dos valores", "valor": valores["nota"], "comparacoes": []}] if valores.get("nota") else []),
        {"rotulo": "Parte do gasto cobrada por tempo", "valor": pct(pct_emp), "comparacoes": []},
        {"rotulo": "Economia mensal estimada", "valor": intervalo(da_empresa, "mensal"), "comparacoes": []},
        {"rotulo": "Economia anual estimada", "valor": intervalo(da_empresa, "anual"), "comparacoes": []},
        {"rotulo": "Economia anual no cenário conservador", "valor": intervalo(conservador, "anual"), "comparacoes": []},
        {"rotulo": "Já economizado (envios registrados)", "valor": brl(ja["total"]), "comparacoes": []},
    ]
    alertas = []
    if r["fonte"] == "validacao":
        alertas.append("Ainda não há avisos com o aviso de hoje no período: a redução usada é a da medição de validação (Leopoldina, 44 s -> 14 s).")
    if gmin is None:
        alertas.append("O gasto mensal com rádio ainda não foi informado: o Admin da empresa preenche no simulador.")
    secoes = [
        {"titulo": "Cenários", "tipo": "tabela", "colunas": ["Faixa", "Cenário", "Gasto mensal", "Cobrado por tempo", "Economia mensal", "Economia anual"],
         "linhas": [[c["faixa"], c["cenario"], brl(c["gasto"]), pct(c["pct"]), brl(c["mensal"]), brl(c["anual"])] for c in cs]},
        {"titulo": "Já economizado de fato", "tipo": "texto",
         "texto": f"{brl(ja['calculada'])} calculada + {brl(ja['informada'])} informada = {brl(ja['total'])}, em {ja['envios']} envio(s) do período."},
        {"titulo": "Tempo no ar usado na redução", "tipo": "texto",
         "texto": f"Aviso tradicional: {r['segundos_hoje']} s; aviso do Norte: {r['segundos_farol']} s."},
    ]
    contas = [f"Conta ({c['faixa']}, {c['cenario']}): {brl(c['gasto'])} x {pct(c['pct'])} x {pct(red * 100)} = {brl(c['mensal'])} por mês; "
              f"x 12 = {brl(c['anual'])} por ano." for c in cs]
    par = lambda xs, k: [str(xs[0][k]), str(xs[-1][k])] if xs else None
    numeros = {   # para os cartões da tela (a View escolhe o formato curto); dinheiro em texto, sem arredondar de novo
        "reducao_pct": str((red * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)), "fonte": r["fonte"], "fonte_texto": fonte, "avisos": r["avisos"],
        "gasto_min": None if gmin is None else str(gmin), "gasto_max": None if gmax is None else str(gmax), "pct_tempo": str(pct_emp),
        "nota": valores.get("nota") or None,
        "estimativa": None if not cs else {"mensal": par(da_empresa, "mensal"), "anual": par(da_empresa, "anual"),
                                           "conservador_anual": par(conservador, "anual")},
        "realizado": {k: str(v) if isinstance(v, Decimal) else v for k, v in ja.items()},
    }
    return {"tipo": "simulador", "titulo": "Simulador de economia com rádio", "resumo": resumo, "alertas": alertas, "secoes": secoes,
            "reducao": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in r.items()}, "numeros": numeros,
            "como_calculamos": [
                "Redução = (segundos do aviso tradicional estimado - segundos do aviso do Norte) / segundos do aviso tradicional, somando os "
                "avisos do período cuja planilha trouxe a coluna local (o aviso de hoje, fazenda a fazenda).",
                "Sem esses avisos no período, vale a medição de validação (Leopoldina): 44 s -> 14 s, redução de 68,2%.",
                "Economia mensal = gasto mensal com rádio x parte do gasto cobrada por tempo x redução. Economia anual = economia mensal x 12.",
                "Cenário conservador: só 50% do gasto é cobrado por tempo (o resto não muda com o tamanho do aviso).",
                *contas,
                "Já economizado = economia calculada + economia informada dos envios registrados no período (envio de aviso cancelado também conta).",
                FORMULAS["economia"],
                "É uma simulação: o gasto mensal e a parte cobrada por tempo são informados pelo Admin da empresa; a redução vem dos avisos.",
            ]}
