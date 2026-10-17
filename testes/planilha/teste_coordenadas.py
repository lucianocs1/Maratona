"""Teste da coordenada de uma linha (nucleo/coordenadas.py), puro: sem banco e sem API.

Confere, num arquivo só, todos os casos do Passo 15 (D):
- vírgula decimal, graus/minutos/segundos (N/S/L/E/O/W), lat e lon na mesma célula, UTM (EPSG:31983);
- correção de troca e de sinal só quando exatamente uma alternativa cai na concessão (margem 50 m);
  mais de uma = correcao_ambigua; nenhuma = fora_da_concessao;
- rejeição: vazio, incompleta, texto sem número, formato, data, fórmula sem valor, NaN/Infinity, limites;
- aviso de menos de 4 casas decimais;
- os 200 postes reais do exemplo (LAT/LONG, LAT_GMS/LONG_GMS e COORD_X/COORD_Y) dão o mesmo ponto;
- Hypothesis (tortura): milhares de valores aleatórios em qualquer combinação de células nunca levantam
  exceção, e o resultado é sempre coerente (rejeitada com motivo da lista fechada; ok/corrigida dentro
  da área e dos limites); pontos gerados e formatados de vários jeitos voltam iguais; mesmo valor dá
  o mesmo resultado.

Cobertura (100% das linhas e ramificações de coordenadas.py e motivos.py):
  uv run coverage run --branch --include="*/nucleo/coordenadas.py,*/nucleo/motivos.py" testes/planilha/teste_coordenadas.py
  uv run coverage report -m --fail-under=100
Uso simples (na raiz): uv run python testes/planilha/teste_coordenadas.py
"""

import math
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import openpyxl
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from comunidades.fontes.concessao import contorno
from comunidades.nucleo import coordenadas as K
from comunidades.nucleo.motivos import FORMULA_SEM_VALOR, TEXTOS, Aviso, Correcao, Motivo

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


AREA = K.Area(contorno())
P = (-21.530443, -42.638946)            # poste real do exemplo (Leopoldina, dentro da concessão)
perto = lambda c, p=P, tol=1e-6: c.lat is not None and abs(c.lat - p[0]) < tol and abs(c.lon - p[1]) < tol


def caso(nome, c: K.Coordenada, status, motivo=None, correcao=None, ponto=None, tol=1e-6, avisos=None):
    ok = c.status == status and c.motivo == motivo and c.correcao == correcao
    ok = ok and (ponto is None or perto(c, ponto, tol)) and (avisos is None or c.avisos == avisos)
    conferir(nome, ok, repr(c))


# ---------- decimal ----------
caso("decimal com ponto (float)", K.interpretar(*P, dentro=AREA), K.OK, ponto=P, avisos=())
caso("decimal com vírgula (texto)", K.interpretar("-21,530443", "-42,638946", dentro=AREA), K.OK, ponto=P, avisos=())
caso("decimal com sinal unicode e espaços", K.interpretar(" −21.530443 ", "− 42.638946", dentro=AREA), K.OK, ponto=P)
caso("menos de 4 casas: ok com aviso", K.interpretar(-21.53, "-42,64", dentro=AREA), K.OK,
     ponto=(-21.53, -42.64), avisos=(Aviso.POUCAS_CASAS,))
caso("4 casas: sem aviso", K.interpretar("-21,5304", "-42,6389", dentro=AREA), K.OK, avisos=())
caso("número inteiro: aviso de casas", K.interpretar(-21, -42, dentro=lambda a, b: True), K.OK, avisos=(Aviso.POUCAS_CASAS,))
conferir("casas de um float com expoente (1e-05)", K.decimal(1e-05) == (1e-05, 5))
conferir("casas de um float inteiro (100.0)", K.decimal(100.0) == (100.0, 0))

# ---------- graus, minutos e segundos ----------
LAT_GMS, LON_GMS = "21°31'49.595\"S", "42°38'20.206\"W"
caso("GMS com S e W", K.interpretar(LAT_GMS, LON_GMS, dentro=AREA), K.OK, ponto=P, tol=1e-5)
caso("GMS nas colunas LAT_GMS/LONG_GMS", K.interpretar(lat_gms=LAT_GMS, lon_gms=LON_GMS, dentro=AREA), K.OK, ponto=P, tol=1e-5)
for txt in ["S 21°31'49.595\"", "21º31'49,595\"S", "-21°31'49.595\"", "21 31 49.595 S", "21°31′49.595″S",
            "21°31'49.595''S", "21°31’49.595”S", "21°31.82658'S", "s21°31'49.595"]:
    v = K.gms(txt)
    conferir(f"GMS {txt!r}", abs(v - P[0]) < 1e-5, str(v))
conferir("GMS com O (oeste) e L (leste)", K.gms("42°38'20.206\"O") < 0 < K.gms("42°38'20.206\"L"))
conferir("GMS só graus com hemisfério", K.gms("21°S") == -21.0 and K.gms("21.5°N") == 21.5 and K.gms("21,5 S") == -21.5)
caso("GMS com ponto+vírgula decimal na longitude", K.interpretar(LAT_GMS, "42°38'20,206\"W", dentro=AREA), K.OK, ponto=P, tol=1e-5)
for txt, motivo in [("21°61'S", Motivo.COORD_FORMATO), ("21°31'75\"S", Motivo.COORD_FORMATO),
                    ("-21°31'S", Motivo.COORD_FORMATO), ("N 21°31'49\"S", Motivo.COORD_FORMATO),
                    ("21 31 49", Motivo.COORD_FORMATO), ("21.5°31'S", Motivo.COORD_FORMATO),
                    ("21°31.5'10\"S", Motivo.COORD_FORMATO), ("graus", Motivo.COORD_SEM_NUMERO),
                    ("21°31'49\"S!", Motivo.COORD_FORMATO)]:
    c = K.interpretar(lat_gms=txt, lon_gms=LON_GMS, dentro=AREA)
    caso(f"GMS inválido {txt!r} -> {motivo.value}", c, K.REJEITADA, motivo)
caso("GMS inválido na coluna decimal: o motivo do decimal", K.interpretar("21 31 49", "-42.63", dentro=AREA),
     K.REJEITADA, Motivo.COORD_FORMATO)
caso("GMS que não é texto", K.interpretar(lat_gms=-21.5, lon_gms=LON_GMS, dentro=AREA), K.REJEITADA, Motivo.COORD_FORMATO)

# ---------- mesma célula ----------
for txt in ["-21.530443, -42.638946", "-21,530443; -42,638946", "-21,530443 -42,638946", "-21.530443|-42.638946",
            "-21,530443,-42,638946", f"{LAT_GMS} {LON_GMS}", f"{LAT_GMS}; {LON_GMS}"]:
    caso(f"mesma célula {txt!r}", K.interpretar(celula=txt, dentro=AREA), K.OK, ponto=P, tol=1e-5)
caso("mesma célula sem número", K.interpretar(celula="em frente à igreja", dentro=AREA), K.REJEITADA, Motivo.COORD_SEM_NUMERO)
caso("mesma célula fora do formato", K.interpretar(celula="-21.5 x -42.6 y", dentro=AREA), K.REJEITADA, Motivo.COORD_FORMATO)
caso("mesma célula com número (não texto)", K.interpretar(celula=-21.5, dentro=AREA), K.REJEITADA, Motivo.COORD_FORMATO)

# ---------- UTM ----------
X, Y = 744555, 7617295
c = K.interpretar(x=X, y=Y, dentro=AREA)
conferir("UTM 23S do poste: a menos de 5 m do LAT/LONG", c.status == K.OK and c.origem == "utm"
         and math.dist((c.lat * 111_320, c.lon * 103_600), (P[0] * 111_320, P[1] * 103_600)) < 5, repr(c))
caso("UTM com vírgula decimal (texto)", K.interpretar(x="744555,00", y="7617295,00", dentro=AREA), K.OK, ponto=P, tol=1e-4)
caso("UTM com X e Y trocados: corrigida", K.interpretar(x=Y, y=X, dentro=AREA), K.CORRIGIDA, correcao=Correcao.UTM_TROCADO,
     ponto=P, tol=1e-4)
caso("UTM trocado e fora da concessão", K.interpretar(x=7400000, y=300000, dentro=AREA), K.REJEITADA, Motivo.FORA_DA_CONCESSAO)
caso("UTM trocado sem área: não corrige", K.interpretar(x=Y, y=X), K.REJEITADA, Motivo.COORD_LIMITES)
caso("UTM no fuso mas fora da concessão", K.interpretar(x=300000, y=7400000, dentro=AREA), K.REJEITADA, Motivo.FORA_DA_CONCESSAO)
caso("UTM fora de qualquer fuso", K.interpretar(x=5, y=5, dentro=AREA), K.REJEITADA, Motivo.COORD_LIMITES)
caso("UTM em outro fuso configurado (24S)", K.interpretar(x=X, y=Y, epsg_utm=31984, dentro=AREA), K.REJEITADA,
     Motivo.FORA_DA_CONCESSAO)
caso("UTM só com X", K.interpretar(x=X, dentro=AREA), K.REJEITADA, Motivo.COORD_INCOMPLETA)
caso("UTM só com Y numa data", K.interpretar(y=datetime(2026, 1, 1), dentro=AREA), K.REJEITADA, Motivo.COORD_DATA)

# ---------- troca e sinal (só dentro da concessão) ----------
caso("lat e lon trocadas: corrigida", K.interpretar(P[1], P[0], dentro=AREA), K.CORRIGIDA, correcao=Correcao.TROCA, ponto=P)
c = K.interpretar(P[1], P[0], dentro=AREA)
conferir("a corrigida guarda o original", c.original == (P[1], P[0]) and c.origem == "decimal", repr(c))
caso("sem o sinal da latitude", K.interpretar(-P[0], P[1], dentro=AREA), K.CORRIGIDA, correcao=Correcao.SINAL_LAT, ponto=P)
caso("sem o sinal da longitude", K.interpretar(P[0], -P[1], dentro=AREA), K.CORRIGIDA, correcao=Correcao.SINAL_LON, ponto=P)
caso("sem os dois sinais", K.interpretar(-P[0], -P[1], dentro=AREA), K.CORRIGIDA, correcao=Correcao.SINAL_AMBOS, ponto=P)
caso("trocadas e sem sinal", K.interpretar(-P[1], -P[0], dentro=AREA), K.CORRIGIDA, correcao=Correcao.TROCA_E_SINAL, ponto=P)
caso("trocadas, longitude sem sinal", K.interpretar(-P[1], P[0], dentro=AREA), K.CORRIGIDA, correcao=Correcao.TROCA_E_SINAL, ponto=P)
caso("trocadas, latitude sem sinal", K.interpretar(P[1], -P[0], dentro=AREA), K.CORRIGIDA, correcao=Correcao.TROCA_E_SINAL, ponto=P)
caso("fora da concessão (São Paulo)", K.interpretar(-23.5505, -46.6333, dentro=AREA), K.REJEITADA, Motivo.FORA_DA_CONCESSAO)
caso("trocado e fora da concessão: rejeita, não adivinha", K.interpretar(-46.6333, -23.5505, dentro=AREA), K.REJEITADA,
     Motivo.FORA_DA_CONCESSAO)
caso("fora dos limites e sem correção", K.interpretar(95.123, 200.456, dentro=AREA), K.REJEITADA, Motivo.COORD_LIMITES)
caso("fora dos limites, a troca também fora", K.interpretar(-95.1234, 10.1234, dentro=AREA), K.REJEITADA, Motivo.COORD_LIMITES)
# duas alternativas dentro (área de teste com duas regiões): ambígua
duas = lambda a, b: (abs(a + 10) < 1 and abs(b + 20) < 1) or (abs(a + 20) < 1 and abs(b + 10) < 1)
caso("duas correções possíveis: rejeitada (ambígua)", K.interpretar(10.0001, -20.0001, dentro=duas), K.REJEITADA,
     Motivo.CORRECAO_AMBIGUA)
caso("dentro sem área: ok", K.interpretar(*P), K.OK, ponto=P)
caso("fora dos limites sem área: rejeitada, nada corrigido", K.interpretar(-95.1234, 10.1234), K.REJEITADA, Motivo.COORD_LIMITES)
caso("lat = lon: sem alternativa repetida", K.interpretar(-21.5304, -21.5304, dentro=AREA), K.REJEITADA, Motivo.FORA_DA_CONCESSAO)
conferir("Area: ponto que vira infinito na projeção não está dentro", AREA(89.99999, 179.9) is False)

# margem: um ponto logo fora do contorno
from shapely.geometry import Point  # noqa: E402
from shapely.ops import nearest_points, transform  # noqa: E402
from pyproj import Transformer  # noqa: E402

para_m = Transformer.from_crs(4674, 5880, always_xy=True)
para_geo = Transformer.from_crs(5880, 4674, always_xy=True)
borda = transform(para_m.transform, contorno()).boundary
de_fora = Point(para_m.transform(-43.6, -21.0))          # bem fora (oeste da concessão)
b = nearest_points(borda, de_fora)[0]
direcao = ((de_fora.x - b.x), (de_fora.y - b.y))
norma = math.hypot(*direcao)
ponto_a = lambda d: para_geo.transform(b.x + direcao[0] / norma * d, b.y + direcao[1] / norma * d)
(l30, a30), (l200, a200) = ponto_a(30), ponto_a(200)
conferir("Area: margem de 50 m (a 30 m fora do contorno entra; a 200 m não)", AREA(a30, l30) and not AREA(a200, l200),
         f"30 m: {AREA(a30, l30)} 200 m: {AREA(a200, l200)}")

# ---------- rejeições por tipo ----------
caso("vazio", K.interpretar(dentro=AREA), K.REJEITADA, Motivo.COORD_VAZIA)
caso("vazio (textos em branco)", K.interpretar("  ", "", celula=" ", lat_gms="", x="", dentro=AREA), K.REJEITADA, Motivo.COORD_VAZIA)
caso("só a latitude", K.interpretar(-21.53, None, dentro=AREA), K.REJEITADA, Motivo.COORD_INCOMPLETA)
caso("só a longitude", K.interpretar("", "-42,63", dentro=AREA), K.REJEITADA, Motivo.COORD_INCOMPLETA)
caso("só a latitude GMS", K.interpretar(lat_gms=LAT_GMS, dentro=AREA), K.REJEITADA, Motivo.COORD_INCOMPLETA)
caso("fórmula sem valor e a outra vazia", K.interpretar(FORMULA_SEM_VALOR, None, dentro=AREA), K.REJEITADA, Motivo.COORD_FORMULA)
caso("fórmula sem valor", K.interpretar(FORMULA_SEM_VALOR, -42.63, dentro=AREA), K.REJEITADA, Motivo.COORD_FORMULA)
for v in [datetime(2026, 10, 13, 8), date(2026, 10, 13), time(21, 31), timedelta(hours=21)]:
    caso(f"data na coordenada ({type(v).__name__})", K.interpretar(v, -42.63, dentro=AREA), K.REJEITADA, Motivo.COORD_DATA)
caso("verdadeiro/falso na coordenada", K.interpretar(True, -42.63, dentro=AREA), K.REJEITADA, Motivo.COORD_FORMATO)
caso("lista na coordenada", K.interpretar([1], -42.63, dentro=AREA), K.REJEITADA, Motivo.COORD_FORMATO)
for v in [float("nan"), float("inf"), float("-inf"), "NaN", "-Infinity", "inf", "+nan"]:
    caso(f"não finito {v!r}", K.interpretar(v, -42.63, dentro=AREA), K.REJEITADA, Motivo.COORD_NAO_FINITA)
for v, motivo in [("abc", Motivo.COORD_SEM_NUMERO), ("1e5", Motivo.COORD_FORMATO), ("-21.5.3", Motivo.COORD_FORMATO),
                  ("--21.5", Motivo.COORD_FORMATO), ("21 31 49", Motivo.COORD_FORMATO), ("=-21.53", Motivo.COORD_FORMATO),
                  ("<script>alert(1)</script>", Motivo.COORD_FORMATO), ("", Motivo.COORD_INCOMPLETA)]:
    caso(f"texto {v!r} -> {motivo.value}", K.interpretar(v, -42.63, dentro=AREA), K.REJEITADA, motivo)
conferir("todo código tem texto para a tela", all(m in TEXTOS for e in (Motivo, Correcao, Aviso) for m in e))
conferir("repr do marcador de fórmula", repr(FORMULA_SEM_VALOR) == "FormulaSemValor()")

# ---------- os 200 postes reais do exemplo: os 3 formatos dão o mesmo ponto ----------
ARQ = Path(__file__).resolve().parent / "exemplos" / "planilha_postes.xlsx"
wb = openpyxl.load_workbook(ARQ, read_only=True, data_only=True)
linhas = list(wb["Postes"].iter_rows(values_only=True))
cab = {n: i for i, n in enumerate(linhas[0])}
dist_max, todos_ok = 0.0, True
for r in linhas[1:]:
    d = K.interpretar(r[cab["LAT"]], r[cab["LONG"]], dentro=AREA)
    g = K.interpretar(lat_gms=r[cab["LAT_GMS"]], lon_gms=r[cab["LONG_GMS"]], dentro=AREA)
    u = K.interpretar(x=r[cab["COORD_X"]], y=r[cab["COORD_Y"]], dentro=AREA)
    todos_ok &= all(c.status == K.OK for c in (d, g, u))
    m = lambda c: (c.lat * 110_574, c.lon * 103_600)
    dist_max = max(dist_max, math.dist(m(d), m(g)), math.dist(m(d), m(u)))
conferir("200 postes reais: LAT/LONG, GMS e UTM ok e a menos de 5 m um do outro", todos_ok and dist_max < 5,
         f"todos ok: {todos_ok}, maior distância {dist_max:.2f} m")

# ---------- Hypothesis: tortura ----------
celula = st.one_of(st.none(), st.text(max_size=40), st.floats(allow_nan=True, allow_infinity=True),
                   st.integers(-10**9, 10**9), st.booleans(), st.datetimes(), st.just(FORMULA_SEM_VALOR),
                   st.sampled_from(["-21,53", "21°31'49\"S", "-42.64", "NaN", "  ", "1e400", "744555", "7617295",
                                    "-21.53, -42.64", "N", "°", "'", "S 91°", "21°59'59.9999\"S"]))
contador = {"n": 0}


@settings(max_examples=3000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(lat=celula, lon=celula, cel=celula, lat_gms=celula, lon_gms=celula, x=celula, y=celula)
def nunca_quebra_e_e_coerente(lat, lon, cel, lat_gms, lon_gms, x, y):
    contador["n"] += 1
    c = K.interpretar(lat, lon, celula=cel, lat_gms=lat_gms, lon_gms=lon_gms, x=x, y=y, dentro=AREA)
    assert c.status in (K.OK, K.CORRIGIDA, K.REJEITADA)
    if c.status == K.REJEITADA:
        assert isinstance(c.motivo, Motivo) and c.lat is None and c.lon is None and c.correcao is None
    else:
        assert c.motivo is None and math.isfinite(c.lat) and math.isfinite(c.lon)
        assert -90 <= c.lat <= 90 and -180 <= c.lon <= 180 and AREA(c.lat, c.lon)
        assert (c.correcao is not None) == (c.status == K.CORRIGIDA)
    assert c == K.interpretar(lat, lon, celula=cel, lat_gms=lat_gms, lon_gms=lon_gms, x=x, y=y, dentro=AREA)


@settings(max_examples=1500, deadline=None)
@given(lat=st.floats(-21.9, -21.2), lon=st.floats(-42.9, -42.3), virgula=st.booleans(), casas=st.integers(4, 8))
def ida_e_volta(lat, lon, virgula, casas):
    contador["n"] += 1
    fmt = lambda v: f"{v:.{casas}f}".replace(".", "," if virgula else ".")
    d = K.interpretar(fmt(lat), fmt(lon), dentro=lambda a, b: True)
    assert d.status == K.OK and d.avisos == () and abs(d.lat - lat) < 10 ** -casas and abs(d.lon - lon) < 10 ** -casas
    def gr(v, h):
        total = round(abs(v) * 3600, 4)
        g, m = int(total // 3600), int(total % 3600 // 60)
        return f"{g}°{m}'{total - g * 3600 - m * 60:.4f}\"{h}"
    g = K.interpretar(gr(lat, "S"), gr(lon, "W"), dentro=lambda a, b: True)
    assert g.status == K.OK and abs(g.lat - lat) < 1e-6 and abs(g.lon - lon) < 1e-6


for prop in (nunca_quebra_e_e_coerente, ida_e_volta):
    try:
        prop()
        conferir(f"Hypothesis: {prop.__name__}", True)
    except Exception as e:  # noqa: BLE001 (o teste mostra o contraexemplo)
        conferir(f"Hypothesis: {prop.__name__}", False, f"{type(e).__name__}: {e}"[:500])
conferir(f"Hypothesis rodou {contador['n']} casos (pelo menos 4.000)", contador["n"] >= 4000, str(contador["n"]))

for st_, nome, extra in resultados:
    print(st_, nome, f"-> {extra}" if st_ != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
