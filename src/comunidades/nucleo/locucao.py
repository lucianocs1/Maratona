"""Texto do aviso como deve ser falado (para a voz sintetizada).

Puro. O aviso escrito usa formas curtas que a voz leria errado: "8h" sairia "oito agá" e "20/11",
"vinte barra onze". Aqui elas viram o que o locutor diria: "8 horas", "20 de novembro".
Os números continuam em algarismos: a própria voz os lê por extenso.
Fase K: em inglês ("8:00 a.m." -> "8 A M") e em espanhol ("14:30" -> "14 y 30", "20/11" -> "20 de noviembre").
"""

import re

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def _hora(m: re.Match) -> str:
    h, mi = int(m.group(1)), m.group(2)
    horas = "hora" if h == 1 else "horas"
    if not mi or int(mi) == 0:
        return f"{h} {horas}"
    return f"{h} {horas} e {int(mi)}"


def _data(m: re.Match) -> str:
    d, mes = int(m.group(1)), int(m.group(2))
    if not (1 <= d <= 31 and 1 <= mes <= 12):
        return m.group(0)
    dia = "primeiro" if d == 1 else str(d)
    return f"{dia} de {MESES[mes - 1]}" + (f" de {m.group(3)}" if m.group(3) else "")


MESES_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
            "December"]
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
            "diciembre"]


def _fala_en(t: str) -> str:
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})\b", lambda m: f"{MESES_EN[int(m.group(2)) - 1]} {int(m.group(1))}"
               if 1 <= int(m.group(2)) <= 12 else m.group(0), t)                          # 20/11 -> November 20
    t = re.sub(r"\b(\d{1,2}):00\s*([ap])\.m\.", r"\1 \2.m.", t)                           # 8:00 a.m. -> 8 a.m.
    return re.sub(r"\b([ap])\.m\.", lambda m: "A M" if m.group(1) == "a" else "P M", t)   # a voz lê "A M" e "P M"


def _fala_es(t: str) -> str:
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})\b", lambda m: f"{int(m.group(1))} de {MESES_ES[int(m.group(2)) - 1]}"
               if 1 <= int(m.group(2)) <= 12 else m.group(0), t)                          # 20/11 -> 20 de noviembre
    t = re.sub(r"\b(\d{1,2}):00\b", r"\1", t)                                             # 8:00 -> 8
    return re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: f"{m.group(1)} y {int(m.group(2))}", t)   # 14:30 -> 14 y 30


def sem_marcacao(texto: str) -> str:
    """Tira as marcas de Markdown (asteriscos, #, crase, til e sublinhado de ênfase): a voz as leria ou faria uma pausa."""
    t = re.sub(r"[*#`~]+", "", str(texto))
    return re.sub(r"(?<!\w)_+|_+(?!\w)", "", t)


def texto_para_fala(texto: str, idioma: str = "pt-BR") -> str:
    t = " ".join(sem_marcacao(texto).split())
    if idioma == "en":
        return _fala_en(t)
    if idioma == "es":
        return _fala_es(t)
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", _data, t)       # 20/11 -> 20 de novembro
    t = re.sub(r"\b(\d{1,2})h(?:(\d{2})(?:min)?)?\b", _hora, t)          # 8h -> 8 horas; 14h30 -> 14 horas e 30
    t = re.sub(r"\bnº\s*", "número ", t)
    return t
