"""Tipos de desligamento programado: a lista fechada e o "Outro" com texto livre curto. Puro.

O tipo vira o {motivo} da mensagem da rádio ("haverá desligamento programado de energia para {motivo}").
O texto do "Outro" é digitado pelo operador: até 200 caracteres, sem caracteres de controle, e
recusado se parecer dado pessoal (sequência longa de números, como UC, CPF, CEP ou telefone; e-mail;
endereço de site). A tela avisa "não escreva nome de cliente"; a varredura de minimização confere de novo.
"""

import re
import unicodedata

TIPOS = {   # código -> como entra na mensagem ("para ...")
    "manutencao_preventiva": "manutenção preventiva na rede",
    "corretiva_programada": "manutenção corretiva programada",
    "obra": "obra de ampliação da rede",
    "poda": "poda de árvores perto da rede",
    "troca_equipamento": "troca de equipamento da rede",
}
ROTULOS = {"manutencao_preventiva": "Manutenção preventiva", "corretiva_programada": "Manutenção corretiva programada",
           "obra": "Obra ou ampliação da rede", "poda": "Poda de árvores", "troca_equipamento": "Troca de equipamento",
           "outro": "Outro"}
# Fase K: o motivo (como entra na mensagem) e o rótulo em inglês e em espanhol; o "Outro" vai como foi digitado
TIPOS_IDIOMA = {
    "en": {"manutencao_preventiva": "preventive maintenance on the power grid", "corretiva_programada": "scheduled corrective maintenance",
           "obra": "work to expand the power grid", "poda": "tree trimming near the power lines",
           "troca_equipamento": "replacement of grid equipment"},
    "es": {"manutencao_preventiva": "mantenimiento preventivo de la red", "corretiva_programada": "mantenimiento correctivo programado",
           "obra": "obras de ampliación de la red", "poda": "poda de árboles cerca de la red", "troca_equipamento": "cambio de equipos de la red"},
}
ROTULOS_IDIOMA = {
    "en": {"manutencao_preventiva": "Preventive maintenance", "corretiva_programada": "Scheduled corrective maintenance",
           "obra": "Grid work or expansion", "poda": "Tree trimming", "troca_equipamento": "Equipment replacement", "outro": "Other"},
    "es": {"manutencao_preventiva": "Mantenimiento preventivo", "corretiva_programada": "Mantenimiento correctivo programado",
           "obra": "Obra o ampliación de la red", "poda": "Poda de árboles", "troca_equipamento": "Cambio de equipos", "outro": "Otro"},
}
PADRAO = "manutencao_preventiva"


def rotulos(idioma: str = "pt-BR") -> dict[str, str]:
    return ROTULOS_IDIOMA.get(idioma, ROTULOS)
MAX_OUTRO = 200
_NUMEROS = re.compile(r"\d[\d.\-/ ]{4,}\d")     # 6 ou mais algarismos seguidos (com pontos, traços, barras)
_EMAIL = re.compile(r"\S+@\S+")
_SITE = re.compile(r"(https?://|www\.)", re.I)


def limpar(texto: str) -> str:
    s = unicodedata.normalize("NFC", str(texto or ""))
    s = "".join(c if unicodedata.category(c)[0] != "C" else " " for c in s)
    return " ".join(s.split())


def problema_outro(texto: str) -> str | None:
    """Por que o texto do "Outro" não pode entrar no aviso (None: pode)."""
    t = limpar(texto)
    if len(t) < 3:
        return "Descreva o motivo do desligamento (de 3 a 200 caracteres)."
    if len(t) > MAX_OUTRO:
        return f"O motivo pode ter no máximo {MAX_OUTRO} caracteres."
    if _NUMEROS.search(t):
        return "O motivo não pode ter números longos (UC, CPF, CEP ou telefone)."
    if _EMAIL.search(t) or _SITE.search(t):
        return "O motivo não pode ter e-mail nem endereço de site."
    return None


def motivo(tipo: str, outro: str | None = None, idioma: str = "pt-BR") -> tuple[str, str]:
    """(código, texto do motivo no idioma da mensagem) do tipo escolhido; ValueError com a mensagem se não servir."""
    if tipo in TIPOS:
        return tipo, TIPOS_IDIOMA.get(idioma, TIPOS)[tipo]
    if tipo == "outro":
        p = problema_outro(outro or "")
        if p:
            raise ValueError(p)
        return "outro", limpar(outro)
    raise ValueError("Tipo de desligamento inválido.")
