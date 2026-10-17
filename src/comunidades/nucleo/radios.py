"""Que rádio alcança que comunidade. Puro: recebe as rádios (com o alcance) e um município do aviso.

O alcance de uma rádio é uma lista de municípios inteiros (código IBGE) e de comunidades, pelo nome
completo: o município, o nome sem o sufixo de homônimo e o distrito ("Piacatuba", distrito "Tebas",
em 3138401). Assim duas comunidades com o mesmo nome em distritos diferentes não se confundem.
"""

import re

MAX_COMUNIDADES = 1000
_SUFIXO = re.compile(r" \([^()]*\)$")


def nome_base(nome: str) -> str:
    return _SUFIXO.sub("", str(nome))


def chave(municipio: str, nome: str, distrito: str) -> tuple[str, str, str]:
    return (str(municipio), nome_base(nome).casefold(), str(distrito or "").casefold())


def normalizar_alcance(alcance: dict | None, municipios_validos: set[str]) -> dict:
    """O alcance como fica gravado; ValueError se trouxer município fora da concessão ou formato errado."""
    a = alcance or {}
    mun = a.get("municipios") or []
    com = a.get("comunidades") or []
    if not isinstance(mun, list) or not isinstance(com, list) or len(com) > MAX_COMUNIDADES or len(mun) > 200:
        raise ValueError("alcance inválido")
    municipios = sorted({str(m) for m in mun})
    if any(m not in municipios_validos for m in municipios):
        raise ValueError("alcance com município fora da concessão")
    comunidades, vistas = [], set()
    for c in com:
        if not isinstance(c, dict) or str(c.get("municipio")) not in municipios_validos:
            raise ValueError("alcance com comunidade fora da concessão")
        nome, distrito = " ".join(str(c.get("nome", "")).split())[:120], " ".join(str(c.get("distrito", "")).split())[:120]
        if not nome:
            raise ValueError("alcance com comunidade sem nome")
        k = chave(c["municipio"], nome, distrito)
        if k not in vistas:
            vistas.add(k)
            comunidades.append({"municipio": str(c["municipio"]), "nome": nome_base(nome), "distrito": distrito})
    return {"municipios": municipios, "comunidades": comunidades}


def cobertura(radios: list[dict], municipio: dict) -> dict:
    """Para um município do aviso: que rádio alcança quais comunidades afetadas e quais ficam sem rádio."""
    cod = str(municipio["codigo_ibge"])
    afetadas = [(c, chave(cod, c["nome"], c.get("distrito"))) for c in municipio["comunidades"]]
    por_radio = []
    cobertas = set()
    for r in radios:
        a = r.get("alcance") or {}
        inteiro = cod in set(a.get("municipios") or [])
        dela = {chave(c["municipio"], c["nome"], c.get("distrito")) for c in a.get("comunidades") or []}
        alcanca = [c for c, k in afetadas if inteiro or k in dela]
        if alcanca:
            cobertas.update(id(c) for c in alcanca)
            por_radio.append({"radio_id": r["id"], "municipio_inteiro": inteiro, "comunidades": len(alcanca)})
    sem = [c for c, _ in afetadas if id(c) not in cobertas]
    distrito = lambda d: "Sede" if d == municipio.get("nome") else d or "?"   # o distrito-sede tem o nome do município
    return {"radios": por_radio, "sem_radio": [f"{nome_base(c['nome'])} ({distrito(c.get('distrito'))})" for c in sem]}


def alcanca(radio: dict, municipio: str, nome: str, distrito: str | None) -> bool:
    """A rádio alcança a comunidade (pelo município inteiro ou pelo nome com o distrito)?"""
    a = radio.get("alcance") or {}
    if str(municipio) in set(a.get("municipios") or []):
        return True
    k = chave(municipio, nome, distrito or "")
    return any(chave(c["municipio"], c["nome"], c.get("distrito")) == k for c in a.get("comunidades") or [])
