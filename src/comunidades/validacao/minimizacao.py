"""Varredura de minimização: o HTML gerado não pode levar titular, número de UC nem endereço.

Procura no mapa (mapa_comunidades.html), no resumo do cartão (resumo_mapa.json), na página de
entrada (index.html) e na área administrativa (admin.html, com usuários fictícios de exemplo) cada titular, nome de imóvel, logradouro e número de UC do cadastro fictício.
A busca ignora acentos, maiúsculas e pontuação e compara palavra por palavra, então "SITIO BOA VISTA"
acha "Sítio Boa Vista" e "sitio-boa-vista".

Um nome do cadastro pode coincidir com um texto público que o mapa leva de propósito: um nome de
comunidade ou de localidade ou distrito do IBGE. Essas coincidências aparecem no relatório, com a origem,
e não reprovam. Qualquer outra ocorrência reprova, inclusive na localidade digitada no cadastro que o
popup mostra (quando ela é nome de imóvel, o mapa não leva o texto).

O texto do aviso de hoje de cada chave (cenarios[*].antigo) reproduz o comunicado público e pode citar
imóveis e ruas. Ele é conferido à parte: nenhum número de UC, e um nome de titular só pode aparecer
como parte do nome de uma rua ou imóvel (ruas com nome de pessoa, como "Rua Maria Oliveira Ramos").

Rode em todo passo que mexer no HTML.
Uso: py -m uv run python -m comunidades.validacao.minimizacao [mapa.html]
(padrão: o mapa do município da configuração; com FAROL_DISTRIBUIDORA, o outro município)
"""

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import geopandas as gpd

from .. import config as C
from ..apresentacao.mapa import ARQ_RESUMO, ARQ_SAIDA, SAIDA_RAIZ
from ..nucleo.planilha import e_so_tipo_de_via

CAMPOS = {"TITULAR": "titular", "NOME_IMOVEL": "nome de imóvel", "LOGRADOURO": "logradouro"}

# Número de casa e CEP no aviso de hoje: o aviso cita a rua, nunca o endereço completo.
# Nomes com número ("Estrada 267", "Rodovia BR 116", "Rua 27 de Abril") e a data e o horário do aviso passam.
ENDERECO_COMPLETO = re.compile(
    r"\bCEP\b|\b\d{2}\.?\d{3}-\d{3}\b|\b\d{8}\b"                                    # CEP
    r"|[A-Za-zÀ-ÿ]\s*,\s*\d+"                                                        # "Rua X, 123"
    r"|\b(?P<num>n[º°]|n\.|no\.|num\.?|n[úu]mero)\s*\d+"                             # "nº 45"
    r"|\b(casa|apto?|apartamento|lote|quadra|qd|bloco|sala)\.?\s*\d+", re.I)          # "casa 2"


def numero_de_casa_ou_cep(texto: str) -> list[str]:
    """Os trechos do texto que parecem número de casa, complemento ou CEP (vazio: nenhum).
    "Beco Número 399" (nome de via do CNEFE: o "número" vem logo depois do tipo de via) não conta."""
    achados = []
    for m in ENDERECO_COMPLETO.finditer(texto):
        antes = texto[:m.start()].split()
        if m.group("num") and antes and e_so_tipo_de_via(antes[-1]):
            continue
        achados.append(m.group(0))
    return achados


def _palavras(texto: str) -> list[str]:
    s = unicodedata.normalize("NFD", str(texto))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").upper()
    return re.findall(r"[A-Z0-9]+", s)


class Indice:
    """As palavras de um texto, com as posições de cada uma, para achar sequências de palavras."""

    def __init__(self, texto: str):
        self.p = _palavras(texto)
        self.pos = defaultdict(list)
        for i, w in enumerate(self.p):
            self.pos[w].append(i)

    def contem(self, termo: list[str]) -> bool:
        n = len(termo)
        return any(self.p[i:i + n] == termo for i in self.pos.get(termo[0], ()))


def textos_publicos(D: dict) -> dict[str, list[str]]:
    """Os nomes que o mapa leva de propósito, por origem."""
    feicoes = lambda camada, prop: [f["properties"][prop] for f in D["camadas"][camada]["features"]]
    return {
        "comunidade": D["comPrev"] + D["comReal"] + feicoes("previstas", "NOME") + feicoes("gabarito", "NOME"),
        "localidade do IBGE": feicoes("localidades", "NM_LOCALIDADE"),
        "distrito ou município": feicoes("distritos", "NM_DIST") + feicoes("municipio", "NM_MUN") + D["distritosUC"],
    }


def _separar_avisos_de_hoje(html: str) -> tuple[str, str, dict]:
    """O HTML sem os textos do aviso de hoje, os textos à parte e os dados do mapa."""
    m = re.search(r"const D = (\{.*?\});\n", html, flags=re.S)
    D = json.loads(m.group(1))
    avisos = "\n".join(c["antigo"] for c in D["cenarios"].values())
    sem = json.loads(m.group(1))
    for c in sem["cenarios"].values():
        c["antigo"] = ""
    return html[:m.start(1)] + json.dumps(sem, ensure_ascii=False) + html[m.end(1):], avisos, D


def varrer(mapa: Path = ARQ_SAIDA) -> dict:
    ucs = gpd.read_file(C.SINTETICO / "ucs.gpkg", ignore_geometry=True)
    html, avisos, D = _separar_avisos_de_hoje(mapa.read_text(encoding="utf-8"))
    outros = [p for p in (ARQ_RESUMO, SAIDA_RAIZ / "index.html", SAIDA_RAIZ / "admin.html") if p.exists()]
    texto = "\n".join([html] + [p.read_text(encoding="utf-8") for p in outros])
    indice, ind_avisos = Indice(texto), Indice(avisos)
    publicos = {origem: Indice("\n".join(map(str, nomes))) for origem, nomes in textos_publicos(D).items()}
    locais = Indice("\n".join(ucs["NOME_IMOVEL"].dropna().tolist() + ucs["LOGRADOURO"].dropna().tolist()))

    r = {"arquivos": [str(p) for p in [mapa] + outros], "procurados": {}, "explicados": defaultdict(list),
         "proibidos": [], "avisos_de_hoje": len(D["cenarios"]), "no_aviso_de_hoje": defaultdict(int)}
    for col, rotulo in CAMPOS.items():
        termos = {tuple(_palavras(v)) for v in ucs[col].dropna().astype(str)} - {()}
        r["procurados"][rotulo] = len(termos)
        for t in sorted(termos):
            t = list(t)
            # no aviso de hoje: imóveis e ruas podem; titular só como parte do nome de uma rua ou imóvel
            if ind_avisos.contem(t):
                if col == "TITULAR" and not locais.contem(t):
                    r["proibidos"].append((rotulo + " (aviso de hoje)", " ".join(t)))
                else:
                    r["no_aviso_de_hoje"][rotulo + (" (parte do nome de uma rua ou imóvel)" if col == "TITULAR" else "")] += 1
            if not indice.contem(t):
                continue
            origem = next((o for o, ind in publicos.items() if ind.contem(t)), None)
            if origem:
                r["explicados"][(rotulo, origem)].append(" ".join(t))
            else:
                r["proibidos"].append((rotulo, " ".join(t)))
    # número de UC: qualquer sequência de dígitos igual a um número de UC, em qualquer parte
    numeros = set(re.findall(r"\d+", texto + avisos))
    r["procurados"]["número de UC"] = ucs["UC"].nunique()
    r["proibidos"] += [("número de UC", u) for u in sorted(set(ucs["UC"].astype(str)) & numeros)]
    # o aviso de hoje cita a rua, nunca o número da casa nem o CEP
    r["proibidos"] += [("número de casa ou CEP (aviso de hoje)", t) for t in sorted(set(numero_de_casa_ou_cep(avisos)))]
    return r


if __name__ == "__main__":
    r = varrer(Path(sys.argv[1]) if len(sys.argv) > 1 else ARQ_SAIDA)
    print("Arquivos:", *r["arquivos"], sep="\n  ")
    print("Procurados:", ", ".join(f"{n} {k}" for k, n in r["procurados"].items()))
    print(f"Avisos de hoje (modo chave, comunicado público) conferidos à parte: {r['avisos_de_hoje']}; citam "
          + ", ".join(f"{n} {k}" for k, n in r["no_aviso_de_hoje"].items()))
    for (rotulo, origem), nomes in sorted(r["explicados"].items()):
        print(f"Coincidência permitida ({rotulo} igual a {origem}): {len(nomes)}, ex.: {', '.join(nomes[:5])}")
    if r["proibidos"]:
        print(f"PROIBIDO: {len(r['proibidos'])} ocorrências, ex.: {r['proibidos'][:10]}")
        sys.exit(1)
    print("Nenhum titular, número de UC, nome de imóvel ou logradouro fora dos nomes públicos.")
