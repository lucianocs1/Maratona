"""Teste da escolha de quem será desligado (nucleo/selecao.py), puro (sem banco e sem API).

Confere, na réplica da base de clientes (testes/planilha/exemplos/demo/6_base_clientes.xlsx) e em planilhas
montadas aqui:
- a planilha inteira: entram todas, menos as inativas (salvo incluir_inativas);
- filtros: dentro de um filtro vale qualquer valor marcado; entre filtros, todos; inativas fora;
- área desenhada: as mesmas linhas de uma conta à força bruta; comunidades clicadas; mapa + filtro;
- conta fechada: lidas = inativas fora + não escolhidas + escolhidas; escolhidas = ok + corrigidas + rejeitadas;
- equipamento vital: rejeitado dentro da escolha bloqueia; fora dela não bloqueia; sem coordenada, com o mapa,
  entra e bloqueia; inativo com vital fora não bloqueia;
- a mesma escolha (valores em outra ordem, repetidos) dá o mesmo critério, o mesmo sha256 e as mesmas linhas;
- critério inválido recusado (campo a mais, planilha com filtro, escolha vazia, anel aberto, vértices demais);
- a descrição (o que vai para a auditoria) cita o critério e as contagens, nunca uma UC.
Uso (na raiz): uv run python -W ignore testes/nucleo/teste_selecao.py
"""

import sys
from pathlib import Path

from pydantic import ValidationError

from comunidades.api import leitura
from comunidades.nucleo import planilha as P
from comunidades.nucleo import selecao as S
from comunidades.nucleo import travas

REPLICA = Path(__file__).resolve().parents[2] / "testes" / "planilha" / "exemplos" / "demo" / "6_base_clientes.xlsx"
resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def montar_tabela(t):
    return P.montar(t.campos, t.cabecalho, t.linhas, P.Parametros(dentro=None, epsg_utm=31983),
                    arquivo={"nome": "base.xlsx", "sha256": "0" * 64, "formato": t.formato, "aba": t.aba,
                             "colunas_ignoradas": t.colunas_ignoradas},
                    empresa="teste", gerado_em="2026-10-16T10:00", gerado_por="teste")


def montar(cab, linhas):
    campos = P.campos_por_indice(cab)
    return P.montar(campos, cab, [(i + 2, list(r)) for i, r in enumerate(linhas)], P.Parametros(dentro=None),
                    arquivo={"nome": "t.csv", "sha256": "0" * 64, "formato": "csv", "aba": None, "colunas_ignoradas": 0},
                    empresa="teste", gerado_em="2026-10-16T10:00", gerado_por="teste")


def fecha(e: S.Escolha) -> bool:
    c = e.conta
    return (c["lidas"] == c["inativas_fora"] + c["nao_escolhidas"] + c["escolhidas"]
            and c["escolhidas"] == c["ok"] + c["corrigidas"] + c["rejeitadas"] == len(e.modelo.pontos) == e.modelo.resumo.total)


def caixa(lon0, lat0, lon1, lat1):
    return [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]


m = montar_tabela(leitura.ler_tabela(REPLICA.read_bytes()))
ativas = [p for p in m.pontos if not P.inativa(p.situacao)]
sem = {}

# ---------- a planilha inteira ----------
e = S.aplicar(m, S.Criterio(modo="planilha"), sem)
conferir(f"planilha inteira: {len(ativas)} de {m.resumo.total} (inativas fora: {e.conta['inativas_fora']})",
         e.conta["escolhidas"] == len(ativas) and e.conta["inativas_fora"] == m.resumo.total - len(ativas) and fecha(e), str(e.conta))
conferir("inativas fora contadas por bairro e por circuito (nunca a UC)",
         sum(e.inativas["bairro"].values()) == sum(e.inativas["circuito"].values()) == e.conta["inativas_fora"]
         and not any(p.uc in str(e.inativas) for p in m.pontos))
e2 = S.aplicar(m, S.Criterio(modo="planilha", incluir_inativas=True), sem)
conferir("planilha inteira com as inativas: todas", e2.conta["escolhidas"] == m.resumo.total and e2.conta["inativas_fora"] == 0 and fecha(e2))

# ---------- filtros ----------
circuitos = sorted({p.circuito for p in m.pontos})
bairros = sorted({p.bairro for p in m.pontos if p.bairro})
c1 = circuitos[0]
e = S.aplicar(m, S.Criterio(modo="escolha", circuito=(c1,)), sem)
conferir(f"filtro circuito {c1}: só as ativas dele", set(e.linhas) == {p.linha for p in ativas if p.circuito == c1} and fecha(e), str(e.conta))
e = S.aplicar(m, S.Criterio(modo="escolha", circuito=tuple(circuitos[:2])), sem)
conferir("dois circuitos: vale qualquer um (OU)", set(e.linhas) == {p.linha for p in ativas if p.circuito in circuitos[:2]} and fecha(e))
b1 = max(bairros, key=lambda b: sum(p.bairro == b for p in ativas))
e = S.aplicar(m, S.Criterio(modo="escolha", circuito=(c1,), bairro=(b1,)), sem)
conferir("circuito e bairro: tem de atender aos dois (E)",
         set(e.linhas) == {p.linha for p in ativas if p.circuito == c1 and p.bairro == b1} and fecha(e), str(e.conta))
trafo = next(p.transformador for p in ativas)
e = S.aplicar(m, S.Criterio(modo="escolha", transformador=(trafo,), conjunto=(next(p.conjunto for p in ativas if p.transformador == trafo),)), sem)
conferir("transformador e conjunto", set(e.linhas) == {p.linha for p in ativas if p.transformador == trafo} and fecha(e))
e = S.aplicar(m, S.Criterio(modo="escolha", circuito=("CIR-QUE-NAO-EXISTE",)), sem)
conferir("filtro sem nenhuma UC: zero escolhidas, a conta fecha", e.conta["escolhidas"] == 0 and fecha(e))

# ---------- área desenhada e comunidades ----------
lats = sorted(p.lat for p in ativas)
lons = sorted(p.lon for p in ativas)
area = caixa(lons[len(lons) // 4], lats[len(lats) // 4], lons[3 * len(lons) // 4], lats[3 * len(lats) // 4])
forca = {p.linha for p in ativas if area[0][0][0] <= round(p.lon, 5) <= area[0][1][0] and area[0][0][1] <= round(p.lat, 5) <= area[0][2][1]}
e = S.aplicar(m, S.Criterio(modo="escolha", poligonos=(area,)), sem)
conferir(f"área desenhada: {len(e.linhas)} UCs, as mesmas da força bruta", set(e.linhas) == forca and 0 < len(forca) < len(ativas) and fecha(e))
e = S.aplicar(m, S.Criterio(modo="escolha", poligonos=(area,), circuito=(c1,)), sem)
conferir("área e circuito: os dois (o mapa é mais um filtro)", set(e.linhas) == {l for l in forca if any(p.linha == l and p.circuito == c1 for p in ativas)})
comunidade = {p.linha: ("3138401", "Centro" if i % 3 == 0 else "Bela Vista") for i, p in enumerate(m.pontos)}
e = S.aplicar(m, S.Criterio(modo="escolha", comunidades=({"municipio": "3138401", "nome": "Centro"},)), comunidade)
conferir("comunidade clicada: as UCs dela", set(e.linhas) == {p.linha for p in ativas if comunidade[p.linha][1] == "Centro"} and fecha(e))
e = S.aplicar(m, S.Criterio(modo="escolha", comunidades=({"municipio": "3138401", "nome": "Centro"},), poligonos=(area,)), comunidade)
conferir("comunidade + área: qualquer uma das duas (o mapa junto)",
         set(e.linhas) == {p.linha for p in ativas if comunidade[p.linha][1] == "Centro"} | forca)

# ---------- a mesma escolha, o mesmo resultado ----------
a = S.Criterio(modo="escolha", circuito=tuple(circuitos[:3]), bairro=(b1,), poligonos=(area,))
b = S.Criterio(modo="escolha", circuito=(circuitos[2], circuitos[0], circuitos[1], circuitos[0]), bairro=(b1, b1),
               poligonos=([[[x + 1e-9, y] for x, y in area[0]]],))
conferir("a mesma escolha (outra ordem, repetidos, 1e-9 de diferença) dá o mesmo critério e sha256",
         S.texto_canonico(a) == S.texto_canonico(b) and S.sha256(a) == S.sha256(b))
conferir("a mesma escolha dá as mesmas linhas e a mesma conta",
         S.aplicar(m, a, sem).linhas == S.aplicar(m, b, sem).linhas and S.aplicar(m, a, sem).conta == S.aplicar(m, b, sem).conta)

# ---------- equipamento vital: vale sobre as escolhidas ----------
CAB = ["uc", "latitude", "longitude", "equipamento_vital", "circuito", "bairro", "situacao"]
linhas = [[f"{i:05d}", -21.53 + i * 0.001, -42.64, "não", "CIR1" if i < 10 else "CIR2", "Centro", "ATIVO"] for i in range(20)]
linhas[3][1:4] = [None, None, "sim"]        # linha 5: vital sem coordenada, no CIR1
linhas[15][3] = "sim"                         # linha 17: vital no CIR2, mas inativa
linhas[15][6] = "INATIVO"
linhas[12][1:4] = ["abc", "abc", "sim"]     # linha 14: vital rejeitado no CIR2
mv = montar(CAB, linhas)
bloqueio = lambda e: [x["linha"] for x in travas.vital_bloqueio(e.modelo, set())]
e = S.aplicar(mv, S.Criterio(modo="escolha", circuito=("CIR1",)), {})
conferir("vital rejeitado DENTRO da escolha (CIR1, sem coordenada) bloqueia", bloqueio(e) == [5] and fecha(e), str(bloqueio(e)))
e = S.aplicar(mv, S.Criterio(modo="escolha", circuito=("CIR2",)), {})
conferir("vital rejeitado no CIR2 bloqueia só quem escolhe o CIR2", bloqueio(e) == [14])
area_cir1 = caixa(-42.65, -21.531, -42.63, -21.5205)   # linhas do CIR1 com coordenada (2 a 11, fora a 5)
e = S.aplicar(mv, S.Criterio(modo="escolha", poligonos=(area_cir1,)), {})
conferir("área: vital sem coordenada (linhas 5 e 14) entra (não dá para saber se está na área) e bloqueia",
         bloqueio(e) == [5, 14] and set(e.linhas) == {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14}, str(e.linhas))
e = S.aplicar(mv, S.Criterio(modo="escolha", poligonos=(area_cir1,), bairro=("Outro",)), {})
conferir("vital sem coordenada que não atende aos outros filtros fica fora", 5 not in e.linhas and not bloqueio(e))
e = S.aplicar(mv, S.Criterio(modo="escolha", circuito=("CIR2",), bairro=("Centro",)), {})
conferir("vital FORA da escolha (CIR1) não bloqueia o CIR2; o vital inativo fica fora", 5 not in e.linhas and 17 not in e.linhas)
conferir("limite de rejeição sobre as escolhidas", travas.rejeicao(e.modelo, 0.02)["total"] == e.conta["escolhidas"])

# ---------- critério inválido ----------
def recusa(nome, dados):
    try:
        S.Criterio.model_validate(dados)
        conferir(f"critério inválido recusado: {nome}", False)
    except ValidationError:
        conferir(f"critério inválido recusado: {nome}", True)


recusa("campo a mais", {"modo": "planilha", "ucs": ["1"]})
recusa("planilha inteira com filtro", {"modo": "planilha", "circuito": ["CIR1"]})
recusa("escolha sem nada", {"modo": "escolha"})
recusa("anel aberto", {"modo": "escolha", "poligonos": [[[[0, 0], [1, 0], [1, 1]]]]})
recusa("vértices demais", {"modo": "escolha", "poligonos": [[[[i / 1e5, 0] for i in range(25_000)] + [[0, 0]]]]})
recusa("valor vazio", {"modo": "escolha", "bairro": [""]})
recusa("comunidade com código inválido", {"modo": "escolha", "comunidades": [{"municipio": "31", "nome": "X"}]})
recusa("NaN na área", {"modo": "escolha", "poligonos": [[[[float("nan"), 0], [1, 0], [1, 1], [float("nan"), 0]]]]})

# ---------- o que vai para a auditoria ----------
t = S.descrever(S.Criterio(modo="escolha", poligonos=(area,)), 42, 3)
conferir("descrição da área: 'área desenhada (1 polígono, 4 vértices), 42 UCs, 3 comunidades'",
         t == "área desenhada (1 polígono, 4 vértices), 42 UCs, 3 comunidades", t)
t = S.descrever(S.Criterio(modo="escolha", circuito=("CIR771", "CIR147")), 96, 2)
conferir("descrição dos circuitos: 'circuitos CIR147, CIR771, 96 UCs, 2 comunidades'", t == "circuitos CIR147, CIR771, 96 UCs, 2 comunidades", t)
t = S.descrever(S.Criterio(modo="planilha", incluir_inativas=True), 1, 1)
conferir("descrição da planilha inteira com as inativas", t == "a planilha inteira (lista do desligamento), 1 UC, 1 comunidade (inativas incluídas)", t)
t = S.descrever(S.Criterio(modo="escolha", transformador=tuple(f"TR{i}" for i in range(20))), 20, 1)
conferir("descrição com muitos valores: os primeiros e '+N'", t.startswith("transformadores TR0, TR1") and "(+12)" in t, t)
t = S.descrever(S.Criterio(modo="escolha", poligonos=(area,), bairro=("Centro",)), 42, 3, "en")
conferir("descrição em inglês (o PDF sai no idioma do aviso)", t == "drawn area (1 polygon, 4 vertices) and neighborhood Centro, 42 UCs, 3 communities", t)
t = S.descrever(S.Criterio(modo="planilha"), 7, 2, "es")
conferir("descrição em espanhol", t == "toda la planilla (lista del corte), 7 UC, 2 comunidades", t)
r = S.resumo(S.Criterio(modo="escolha", circuito=(c1,)), S.aplicar(m, S.Criterio(modo="escolha", circuito=(c1,)), sem).conta, 2)
conferir("resumo do histórico: critério, conta e sha256, sem nenhuma UC",
         r["circuito"] == [c1] and r["conta"]["lidas"] == 400 and len(r["sha256"]) == 64 and not any(p.uc in str(r) for p in m.pontos))

for st_, nome, extra in resultados:
    print(st_, nome, f"-> {extra}" if st_ != "OK  " and extra else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
