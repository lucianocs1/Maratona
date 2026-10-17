"""Consultas fixas ao histórico de avisos, para o "Pergunte ao painel".

Puro (sem rede, banco ou arquivos). A IA nunca escreve SQL nem calcula: ela só escolhe uma destas
consultas e os parâmetros (período e município); quem calcula é este módulo, em cima dos avisos da
empresa que a API já separou (nucleo/painel.py faz as contas). Só agregados: nunca UC, coordenada
ou nome de pessoa, porque o histórico não os guarda.

A resposta em texto, venha ela da IA ou do modelo padrão daqui, é conferida por conferir_resposta:
todo número dela tem de estar nos dados devolvidos (ou na própria pergunta). Se não estiver, vale o
texto padrão.
"""

import re
from datetime import date, timedelta

from ..config import sem_acento
from . import painel
from .custo import SPOT_SEGUNDOS

MAX_PERIODO_DIAS = 3650
MAX_PERGUNTA = 300
MAX_RESPOSTA = 700
PARAMETROS = {
    "periodo_dias": "só os avisos gerados nos últimos N dias (inteiro de 1 a 3650); sem ele, todo o histórico",
    "municipio": "só os avisos que incluem este município (o nome como aparece no histórico)",
}
CATALOGO = {  # nome -> (rótulo na tela, o que responde)
    "totais": ("Resumo geral", "Totais do histórico: avisos, UCs avisadas, comunidades, municípios, avisos com equipamento vital e tempo médio no ar."),
    "municipios_mais_avisados": ("Municípios com mais avisos", "Ranking dos municípios por número de avisos e UCs avisadas."),
    "comunidades_mais_afetadas": ("Comunidades mais citadas", "Ranking das comunidades que mais apareceram nos avisos, com as UCs afetadas."),
    "avisos_por_mes": ("Avisos por mês", "Avisos e UCs avisadas em cada um dos últimos 12 meses (o período não se aplica)."),
    "proximos_desligamentos": ("Próximos desligamentos", "Os desligamentos já avisados com data de hoje em diante (o período não se aplica)."),
    "comparativo_tempo_no_ar": ("Aviso de hoje x por comunidade", "Quantos segundos e palavras o aviso de hoje (fazenda a fazenda) leva no ar contra o aviso por comunidade, nos municípios em que a planilha trouxe a coluna local."),
}
SEM_PERIODO = ("proximos_desligamentos", "avisos_por_mes")   # consultas com janela própria
EXEMPLOS = ["Quais municípios tiveram mais avisos no último trimestre?", "Quais as comunidades mais citadas em Leopoldina?",
            "Quais são os próximos desligamentos?", "Quanto tempo o aviso por comunidade economiza no rádio?"]
_NUMERO = re.compile(r"\d+")
_MILHAR = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{3})+(?![\d.])")


def _norma(s: str) -> str:
    return " ".join(sem_acento(str(s)).lower().split())


def normalizar_parametros(nome: str, brutos: dict | None) -> dict:
    """Só os parâmetros conhecidos e válidos (ValueError se a consulta não existe ou o valor é absurdo)."""
    if nome not in CATALOGO:
        raise ValueError(f"consulta desconhecida: {nome}")
    brutos = brutos or {}
    saida = {}
    if brutos.get("periodo_dias") not in (None, ""):
        try:
            n = int(brutos["periodo_dias"])
        except (TypeError, ValueError):
            raise ValueError("periodo_dias: use um número de dias") from None
        if not 1 <= n <= MAX_PERIODO_DIAS:
            raise ValueError(f"periodo_dias: de 1 a {MAX_PERIODO_DIAS}")
        if nome not in SEM_PERIODO:
            saida["periodo_dias"] = n
    if brutos.get("municipio") not in (None, ""):
        m = " ".join(str(brutos["municipio"]).split())
        if len(m) > 80:
            raise ValueError("municipio: até 80 caracteres")
        saida["municipio"] = m
    return saida


def filtrar(avisos: list[dict], hoje: date, periodo_dias: int | None = None, municipio: str | None = None) -> list[dict]:
    """Os avisos do período e, se pedido, só com o município indicado (os outros saem de cada aviso)."""
    saida = []
    for a in avisos:
        if periodo_dias and a["criado_em"].date() < hoje - timedelta(days=periodo_dias):
            continue
        if municipio:
            ms = [m for m in (a["municipios"] or []) if _norma(m["nome"]) == _norma(municipio)]
            if not ms:
                continue
            a = {**a, "municipios": ms}
        saida.append(a)
    return saida


def _data(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def executar(nome: str, parametros: dict, avisos: list[dict], hoje: date, spot_segundos: int = SPOT_SEGUNDOS) -> dict:
    """{colunas, linhas}: a tabela da resposta. Parâmetros já passaram por normalizar_parametros."""
    f = filtrar(avisos, hoje, parametros.get("periodo_dias"), parametros.get("municipio"))
    r = painel.resumir(f, hoje, spot_segundos)
    t = r["totais"]
    if nome == "totais":
        return {"colunas": ["Indicador", "Valor"], "linhas": [
            ["Avisos gerados", t["avisos"]], ["UCs avisadas", t["ucs"]], ["Comunidades citadas", t["comunidades"]],
            ["Municípios", t["municipios"]], ["Avisos com equipamento vital", t["com_equipamento_vital"]],
            ["Tempo médio no ar (segundos)", t["segundos_medio"]]]}
    if nome == "municipios_mais_avisados":
        return {"colunas": ["Município", "Avisos", "UCs"], "linhas": [[f"{m['nome']}/{m['uf']}", m["avisos"], m["ucs"]] for m in r["municipios"]]}
    if nome == "comunidades_mais_afetadas":
        return {"colunas": ["Comunidade", "Município", "Avisos", "UCs"],
                "linhas": [[c["nome"], c["municipio"], c["avisos"], c["ucs"]] for c in r["comunidades"]]}
    if nome == "avisos_por_mes":
        return {"colunas": ["Mês", "Avisos", "UCs"], "linhas": [[f"{m['mes'][5:]}/{m['mes'][:4]}", m["avisos"], m["ucs"]] for m in r["por_mes"]]}
    if nome == "proximos_desligamentos":
        return {"colunas": ["Data", "Horário", "Municípios", "UCs"],
                "linhas": [[_data(p["data"]), p["horario"], ", ".join(p["municipios"]), p["ucs"]] for p in r["proximos"]]}
    c = r["comparativo"]
    return {"colunas": ["Indicador", "Aviso de hoje", "Aviso por comunidade"], "linhas": [] if not c["municipios"] else [
        ["Locais ou comunidades citados", c["locais"], c["comunidades"]], ["Palavras", c["palavras_hoje"], c["palavras_farol"]],
        ["Segundos no ar", c["segundos_hoje"], c["segundos_farol"]],
        [f"Spots de rádio ({spot_segundos} s)", c["spots_hoje"], c["spots_farol"]]], "municipios": c["municipios"]}


def _onde(p: dict) -> str:
    quando = f"nos últimos {p['periodo_dias']} dias" if p.get("periodo_dias") else "em todo o histórico"
    return quando + (f", em {p['municipio']}" if p.get("municipio") else "")


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def texto_padrao(nome: str, parametros: dict, tabela: dict) -> str:
    """A resposta escrita só com o que está na tabela (a que vale quando a IA não escreve ou erra)."""
    l, onde = tabela["linhas"], _onde(parametros)
    if not l:
        return f"Não há dados para essa consulta {onde}."
    if nome == "totais":
        v = {x[0]: x[1] for x in l}
        return (f"{_cap(onde)}: {v['Avisos gerados']} avisos, {v['UCs avisadas']} UCs avisadas, {v['Comunidades citadas']} comunidades "
                f"citadas em {v['Municípios']} municípios; tempo médio no ar de {v['Tempo médio no ar (segundos)']} segundos.")
    if nome == "municipios_mais_avisados":
        resto = f", seguido de {', '.join(x[0] for x in l[1:3])}" if len(l) > 1 else ""
        return f"{_cap(onde)}, o município com mais avisos é {l[0][0]} ({l[0][1]} avisos, {l[0][2]} UCs){resto}."
    if nome == "comunidades_mais_afetadas":
        resto = f", seguida de {', '.join(x[0] for x in l[1:3])}" if len(l) > 1 else ""
        return f"{_cap(onde)}, a comunidade mais citada é {l[0][0]} ({l[0][1]}), com {l[0][2]} avisos e {l[0][3]} UCs{resto}."
    if nome == "avisos_por_mes":
        top = max(l, key=lambda x: x[1])
        return (f"{_cap(onde)}, o mês com mais avisos foi {top[0]} ({top[1]} avisos, {top[2]} UCs)." if top[1]
                else f"Nenhum aviso nos últimos 12 meses {onde}.")
    if nome == "proximos_desligamentos":
        return f"Há {len(l)} desligamento(s) já avisado(s); o próximo é {l[0][0]}, {l[0][1]}, em {l[0][2]} ({l[0][3]} UCs)."
    v = {x[0]: x[1:] for x in l}
    s, sp = v["Segundos no ar"], l[-1]
    return (f"Em {tabela['municipios']} município(s) com a coluna local, o aviso de hoje leva {s[0]} segundos no ar e o aviso por "
            f"comunidade {s[1]} segundos ({v['Palavras'][0]} contra {v['Palavras'][1]} palavras). Como a rádio cobra por spot, "
            f"são {sp[1]} spots contra {sp[2]}.")


def _numeros(texto: str) -> set[str]:
    texto = _MILHAR.sub(lambda m: m.group(0).replace(".", ""), texto)
    return {n.lstrip("0") or "0" for n in _NUMERO.findall(texto)}


def conferir_resposta(texto: str, pergunta: str, parametros: dict, tabela: dict) -> bool:
    """O texto escrito só usa números que estão na tabela, nos parâmetros ou na própria pergunta?"""
    texto = (texto or "").strip()
    if not texto or len(texto) > MAX_RESPOSTA:
        return False
    permitidos = _numeros(pergunta) | _numeros(" ".join(map(str, parametros.values())))
    for linha in [tabela["colunas"], *tabela["linhas"]]:
        permitidos |= _numeros(" ".join(map(str, linha)))
    permitidos |= _numeros(str(tabela.get("municipios", "")))
    return _numeros(texto) <= permitidos
