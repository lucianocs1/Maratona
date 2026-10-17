"""Área de atuação das empresas e o mapa das empresas (desde 15/10/2026). FastAPI em processo, Postgres local.

Num esquema próprio (FAROL_ESQUEMA=teste_area, apagado no fim). Confere:
- a EMG de demonstração recebe, uma vez só, a área que já existia (os municípios da base territorial), com auditoria;
- a área salva só com confirmação, com o resumo antes (X municípios, Y novos, Z removidos, W em sobreposição) e a linha
  da auditoria com quem fez e o antes e o depois; a mesma área de novo é 409;
- a sobreposição (município em duas empresas) aparece no resumo e no mapa;
- códigos inválidos e KML/GeoJSON inválidos são recusados (script, DTD/entidade, só pontos, fora do Brasil, grande
  demais, extensão errada); o KML da concessão da EMG dá os municípios dela; nada do arquivo é guardado;
- aviso fora da área: a UC de município fora da área é rejeitada (nunca entra no aviso) e empresa sem área não gera;
- o mapa e a ficha da empresa só têm cadastro e contagens; o Admin do Norte é recusado nas rotas operacionais;
- o mapa operacional dos perfis da empresa mostra só a área dela.

Uso (na raiz): uv run python -W ignore testes/api/teste_area_atuacao.py
"""

import json
import os
import sys

os.environ["FAROL_ESQUEMA"] = "teste_area"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades import config as C  # noqa: E402
from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.simulacao import planilhas_teste  # noqa: E402

resultados = []
NOVA = "Lanterna-do-Farol-2026"
LEOPOLDINA, SAO_PAULO, CATAGUASES = "3138401", "3550308", "3115300"


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(q, args=()):
    with conectar() as c, c.cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


def pronto(email, senha):
    api_acesso._tentativas_ip.clear()
    c = TestClient(app, base_url="http://farol.teste")
    c.post("/api/entrar", json={"email": email, "senha": senha})
    c.post("/api/senha", json={"atual": senha, "nova": NOVA})
    return c


with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_area CASCADE")
senhas = {e: s for _, e, s in semear()}
farol, adm, op, con = (pronto(e, senhas[e]) for e in ("admin@farol.example", "admin@emg.example", "operador@emg.example", "consulta@emg.example"))
base = {r[0] for r in sql("SELECT codigo_ibge FROM municipio")}
emg = sql("SELECT id FROM empresa WHERE sigla = 'EMG'")[0][0]

# ---------- a área inicial da EMG ----------
area_emg = {r[0] for r in sql("SELECT codigo_ibge FROM empresa_municipio WHERE empresa_id = %s", (emg,))}
conferir("EMG: a área inicial é a concessão já carregada (os municípios da base territorial)", area_emg == base and len(base) > 0, f"{len(area_emg)} de {len(base)}")
conferir("a carga inicial está na auditoria", sql("SELECT count(*) FROM registro WHERE acao = 'área de atuação: carga inicial'")[0][0] == 1)
semear()
conferir("a carga inicial não se repete (semente de novo)", sql("SELECT count(*) FROM registro WHERE acao = 'área de atuação: carga inicial'")[0][0] == 1)

# ---------- outra empresa, sem área ----------
r = farol.post("/api/empresas", json={"nome": "Outra Distribuidora", "sigla": "OUT", "dominio": "out.example",
                                      "admin_nome": "Admin Outra", "admin_email": "admin@out.example"})
out = r.json()["empresa"]["id"]
outra = pronto("admin@out.example", r.json()["senha_temporaria"])
m = farol.get("/api/empresas/mapa").json()
e_out = next(e for e in m["empresas"] if e["sigla"] == "OUT")
conferir("mapa: a empresa sem área aparece com 0 municípios", e_out["municipios"] == [] and e_out["status"] == "ativa")
conferir("mapa: os contornos da área da EMG vêm com o ponto onde escrever a sigla",
         len(m["municipios"]["features"]) == len(base) and all(len(f["properties"]["ponto"]) == 2 for f in m["municipios"]["features"]))
conferir("mapa: só cadastro e contagens (nada de aviso, comunidade ou pacote)",
         set(e_out) == {"id", "sigla", "nome", "status", "municipios", "usuarios", "avisos_mes"} and "comunidades" not in json.dumps(m))
conferir("empresa sem área não gera aviso (422)", outra.post("/api/planilha", files={"arquivo": ("p.csv", b"uc;latitude;longitude\n1;-21.5;-42.6\n")},
                                                              data={"data": "12/11", "horario": "8h"}).status_code == 422)

# ---------- salvar a área: prévia, confirmação, auditoria, sobreposição ----------
previa = farol.put(f"/api/empresas/{out}/area", json={"codigos": [LEOPOLDINA, SAO_PAULO]})
p = previa.json()["resumo"]
conferir("prévia: 2 municípios, 2 novos, 0 removidos, 1 em sobreposição com a EMG", previa.status_code == 200 and not previa.json()["salvo"]
         and p["municipios"] == 2 and len(p["novos"]) == 2 and not p["removidos"]
         and p["sobreposicao"] == [{"codigo_ibge": LEOPOLDINA, "empresas": ["EMG"], "nome": "Leopoldina", "uf": "MG"}], json.dumps(p)[:300])
conferir("a prévia não salva nada", sql("SELECT count(*) FROM empresa_municipio WHERE empresa_id = %s", (out,))[0][0] == 0)
s = farol.put(f"/api/empresas/{out}/area", json={"codigos": [LEOPOLDINA, SAO_PAULO], "confirmar": True})
conferir("confirmado: área salva", s.status_code == 200 and s.json()["salvo"]
         and {r[0] for r in sql("SELECT codigo_ibge FROM empresa_municipio WHERE empresa_id = %s", (out,))} == {LEOPOLDINA, SAO_PAULO})
ln = sql("SELECT usuario_nome, perfil, detalhe FROM registro WHERE acao = 'alterou área de atuação' ORDER BY id DESC LIMIT 1")
conferir("auditoria: quem fez e o antes → depois com os municípios", bool(ln) and ln[0][0] == "Admin do Norte" and ln[0][1] == "admin_farol"
         and "0 → 2 municípios" in ln[0][2] and "Leopoldina/MG" in ln[0][2] and "São Paulo/SP" in ln[0][2], str(ln))
conferir("a mesma área de novo: 409 (nada a salvar)", farol.put(f"/api/empresas/{out}/area", json={"codigos": [SAO_PAULO, LEOPOLDINA], "confirmar": True}).status_code == 409)
m = farol.get("/api/empresas/mapa").json()
conferir("mapa: sobreposição detectada (Leopoldina na EMG e na OUT)", m["sobreposicao"].get(LEOPOLDINA) == ["EMG", "OUT"], str(m["sobreposicao"])[:200])
r = farol.put(f"/api/empresas/{out}/area", json={"codigos": [SAO_PAULO], "confirmar": True})
conferir("remover um município: o resumo mostra o removido", r.status_code == 200 and [x["codigo_ibge"] for x in r.json()["resumo"]["removidos"]] == [LEOPOLDINA])
conferir("código que não é município: 422", farol.put(f"/api/empresas/{out}/area", json={"codigos": ["9999999"], "confirmar": True}).status_code == 422)
conferir("código fora do formato: 422", farol.put(f"/api/empresas/{out}/area", json={"codigos": ["31384"], "confirmar": True}).status_code == 422)
f = farol.get(f"/api/empresas/{out}/ficha").json()["empresa"]
conferir("ficha: cadastro, contagens e municípios (nada de aviso)", f["sigla"] == "OUT" and f["criada_por"] == "Admin do Norte"
         and [x["nome"] for x in f["municipios"]] == ["São Paulo"] and {"usuarios", "avisos_mes", "avisos_total"} <= set(f), json.dumps(f)[:300])


# ---------- arquivo KML/GeoJSON ----------
def arquivo(nome, dados):
    return farol.post(f"/api/empresas/{out}/area/arquivo", files={"arquivo": (nome, dados)})


kml = (C.DISTRIBUIDORAS / "concessao" / "EMG.kml").read_bytes()
r = arquivo("EMG.kml", kml)
cod = set(r.json().get("codigos", []))
conferir("KML da concessão da EMG: os municípios dela (e nada guardado)", r.status_code == 200 and LEOPOLDINA in cod and len(cod & base) >= 0.9 * len(base),
         f"{r.status_code} {len(cod)} municípios, {len(cod & base)} da base")
conferir("ler o arquivo não muda a área", {x[0] for x in sql("SELECT codigo_ibge FROM empresa_municipio WHERE empresa_id = %s", (out,))} == {SAO_PAULO})
geo = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[
    [-43.2, -21.9], [-42.3, -21.9], [-42.3, -21.2], [-43.2, -21.2], [-43.2, -21.9]]]}}]}
r = arquivo("area.geojson", json.dumps(geo).encode())
conferir("GeoJSON com um polígono: devolve os municípios cobertos", r.status_code == 200 and LEOPOLDINA in r.json().get("codigos", []), r.text[:200])
ruins = {
    "com script": ("x.kml", b'<kml xmlns="http://www.opengis.net/kml/2.2"><script>alert(1)</script></kml>'),
    "com DTD/entidade": ("x.kml", b'<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY x "y">]><kml>&x;</kml>'),
    "só pontos": ("x.geojson", json.dumps({"type": "Point", "coordinates": [-42.6, -21.5]}).encode()),
    "fora do Brasil": ("x.geojson", json.dumps({"type": "Polygon", "coordinates": [[[2, 48], [3, 48], [3, 49], [2, 48]]]}).encode()),
    "grande demais": ("x.kml", b"<kml>" + b" " * (5 * 1024 * 1024 + 10) + b"</kml>"),
    "extensão errada": ("x.shp", b"qualquer coisa"),
    "não é KML": ("x.kml", b"isto nao e xml"),
    "vazio": ("x.geojson", b""),
}
recusados = {k: arquivo(*v).status_code for k, v in ruins.items()}
conferir("arquivos inválidos recusados (422): " + ", ".join(ruins), all(s == 422 for s in recusados.values()), str(recusados))
conferir("o arquivo recusado fica na auditoria (sem o conteúdo)", sql("SELECT count(*) FROM registro WHERE acao = 'arquivo de área recusado'")[0][0] == len(ruins))

# ---------- aviso fora da área ----------
planilha = planilhas_teste.planilha("CF-0066").head(40).to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")
envio = lambda: op.post("/api/planilha", files={"arquivo": ("p.csv", planilha)}, data={"data": "12/11", "horario": "8h"})
dentro = envio().json()
conferir("dentro da área: o aviso cita Leopoldina", LEOPOLDINA in [x["codigo_ibge"] for x in dentro["municipios"]] and dentro["fora_da_area"]["ucs"] == 0,
         str([(x["codigo_ibge"], x["ucs"]) for x in dentro.get("municipios", [])]) + str(dentro.get("fora_da_area")))
farol.put(f"/api/empresas/{emg}/area", json={"codigos": sorted(base - {LEOPOLDINA}), "confirmar": True})
fora = envio()
j = fora.json()
conferir("Leopoldina fora da área da EMG: as UCs viram linhas rejeitadas (fora da área de atuação)", fora.status_code == 200
         and j["fora_da_area"]["ucs"] == sum(x["ucs"] for x in dentro["municipios"] if x["codigo_ibge"] == LEOPOLDINA)
         and LEOPOLDINA not in [x["codigo_ibge"] for x in j["municipios"]]
         and "fora da área de atuação da empresa" in j["planilha"]["problemas_por_motivo"], json.dumps(j.get("fora_da_area"))[:200])
conferir("as rejeitadas fora da área entram no limite de rejeição", j["conferencia"]["rejeicao"]["acima"] and j["conferencia"]["numeros"]["fora_da_area"] > 0)
g = op.post("/api/avisos", json={"pacote": j["pacote"], "data": "12/11", "horario": "8h", "conferi": True, "justificativa": "teste da área"})
conferir("o servidor não gera aviso de município fora da área", not (200 <= g.status_code < 300 and any(x["codigo_ibge"] == LEOPOLDINA for x in g.json().get("municipios", []))),
         f"{g.status_code} {g.text[:150]}")
conferir("mapa operacional: Leopoldina sumiu do mapa da EMG (só a área da empresa)",
         LEOPOLDINA not in {x["properties"]["codigo_ibge"] for x in con.get("/api/concessao").json()["features"]}
         and con.get(f"/api/municipios/{LEOPOLDINA}/comunidades").status_code == 404)
farol.put(f"/api/empresas/{emg}/area", json={"codigos": sorted(base), "confirmar": True})
conferir("área restaurada: o aviso volta a citar Leopoldina", LEOPOLDINA in [x["codigo_ibge"] for x in envio().json()["municipios"]])

# ---------- o Admin do Norte não vê nada operacional; os outros perfis não mexem na área ----------
st = {r: farol.get(r).status_code for r in ("/api/historico", "/api/painel", f"/api/municipios/{LEOPOLDINA}/comunidades",
                                            f"/api/municipios/{LEOPOLDINA}/rede", "/api/comunidades/calor", "/api/relatorios/mensal")}
st["POST /api/planilha"] = farol.post("/api/planilha", files={"arquivo": ("p.csv", planilha)}, data={"data": "12/11", "horario": "8h"}).status_code
conferir("Admin do Norte: 403 em histórico, painel, comunidades, rede, calor, relatórios operacionais e planilha", all(s == 403 for s in st.values()), str(st))
conferir("Admin da empresa não mexe na área (403)", adm.put(f"/api/empresas/{emg}/area", json={"codigos": [LEOPOLDINA], "confirmar": True}).status_code == 403
         and adm.get("/api/empresas/mapa").status_code == 403)

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_area CASCADE")
for r in resultados:
    print(r[0], r[1], f"-> {r[2]}" if r[0] != "OK  " and r[2] else "")
falhas = sum(r[0] != "OK  " for r in resultados)
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
