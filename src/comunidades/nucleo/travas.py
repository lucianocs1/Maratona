"""Travas da conferência humana: o que segura a geração do aviso depois da tradução da planilha.

Puro: recebe o JSON validado (nucleo/esquema_planilha.py) e o que a API já calculou (as linhas que
ficaram fora dos contornos dos municípios e os municípios de cada linha), e devolve as travas. A API
confere tudo de novo no segundo passo (Gerar aviso); a tela só mostra.

- Equipamento vital (vermelho, bloqueia sempre): linha com equipamento_vital = sim que foi
  rejeitada, corrigida ou ficou fora da concessão. Não há justificativa que libere: a planilha tem de
  ser corrigida e enviada de novo.
- Limite de rejeição (bloqueia sem justificativa): mais rejeitadas que o limite da empresa (padrão 2%)
  só segue com uma justificativa escrita (até 300 caracteres), que vai para a auditoria.
- Pontos suspeitos (amarelo, não bloqueia): ponto isolado, a mesma coordenada em muitas UCs e UC num
  município diferente do da maioria.
- Confirmação humana: sem "Conferi os números e o mapa", nada é gerado.
"""

import csv
import io
import re
from collections import defaultdict

from .esquema_planilha import PlanilhaJSON
from .motivos import TEXTOS, Aviso, Motivo

MAX_JUSTIFICATIVA = 300
MAX_LINHAS_LISTADAS = 200
MUNICIPIO_MINORIA = 0.05     # município com até 5% das UCs, se houver outro com a maioria: suspeito
SITUACAO_VITAL = {"rejeitada": "rejeitada", "corrigida": "corrigida", "fora": "fora da área de concessão",
                  "fora_area": "fora da área de atuação da empresa"}
SUSPEITOS = {
    "ponto_isolado": TEXTOS[Aviso.PONTO_ISOLADO],
    "muitas_ucs": TEXTOS[Aviso.COORD_MUITAS_UCS],
    "municipio_diferente": "UC num município diferente do da maioria (confira se é divisa)",
}


def vital_bloqueio(m: PlanilhaJSON, linhas_fora: set[int], linhas_fora_area: set[int] = frozenset()) -> list[dict]:
    """Linhas com equipamento vital rejeitadas, corrigidas, fora da concessão ou fora da área de atuação da empresa
    (pela linha, sem a UC)."""
    saida = []
    for pt in m.pontos:
        if pt.equipamento_vital is not True:
            continue
        if pt.status == "rejeitada":
            situacao, motivo = "rejeitada", TEXTOS[pt.motivo]
        elif pt.linha in linhas_fora_area:
            situacao, motivo = "fora_area", TEXTOS[Motivo.FORA_DA_AREA]
        elif pt.linha in linhas_fora:
            situacao, motivo = "fora", TEXTOS[Motivo.FORA_DA_CONCESSAO]
        elif pt.status == "corrigida":
            situacao, motivo = "corrigida", TEXTOS[pt.correcao]
        else:
            continue
        saida.append({"linha": pt.linha, "situacao": situacao, "texto": SITUACAO_VITAL[situacao], "motivo": motivo})
    return saida


def municipio_diferente(linhas_por_municipio: dict[str, list[int]]) -> list[dict]:
    """Municípios com poucas UCs (até 5%) quando outro tem a maioria: um aviso amarelo por município."""
    total = sum(len(v) for v in linhas_por_municipio.values())
    if total == 0 or len(linhas_por_municipio) < 2:
        return []
    maioria = max(linhas_por_municipio, key=lambda k: (len(linhas_por_municipio[k]), k))
    return [{"municipio": nome, "maioria": maioria, "linhas": sorted(linhas)[:MAX_LINHAS_LISTADAS], "ucs": len(linhas)}
            for nome, linhas in sorted(linhas_por_municipio.items())
            if nome != maioria and len(linhas) <= MUNICIPIO_MINORIA * total]


def suspeitos(m: PlanilhaJSON, linhas_por_municipio: dict[str, list[int]]) -> list[dict]:
    """Avisos amarelos: não bloqueiam, mas a pessoa confere antes de marcar "Conferi"."""
    por_tipo = defaultdict(list)
    for pt in m.pontos:
        if pt.status == "rejeitada":
            continue
        if Aviso.PONTO_ISOLADO in pt.avisos:
            por_tipo["ponto_isolado"].append(pt.linha)
        if Aviso.COORD_MUITAS_UCS in pt.avisos:
            por_tipo["muitas_ucs"].append(pt.linha)
    saida = [{"tipo": t, "texto": SUSPEITOS[t], "ucs": len(ls), "linhas": ls[:MAX_LINHAS_LISTADAS]}
             for t, ls in por_tipo.items()]
    for x in municipio_diferente(linhas_por_municipio):
        saida.append({"tipo": "municipio_diferente", "texto": SUSPEITOS["municipio_diferente"], **x})
    return saida


def rejeicao(m: PlanilhaJSON, limite: float, fora_da_area: int = 0) -> dict:
    """Fração de linhas rejeitadas e se passa do limite da empresa (aí só segue com justificativa).
    fora_da_area: as linhas válidas que a API rejeitou por estarem fora da área de atuação da empresa."""
    total, rej = m.resumo.total, m.resumo.rejeitadas + fora_da_area
    fracao = rej / total if total else 0.0
    return {"rejeitadas": rej, "total": total, "fracao": round(fracao, 4), "limite": limite, "acima": fracao > limite}


def limpar_justificativa(texto: str | None) -> str:
    """A justificativa como vai para a auditoria: sem caracteres de controle, espaços juntados."""
    s = "".join(c if c.isprintable() else " " for c in str(texto or ""))
    return " ".join(s.split())


def problema_para_gerar(travas: dict, conferi: bool, justificativa: str | None) -> str | None:
    """O que impede gerar o aviso (None: pode gerar). O servidor confere isto no segundo passo."""
    if travas["vital_bloqueio"]:
        return (f"{len(travas['vital_bloqueio'])} linha(s) com equipamento vital rejeitada(s), corrigida(s) ou fora da concessão. "
                "Corrija a planilha e importe de novo: nada foi gerado.")
    j = limpar_justificativa(justificativa)
    if travas["rejeicao"]["acima"]:
        if not j:
            return (f"Mais de {travas['rejeicao']['limite']:.0%} das linhas foram rejeitadas: escreva a justificativa "
                    "para continuar (ela fica na auditoria).")
        if len(j) > MAX_JUSTIFICATIVA:
            return f"A justificativa pode ter no máximo {MAX_JUSTIFICATIVA} caracteres."
    if not conferi:
        return "Marque \"Conferi os números e o mapa\" para gerar o aviso."
    return None


def ucs_opacas(m: PlanilhaJSON) -> PlanilhaJSON:
    """O mesmo JSON com cada número de UC trocado por um código opaco (u1, u2...): é o que vai para o
    navegador no pacote assinado. A mesma UC ganha o mesmo código (a repetida continua repetida)."""
    codigos: dict[str, str] = {}
    pontos = []
    for pt in m.pontos:
        if pt.uc is not None and pt.uc not in codigos:
            codigos[pt.uc] = f"u{len(codigos) + 1}"
        pontos.append(pt.model_copy(update={"uc": codigos.get(pt.uc) if pt.uc is not None else None}))
    return m.model_copy(update={"pontos": tuple(pontos)})


# ---------- relatório da tradução (CSV), só linha, situação e motivo ----------
_PERIGOSO = re.compile(r"^[=+\-@\t\r]")


def celula_segura(v) -> str:
    """Texto de célula de CSV que o Excel não executa: o que começa com = + - @ TAB ou CR ganha um
    apóstrofo. Números (int) entram como estão."""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, int):
        return str(v)
    s = "" if v is None else str(v)
    return "'" + s if _PERIGOSO.match(s) else s


def relatorio_csv(m: PlanilhaJSON) -> str:
    """Uma linha por linha da planilha: número, situação, motivo ou correção e avisos. Nada de UC nem
    coordenada. Separador ";" (o Excel brasileiro); o arquivo e a aba vão no cabeçalho, protegidos."""
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    w.writerow([celula_segura(x) for x in ("arquivo", m.arquivo.nome, "aba", m.arquivo.aba or "", "tradutor", m.tradutor)])
    w.writerow(["linha", "situacao", "motivo_ou_correcao", "equipamento_vital", "avisos"])
    for pt in m.pontos:
        texto = TEXTOS[pt.motivo] if pt.motivo else TEXTOS[pt.correcao] if pt.correcao else ""
        if pt.repete_linha:
            texto += f" (linha {pt.repete_linha})"
        vital = "a confirmar" if pt.equipamento_vital is None else "sim" if pt.equipamento_vital else "não"
        w.writerow([pt.linha, celula_segura(pt.status), celula_segura(texto), celula_segura(vital),
                    celula_segura(" | ".join(TEXTOS[a] for a in pt.avisos))])
    return saida.getvalue()
