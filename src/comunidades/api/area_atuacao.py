"""Mapa das empresas e área de atuação (só o Admin do Norte; desde 15/10/2026).

O Admin do Norte vê o cadastro das empresas, a área de atuação de cada uma (os municípios do IBGE) e só CONTAGENS
(usuários, avisos no mês): nunca o conteúdo de avisos, histórico, comunidades afetadas ou pacotes. A área define onde
a empresa pode criar avisos (api/app.py recusa a UC de município fora dela). Toda mudança vai para a auditoria com o
antes e o depois; o arquivo KML/GeoJSON importado é lido em memória e descartado: só os códigos dos municípios ficam.
"""

import shapely
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..banco import acesso as banco
from ..banco import municipios_ibge
from ..nucleo import acesso as regras
from ..nucleo import area_atuacao as area_
from .acesso import exigir
from .comum import erro

rotas = APIRouter(prefix="/api")
GERENCIAR = exigir("gerenciar_empresas")


def _nomes() -> dict[str, tuple[str, str]]:
    return {c: (n, uf) for c, n, uf in municipios_ibge.lista()}


def _rotulo(codigos, nomes) -> str:
    return ", ".join(f"{nomes[c][0]}/{nomes[c][1]}" if c in nomes else c for c in codigos)


def _empresa(id_: int) -> dict:
    e = banco.empresa(id_)
    if not e:
        raise HTTPException(404, "Empresa não encontrada.")
    return e


@rotas.get("/empresas/mapa")
def mapa_das_empresas(u: dict = Depends(GERENCIAR)) -> dict:
    """Cada empresa com a situação, a área (códigos) e contagens; os contornos de todos os municípios de alguma área
    (com o ponto onde escrever); e os municípios em mais de uma área (sobreposição)."""
    areas, cont = banco.areas(), banco.contagens_empresas()
    siglas = {}
    empresas = []
    for e in banco.empresas():
        siglas[e["id"]] = e["sigla"]
        empresas.append({"id": e["id"], "sigla": e["sigla"], "nome": e["nome"], "status": e["status"],
                         "municipios": sorted(areas.get(e["id"], set())), "usuarios": cont.get(e["id"], {}).get("usuarios", 0),
                         "avisos_mes": cont.get(e["id"], {}).get("avisos_mes", 0)})
    todos = sorted(set().union(*areas.values())) if areas else []
    return {"empresas": empresas, "municipios": municipios_ibge.geojson(todos),
            "sobreposicao": area_.sobreposicoes({siglas[i]: ms for i, ms in areas.items() if i in siglas})}


@rotas.get("/empresas/{id_}/ficha")
def ficha_da_empresa(id_: int, u: dict = Depends(GERENCIAR)) -> dict:
    """Cadastro e contagens da empresa e a lista dos municípios atendidos (nada de avisos, só os números)."""
    e = _empresa(id_)
    area, cont, nomes = banco.area(id_), banco.contagens_empresas().get(id_, {}), _nomes()
    return {"empresa": {"id": e["id"], "sigla": e["sigla"], "nome": e["nome"], "status": e["status"], "dominio": e["dominio"],
                        "cnpj": regras.formatar_cnpj(e["cnpj"]) if e.get("cnpj") else None,
                        "criada_em": e["criada_em"].isoformat(timespec="seconds"), "criada_por": e.get("criada_por"),
                        "usuarios": cont.get("usuarios", 0), "avisos_mes": cont.get("avisos_mes", 0), "avisos_total": cont.get("avisos_total", 0),
                        "municipios": [{"codigo_ibge": c, "nome": nomes.get(c, (c, ""))[0], "uf": nomes.get(c, ("", ""))[1]}
                                       for c in sorted(area, key=lambda c: (nomes.get(c, ("", ""))[1], nomes.get(c, (c, ""))[0]))]}}


@rotas.get("/municipios-ibge")
def municipios_do_brasil(u: dict = Depends(GERENCIAR)) -> dict:
    """Todos os municípios do IBGE (código, nome, UF), para a lista com busca do cadastro da área."""
    return {"municipios": [{"codigo_ibge": c, "nome": n, "uf": uf} for c, n, uf in municipios_ibge.lista()]}


@rotas.get("/municipios-ibge/{uf}/mapa")
def municipios_da_uf(uf: str, u: dict = Depends(GERENCIAR)) -> dict:
    """Os contornos dos municípios de uma UF, para marcar a área clicando no mapa."""
    uf = uf.upper()
    if not (len(uf) == 2 and uf.isalpha()):
        raise HTTPException(422, "UF inválida.")
    return municipios_ibge.da_uf(uf)


class NovaArea(BaseModel):
    codigos: list[str] = Field(max_length=area_.MAX_MUNICIPIOS)
    confirmar: bool = False


@rotas.put("/empresas/{id_}/area")
def salvar_area(id_: int, dados: NovaArea, u: dict = Depends(GERENCIAR)) -> dict:
    """Sem confirmar: só o resumo (X municípios, Y novos, Z removidos, W em sobreposição), nada muda. Confirmado: troca
    a área e grava na auditoria quem fez e o antes e o depois (a lista de municípios)."""
    e = _empresa(id_)
    try:
        codigos = area_.normalizar_codigos(dados.codigos)
    except area_.AreaInvalida as x:
        raise erro(422, str(x), "codigos") from None
    if (faltam := sorted(set(codigos) - municipios_ibge.existentes(codigos))):
        raise erro(422, f"{len(faltam)} código(s) que não são municípios do IBGE.", "codigos")
    areas, siglas = banco.areas(), {x["id"]: x["sigla"] for x in banco.empresas()}
    antes = areas.get(id_, set())
    r = area_.resumo(antes, codigos, {siglas[i]: ms for i, ms in areas.items() if i != id_ and i in siglas})
    nomes = _nomes()
    for k in ("novos", "removidos"):
        r[k] = [{"codigo_ibge": c, "nome": nomes.get(c, (c, ""))[0], "uf": nomes.get(c, ("", ""))[1]} for c in r[k]]
    for s in r["sobreposicao"]:
        s["nome"], s["uf"] = nomes.get(s["codigo_ibge"], (s["codigo_ibge"], ""))
    if not dados.confirmar:
        return {"resumo": r, "salvo": False}
    if not r["mudou"]:
        raise erro(409, "Nada mudou na área de atuação.", "codigos")
    detalhe = (f"{e['nome']} ({e['sigla']}): {len(antes)} → {len(codigos)} municípios"
               f"; incluídos: {_rotulo([x['codigo_ibge'] for x in r['novos']], nomes) or '—'}"
               f"; removidos: {_rotulo([x['codigo_ibge'] for x in r['removidos']], nomes) or '—'}"
               + (f"; em sobreposição: {len(r['sobreposicao'])}" if r["sobreposicao"] else ""))
    banco.salvar_area(id_, codigos, "alterou área de atuação", detalhe, u["id"])
    return {"resumo": r, "salvo": True}


@rotas.post("/empresas/{id_}/area/arquivo")
async def area_do_arquivo(id_: int, arquivo: UploadFile = File(...), u: dict = Depends(GERENCIAR)) -> dict:
    """KML ou GeoJSON da concessão -> os municípios com pelo menos metade da área dentro. O arquivo é lido em memória e
    descartado (nada dele é guardado); nada muda até a pessoa confirmar no PUT da área."""
    e = _empresa(id_)
    dados = await arquivo.read(area_.MAX_ARQUIVO + 1)
    try:
        g = area_.geometria_do_arquivo(arquivo.filename, dados)
    except area_.AreaInvalida as x:
        banco.registrar("arquivo de área recusado", f"{e['sigla']}: {x}", u["id"], id_)
        raise erro(422, str(x), "arquivo") from None
    finally:
        del dados
    codigos = municipios_ibge.que_cruzam(shapely.to_wkb(g))
    if not codigos:
        raise erro(422, "Nenhum município do IBGE tem pelo menos metade da área dentro dos polígonos do arquivo.", "arquivo")
    banco.registrar("leu arquivo de área", f"{e['sigla']}: {len(codigos)} municípios (o arquivo não foi guardado)", u["id"], id_)
    return {"codigos": codigos}
