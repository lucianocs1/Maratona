"""Verificador do aviso reescrito: a trava que a IA não consegue contornar.

Puro (sem rede nem arquivos). Quem reescreve o aviso (um LLM ou o simulado) pode errar, omitir uma
comunidade ou inventar um dado; antes de o texto chegar ao operador, este módulo confere o candidato
contra o aviso original, que o servidor tira do banco, nunca do cliente:
- toda comunidade citada no original continua citada, e o município também;
- todo número do original (data, horário, telefone) continua no texto, e nenhum número novo aparece
  (isso barra número de UC, coordenada, CPF e "milhares de clientes" inventados);
- nada de e-mail, link ou nome próprio que não estava no original (comunidade ou pessoa inventada);
- o texto cabe no limite do canal (SMS, por exemplo).
Se qualquer conferência falhar, o texto candidato é descartado e o aviso padrão fica como está.
"""

import re
from dataclasses import dataclass, field

from ..config import sem_acento

MAX_CARACTERES = 3000                       # o mesmo limite do texto do aviso na API
_NUMERO = re.compile(r"\d+")
_EMAIL = re.compile(r"\S+@\S+")
_LINK = re.compile(r"(?:https?://|www\.)\S+", re.I)
_PALAVRA_MAIUSCULA = re.compile(r"(?<![\w'-])[A-ZÀ-Ý][\w'-]*")
_ABREVIATURA = re.compile(r"(?:^|\s)[A-Za-zÀ-ÿ]{1,3}\.$")   # "Sr.", "Dra.", "Av.": o nome vem logo depois
_INICIO_DE_FRASE = set(".!?:;\n¡¿(*_\"“—–-")  # depois destes, a maiúscula é só início de frase
PERMITIDAS = {"sms", "whatsapp", "ano", "novo"}   # palavras de canal e da saudação de Ano Novo que o aviso pode ganhar


@dataclass
class Resultado:
    ok: bool
    motivos: list[str] = field(default_factory=list)


def _norma(s: str) -> str:
    return " ".join(sem_acento(s).lower().split())


def _numeros(s: str) -> set[str]:
    return {n.lstrip("0") or "0" for n in _NUMERO.findall(s)}


def _nomes_novos(original: str, candidato: str, permitidas: set[str]) -> list[str]:
    conhecidas = set(re.findall(r"[a-z0-9]+", _norma(original))) | {_norma(p) for p in permitidas} | PERMITIDAS
    novos = []
    for m in _PALAVRA_MAIUSCULA.finditer(candidato):
        antes = candidato[:m.start()].rstrip(" \t")
        if not antes or (antes[-1] in _INICIO_DE_FRASE and not _ABREVIATURA.search(antes)):
            continue
        partes = re.findall(r"[a-z0-9]+", _norma(m.group(0)))
        if partes and not all(p in conhecidas for p in partes) and m.group(0) not in novos:
            novos.append(m.group(0))
    return novos


def verificar(original: str, candidato: str, comunidades: list[str], municipio: str,
              max_caracteres: int = MAX_CARACTERES, permitidas: set[str] = frozenset()) -> Resultado:
    """O candidato mantém tudo o que o aviso original dizia e não acrescenta dado nenhum?

    comunidades: nomes das comunidades do município; só as que o original cita são exigidas (o aviso
    pode resumir as menores em "localidades vizinhas"). permitidas: palavras em maiúscula aceitas além
    das do original (o nome da distribuidora, por exemplo)."""
    candidato = (candidato or "").strip()
    if not candidato:
        return Resultado(False, ["o texto veio vazio"])
    motivos = []
    if len(candidato) > min(max_caracteres, MAX_CARACTERES):
        motivos.append(f"passou do limite de {min(max_caracteres, MAX_CARACTERES)} caracteres (tem {len(candidato)})")
    cand_n, orig_n = _norma(candidato), _norma(original)
    faltam = [c for c in comunidades if _norma(c) in orig_n and _norma(c) not in cand_n]
    if faltam:
        motivos.append("deixou de citar: " + ", ".join(faltam))
    if municipio and _norma(municipio) not in cand_n:
        motivos.append(f"deixou de citar o município {municipio}")
    n_orig, n_cand = _numeros(original), _numeros(candidato)
    if n_orig - n_cand:
        motivos.append("perdeu data, horário ou telefone do aviso: " + ", ".join(sorted(n_orig - n_cand, key=int)))
    if n_cand - n_orig:
        motivos.append("acrescentou número que não estava no aviso: " + ", ".join(sorted(n_cand - n_orig, key=int)))
    if _EMAIL.search(candidato) or _LINK.search(candidato):
        motivos.append("acrescentou e-mail ou link")
    novos = _nomes_novos(original, candidato, set(permitidas))
    if novos:
        motivos.append("citou nome que não estava no aviso: " + ", ".join(novos))
    return Resultado(not motivos, motivos)
