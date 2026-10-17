"""Mensagem da rádio pelo modelo da empresa. Puro: recebe o modelo e os valores, devolve o texto.

O Admin da empresa edita o modelo (banco/radios.py guarda). Campos entre chaves:
{distribuidora} {municipio} {data} {inicio} {fim} {motivo} {comunidades} {comunidades_parciais}
{telefone_atendimento} {codigo}
Trecho entre colchetes é opcional: some inteiro se algum campo dentro dele ficar vazio
("[ Dúvidas: {telefone_atendimento}.]" sem telefone não deixa "Dúvidas: ." no ar).
Os nomes das comunidades vão sem o sufixo de distrito dos homônimos ("Piacatuba (Tebas)" -> "Piacatuba"):
o sufixo serve à tela, não ao ouvinte.
"""

import re
import unicodedata

from . import idiomas

CAMPOS = ("distribuidora", "municipio", "data", "inicio", "fim", "motivo", "comunidades", "comunidades_parciais",
          "telefone_atendimento", "codigo")
PADRAO = ("Atenção, ouvintes. A {distribuidora} informa: no dia {data}, das {inicio} às {fim}, haverá desligamento "
          "programado de energia para {motivo}[ nas comunidades {comunidades}].[ Ficará sem energia parte de: "
          "{comunidades_parciais}.] Programe-se.[ Dúvidas: {telefone_atendimento}.]")
# um modelo por idioma (Fase K); a data e as horas entram no formato de cada um (nucleo/idiomas.data_falada e inicio_fim)
PADROES = {
    "pt-BR": PADRAO,
    "en": ("Attention, listeners. {distribuidora} announces a scheduled power outage on {data}, from {inicio} to {fim}, "
           "for {motivo}[ in the communities of {comunidades}].[ Part of {comunidades_parciais} will also be without power.] "
           "Please plan ahead.[ Questions: {telefone_atendimento}.]"),
    "es": ("Atención, oyentes. {distribuidora} informa: el {data}, entre las {inicio} y las {fim}, habrá un corte "
           "programado de energía por {motivo}[ en las comunidades de {comunidades}].[ También quedará sin energía parte de: "
           "{comunidades_parciais}.] Tome sus precauciones.[ Consultas: {telefone_atendimento}.]"),
}
MAX_MODELO = 1500
MAX_MENSAGEM = 3000
_CAMPO = re.compile(r"\{([^{}]*)\}")
_OPCIONAL = re.compile(r"\[([^\[\]]*)\]")


def problema_modelo(modelo: str) -> str | None:
    """Por que o modelo não serve (None: serve). Campos só da lista; colchetes sem aninhar; sem chave solta."""
    m = str(modelo or "")
    if not m.strip():
        return "O modelo da mensagem não pode ficar vazio."
    if len(m) > MAX_MODELO:
        return f"O modelo pode ter no máximo {MAX_MODELO} caracteres."
    if any(unicodedata.category(c)[0] == "C" and c not in "\n" for c in m):
        return "O modelo não pode ter caracteres de controle."
    desconhecidos = sorted({c for c in _CAMPO.findall(m) if c not in CAMPOS})
    if desconhecidos:
        return f"Campo(s) desconhecido(s): {', '.join('{' + c + '}' for c in desconhecidos)}. Use: {', '.join('{' + c + '}' for c in CAMPOS)}."
    if "{" in _CAMPO.sub("", m) or "}" in _CAMPO.sub("", m):
        return "Há uma chave { ou } sobrando no modelo."
    nivel = 0
    for c in m:
        nivel += (c == "[") - (c == "]")
        if nivel < 0 or nivel > 1:
            return "Os colchetes do modelo não fecham direito (trecho opcional: [ ... ], sem um dentro do outro)."
    if nivel:
        return "Há um colchete [ sem o ] que fecha."
    for obrigatorio in ("data", "comunidades"):
        if "{" + obrigatorio + "}" not in m:
            return f"O modelo precisa do campo {{{obrigatorio}}}."
    return None


def sem_sufixo(nome: str) -> str:
    return re.sub(r" \([^()]*\)$", "", str(nome))


def lista_falada(nomes: list[str], idioma: str = idiomas.PADRAO) -> str:
    """['A', 'B', 'C'] -> 'A, B e C' (sem repetir nomes iguais, na ordem); "and" em inglês, "y" (ou "e") em espanhol."""
    vistos = list(dict.fromkeys(n for n in nomes if n))
    if idioma != idiomas.PADRAO:
        return idiomas.lista(vistos, idioma)
    return vistos[0] if len(vistos) == 1 else ", ".join(vistos[:-1]) + " e " + vistos[-1] if vistos else ""


def montar(modelo: str, valores: dict[str, str]) -> str:
    """O texto da mensagem: trechos opcionais com campo vazio somem; os outros perdem os colchetes."""
    v = {c: " ".join(str(valores.get(c) or "").split()) for c in CAMPOS}

    def opcional(m: re.Match) -> str:
        trecho = m.group(1)
        return "" if any(not v[c] for c in _CAMPO.findall(trecho)) else trecho

    texto = _OPCIONAL.sub(opcional, modelo)
    texto = _CAMPO.sub(lambda m: v[m.group(1)], texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" +([.,;:!?])", r"\1", texto)
    return texto.strip()[:MAX_MENSAGEM]


def valores_do_municipio(municipio: dict, *, distribuidora: str, data: str, horario: str, motivo: str,
                         telefone: str = "", codigo: str = "", idioma: str = idiomas.PADRAO) -> dict[str, str]:
    """Os valores dos campos para um município do aviso (comunidades como saem da API), no idioma da mensagem.
    A data e o horário chegam no formato brasileiro ("20/11", "8h às 14h"); em português, ficam como estão."""
    inicio, fim = idiomas.inicio_fim(horario, idioma)
    inteiras = [sem_sufixo(c["nome"]) for c in municipio["comunidades"] if not c.get("parcial") and not c.get("fragmento")]
    parciais = [sem_sufixo(c["nome"]) for c in municipio["comunidades"] if c.get("parcial") or c.get("fragmento")]
    return {"distribuidora": distribuidora, "municipio": municipio["nome"], "data": idiomas.data_falada(data, idioma),
            "inicio": inicio, "fim": fim, "motivo": motivo, "comunidades": lista_falada(inteiras, idioma),
            "comunidades_parciais": lista_falada(parciais, idioma), "telefone_atendimento": telefone, "codigo": codigo}
