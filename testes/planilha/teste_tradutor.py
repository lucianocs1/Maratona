"""Teste do tradutor da planilha (nucleo/planilha.py) e do esquema fechado do JSON (nucleo/esquema_planilha.py).

Puro (sem banco e sem API). Confere:
- planilha_postes.xlsx: as abas Modelo e Postes dão os mesmos pontos no essencial (linha, uc, lat, lon,
  equipamento_vital, classe, status); nenhum nome nem valor de NOME, NUM_CASA, MEDIDOR ou NUM_CONTA no JSON;
- o JSON gerado sempre passa no esquema; JSON adulterado (campo a mais, tipo errado, NaN, código fora da
  lista, conta que não fecha, UC duas vezes, linha fora de ordem, ok sem coordenada...) é recusado;
- reprodutibilidade: o mesmo arquivo dá os mesmos bytes (fora o envelope: empresa, gerado_em, gerado_por);
- UC vazia, inválida e repetida (a primeira entra com aviso; as seguintes são rejeitadas com a linha da
  primeira); célula com mais de 200 caracteres; fórmula e data; textos limpos e cortados; local de
  endereço só com a rua, URBANO/RURAL não é local; equipamento vital (sim, não, vazio, inválido, sem coluna);
- avisos de grupo: coordenada repetida, a mesma coordenada em muitas UCs, ponto isolado;
- conta fechada: se não fechar, ContaNaoFecha e nada é entregue;
- Hypothesis (tortura): milhares de planilhas aleatórias e malformadas nunca levantam exceção não
  tratada, a conta sempre fecha, o JSON sempre passa no esquema e nada é aceito em silêncio;
- desempenho: 50.000 linhas.

Cobertura (100% das linhas e ramificações dos 4 módulos do tradutor), junto com teste_coordenadas.py:
  uv run coverage erase
  uv run coverage run -a --branch --include="*/nucleo/coordenadas.py,*/nucleo/motivos.py,*/nucleo/planilha.py,*/nucleo/esquema_planilha.py" testes/planilha/teste_coordenadas.py
  uv run coverage run -a --branch --include="(o mesmo)" testes/planilha/teste_tradutor.py
  uv run coverage report -m --fail-under=100
Uso simples (na raiz): uv run python testes/planilha/teste_tradutor.py
"""

import io
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import openpyxl
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from comunidades.fontes.concessao import contorno
from comunidades.nucleo import coordenadas as K
from comunidades.nucleo import esquema_planilha as E
from comunidades.nucleo import planilha as P
from comunidades.nucleo.motivos import FORMULA_SEM_VALOR, Aviso, Correcao, Motivo

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


AREA = K.Area(contorno())
PAR = P.Parametros(dentro=AREA)
ARQ = {"nome": "teste.xlsx", "sha256": "a" * 64, "formato": "xlsx", "aba": "Modelo", "colunas_ignoradas": 0}


def montar(cab, linhas, par=PAR, envelope=("EMG", "2026-10-13T12:00", "Fulana (Operador)"), arquivo=None):
    """Monta o JSON a partir de um cabeçalho e de linhas (a linha 1 é o cabeçalho)."""
    numeradas = [(i + 2, list(r)) for i, r in enumerate(linhas)]
    return P.montar(P.campos_por_indice(cab), cab, numeradas, par, arquivo=arquivo or ARQ,
                    empresa=envelope[0], gerado_em=envelope[1], gerado_por=envelope[2])


def aba(nome_arq, aba_):
    wb = openpyxl.load_workbook(Path(__file__).resolve().parent / "exemplos" / nome_arq, read_only=True, data_only=True)
    linhas = list(wb[aba_].iter_rows(values_only=True))
    return [str(c) for c in linhas[0]], [list(r) for r in linhas[1:]]


CAB = ["uc", "latitude", "longitude", "equipamento_vital", "classe", "local"]
P0 = (-21.530443, -42.638946)

# ---------- exemplo oficial: Modelo x Postes ----------
cm, lm = aba("planilha_postes.xlsx", "Modelo")
cp, lp = aba("planilha_postes.xlsx", "Postes")
jm, jp = montar(cm, lm), montar(cp, lp)
essencial = lambda j: [(p.linha, p.uc, round(p.lat, 6), round(p.lon, 6), p.equipamento_vital, p.classe, p.status) for p in j.pontos]
conferir("Modelo e Postes: os mesmos 200 pontos no essencial", essencial(jm) == essencial(jp) and len(jm.pontos) == 200,
         str([a for a, b in zip(essencial(jm), essencial(jp)) if a != b][:2]))
conferir("Modelo: as 200 linhas ok e 16 com equipamento vital", jm.resumo.ok == 200 and jm.resumo.equipamento_vital.sim == 16,
         jm.resumo.model_dump_json())
conferir("Postes: local vem da rua do ENDERECO; transformador e circuito mantidos",
         jp.pontos[0].local == "Rua 792" and jp.pontos[0].transformador == "TR3286" and jp.pontos[0].circuito == "CIR350",
         repr(jp.pontos[0]))
conferir("Modelo: local URBANO/RURAL não vira local", all(p.local is None for p in jm.pontos))
texto_json = E.texto(jp)
# o bairro é lido desde a escolha de quem será desligado (filtro por bairro, nucleo/selecao.py)
vazou = [c for c in ("NOME", "NUM_CASA", "MEDIDOR", "NUM_CONTA") if c in texto_json]
vazou += [v for r in lp for v in [r[cp.index("NOME")]] if str(v) in texto_json]
conferir("JSON da aba Postes: nada de NOME, NUM_CASA, MEDIDOR, NUM_CONTA (nem os valores do NOME)", not vazou, str(vazou[:3]))
conferir("colunas reconhecidas na aba Postes", jp.colunas == ("uc", "latitude", "longitude", "equipamento_vital", "classe",
         "local", "transformador", "circuito", "conjunto", "bairro", "situacao", "lat_gms", "lon_gms", "coord_x", "coord_y"), str(jp.colunas))
jc = montar(*aba("planilha_postes_certo.xlsx", "Postes"))
conferir("planilha_postes_certo: NUMCDC como UC, vital a confirmar (sem a coluna)", jc.resumo.ok == 200
         and jc.resumo.equipamento_vital.a_confirmar == 200 and jc.pontos[0].uc == "872246", jc.resumo.model_dump_json())

# ---------- reprodutibilidade ----------
outra = montar(cp, lp, envelope=("Outra", "2030-01-01T00:00", "Beltrano (Admin da empresa)"))
conferir("mesmo arquivo, mesma versão: os mesmos bytes (fora o envelope)", E.conteudo(jp) == E.conteudo(outra)
         and E.texto(jp) != E.texto(outra))
conferir("o JSON grava a versão do tradutor", jp.tradutor == P.VERSAO_TRADUTOR and json.loads(E.texto(jp))["formato"] == "farol-planilha")
conferir("o texto do JSON volta igual pelo esquema", E.validar_json(E.texto(jp)) == jp)

# ---------- JSON adulterado ----------
base = json.loads(E.texto(jm))


def adulterado(nome, mexer, texto=None):
    d = json.loads(json.dumps(base))
    if mexer:
        mexer(d)
    try:
        E.validar_json(texto if texto is not None else json.dumps(d))
        conferir(f"JSON adulterado recusado: {nome}", False)
    except ValidationError:
        conferir(f"JSON adulterado recusado: {nome}", True)


adulterado("campo a mais na raiz", lambda d: d.update(extra=1))
adulterado("campo a mais num ponto", lambda d: d["pontos"][0].update(nome="Fulano"))
adulterado("tipo errado (linha como texto)", lambda d: d["pontos"][0].update(linha="2"))
adulterado("tipo errado (vital como texto)", lambda d: d["pontos"][0].update(equipamento_vital="sim"))
adulterado("NaN na latitude", None, json.dumps(base).replace(str(base["pontos"][0]["lat"]), "NaN", 1))
adulterado("Infinity na longitude", None, json.dumps(base).replace(str(base["pontos"][0]["lon"]), "Infinity", 1))
adulterado("motivo fora da lista fechada", lambda d: d["pontos"][0].update(status="rejeitada", motivo="porque sim"))
adulterado("rejeitada sem motivo", lambda d: (d["pontos"][0].update(status="rejeitada"), d["resumo"].update(ok=199, rejeitadas=1)))
adulterado("ok sem coordenada", lambda d: d["pontos"][0].update(lat=None, lon=None))
adulterado("ok com motivo", lambda d: d["pontos"][0].update(motivo="uc_vazia"))
adulterado("corrigida sem correção", lambda d: (d["pontos"][0].update(status="corrigida"), d["resumo"].update(ok=199, corrigidas=1)))
adulterado("só a latitude", lambda d: (d["pontos"][0].update(status="rejeitada", motivo="uc_vazia", lon=None),
                                       d["resumo"].update(ok=199, rejeitadas=1)))
adulterado("repete_linha fora da uc_repetida", lambda d: d["pontos"][0].update(repete_linha=3))
adulterado("rejeitada com correção", lambda d: (d["pontos"][0].update(status="rejeitada", motivo="uc_vazia", correcao="sinal_da_latitude"),
                                                d["resumo"].update(ok=199, rejeitadas=1)))
adulterado("conta não fecha (ok a mais)", lambda d: d["resumo"].update(ok=201))
adulterado("total diferente das linhas do arquivo", lambda d: d["arquivo"].update(linhas=199))
adulterado("avisos não batem", lambda d: d["resumo"].update(avisos=d["resumo"]["avisos"] + 1))
adulterado("equipamento vital não bate", lambda d: d["resumo"]["equipamento_vital"].update(sim=0))
adulterado("UC duas vezes", lambda d: d["pontos"][1].update(uc=d["pontos"][0]["uc"]))
adulterado("linhas fora de ordem", lambda d: d["pontos"].reverse())
adulterado("latitude fora dos limites", lambda d: d["pontos"][0].update(lat=95.0))
adulterado("sha256 inválido", lambda d: d["arquivo"].update(sha256="xyz"))
adulterado("versão do formato diferente", lambda d: d.update(versao=2))
adulterado("data em formato livre", lambda d: d.update(gerado_em="ontem"))
adulterado("texto que não é JSON", None, "<script>alert(1)</script>")

# ---------- regras de cada linha ----------
L = lambda *r: list(r)
j = montar(CAB, [
    L("1", *P0, "sim", "residencial", "Rua A"),                       # 2 ok
    L("", *P0, "não", "", ""),                                        # 3 uc vazia
    L(FORMULA_SEM_VALOR, *P0, "não", "", ""),                         # 4 uc fórmula
    L("x" * 41, *P0, "não", "", ""),                                  # 5 uc longa
    L("6", *P0, "não", "", "y" * 201),                                # 6 célula longa
    L("1", -21.5306, -42.6390, "não", "", ""),                        # 7 uc repetida (a 2 entrou)
    L("8", FORMULA_SEM_VALOR, -42.63, "não", "", ""),                 # 8 coordenada com fórmula
    L("9", datetime(2026, 1, 1), -42.63, "não", "", ""),              # 9 coordenada com data
    L("10", -P0[0], P0[1], "talvez", "Comercial​\x07  Rural", "URBANO"),   # 10 corrigida (sinal), vital inválido
    L("11", -23.55, -46.63, "", "", ""),                              # 11 fora da concessão (São Paulo)
    L(11.0, -21.5401, -42.6501, True, "c" * 45, FORMULA_SEM_VALOR),   # 12 uc float, vital bool, classe cortada, local fórmula
    L(True, *P0, "não", "", ""),                                      # 13 uc booleana
    L(float("nan"), *P0, "não", "", ""),                              # 14 uc NaN
    L("15", -21.52, -42.63, FORMULA_SEM_VALOR, None, None),           # 15 vital fórmula, poucas casas
])
pt = {p.linha: p for p in j.pontos}
conferir("linha ok", pt[2].status == "ok" and pt[2].uc == "1" and pt[2].equipamento_vital is True and pt[2].local == "Rua A", repr(pt[2]))
conferir("uc vazia, fórmula, longa, booleana e NaN: rejeitadas",
         [pt[n].motivo for n in (3, 4, 5, 13, 14)] == [Motivo.UC_VAZIA, Motivo.UC_INVALIDA, Motivo.UC_INVALIDA,
                                                         Motivo.UC_INVALIDA, Motivo.UC_INVALIDA])
conferir("célula com mais de 200 caracteres: rejeitada, com a UC e o vital registrados", pt[6].motivo == Motivo.CELULA_LONGA
         and pt[6].uc == "6" and pt[6].equipamento_vital is False, repr(pt[6]))
jl = montar(["uc", "latitude", "longitude", "equipamento_vital"], [L("1", *P0, "s" * 201), L("u" * 201, *P0, "sim")])
conferir("célula longa no vital: vital não lido; UC longa: sem UC", jl.pontos[0].equipamento_vital is None
         and jl.pontos[0].uc == "1" and jl.pontos[1].uc is None and jl.pontos[1].equipamento_vital is True, repr(jl.pontos))
jl2 = montar(["uc", "latitude", "longitude", "local"], [L("1", *P0, "z" * 201)])
conferir("célula longa sem a coluna de vital: vital a confirmar", jl2.pontos[0].equipamento_vital is None
         and jl2.pontos[0].motivo == Motivo.CELULA_LONGA)
conferir("UC repetida: a primeira entra com aviso; a outra rejeitada apontando a linha 2",
         Aviso.UC_REPETIDA in pt[2].avisos and pt[7].status == "rejeitada" and pt[7].motivo == Motivo.UC_REPETIDA
         and pt[7].repete_linha == 2, f"{pt[2].avisos} {pt[7]!r}")
conferir("coordenada com fórmula e com data: rejeitadas", pt[8].motivo == Motivo.COORD_FORMULA and pt[9].motivo == Motivo.COORD_DATA)
conferir("corrigida guarda o original e o que mudou", pt[10].status == "corrigida" and pt[10].correcao == Correcao.SINAL_LAT
         and pt[10].original == (round(-P0[0], 7), round(P0[1], 7)), repr(pt[10]))
conferir("texto limpo (sem invisível nem controle), URBANO não é local, vital inválido vira a confirmar",
         pt[10].classe == "Comercial Rural" and pt[10].local is None and pt[10].equipamento_vital is None
         and Aviso.VITAL_INVALIDO in pt[10].avisos, repr(pt[10]))
conferir("fora da concessão: rejeitada, com o ponto lido para o mapa", pt[11].motivo == Motivo.FORA_DA_CONCESSAO
         and pt[11].lat == -23.55, repr(pt[11]))
conferir("uc 11.0 vira '11'; vital booleano; classe cortada em 40 com aviso; local com fórmula ignorado com aviso",
         pt[12].uc == "11" and pt[12].equipamento_vital is True and pt[12].classe == "c" * 40
         and Aviso.TEXTO_CORTADO in pt[12].avisos and pt[12].local is None and Aviso.CAMPO_FORMULA in pt[12].avisos, repr(pt[12]))
conferir("vital com fórmula: a confirmar com aviso; poucas casas: aviso", pt[15].equipamento_vital is None
         and Aviso.CAMPO_FORMULA in pt[15].avisos and Aviso.POUCAS_CASAS in pt[15].avisos, repr(pt[15]))
conferir("resumo: 14 linhas = 3 ok + 1 corrigida + 10 rejeitadas", (j.resumo.total, j.resumo.ok, j.resumo.corrigidas,
         j.resumo.rejeitadas) == (14, 3, 1, 10), j.resumo.model_dump_json())
conferir("vital do resumo: só das linhas que entram (2 sim, 2 a confirmar)", j.resumo.equipamento_vital.model_dump() ==
         {"sim": 2, "nao": 0, "a_confirmar": 2}, j.resumo.equipamento_vital.model_dump_json())
# a primeira ocorrência rejeitada pela coordenada: a segunda entra
j2 = montar(CAB, [L("7", "", "", "", "", ""), L("7", *P0, "", "", "")])
conferir("UC repetida cuja primeira linha foi rejeitada: a segunda entra", j2.pontos[1].status == "ok"
         and j2.pontos[0].motivo == Motivo.COORD_VAZIA and not j2.pontos[1].avisos, repr(j2.pontos))
# endereço e vital sem coluna; vital vazio com coluna = não
j3 = montar(["uc", "latitude", "longitude", "ENDERECO"], [L("1", *P0, "Rua das Flores, 123, casa 2 - CEP 36700-000")])
conferir("coluna de endereço: só a rua; sem coluna de vital: a confirmar", j3.pontos[0].local == "Rua das Flores"
         and j3.pontos[0].equipamento_vital is None)
j4 = montar(CAB, [L("1", *P0, None, None, None), L("2", -21.5306, -42.6390, "", None, None)])
conferir("vital vazio com a coluna: não", [p.equipamento_vital for p in j4.pontos] == [False, False])
j5 = montar(["uc", "latitude", "longitude", "classe"], [L("1", *P0, datetime(2026, 1, 2, 3, 4)), L("2", -21.5306, -42.6390, 12.5)])
conferir("classe com data ou número: vira texto", [p.classe for p in j5.pontos] == ["2026-01-02T03:04:00", "12.5"])

# ---------- avisos de grupo ----------
muitas = [L(str(i), *P0, "", "", "") for i in range(10)] + [L("isolado", -21.1306, -42.3664, "", "", ""),   # Muriaé, ~50 km
                                                            L("par", -21.5306, -42.6390, "", "", "")]
j6 = montar(CAB, muitas)
a = {p.uc: p.avisos for p in j6.pontos}
conferir("10 UCs na mesma coordenada: repetida e muitas UCs", Aviso.COORD_DUPLICADA in a["0"] and Aviso.COORD_MUITAS_UCS in a["0"])
conferir("ponto a mais de 20 km de todos: isolado", j6.pontos[10].status == "ok" and Aviso.PONTO_ISOLADO in a["isolado"] and Aviso.PONTO_ISOLADO not in a["par"],
         str(a["isolado"]))
j7 = montar(CAB, [L("1", *P0, "", "", ""), L("2", *P0, "", "", "")], par=P.Parametros(dentro=AREA, muitas_ucs=3))
conferir("2 na mesma coordenada (limite 3): repetida, sem 'muitas'", j7.pontos[0].avisos == (Aviso.COORD_DUPLICADA,))
conferir("um ponto só: sem aviso de isolado", not montar(CAB, [L("1", *P0, "", "", "")]).pontos[0].avisos)

# ---------- conta fechada ----------
original = P._avisos_de_grupo
P._avisos_de_grupo = lambda pontos, p: pontos[0].update(status="sumiu")   # sabotagem: uma linha sem status válido
try:
    montar(CAB, [L("1", *P0, "", "", "")])
    conferir("conta que não fecha: ContaNaoFecha, nada entregue", False)
except P.ContaNaoFecha:
    conferir("conta que não fecha: ContaNaoFecha, nada entregue", True)
finally:
    P._avisos_de_grupo = original
conferir("colunas (nomes) a partir do cabeçalho", P.colunas(["NUMCDC", "Lat", "LONG", "x1"]) ==
         {"uc": "NUMCDC", "latitude": "Lat", "longitude": "LONG"})

# ---------- o restante do módulo ----------
j8 = montar(CAB, [L("123.0", *P0, "", "", ""), L("123", -21.5306, -42.6390, "", "", ""), L("123", -21.5310, -42.6395, "", "", "")])
conferir("uc '123.0' (csv exportado) vira '123'; a 3ª repetição também aponta a linha 2, um aviso só na primeira",
         j8.pontos[0].uc == "123" and [p.repete_linha for p in j8.pontos[1:]] == [2, 2]
         and j8.pontos[0].avisos.count(Aviso.UC_REPETIDA) == 1, repr(j8.pontos))
conferir("serve: uc e uma fonte completa de coordenada", P.serve({"uc": 0, "latitude": 1, "longitude": 2})
         and P.serve({"uc": 0, "coord_x": 1, "coord_y": 2}) and not P.serve({"uc": 0, "latitude": 1})
         and not P.serve({"latitude": 1, "longitude": 2}))
conferir("so_rua: nome de via com número fica; número da casa sai", P.so_rua("Beco Número 399") == "Beco Número 399"
         and P.so_rua("Rua Sete de Setembro 120") == "Rua Sete de Setembro" and P.so_rua("Rua 15, 230") == "Rua 15")
v = P.validas(j)
conferir("validas: só ok e corrigidas, do JSON validado", list(v["LINHA"]) == [2, 10, 12, 15]
         and list(v.columns[:7]) == ["LINHA", "UC", "LAT", "LON", "VITAL", "CLASSE", "LOCAL"], str(list(v["LINHA"])))
modelo = [linha.split(";") for linha in P.modelo_csv().strip().split("\n")]
jm2 = montar(modelo[0], modelo[1:])
conferir("o modelo para baixar é traduzido sem problema", jm2.resumo.ok == 2 and jm2.resumo.rejeitadas == 0, jm2.resumo.model_dump_json())

# ---------- Hypothesis: planilhas aleatórias e malformadas ----------
celula = st.one_of(st.none(), st.text(max_size=30), st.text(min_size=195, max_size=230), st.floats(allow_nan=True, allow_infinity=True),
                   st.integers(-10**12, 10**12), st.booleans(), st.datetimes(), st.just(FORMULA_SEM_VALOR),
                   st.sampled_from(["-21,5304", "-42,6389", "21°31'49\"S", "42°38'20\"W", "SIM", "não", "talvez", "URBANO",
                                    "Rua das Flores, 12", "744555", "7617295", "-21.53, -42.64", "=HYPERLINK(\"x\")"]))
nomes = st.lists(st.sampled_from(["uc", "NUMCDC", "latitude", "LAT", "longitude", "LONG", "LAT_GMS", "LONG_GMS", "COORD_X",
                                  "COORD_Y", "coordenada", "equipamento_vital", "classe", "local", "ENDERECO", "TRANSFORMADOR",
                                  "CIRCUITO", "NOME", "", "outra"]), min_size=1, max_size=10)
contador = {"n": 0}


@settings(max_examples=1500, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(cab=nomes, dados=st.data())
def tortura(cab, dados):
    contador["n"] += 1
    linhas = dados.draw(st.lists(st.lists(celula, min_size=len(cab), max_size=len(cab)), max_size=12))
    m = montar(cab, linhas)                                    # nunca levanta: o esquema e a conta passaram
    r = m.resumo
    assert r.total == len(linhas) == r.ok + r.corrigidas + r.rejeitadas == len(m.pontos)
    for p in m.pontos:                                         # nada aceito em silêncio
        if p.status == "rejeitada":
            assert p.motivo is not None
        else:
            assert p.uc and p.motivo is None and AREA(p.lat, p.lon)
            assert all(len(x or "") <= 80 for x in (p.classe, p.local, p.transformador, p.circuito))
    assert E.validar_json(E.texto(m)) == m and E.conteudo(m) == E.conteudo(montar(cab, linhas))


try:
    tortura()
    conferir("Hypothesis: planilhas aleatórias nunca quebram, a conta fecha, o esquema passa, nada em silêncio", True)
except Exception as e:  # noqa: BLE001
    conferir("Hypothesis: planilhas aleatórias nunca quebram, a conta fecha, o esquema passa, nada em silêncio", False,
             f"{type(e).__name__}: {e}"[:600])
conferir(f"Hypothesis rodou {contador['n']} planilhas (pelo menos 1.000)", contador["n"] >= 1000, str(contador["n"]))

# ---------- desempenho: 50.000 linhas ----------
n = 50_000
grandes = [[f"{i:010d}", -21.5 - (i % 900) / 10_000, -42.6 - (i % 700) / 10_000, "não", "residencial", f"Rua {i % 300}"]
           for i in range(n)]
inicio = time.perf_counter()
jg = montar(CAB, grandes)
seg = time.perf_counter() - inicio
conferir(f"50.000 linhas traduzidas e validadas em {seg:.1f} s (limite 60 s)", jg.resumo.total == n and seg < 60,
         jg.resumo.model_dump_json())

for st_, nome, extra in resultados:
    print(st_, nome, f"-> {extra}" if st_ != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
