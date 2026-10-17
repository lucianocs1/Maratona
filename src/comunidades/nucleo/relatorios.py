"""Os relatórios completos (Fase H) como "documentos": dados prontos para virar PDF, CSV e tela. Puro.

Um documento é um dicionário:
  {"tipo", "titulo", "subtitulo", "resumo": [{"rotulo", "valor", "comparacoes": [{"contra", "texto"}]}],
   "alertas": [texto], "secoes": [seção], "como_calculamos": [texto]}
e cada seção é {"titulo", "tipo": "tabela", "colunas", "linhas"} | {"titulo", "tipo": "texto", "texto"} |
{"titulo", "tipo": "lista", "itens"} | {"titulo", "tipo": "grafico", "rotulos", "valores", "projecao"?, "formato"}.

Recebe avisos e envios como o banco os devolve (só agregados: municípios, comunidades, contagens,
valores dos envios) e linhas da auditoria. Nada de UC, coordenada ou nome de cliente: as pessoas que
aparecem são as do login. Números só do que está gravado; o que não dá para saber fica de fora.
Regras de atribuição: cada desligamento e os seus envios contam no mês em que o aviso foi gerado.
"""

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from . import prazo as P
from .relatorio import MESES_PT, filtrar
from .tipos_desligamento import ROTULOS

CENTAVO = Decimal("0.01")
MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
CANAIS = {"email": "e-mail", "whatsapp": "WhatsApp", "copia": "cópia"}

FORMULAS = {
    "custo": "Custo de um envio: o valor informado. Por minuto no ar: valor por minuto x segundos da mensagem / 60; valor fechado: o próprio valor.",
    "economia": "Economia calculada: só com cobrança por minuto e com o aviso de hoje (fazenda a fazenda): (segundos do aviso de hoje - segundos da "
                "mensagem do Norte) x valor por minuto / 60. Economia informada: custo antigo digitado por quem enviou - custo. Sem um dos dois, "
                "não há economia (não estimamos).",
    "projecao": "Projeção do ano: gasto acumulado até o mês do relatório + média dos meses já fechados x meses que faltam até dezembro. "
                "Sem mês fechado, não há projeção.",
    "prazo": "No prazo: o primeiro envio à rádio saiu pelo menos 72 horas antes do início do desligamento (5 dias úteis quando há equipamento "
             "vital; feriados não entram). % no prazo = avisos no prazo / avisos com envio. Aviso sem envio fica fora da conta.",
    "frequencia": "Frequência: quantos desligamentos a comunidade teve no período; repetição = N ou mais desligamentos dentro de D dias "
                  "(configuração da empresa). Intervalo médio: média dos dias entre um desligamento e o seguinte.",
    "duracao": "Duração: fim - início do horário do aviso (\"8h às 14h\" = 6 h). Horas sem luz de uma comunidade: soma das durações dos "
               "desligamentos em que ela entrou (inteira ou em parte).",
    "comparacao": "Comparações: (atual - anterior) / anterior; seta para cima quando aumentou, para baixo quando diminuiu; sem o número "
                  "anterior (ou zero), não há porcentagem.",
    "atribuicao": "Cada desligamento, e os envios dele, contam no mês em que o aviso foi gerado.",
}


# ---------- formatos ----------
def brl(v) -> str:
    d = Decimal(str(v or 0)).quantize(CENTAVO, ROUND_HALF_UP)
    s = f"{abs(d):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{'-' if d < 0 else ''}R$ {s}"


def tempo(segundos) -> str:
    s = int(segundos or 0)
    sinal, s = ("-" if s < 0 else ""), abs(s)
    if s >= 3600:
        return f"{sinal}{s // 3600} h {s % 3600 // 60:02d} min"
    return f"{sinal}{s // 60} min {s % 60:02d} s" if s >= 60 else f"{sinal}{s} s"


def horas_txt(h) -> str:
    m = round(float(h or 0) * 60)
    return f"{m // 60} h" + (f" {m % 60:02d} min" if m % 60 else "")


def pct(n, d) -> float | None:
    return round(100 * n / d, 1) if d else None


def pct_txt(v) -> str:
    return "—" if v is None else f"{v:.1f}%".replace(".", ",")


def comparar(atual, anterior) -> str | None:
    """'↑ 12,5%', '↓ 3%', '= 0%' ou None (sem o anterior, ou anterior zero)."""
    if atual is None or anterior is None:
        return None
    a, b = Decimal(str(atual)), Decimal(str(anterior))
    if b == 0:
        return None
    v = (a - b) / b * 100
    seta = "↑" if v > 0 else "↓" if v < 0 else "="
    return f"{seta} {abs(v):.1f}%".replace(".", ",")


# ---------- contas ----------
_HORA = re.compile(r"(\d{1,2})\s*h\s*(\d{2})?")


def duracao_horas(horario: str) -> float | None:
    """'8h às 14h' -> 6.0; '8h30 às 12h' -> 3.5; None se não houver início e fim."""
    hs = _HORA.findall(str(horario or ""))
    if len(hs) < 2:
        return None
    ini = int(hs[0][0]) + int(hs[0][1] or 0) / 60
    fim = int(hs[1][0]) + int(hs[1][1] or 0) / 60
    return round(fim - ini, 2) if fim > ini else None


def projecao(por_mes: list, mes_ref: int, mes_fechado: bool) -> dict:
    """por_mes: 12 valores (jan..dez). Meses fechados: 1..mes_ref se o mês do relatório já acabou, senão 1..mes_ref-1."""
    valores = [Decimal(str(v or 0)) for v in por_mes]
    acumulado = sum(valores[:mes_ref], Decimal("0"))
    fechados = mes_ref if mes_fechado else mes_ref - 1
    restantes = 12 - mes_ref
    if fechados <= 0:
        return {"acumulado": acumulado, "media": None, "restantes": restantes, "projecao": None,
                "conta": f"acumulado {brl(acumulado)}; sem mês fechado, não há projeção"}
    media = (sum(valores[:fechados], Decimal("0")) / fechados).quantize(CENTAVO, ROUND_HALF_UP)
    proj = (acumulado + media * restantes).quantize(CENTAVO, ROUND_HALF_UP)
    return {"acumulado": acumulado, "media": media, "restantes": restantes, "projecao": proj,
            "conta": f"{brl(acumulado)} (acumulado) + {brl(media)} (média de {fechados} mês(es) fechado(s)) x {restantes} = {brl(proj)}"}


def orcamento(projecao_valor, acumulado, orcamento_valor) -> dict:
    if not orcamento_valor:
        return {"usado": None, "alerta": None}
    o = Decimal(str(orcamento_valor))
    usado = pct(Decimal(str(acumulado)), o)
    alerta = (f"A projeção do ano ({brl(projecao_valor)}) passa do orçamento ({brl(o)})."
              if projecao_valor is not None and Decimal(str(projecao_valor)) > o else None)
    return {"usado": usado, "alerta": alerta}


def mes_do(momento: datetime) -> int:
    return momento.astimezone(P.BRASILIA).month


def _d(v) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal("0")


def _vital(a: dict) -> int:
    return sum(int(m.get("equipamento_vital", {}).get("sim", 0)) for m in a["municipios"])


def _ucs(a: dict) -> int:
    return sum(int(m.get("ucs", 0)) for m in a["municipios"])


def _envios_por_aviso(envios):
    por = defaultdict(list)
    for e in envios:
        por[e["aviso_id"]].append(e)
    return por


def _prazo(a, envs, horas_legais, dias_vital):
    comeco = P.inicio(a["data"], a["horario"], a["criado_em"])
    primeiro = min((e["criado_em"] for e in envs), default=None)
    vital = _vital(a) > 0
    return {**P.situacao(comeco, primeiro, vital, horas_legais, dias_vital), "inicio": comeco, "avisado_em": primeiro,
            "regra": P.regra(vital, horas_legais, dias_vital), "vital": vital}


def nome_comunidade(c: dict, m: dict) -> str:
    distrito = "Sede" if c.get("distrito") == m["nome"] else c.get("distrito") or "?"
    return f"{str(c['nome']).split(' (')[0]} ({distrito})"


def _no_periodo(avisos, inicio: date, fim: date):
    return [a for a in avisos if inicio <= a["criado_em"].astimezone(P.BRASILIA).date() <= fim]


# ---------- números de um período (servem às comparações) ----------
def numeros(avisos, envios, inicio, fim, filtros, horas_legais=72, dias_vital=5) -> dict:
    av, en = filtrar(_no_periodo(avisos, inicio, fim), envios, filtros or {})
    ativos = [a for a in av if a.get("status") != "cancelado"]
    ids = {a["id"] for a in av}           # envio de aviso cancelado também conta: a rádio foi paga
    en = [e for e in en if e["aviso_id"] in ids]
    por = _envios_por_aviso(en)
    prazos = [_prazo(a, por[a["id"]], horas_legais, dias_vital) for a in ativos]
    com_envio = [p for p in prazos if p["no_prazo"] is not None]
    comunidades = {(m["codigo_ibge"], c["nome"], c.get("distrito")) for a in ativos for m in a["municipios"] for c in m["comunidades"]}
    return {
        "desligamentos": len(ativos), "cancelados": len(av) - len(ativos), "avisos": sum(len(a["municipios"]) for a in ativos),
        "pedidos": len(en), "por_canal": dict(Counter(e["canal"] for e in en)), "confirmados": sum(1 for e in en if e["status"] == "confirmado"),
        "comunidades": len(comunidades), "ucs": sum(_ucs(a) for a in ativos), "vital": sum(_vital(a) for a in ativos),
        "horas": round(sum(duracao_horas(a["horario"]) or 0 for a in ativos), 2), "segundos_no_ar": sum(int(e["segundos"]) for e in en),
        "gasto": sum((_d(e["custo"]) for e in en), Decimal("0")),
        "economia_calculada": sum((_d(e["economia"]) for e in en if e.get("economia_tipo") == "calculada"), Decimal("0")),
        "economia_informada": sum((_d(e["economia"]) for e in en if e.get("economia_tipo") == "informada"), Decimal("0")),
        "no_prazo": sum(1 for p in com_envio if p["no_prazo"]), "com_envio": len(com_envio),
        "pct_no_prazo": pct(sum(1 for p in com_envio if p["no_prazo"]), len(com_envio)),
        "pct_confirmados": pct(sum(1 for e in en if e["status"] == "confirmado"), len(en)),
        "_ativos": ativos, "_envios": en, "_prazos": dict(zip([a["id"] for a in ativos], prazos)), "_todos": av,
    }


def _item(rotulo, valor, atual=None, anterior=None, ano_anterior=None):
    comps = []
    for contra, ref in (("mês anterior", anterior), ("mesmo mês do ano anterior", ano_anterior)):
        t = comparar(atual, ref)
        if t:
            comps.append({"contra": contra, "texto": t})
    return {"rotulo": rotulo, "valor": valor, "comparacoes": comps}


def _gasto_por_mes(avisos_ano, envios_ano, ano, filtros):
    por_mes = [Decimal("0")] * 12
    av, en = filtrar([a for a in avisos_ano if a["criado_em"].astimezone(P.BRASILIA).year == ano],
                     envios_ano, filtros or {})
    ids = {a["id"]: a for a in av}
    for e in en:
        if e["aviso_id"] in ids:
            por_mes[mes_do(ids[e["aviso_id"]]["criado_em"]) - 1] += _d(e["custo"])
    return por_mes, av, [e for e in en if e["aviso_id"] in ids]


# ---------- H1: relatório mensal (diretoria) ----------
def mensal(avisos_ano, envios_ano, avisos_comp, envios_comp, registros, inicio: date, fim: date, filtros: dict, hoje: date,
           horas_legais=72, dias_vital=5, fechado: bool = True) -> dict:
    """avisos_ano/envios_ano: do 1º de janeiro até o fim do período; avisos_comp/envios_comp: o mês anterior e o mesmo mês do ano anterior."""
    n = numeros(avisos_ano, envios_ano, inicio, fim, filtros, horas_legais, dias_vital)
    ini_ant = (inicio.replace(day=1) - timedelta(days=1)).replace(day=1)
    fim_ant = inicio.replace(day=1) - timedelta(days=1)
    ant = numeros(avisos_comp + avisos_ano, envios_comp + envios_ano, ini_ant, fim_ant, filtros, horas_legais, dias_vital)
    try:
        ini_aa, fim_aa = inicio.replace(year=inicio.year - 1), fim.replace(year=fim.year - 1)
    except ValueError:
        ini_aa, fim_aa = inicio.replace(year=inicio.year - 1, day=28), fim.replace(year=fim.year - 1, day=28)
    aa = numeros(avisos_comp, envios_comp, ini_aa, fim_aa, filtros, horas_legais, dias_vital)
    tem = lambda x: x["desligamentos"] + x["cancelados"] > 0
    mes_unico = inicio.day == 1 and (inicio.year, inicio.month) == (fim.year, fim.month)   # comparar só quando o período é um mês
    ant_ok, aa_ok = tem(ant) and mes_unico, tem(aa) and mes_unico
    g = lambda x, k: x[k] if x is not None else None
    A, AA = (ant if ant_ok else None), (aa if aa_ok else None)
    por_mes, av_ano, en_ano = _gasto_por_mes(avisos_ano, envios_ano, fim.year, filtros)
    proj = projecao(por_mes, fim.month, fechado)
    eco_ano_c = sum((_d(e["economia"]) for e in en_ano if e.get("economia_tipo") == "calculada"), Decimal("0"))
    eco_ano_i = sum((_d(e["economia"]) for e in en_ano if e.get("economia_tipo") == "informada"), Decimal("0"))
    canais = " · ".join(f"{CANAIS[k]} {v}" for k, v in sorted(n["por_canal"].items())) or "nenhum"
    resumo = [
        _item("Desligamentos programados", str(n["desligamentos"]), n["desligamentos"], g(A, "desligamentos"), g(AA, "desligamentos")),
        _item("Avisos gerados (por município)", str(n["avisos"]), n["avisos"], g(A, "avisos"), g(AA, "avisos")),
        _item("Pedidos às rádios", f"{n['pedidos']} ({canais})", n["pedidos"], g(A, "pedidos"), g(AA, "pedidos")),
        _item("Confirmados pela rádio", pct_txt(n["pct_confirmados"]), n["pct_confirmados"], g(A, "pct_confirmados"), g(AA, "pct_confirmados")),
        _item("Comunidades avisadas", str(n["comunidades"]), n["comunidades"], g(A, "comunidades"), g(AA, "comunidades")),
        _item("UCs afetadas", str(n["ucs"]), n["ucs"], g(A, "ucs"), g(AA, "ucs")),
        _item("UCs com equipamento vital (contagem)", str(n["vital"]), n["vital"], g(A, "vital"), g(AA, "vital")),
        _item("Horas de desligamento", horas_txt(n["horas"]), n["horas"], g(A, "horas"), g(AA, "horas")),
        _item("Tempo no ar", tempo(n["segundos_no_ar"]), n["segundos_no_ar"], g(A, "segundos_no_ar"), g(AA, "segundos_no_ar")),
        _item("Gasto do mês", brl(n["gasto"]), n["gasto"], g(A, "gasto"), g(AA, "gasto")),
        _item("Gasto acumulado no ano", brl(proj["acumulado"])),
        _item("Projeção do ano", brl(proj["projecao"]) if proj["projecao"] is not None else "sem mês fechado"),
        _item("Economia do mês (calculada / informada)", f"{brl(n['economia_calculada'])} / {brl(n['economia_informada'])}",
              n["economia_calculada"] + n["economia_informada"], (g(A, "economia_calculada") or 0) + (g(A, "economia_informada") or 0) if A else None,
              (g(AA, "economia_calculada") or 0) + (g(AA, "economia_informada") or 0) if AA else None),
        _item("Economia acumulada no ano (calculada / informada)", f"{brl(eco_ano_c)} / {brl(eco_ano_i)}"),
        _item("Avisos no prazo", f"{pct_txt(n['pct_no_prazo'])} ({n['no_prazo']} de {n['com_envio']} com envio)",
              n["pct_no_prazo"], g(A, "pct_no_prazo"), g(AA, "pct_no_prazo")),
    ]
    ativos, en, prazos = n["_ativos"], n["_envios"], n["_prazos"]
    por_aviso = _envios_por_aviso(en)
    custo_aviso = {a["id"]: sum((_d(e["custo"]) for e in por_aviso[a["id"]]), Decimal("0")) for a in ativos}
    # gráficos
    semanas = Counter(min(5, (a["criado_em"].astimezone(P.BRASILIA).day - 1) // 7 + 1) for a in ativos)
    tipos = Counter(ROTULOS.get(a.get("tipo"), "sem tipo") for a in ativos)
    graficos = [
        {"titulo": f"Gasto mês a mês em {fim.year} (projeção até dezembro)", "tipo": "grafico", "formato": "dinheiro",
         "rotulos": MESES_CURTOS, "valores": [float(v) if i < fim.month else None for i, v in enumerate(por_mes)],
         "projecao": [float(proj["media"]) if (proj["media"] is not None and i >= fim.month) else None for i in range(12)]},
        {"titulo": "Avisos por semana do mês", "tipo": "grafico", "formato": "numero",
         "rotulos": [f"semana {i}" for i in range(1, 6)], "valores": [semanas.get(i, 0) for i in range(1, 6)]},
        {"titulo": "Desligamentos por tipo", "tipo": "grafico", "formato": "numero", "rotulos": list(tipos), "valores": list(tipos.values())},
    ]
    # seções
    por_tipo = defaultdict(lambda: {"n": 0, "ucs": 0, "horas": 0.0, "custo": Decimal("0")})
    por_mun = defaultdict(lambda: {"n": 0, "ucs": 0, "horas": 0.0, "custo": Decimal("0")})
    for a in ativos:
        t = por_tipo[ROTULOS.get(a.get("tipo"), "sem tipo")]
        t["n"] += 1
        t["ucs"] += _ucs(a)
        t["horas"] += duracao_horas(a["horario"]) or 0
        t["custo"] += custo_aviso[a["id"]]
        for m in a["municipios"]:
            x = por_mun[f"{m['nome']}/{m['uf']}"]
            x["n"] += 1
            x["ucs"] += int(m.get("ucs", 0))
            x["horas"] += duracao_horas(a["horario"]) or 0
            x["custo"] += sum((_d(e["custo"]) for e in por_aviso[a["id"]] if e["municipio"] == m["codigo_ibge"]), Decimal("0"))
    radios = defaultdict(lambda: {"n": 0, "conf": 0, "seg": 0, "custo": Decimal("0"), "eco": Decimal("0")})
    for e in en:
        r = radios[e["radio_nome"]]
        r["n"] += 1
        r["conf"] += e["status"] == "confirmado"
        r["seg"] += int(e["segundos"])
        r["custo"] += _d(e["custo"])
        r["eco"] += _d(e["economia"])
    com = defaultdict(lambda: {"n": 0, "ucs": 0, "horas": 0.0, "mun": ""})
    for a in ativos:
        for m in a["municipios"]:
            for c in m["comunidades"]:
                k = nome_comunidade(c, m)
                x = com[(k, m["nome"])]
                x["n"] += 1
                x["ucs"] += int(c.get("afetadas", 0))
                x["horas"] += duracao_horas(a["horario"]) or 0
    top = sorted(com.items(), key=lambda kv: (-kv[1]["n"], -kv[1]["ucs"], kv[0]))[:10]
    fora = [a for a in ativos if prazos[a["id"]]["no_prazo"] is False]
    sem_envio = [a for a in ativos if prazos[a["id"]]["no_prazo"] is None]
    ids_periodo = {a["id"] for a in n["_todos"]}
    regs_aviso = lambda acao: [r for r in registros if r["acao"] == acao and _aviso_do_detalhe(r["detalhe"]) in ids_periodo]
    no_periodo = lambda r: inicio <= r["quando"].astimezone(P.BRASILIA).date() <= fim
    importadas = [a for a in n["_todos"]]
    bloqueios = [r for r in registros if r["acao"] == "geração bloqueada (equipamento vital)" and no_periodo(r)]
    justificativas = [r for r in registros if r["acao"] == "justificou rejeições acima do limite" and no_periodo(r)]
    pessoas = defaultdict(lambda: {"avisos": 0, "envios": 0})
    for a in ativos:
        pessoas[a.get("usuario") or "—"]["avisos"] += 1
    for e in en:
        pessoas[e.get("criado_por_nome") or "—"]["envios"] += 1
    secoes = graficos + [
        {"titulo": "Por tipo de desligamento", "tipo": "tabela", "colunas": ["Tipo", "Desligamentos", "UCs", "Horas", "Custo"],
         "linhas": [[k, v["n"], v["ucs"], horas_txt(v["horas"]), brl(v["custo"])] for k, v in sorted(por_tipo.items(), key=lambda kv: -kv[1]["n"])]},
        {"titulo": "Por município", "tipo": "tabela", "colunas": ["Município", "Desligamentos", "UCs", "Horas", "Custo"],
         "linhas": [[k, v["n"], v["ucs"], horas_txt(v["horas"]), brl(v["custo"])] for k, v in sorted(por_mun.items(), key=lambda kv: (-kv[1]["n"], kv[0]))]},
        {"titulo": "Resumo por rádio", "tipo": "tabela", "colunas": ["Rádio", "Pedidos", "Confirmados", "Tempo no ar", "Custo", "Economia"],
         "linhas": [[k, v["n"], f"{v['conf']} ({pct_txt(pct(v['conf'], v['n']))})", tempo(v["seg"]), brl(v["custo"]), brl(v["eco"])]
                    for k, v in sorted(radios.items(), key=lambda kv: -kv[1]["custo"])]},
        {"titulo": "Top 10 comunidades", "tipo": "tabela", "colunas": ["Comunidade", "Município", "Desligamentos", "UCs afetadas", "Horas"],
         "linhas": [[k[0], k[1], v["n"], v["ucs"], horas_txt(v["horas"])] for k, v in top]},
        {"titulo": "Prazos", "tipo": "tabela", "colunas": ["Aviso", "Desligamento", "Regra", "Situação", "Atraso"],
         "linhas": [[f"nº {a['id']}", f"{a['data']}, {a['horario']}", prazos[a["id"]]["regra"],
                     "sem envio" if prazos[a["id"]]["no_prazo"] is None else "no prazo" if prazos[a["id"]]["no_prazo"] else "fora do prazo",
                     f"{prazos[a['id']]['atraso_horas']} h" if prazos[a["id"]]["no_prazo"] is False else "—"] for a in fora + sem_envio]},
        {"titulo": "Qualidade das planilhas", "tipo": "tabela",
         "colunas": ["Aviso", "Linhas lidas", "Entraram", "Rejeitadas", "Corrigidas"],
         "linhas": [[f"nº {a['id']}", a["resumo"].get("linhas", "—"), a["resumo"].get("validas", "—"), a["resumo"].get("problemas", "—"),
                     a["resumo"].get("corrigidas", "—")] for a in importadas]},
        {"titulo": "Bloqueios por equipamento vital e justificativas", "tipo": "lista",
         "itens": [f"{r['quando'].astimezone(P.BRASILIA):%d/%m %H:%M} · {r['usuario'] or '—'}: bloqueio por equipamento vital" for r in bloqueios]
         + [f"{r['quando'].astimezone(P.BRASILIA):%d/%m %H:%M} · {r['usuario'] or '—'}: justificou ({r['detalhe']})" for r in justificativas]},
        {"titulo": "Ocorrências (cancelamentos e datas alteradas)", "tipo": "lista",
         "itens": [f"{r['quando'].astimezone(P.BRASILIA):%d/%m %H:%M} · {r['usuario'] or '—'} {r['acao']}: {r['detalhe']}"
                   for r in sorted(regs_aviso("cancelou o aviso") + regs_aviso("mudou a data do aviso"), key=lambda r: r["quando"])]},
        {"titulo": "Atividade por pessoa", "tipo": "tabela", "colunas": ["Pessoa", "Avisos", "Envios"],
         "linhas": [[k, v["avisos"], v["envios"]] for k, v in sorted(pessoas.items(), key=lambda kv: (-kv[1]["avisos"] - kv[1]["envios"], kv[0]))]},
        {"titulo": "Anexo: lista completa de avisos do mês", "tipo": "tabela",
         "colunas": ["Aviso", "Gerado", "Desligamento", "Tipo", "Municípios", "UCs", "Vital", "Envios", "Custo", "Pedido por", "Situação"],
         "linhas": [[f"nº {a['id']}", f"{a['criado_em'].astimezone(P.BRASILIA):%d/%m %H:%M}", f"{a['data']}, {a['horario']}",
                     ROTULOS.get(a.get("tipo"), "—"), ", ".join(m["nome"] for m in a["municipios"]), _ucs(a), _vital(a),
                     len(por_aviso[a["id"]]), brl(custo_aviso.get(a["id"], 0)), a.get("usuario") or "—", a.get("status") or "gerado"]
                    for a in sorted(n["_todos"], key=lambda x: x["criado_em"])]},
    ]
    alertas = [f"{len(fora)} aviso(s) fora do prazo."] if fora else []
    return {"tipo": "mensal", "titulo": f"Relatório mensal - {MESES_PT[inicio.month - 1]} de {inicio.year}", "resumo": resumo,
            "alertas": alertas, "secoes": secoes, "projecao": proj,
            "como_calculamos": [FORMULAS[k] for k in ("atribuicao", "custo", "economia", "projecao", "prazo", "duracao", "frequencia", "comparacao")]
            + [f"Projeção deste relatório: {proj['conta']}."]}


_AVISO = re.compile(r"\baviso (\d+)\b")


def _aviso_do_detalhe(detalhe: str) -> int | None:
    m = _AVISO.search(str(detalhe or ""))
    return int(m.group(1)) if m else None


# ---------- H2: custos por rádio (financeiro) ----------
def custos(avisos_ano, envios_ano, avisos_ano_ant, envios_ano_ant, ano: int, mes_ref: int, fechado: bool, filtros: dict, cfg: dict) -> dict:
    por_mes, av, en = _gasto_por_mes(avisos_ano, envios_ano, ano, filtros)
    aviso = {a["id"]: a for a in av}
    proj = projecao(por_mes, mes_ref, fechado)
    orc = orcamento(proj["projecao"], proj["acumulado"], cfg.get("orcamento_radio"))
    por_radio_mes = defaultdict(lambda: [Decimal("0")] * 12)
    for e in en:
        por_radio_mes[e["radio_nome"]][mes_do(aviso[e["aviso_id"]]["criado_em"]) - 1] += _d(e["custo"])
    nomes = sorted(por_radio_mes, key=lambda k: -sum(por_radio_mes[k]))
    tabela_ano = [[k] + [brl(v) if v else "—" for v in por_radio_mes[k]] + [brl(sum(por_radio_mes[k]))] for k in nomes]
    tabela_ano.append(["Total"] + [brl(v) if v else "—" for v in por_mes] + [brl(sum(por_mes))])
    stats = {}
    for k in nomes:
        es = [e for e in en if e["radio_nome"] == k]
        valores = [_d(e["valor"]) for e in es]
        custos_ = [_d(e["custo"]) for e in es]
        media = (sum(custos_, Decimal("0")) / len(custos_)).quantize(CENTAVO) if custos_ else Decimal("0")
        stats[k] = {"pedidos": len(es), "segundos": sum(int(e["segundos"]) for e in es), "min": min(valores), "max": max(valores),
                    "custo": sum(custos_, Decimal("0")), "media": media,
                    "eco_c": sum((_d(e["economia"]) for e in es if e.get("economia_tipo") == "calculada"), Decimal("0")),
                    "eco_i": sum((_d(e["economia"]) for e in es if e.get("economia_tipo") == "informada"), Decimal("0")),
                    "conf": pct(sum(1 for e in es if e["status"] == "confirmado"), len(es)), "envios": es}
    limite = Decimal(str(cfg.get("alerta_preco") or 0.2))
    alertas_preco = [(e, k) for k in nomes for e in stats[k]["envios"]
                     if stats[k]["pedidos"] > 1 and _d(e["custo"]) > stats[k]["media"] * (1 + limite)]
    _, av_ant, en_ant = _gasto_por_mes(avisos_ano_ant, envios_ano_ant, ano - 1, filtros)
    aviso_ant = {a["id"]: a for a in av_ant}
    gasto_ant_mesmo_periodo = sum((_d(e["custo"]) for e in en_ant if mes_do(aviso_ant[e["aviso_id"]]["criado_em"]) <= mes_ref), Decimal("0"))
    sem_conf = [e for e in en if e["status"] != "confirmado"]
    alertas = [x for x in [orc["alerta"]] if x] + [f"{len(alertas_preco)} envio(s) com custo mais de {limite * 100:.0f}% acima da média da própria rádio."
                                                   if alertas_preco else None]
    resumo = [
        _item(f"Gasto acumulado em {ano} (até {MESES_CURTOS[mes_ref - 1]})", brl(proj["acumulado"]))
        | {"comparacoes": [{"contra": f"mesmo período de {ano - 1}", "texto": t}] if (t := comparar(proj["acumulado"], gasto_ant_mesmo_periodo)) else []},
        _item("Média mensal (meses fechados)", brl(proj["media"]) if proj["media"] is not None else "—"),
        _item("Projeção até dezembro", brl(proj["projecao"]) if proj["projecao"] is not None else "sem mês fechado"),
        _item("Orçamento anual de rádio", brl(cfg["orcamento_radio"]) if cfg.get("orcamento_radio") else "não definido"),
        _item("Orçamento usado", pct_txt(orc["usado"])),
        _item("Pedidos às rádios", str(len(en))),
        _item("Envios sem confirmação da rádio", str(len(sem_conf))),
    ]
    secoes = [
        {"titulo": f"Gasto mês a mês em {ano} (projeção até dezembro)", "tipo": "grafico", "formato": "dinheiro", "rotulos": MESES_CURTOS,
         "valores": [float(v) if i < mes_ref else None for i, v in enumerate(por_mes)],
         "projecao": [float(proj["media"]) if (proj["media"] is not None and i >= mes_ref) else None for i in range(12)]},
        {"titulo": "A conta da projeção", "tipo": "texto", "texto": proj["conta"]},
        {"titulo": f"Gasto por rádio, mês a mês ({ano})", "tipo": "tabela", "colunas": ["Rádio"] + MESES_CURTOS + ["Total"], "linhas": tabela_ano},
        {"titulo": "Por rádio", "tipo": "tabela",
         "colunas": ["Rádio", "Pedidos", "Tempo no ar", "Valor mín.", "Valor máx.", "Variação", "Custo total", "Custo médio", "Economia calc.",
                     "Economia inf.", "Confirmação"],
         "linhas": [[k, s["pedidos"], tempo(s["segundos"]), brl(s["min"]), brl(s["max"]), brl(s["max"] - s["min"]), brl(s["custo"]), brl(s["media"]),
                     brl(s["eco_c"]), brl(s["eco_i"]), pct_txt(s["conf"])] for k, s in stats.items()]},
        {"titulo": "Ranking das rádios por custo", "tipo": "lista",
         "itens": [f"{i}. {k}: {brl(s['custo'])}" for i, (k, s) in enumerate(sorted(stats.items(), key=lambda kv: -kv[1]["custo"]), 1)]},
        {"titulo": f"Alertas de preço (custo mais de {limite * 100:.0f}% acima da média da rádio)", "tipo": "tabela",
         "colunas": ["Rádio", "Aviso", "Data", "Custo", "Média da rádio", "Acima"],
         "linhas": [[k, f"nº {e['aviso_id']}", f"{e['criado_em'].astimezone(P.BRASILIA):%d/%m/%Y}", brl(e["custo"]), brl(stats[k]["media"]),
                     f"{(_d(e['custo']) / stats[k]['media'] - 1) * 100:.0f}%" if stats[k]["media"] else "—"] for e, k in alertas_preco]},
        {"titulo": "Conferência de fatura (cada envio, por rádio)", "tipo": "tabela",
         "colunas": ["Rádio", "Data", "Aviso", "Município", "Canal", "Valor", "Cobrança", "Custo", "Informado por"],
         "linhas": [[e["radio_nome"], f"{e['criado_em'].astimezone(P.BRASILIA):%d/%m/%Y %H:%M}", f"nº {e['aviso_id']}", e["municipio_nome"],
                     CANAIS[e["canal"]], brl(e["valor"]), "por minuto" if e["cobranca"] == "minuto" else "valor fechado", brl(e["custo"]),
                     e.get("criado_por_nome") or "—"] for e in sorted(en, key=lambda x: (x["radio_nome"], x["criado_em"]))]},
        {"titulo": "Envios sem confirmação da rádio", "tipo": "tabela", "colunas": ["Rádio", "Data", "Aviso", "Canal", "Situação"],
         "linhas": [[e["radio_nome"], f"{e['criado_em'].astimezone(P.BRASILIA):%d/%m/%Y}", f"nº {e['aviso_id']}", CANAIS[e["canal"]], e["status"]]
                    for e in sorted(sem_conf, key=lambda x: x["criado_em"])]},
    ]
    return {"tipo": "custos", "titulo": f"Custos por rádio - {ano}", "resumo": resumo, "alertas": [a for a in alertas if a], "secoes": secoes,
            "projecao": proj, "orcamento": orc,
            "como_calculamos": [FORMULAS[k] for k in ("atribuicao", "custo", "economia", "projecao", "comparacao")]
            + [f"Projeção: {proj['conta']}.", f"Alerta de preço: custo do envio > média de custo da própria rádio no ano x (1 + {limite * 100:.0f}%).",
               "Orçamento usado = gasto acumulado / orçamento anual."]}


# ---------- H3: comunidades mais afetadas ----------
def _por_comunidade(avisos):
    """(chave, município) -> eventos [(data do desligamento, horas, tipo, afetadas, aviso)] dos avisos ativos."""
    ev = defaultdict(list)
    info = {}
    for a in avisos:
        if a.get("status") == "cancelado":
            continue
        comeco = P.inicio(a["data"], a["horario"], a["criado_em"])
        dia = comeco.date() if comeco else a["criado_em"].astimezone(P.BRASILIA).date()
        for m in a["municipios"]:
            for c in m["comunidades"]:
                k = (nome_comunidade(c, m), m["nome"])
                info[k] = {"municipio": m["nome"], "codigo": m["codigo_ibge"], "distrito": "Sede" if c.get("distrito") == m["nome"] else c.get("distrito"),
                           "nome": str(c["nome"]).split(" (")[0], "uf": m.get("uf")}
                ev[k].append({"dia": dia, "horas": duracao_horas(a["horario"]) or 0, "tipo": a.get("tipo"), "afetadas": int(c.get("afetadas", 0)),
                              "aviso": a["id"], "parcial": bool(c.get("parcial") or c.get("fragmento")),
                              "vital_municipio": int(m.get("equipamento_vital", {}).get("sim", 0))})
    return ev, info


def repeticao(dias: list[date], n: int, janela: int) -> int:
    """O maior número de desligamentos dentro de uma janela de 'janela' dias (para comparar com n)."""
    ds = sorted(dias)
    melhor, j = 0, 0
    for i in range(len(ds)):
        while ds[i] - ds[j] > timedelta(days=janela - 1):
            j += 1
        melhor = max(melhor, i - j + 1)
    return melhor


def intervalo_medio(dias: list[date]) -> float | None:
    ds = sorted(set(dias))
    return round(sum((b - a).days for a, b in zip(ds, ds[1:])) / (len(ds) - 1), 1) if len(ds) > 1 else None


def comunidades(avisos, envios, radios_cobertura, inicio: date, fim: date, filtros: dict, cfg: dict) -> dict:
    """radios_cobertura: chave (nome com distrito, município) -> [nomes das rádios que alcançam]."""
    av, en = filtrar(_no_periodo(avisos, inicio, fim), envios, filtros or {})
    ev, info = _por_comunidade(av)
    n_rep, janela = int(cfg.get("repeticao_n") or 3), int(cfg.get("repeticao_dias") or 30)
    por_aviso = _envios_por_aviso(en)
    linhas = []
    for k, evs in ev.items():
        dias = [e["dia"] for e in evs]
        envs = [e for x in evs for e in por_aviso[x["aviso"]] if e["municipio"] == info[k]["codigo"]]
        linhas.append({"k": k, "n": len(evs), "horas": sum(e["horas"] for e in evs), "ucs": sum(e["afetadas"] for e in evs),
                       "tipos": Counter(ROTULOS.get(e["tipo"], "sem tipo") for e in evs), "dias": dias, "rep": repeticao(dias, n_rep, janela),
                       "intervalo": intervalo_medio(dias), "conf": pct(sum(1 for e in envs if e["status"] == "confirmado"), len(envs)),
                       "vital": max((e["vital_municipio"] for e in evs), default=0)})
    rank = sorted(linhas, key=lambda x: (-x["n"], -x["horas"], x["k"]))
    rank_h = sorted(linhas, key=lambda x: (-x["horas"], -x["n"], x["k"]))
    top10 = rank[:10]
    tipos = sorted({t for x in rank[:15] for t in x["tipos"]})
    meses = []
    d = inicio.replace(day=1)
    while d <= fim:
        meses.append((d.year, d.month))
        d = (d + timedelta(days=32)).replace(day=1)
    repetidas = [x for x in rank if x["rep"] >= n_rep]
    sugestoes = []
    for x in rank:
        for t, q in x["tipos"].items():
            dias_t = sorted(e["dia"] for e in ev[x["k"]] if ROTULOS.get(e["tipo"], "sem tipo") == t)
            if q >= 2 and (dias_t[-1] - dias_t[0]).days <= 60:
                sugestoes.append(f"{x['k'][0]} ({x['k'][1]}) teve {q} desligamentos por {t.lower()} em {(dias_t[-1] - dias_t[0]).days + 1} dias: "
                                 "avaliar juntar os serviços.")
        if x["rep"] >= n_rep:
            sugestoes.append(f"{x['k'][0]} ({x['k'][1]}) teve {x['rep']} desligamentos em até {janela} dias: avisar com mais antecedência e "
                             "conversar com a comunidade.")
    vital_mun = defaultdict(int)
    for a in av:
        if a.get("status") != "cancelado":
            for m in a["municipios"]:
                vital_mun[f"{m['nome']}/{m['uf']}"] += int(m.get("equipamento_vital", {}).get("sim", 0))
    secoes = [
        {"titulo": "Ranking por número de desligamentos", "tipo": "tabela",
         "colunas": ["Comunidade (distrito)", "Município", "Desligamentos", "Horas sem luz", "UCs afetadas", "Intervalo médio"],
         "linhas": [[x["k"][0], x["k"][1], x["n"], horas_txt(x["horas"]), x["ucs"], f"{x['intervalo']:.1f} dias".replace(".", ",") if x["intervalo"] else "—"]
                    for x in rank[:30]]},
        {"titulo": "Ranking por horas sem luz", "tipo": "tabela", "colunas": ["Comunidade (distrito)", "Município", "Horas sem luz", "Desligamentos"],
         "linhas": [[x["k"][0], x["k"][1], horas_txt(x["horas"]), x["n"]] for x in rank_h[:30]]},
        {"titulo": "Comunidade x tipo de desligamento", "tipo": "tabela", "colunas": ["Comunidade"] + tipos,
         "linhas": [[x["k"][0]] + [x["tipos"].get(t, 0) for t in tipos] for x in rank[:15]]},
        {"titulo": "Evolução mensal das 10 mais afetadas", "tipo": "tabela",
         "colunas": ["Comunidade"] + [f"{MESES_CURTOS[m - 1]}/{str(a)[2:]}" for a, m in meses],
         "linhas": [[x["k"][0]] + [sum(1 for dd in x["dias"] if (dd.year, dd.month) == am) for am in meses] for x in top10]},
        {"titulo": f"Repetição: {n_rep} ou mais desligamentos em {janela} dias", "tipo": "tabela",
         "colunas": ["Comunidade", "Município", f"Maior número em {janela} dias", "Intervalo médio"],
         "linhas": [[x["k"][0], x["k"][1], x["rep"], f"{x['intervalo']:.1f} dias".replace(".", ",") if x["intervalo"] else "—"] for x in repetidas]},
        {"titulo": "Rádios que cobrem e confirmação", "tipo": "tabela", "colunas": ["Comunidade", "Rádios que alcançam", "Confirmação dos envios"],
         "linhas": [[x["k"][0], ", ".join(radios_cobertura.get(x["k"], [])) or "sem rádio cadastrada", pct_txt(x["conf"])] for x in top10]},
        {"titulo": "Equipamento vital (contagem por município; o histórico não guarda por comunidade)", "tipo": "tabela",
         "colunas": ["Município", "UCs com equipamento vital nos avisos"], "linhas": [[k, v] for k, v in sorted(vital_mun.items())]},
        {"titulo": "Sugestões", "tipo": "lista", "itens": sugestoes or ["Nenhuma repetição que peça atenção neste período."]},
    ]
    resumo = [_item("Comunidades afetadas", str(len(linhas))), _item("Com repetição", str(len(repetidas))),
              _item("Mais afetada", f"{rank[0]['k'][0]} ({rank[0]['n']})" if rank else "—"),
              _item("Horas sem luz (soma das comunidades)", horas_txt(sum(x["horas"] for x in linhas)))]
    return {"tipo": "comunidades", "titulo": "Comunidades mais afetadas", "resumo": resumo,
            "alertas": [f"{len(repetidas)} comunidade(s) com {n_rep}+ desligamentos em {janela} dias."] if repetidas else [],
            "secoes": secoes, "como_calculamos": [FORMULAS[k] for k in ("atribuicao", "frequencia", "duracao")]
            + ["Sugestões: mesmo tipo de desligamento 2 ou mais vezes em 60 dias, ou repetição acima do limite da empresa."]}


# ---------- H4: prazos (regulação) ----------
def prazos(avisos, envios, avisos_comp, envios_comp, inicio: date, fim: date, filtros: dict, hoje: date, avisos_futuros, envios_futuros,
           horas_legais=72, dias_vital=5, mes: bool = False) -> dict:
    n = numeros(avisos, envios, inicio, fim, filtros, horas_legais, dias_vital)
    ativos, prz = n["_ativos"], n["_prazos"]
    def grupo(chave):
        g = defaultdict(lambda: [0, 0])
        for a in ativos:
            p = prz[a["id"]]
            if p["no_prazo"] is None:
                continue
            for k in chave(a):
                g[k][1] += 1
                g[k][0] += bool(p["no_prazo"])
        return [[k, f"{v[0]} de {v[1]}", pct_txt(pct(v[0], v[1]))] for k, v in sorted(g.items())]
    por_mes = grupo(lambda a: [f"{MESES_CURTOS[mes_do(a['criado_em']) - 1]}/{str(a['criado_em'].year)[2:]}"])
    fora = []
    for a in ativos:
        p = prz[a["id"]]
        if p["no_prazo"] is False:
            real = (p["inicio"] - p["avisado_em"]).total_seconds() / 3600
            exigida = (p["inicio"] - p["limite"]).total_seconds() / 3600
            fora.append([f"nº {a['id']}", f"{p['avisado_em'].astimezone(P.BRASILIA):%d/%m/%Y %H:%M}", f"{p['inicio']:%d/%m/%Y %H:%M}",
                         f"{real:.0f} h", f"{exigida:.0f} h ({p['regra']})", "—", a.get("usuario") or "—"])
    risco = []
    por_fut = _envios_por_aviso(envios_futuros)
    for a in avisos_futuros:
        comeco = P.inicio(a["data"], a["horario"], a["criado_em"])
        if a.get("status") == "cancelado" or not comeco or not (hoje <= comeco.date() <= hoje + timedelta(days=3)):
            continue
        for e in por_fut[a["id"]]:
            if e["status"] != "confirmado":
                risco.append([f"nº {a['id']}", f"{comeco:%d/%m %H:%M}", e["radio_nome"], CANAIS[e["canal"]], e["status"]])
    ini_ant = (inicio.replace(day=1) - timedelta(days=1)).replace(day=1)
    ant = numeros(avisos_comp + avisos, envios_comp + envios, ini_ant, inicio.replace(day=1) - timedelta(days=1), filtros, horas_legais, dias_vital) if mes else None
    try:
        aa = numeros(avisos_comp, envios_comp, inicio.replace(year=inicio.year - 1), fim.replace(year=fim.year - 1), filtros, horas_legais, dias_vital) if mes else None
    except ValueError:
        aa = None
    resumo = [
        _item("Regra aplicada", f"{horas_legais} horas; {dias_vital} dias úteis com equipamento vital"),
        _item("Avisos no prazo", f"{pct_txt(n['pct_no_prazo'])} ({n['no_prazo']} de {n['com_envio']})", n["pct_no_prazo"],
              ant["pct_no_prazo"] if ant and ant["com_envio"] else None, aa["pct_no_prazo"] if aa and aa["com_envio"] else None),
        _item("Fora do prazo", str(len(fora))), _item("Sem envio registrado", str(sum(1 for p in prz.values() if p["no_prazo"] is None))),
        _item("Em risco (desligamento em até 3 dias sem confirmação)", str(len(risco))),
    ]
    secoes = [
        {"titulo": "Regra aplicada", "tipo": "texto", "texto": f"Antecedência mínima de {horas_legais} horas; com equipamento vital, {dias_vital} "
                                                             "dias úteis (REN ANEEL 1.000/2021, art. 436). O momento do aviso é o primeiro envio à rádio."},
        {"titulo": "% no prazo, mês a mês", "tipo": "tabela", "colunas": ["Mês", "No prazo", "%"], "linhas": por_mes},
        {"titulo": "% no prazo por município", "tipo": "tabela", "colunas": ["Município", "No prazo", "%"],
         "linhas": grupo(lambda a: [f"{m['nome']}/{m['uf']}" for m in a["municipios"]])},
        {"titulo": "% no prazo por tipo", "tipo": "tabela", "colunas": ["Tipo", "No prazo", "%"], "linhas": grupo(lambda a: [ROTULOS.get(a.get("tipo"), "sem tipo")])},
        {"titulo": "% no prazo por pessoa", "tipo": "tabela", "colunas": ["Pessoa", "No prazo", "%"], "linhas": grupo(lambda a: [a.get("usuario") or "—"])},
        {"titulo": "Avisos fora do prazo", "tipo": "tabela",
         "colunas": ["Aviso", "Primeiro envio", "Desligamento", "Antecedência real", "Exigida", "Justificativa", "Gerado por"], "linhas": fora},
        {"titulo": "Risco: envios não confirmados com desligamento nos próximos 3 dias", "tipo": "tabela",
         "colunas": ["Aviso", "Desligamento", "Rádio", "Canal", "Situação"], "linhas": risco},
    ]
    return {"tipo": "prazos", "titulo": "Prazos dos avisos", "resumo": resumo,
            "alertas": ([f"{len(fora)} aviso(s) fora do prazo."] if fora else []) + ([f"{len(risco)} envio(s) em risco."] if risco else []),
            "secoes": secoes, "como_calculamos": [FORMULAS[k] for k in ("prazo", "comparacao", "atribuicao")]
            + ["Justificativa de atraso: o Norte ainda não pede; a coluna fica com \"—\"."]}


# ---------- H5: auditoria ----------
CATEGORIAS = {
    "acesso": ("entrou", "saiu", "senha errada", "login recusado", "trocou a senha", "gerou senha temporária"),
    "planilha": ("importou planilha", "conferiu", "justificou", "planilha bloqueada", "geração bloqueada", "baixou o JSON", "baixou o relatório da planilha",
                 "baixou o modelo"),
    "aviso": ("gerou aviso", "cancelou", "mudou a data", "editou a mensagem", "guardou o texto final", "gerou PDF", "gerou MP3", "alerta de repetição"),
    "radio": ("cadastrou rádio", "alterou cadastro de rádio", "informou o valor", "enviou por", "e-mail entregue", "envio por e-mail falhou",
              "copiou a mensagem", "rádio confirmou", "baixou o PDF enviado", "baixou o MP3 enviado", "arquivo enviado"),
    "cadastro": ("cadastrou usuário", "alterou usuário", "cadastrou empresa", "suspendeu empresa", "reativou empresa", "alterou a configuração",
                 "semente"),
    "relatorio": ("gerou relatório", "gerou comprovante", "gerou auditoria", "guardou a via", "baixou a segunda via", "enviou relatório",
                  "conferiu a integridade"),
}


def categoria(acao: str) -> str:
    return next((c for c, prefixos in CATEGORIAS.items() if any(acao.startswith(p) for p in prefixos)), "outros")


def auditoria(linhas: list[dict], verificacao: dict, geral: bool, rotulo_periodo: str) -> dict:
    """linhas: as do período já filtradas (quando, usuario, perfil, empresa, acao, detalhe, codigo)."""
    por_cat = defaultdict(list)
    for x in linhas:
        por_cat[categoria(x["acao"])].append(x)
    pessoas = defaultdict(Counter)
    for x in linhas:
        pessoas[x["usuario"] or "(sem login)"][categoria(x["acao"])] += 1
    logins = Counter("sucesso" if x["acao"] == "entrou" else "bloqueio" if "bloque" in x["acao"] else "falha"
                     for x in por_cat["acesso"] if x["acao"] in ("entrou",) or x["acao"].startswith(("senha errada", "login recusado")))
    cadeia = ("Cadeia de registros verificada ✓" if verificacao.get("ok")
              else f"A cadeia NÃO confere a partir da linha {verificacao.get('quebra_id') or '?'} ({verificacao.get('motivo')})")
    tab = lambda xs: [[x["quando"], x["usuario"] or "—", x["perfil"] or "—"] + ([x["empresa"] or "—"] if geral else []) + [x["acao"], x["detalhe"], x["codigo"] or ""]
                      for x in xs]
    col = ["Quando", "Quem", "Perfil"] + (["Empresa"] if geral else []) + ["O quê", "Detalhe", "Código"]
    alteracoes = [x for x in linhas if x["acao"].startswith(("alterou", "suspendeu", "reativou", "cadastrou", "informou o valor"))]
    secoes = [
        {"titulo": "Verificação da cadeia", "tipo": "texto", "texto": cadeia},
        {"titulo": "Resumo por pessoa", "tipo": "tabela", "colunas": ["Pessoa"] + list(CATEGORIAS) + ["outros", "total"],
         "linhas": [[p] + [c[k] for k in CATEGORIAS] + [c["outros"], sum(c.values())] for p, c in sorted(pessoas.items())]},
        {"titulo": "Logins", "tipo": "tabela", "colunas": ["Sucesso", "Falha", "Bloqueio"],
         "linhas": [[logins["sucesso"], logins["falha"], logins["bloqueio"]]]},
        {"titulo": "Alterações de cadastro (antes → depois)", "tipo": "tabela", "colunas": col, "linhas": tab(alteracoes)},
        {"titulo": "Downloads do JSON com números de UC", "tipo": "tabela", "colunas": col, "linhas": tab([x for x in linhas if x["acao"].startswith("baixou o JSON")])},
        {"titulo": "Relatórios gerados, baixados e enviados", "tipo": "tabela", "colunas": col, "linhas": tab(por_cat["relatorio"])},
        {"titulo": "Todas as ações", "tipo": "tabela", "colunas": col, "linhas": tab(linhas)},
    ]
    resumo = [_item("Ações no período", str(len(linhas))), _item("Pessoas", str(len(pessoas))),
              _item("Logins com sucesso / falha / bloqueio", f"{logins['sucesso']} / {logins['falha']} / {logins['bloqueio']}"),
              _item("Cadeia", "verificada ✓" if verificacao.get("ok") else "QUEBRADA")]
    return {"tipo": "acessos" if geral else "auditoria",
            "titulo": ("Auditoria geral de acessos" if geral else "Relatório de auditoria") + f" - {rotulo_periodo}", "resumo": resumo,
            "alertas": [] if verificacao.get("ok") else [cadeia], "secoes": secoes,
            "como_calculamos": ["Cada linha da auditoria guarda o hash da anterior; a verificação refaz a conta da primeira à última.",
                                "Tipos: acesso, planilha, aviso, rádio, cadastro, relatório e outros, pelo começo do nome da ação."]}


# ---------- H7: ficha da comunidade ----------
def ficha(chave: tuple, avisos_12m, envios, radios_que_alcancam: list[str], enderecos: int | None, hoje: date,
          horas_legais=72, dias_vital=5) -> dict:
    """chave: (código do município, nome sem sufixo, distrito como no IBGE). Últimos 12 meses."""
    cod, nome, distrito = chave
    evs = []
    por_aviso = _envios_por_aviso(envios)
    municipio = None
    for a in avisos_12m:
        if a.get("status") == "cancelado":
            continue
        for m in a["municipios"]:
            if m["codigo_ibge"] != cod:
                continue
            for c in m["comunidades"]:
                if str(c["nome"]).split(" (")[0] == nome and (c.get("distrito") or "") == (distrito or ""):
                    municipio = m["nome"]
                    comeco = P.inicio(a["data"], a["horario"], a["criado_em"])
                    p = _prazo(a, por_aviso[a["id"]], horas_legais, dias_vital)
                    evs.append({"aviso": a["id"], "dia": comeco.date() if comeco else a["criado_em"].astimezone(P.BRASILIA).date(),
                                "horas": duracao_horas(a["horario"]) or 0, "tipo": ROTULOS.get(a.get("tipo"), "sem tipo"),
                                "afetadas": int(c.get("afetadas", 0)), "parcial": bool(c.get("parcial") or c.get("fragmento")),
                                "no_prazo": p["no_prazo"], "vital_municipio": int(m.get("equipamento_vital", {}).get("sim", 0))})
    meses = []
    d = hoje.replace(day=1)
    for _ in range(12):
        meses.append((d.year, d.month))
        d = (d - timedelta(days=1)).replace(day=1)
    meses.reverse()
    por_mes = [sum(1 for e in evs if (e["dia"].year, e["dia"].month) == am) for am in meses]
    passados = sorted((e for e in evs if e["dia"] <= hoje), key=lambda e: e["dia"])
    futuros = sorted((e for e in evs if e["dia"] > hoje), key=lambda e: e["dia"])
    com_prazo = [e for e in evs if e["no_prazo"] is not None]
    return {"nome": nome, "distrito": "Sede" if distrito == municipio else distrito, "municipio": municipio, "codigo_ibge": cod,
            "enderecos": enderecos, "radios": radios_que_alcancam, "desligamentos": len(evs), "horas": round(sum(e["horas"] for e in evs), 2),
            "ucs_afetadas": sum(e["afetadas"] for e in evs), "vital_municipio": max((e["vital_municipio"] for e in evs), default=0),
            "por_mes": [{"mes": f"{MESES_CURTOS[m - 1]}/{str(a)[2:]}", "desligamentos": v} for (a, m), v in zip(meses, por_mes)],
            "ultimo": {"dia": passados[-1]["dia"].isoformat(), "aviso": passados[-1]["aviso"], "tipo": passados[-1]["tipo"]} if passados else None,
            "proximo": {"dia": futuros[0]["dia"].isoformat(), "aviso": futuros[0]["aviso"], "tipo": futuros[0]["tipo"]} if futuros else None,
            "tipos": [{"tipo": t, "n": n} for t, n in Counter(e["tipo"] for e in evs).most_common(3)],
            "pct_no_prazo": pct(sum(1 for e in com_prazo if e["no_prazo"]), len(com_prazo)),
            "mes_atual": por_mes[-1], "mes_anterior": por_mes[-2], "comparacao": comparar(por_mes[-1], por_mes[-2]),
            "avisos": [{"aviso": e["aviso"], "dia": e["dia"].isoformat(), "tipo": e["tipo"], "horas": e["horas"], "parcial": e["parcial"]}
                       for e in sorted(evs, key=lambda e: e["dia"])]}


def ficha_documento(f: dict) -> dict:
    resumo = [_item("Desligamentos em 12 meses", str(f["desligamentos"])), _item("Horas sem luz", horas_txt(f["horas"])),
              _item("UCs afetadas (soma)", str(f["ucs_afetadas"])),
              _item("Endereços na comunidade (IBGE)", str(f["enderecos"]) if f["enderecos"] is not None else "—"),
              _item("Avisos no prazo", pct_txt(f["pct_no_prazo"])),
              _item("Este mês", str(f["mes_atual"])) | {"comparacoes": [{"contra": "mês anterior", "texto": f["comparacao"]}] if f["comparacao"] else []}]
    secoes = [
        {"titulo": "Desligamentos por mês (12 meses)", "tipo": "grafico", "formato": "numero", "rotulos": [x["mes"] for x in f["por_mes"]],
         "valores": [x["desligamentos"] for x in f["por_mes"]]},
        {"titulo": "Rádios que alcançam", "tipo": "lista", "itens": f["radios"] or ["Nenhuma rádio cadastrada alcança esta comunidade."]},
        {"titulo": "Último e próximo desligamento", "tipo": "lista",
         "itens": [f"Último: {f['ultimo']['dia']} (aviso nº {f['ultimo']['aviso']}, {f['ultimo']['tipo']})" if f["ultimo"] else "Último: —",
                   f"Próximo: {f['proximo']['dia']} (aviso nº {f['proximo']['aviso']}, {f['proximo']['tipo']})" if f["proximo"] else "Próximo: —"]},
        {"titulo": "Tipos mais comuns", "tipo": "lista", "itens": [f"{t['tipo']}: {t['n']}" for t in f["tipos"]] or ["—"]},
        {"titulo": "Equipamento vital", "tipo": "texto",
         "texto": f"Até {f['vital_municipio']} UC(s) com equipamento vital nos avisos do município (o histórico guarda a contagem por município)."},
        {"titulo": "Avisos que passaram pela comunidade", "tipo": "tabela", "colunas": ["Aviso", "Desligamento", "Tipo", "Horas", "Como entrou"],
         "linhas": [[f"nº {x['aviso']}", x["dia"], x["tipo"], horas_txt(x["horas"]), "em parte" if x["parcial"] else "inteira"] for x in f["avisos"]]},
    ]
    return {"tipo": "comunidade", "titulo": f"Comunidade {f['nome']} ({f['distrito'] or '?'}) - {f['municipio'] or ''}", "resumo": resumo,
            "alertas": [], "secoes": secoes, "como_calculamos": [FORMULAS[k] for k in ("frequencia", "duracao", "prazo", "comparacao")]}


# ---------- CSV (protegido contra fórmula) ----------
def csv_documento(doc: dict, subtitulo: str, gerado_por: str, codigo: str) -> str:
    import csv
    import io

    from .travas import celula_segura
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")

    def linha(xs):
        w.writerow([celula_segura(v) for v in xs])

    linha(["relatorio", doc["titulo"]])
    linha(["periodo_e_filtros", subtitulo])
    linha(["gerado_por", gerado_por])
    linha(["codigo_verificacao", codigo])
    for a in doc.get("alertas") or []:
        linha(["alerta", a])
    linha([])
    linha(["resumo", "valor", "comparacoes"])
    for i in doc["resumo"]:
        linha([i["rotulo"], i["valor"], " · ".join(f"{c['texto']} vs {c['contra']}" for c in i.get("comparacoes") or [])])
    for s in doc["secoes"]:
        linha([])
        linha([s["titulo"]])
        if s["tipo"] == "tabela":
            linha(s["colunas"])
            for ln in s["linhas"]:
                linha(ln)
        elif s["tipo"] == "lista":
            for it in s["itens"]:
                linha([it])
        elif s["tipo"] == "texto":
            linha([s["texto"]])
        elif s["tipo"] == "grafico":
            linha(["rotulo", "valor"] + (["projecao"] if s.get("projecao") else []))
            for i, r in enumerate(s["rotulos"]):
                linha([r, "" if s["valores"][i] is None else s["valores"][i]] + ([s["projecao"][i] or ""] if s.get("projecao") else []))
    linha([])
    linha(["como_calculamos"])
    for t in doc["como_calculamos"]:
        linha([t])
    return saida.getvalue()
