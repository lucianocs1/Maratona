"""Teste da API (FastAPI, em processo, com o banco local): planilha -> municípios, comunidades e aviso.

Confere:
- a base de Leopoldina no banco dá o mesmo resultado da base em arquivo (fontes/base_territorial.py);
- na CF-0066, 4 UCs ficam 1 a 55 m além da divisa, dentro de São João Nepomuceno: a API as põe lá;
- .csv (padrão do Excel brasileiro) e .xlsx dão a mesma resposta;
- uma planilha com UCs de dois municípios gera um aviso para cada um;
- cada tipo de problema aponta a linha certa, e UCs fora da concessão são contadas pela linha;
- erros de arquivo inteiro (vazio, sem coluna, grande demais) e de formulário respondem 422;
- a resposta não traz nenhum número de UC; as coordenadas só vêm nos pontos do mapa (um por UC, com a
  comunidade certa) e nunca no histórico;
- a rede fictícia de Leopoldina sai do banco igual à de data/sintetico, só com login, sem nada de cliente.

Uso (na raiz, depois do pipeline de Leopoldina e do base_concessao): uv run python testes/api/teste_api.py
"""

import io
from pathlib import Path
import json
import re
from collections import Counter
import os
import sys

os.environ["FAROL_ESQUEMA"] = "teste_api"   # usuários de teste num esquema próprio, apagado no fim

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from comunidades import distribuidora as dist_  # noqa: E402
from comunidades.api import app as app_mod  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco import base_territorial as banco  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.fontes import base_territorial as BT  # noqa: E402
from comunidades.nucleo.afetados import BaseMunicipio, afetados  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.simulacao import planilhas_teste  # noqa: E402
from comunidades.validacao.minimizacao import numero_de_casa_ou_cep  # noqa: E402

# entra como Operador (a semente cria os usuários; a senha temporária é trocada na hora)
with conectar() as _c:
    _c.execute("DROP SCHEMA IF EXISTS teste_api CASCADE")
_temps = {email: s for _, email, s in semear()}
_temp = _temps["operador@emg.example"]
cli = TestClient(app, base_url="http://farol.teste")
cli.post("/api/entrar", json={"email": "operador@emg.example", "senha": _temp})
assert cli.post("/api/senha", json={"atual": _temp, "nova": "Lanterna-do-Farol-2026"}).status_code == 200
resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def importar(conteudo: bytes, nome="planilha.csv", data="12/11", horario="8h às 14h", c=None, **extra):
    """1º passo (Conferir): traduz e devolve a conferência com o pacote assinado; nada vai para o histórico."""
    app_mod._envios.clear()   # o limite de envios por hora tem teste próprio (seção 5)
    return (c or cli).post("/api/planilha", files={"arquivo": (nome, conteudo)}, data={"data": data, "horario": horario, **extra})


def gerar(conferencia: dict, data="12/11", horario="8h às 14h", idioma="pt-BR", conferi=True, justificativa=None, c=None):
    """2º passo (Gerar aviso): o pacote da conferência, a caixa "Conferi" e, se precisar, a justificativa."""
    return (c or cli).post("/api/avisos", json={"pacote": conferencia["pacote"], "data": data, "horario": horario, "idioma": idioma,
                                                "conferi": conferi, "justificativa": justificativa})


def enviar(conteudo: bytes, nome="planilha.csv", data="12/11", horario="8h às 14h", **extra):
    """Os dois passos, como a tela faz (com a justificativa quando a rejeição passa do limite)."""
    r = importar(conteudo, nome, data, horario, **extra)
    if r.status_code != 200:
        return r
    j = r.json()
    just = "Teste: linhas rejeitadas conhecidas." if j["conferencia"]["rejeicao"]["acima"] else None
    return gerar(j, data, horario, extra.get("idioma", "pt-BR"), justificativa=just)


def csv_bytes(t: pd.DataFrame) -> bytes:
    return t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")


def xlsx_bytes(t: pd.DataFrame) -> bytes:
    b = io.BytesIO()
    t.to_excel(b, index=False)
    return b.getvalue()


def sem_dados_da_planilha(texto: str, t: pd.DataFrame) -> list[str]:
    """UCs e coordenadas da planilha que aparecem na resposta (deve ser lista vazia)."""
    achados = [u for u in t["uc"].astype(str) if len(u) >= 6 and u in texto]
    for col in ("latitude", "longitude"):
        for v in t[col].astype(float):
            for s in (f"{v:.6f}", f"{v:.5f}", f"{v:.4f}".replace(".", ",")):
                if s in texto:
                    achados.append(s)
    return achados[:5]


# ---------- 1. Saúde e modelo ----------
r = cli.get("/api/saude")
conferir("saúde: 66 municípios da concessão no banco", r.status_code == 200 and r.json()["municipios"] == 66, r.text)
r = cli.get("/api/modelo-planilha")
conferir("modelo da planilha: CSV com o cabeçalho do modelo", r.status_code == 200
         and r.content.decode("utf-8-sig").startswith("uc;latitude;longitude;equipamento_vital;classe"), r.text[:60])
conferir("cabeçalhos de segurança (nosniff, no-store)", r.headers.get("x-content-type-options") == "nosniff"
         and r.headers.get("cache-control") == "no-store")

# ---------- 2. CF-0066: banco x arquivo, csv x xlsx ----------
t = planilhas_teste.planilha("CF-0066")
rc, rx = enviar(csv_bytes(t)), enviar(xlsx_bytes(t), "planilha.xlsx")
conferir("CF-0066 (.csv): 200", rc.status_code == 200, rc.text[:200])
j = rc.json()
m = j["municipios"][0] if j.get("municipios") else {}
conferir("CF-0066: 758 UCs, 754 em Leopoldina e 4 além da divisa em São João Nepomuceno",
         [(mm["nome"], mm["ucs"]) for mm in j["municipios"]] == [("Leopoldina", 754), ("São João Nepomuceno", 4)]
         and j["planilha"]["validas"] == 758 and j["fora_da_concessao"]["ucs"] == 0,
         json.dumps([(mm["nome"], mm["ucs"]) for mm in j["municipios"]], ensure_ascii=False))
# cada envio ganha um id no histórico; nome, formato e aba do arquivo mudam de .csv para .xlsx
sem_id = lambda d: {k: ({**v, "arquivo": None} if k == "traducao" else {**v, "arquivo": None, "sha256": None} if k == "conferencia" else v)
                    for k, v in d.items() if k not in ("id", "codigo", "criado_em")}
conferir(".xlsx dá a mesma resposta que o .csv (fora o id do histórico)", rx.status_code == 200 and sem_id(rx.json()) == sem_id(j))
from pyproj import Transformer
x, y = Transformer.from_crs("EPSG:4674", BT.CRS_BASE, always_xy=True).transform(t["longitude"].to_numpy(), t["latitude"].to_numpy())
# a base de Leopoldina guardada no banco x a montada dos arquivos: mesmo núcleo, mesmo resultado
cod_leo, _, _, contorno_leo = next(c for c in banco.contornos(BT.CRS_BASE) if c[1] == "Leopoldina")
do_banco = BaseMunicipio(cod_leo, "Leopoldina", "MG", contorno_leo, *banco.enderecos(cod_leo, BT.CRS_BASE))
regras = dist_.carregar().regras
rb = afetados(np.c_[x, y], [do_banco], regras, "12/11", "8h às 14h").municipios[0]
ra = afetados(np.c_[x, y], [BT.base()], regras, "12/11", "8h às 14h").municipios[0]
conferir("banco = arquivo (Leopoldina): mesmo aviso", rb.aviso == ra.aviso, f"\n  banco:   {rb.aviso}\n  arquivo: {ra.aviso}")
iguais = float((rb.ucs["COMUNIDADE_PREVISTA"].to_numpy() == ra.ucs["COMUNIDADE_PREVISTA"].to_numpy()).mean())
conferir("banco = arquivo (Leopoldina): mesma comunidade em todas as UCs", iguais == 1.0, f"{iguais:.2%}")
conferir("banco = arquivo (Leopoldina): mesmas comunidades e contagens",
         rb.comunidades.drop(columns="CONFIANCA").equals(ra.comunidades.drop(columns="CONFIANCA")))
cod_sjn, _, _, contorno_sjn = next(c for c in banco.contornos(BT.CRS_BASE) if c[1] == "São João Nepomuceno")
sjn = BaseMunicipio(cod_sjn, "São João Nepomuceno", "MG", contorno_sjn, *banco.enderecos(cod_sjn, BT.CRS_BASE))
nucleo = afetados(np.c_[x, y], [do_banco, sjn], regras, "12/11", "8h às 14h").municipios
conferir("API = núcleo com as bases do banco: os mesmos dois avisos", [mm["aviso"] for mm in j["municipios"]] == [mm.aviso for mm in nucleo],
         "\n  " + "\n  ".join(mm["aviso"] for mm in j["municipios"]))
conferir("prazo: com equipamento vital sorteado, 5 dias úteis", m["equipamento_vital"]["sim"] > 0 and "5 dias úteis" in j["prazo"]["antecedencia_minima"],
         json.dumps([m["equipamento_vital"], j["prazo"]], ensure_ascii=False))
sem_ucs = t.assign(latitude=0.0, longitude=0.0)  # só os números de UC
conferir("nenhum número de UC na resposta (.csv)", not sem_dados_da_planilha(rc.text, sem_ucs), str(sem_dados_da_planilha(rc.text, sem_ucs)))
sem_pontos = json.dumps({**{k: v for k, v in j.items() if k != "pontos_fora"},
                         "municipios": [{k: v for k, v in mm.items() if k != "pontos"} for mm in j["municipios"]]})
conferir("coordenadas só nos pontos do mapa", not sem_dados_da_planilha(sem_pontos, t), str(sem_dados_da_planilha(sem_pontos, t)))
pontos_ok = all(len(mm["pontos"]) == mm["ucs"] for mm in j["municipios"]) and len(j["pontos_fora"]) == j["fora_da_concessao"]["ucs"]
por_com = Counter((mm["nome"], mm["comunidades"][i]["nome"]) for mm in j["municipios"] for *_, i in mm["pontos"] if i >= 0)
afet = {(mm["nome"], c["nome"]): c["afetadas"] for mm in j["municipios"] for c in mm["comunidades"]}
conferir("pontos: um por UC, cada um na comunidade que conta a UC", pontos_ok and dict(por_com) == afet,
         f"{pontos_ok} {sum(por_com.values())} x {sum(afet.values())}")
h = cli.get(f"/api/historico/{j['id']}")
conferir("o histórico não guarda pontos nem coordenadas", h.status_code == 200 and "pontos" not in h.text
         and not sem_dados_da_planilha(h.text, t), h.text[:120])
conferir("idioma en: aviso em inglês", (e := enviar(csv_bytes(t), idioma="en")).status_code == 200
         and e.json()["municipios"][0]["aviso"] != m["aviso"], e.json()["municipios"][0]["aviso"][:80] if e.status_code == 200 else e.text)

# ---------- 3. Dois municípios: CF-0066 + 40 endereços de Cataguases ----------
cod_cat = next(c for c, n, u, g in banco.contornos(BT.CRS_BASE) if n == "Cataguases")
exy, _, _ = banco.enderecos(cod_cat, BT.CRS_BASE)
lon, lat = Transformer.from_crs(BT.CRS_BASE, "EPSG:4674", always_xy=True).transform(exy[:40, 0], exy[:40, 1])
cat = pd.DataFrame({"uc": [f"9{i:09d}" for i in range(40)], "latitude": lat.round(6), "longitude": lon.round(6),
                    "equipamento_vital": "não", "classe": "residencial"})
r2 = enviar(csv_bytes(pd.concat([t, cat], ignore_index=True)))
nomes = [(mm["nome"], mm["ucs"]) for mm in r2.json().get("municipios", [])] if r2.status_code == 200 else r2.text
conferir("dois municípios: Leopoldina (754), Cataguases (40) e as 4 da divisa, um aviso cada",
         nomes == [("Leopoldina", 754), ("Cataguases", 40), ("São João Nepomuceno", 4)], str(nomes))
if r2.status_code == 200 and len(r2.json()["municipios"]) == 2:
    conferir("o aviso de Cataguases cita Cataguases", "em Cataguases" in r2.json()["municipios"][1]["aviso"], r2.json()["municipios"][1]["aviso"])

# ---------- 2b. Comparativo: o aviso de hoje (coluna local) pela planilha = o do cadastro fictício ----------
import geopandas as _gpd  # noqa: E402
from comunidades import config as _C  # noqa: E402
from comunidades.nucleo import desligamento as D  # noqa: E402
cad = _gpd.read_file(_C.SINTETICO / "ucs.gpkg", ignore_geometry=True).set_index("UC")
hoje = m.get("hoje") or {}
locais_cad = D.locais_antigos(cad.loc[t["uc"].iloc[nucleo[0].ucs.index]].reset_index())  # as 2 bases, como a API
lista_cad = D.idiomas.lista(locais_cad, "pt-BR")
texto_hoje, msg = str(hoje.get("texto")), m.get("mensagem", "")
# comparação justa: o mesmo modelo da empresa nos dois lados, só a lista muda (locais x comunidades)
comeco = msg[:msg.index(" nas comunidades")] if " nas comunidades" in msg else msg[:40]
conferir("comparativo: aviso de hoje de Leopoldina pela coluna local = os locais do cadastro, no mesmo modelo do Norte",
         hoje.get("lista") == locais_cad and lista_cad in texto_hoje and texto_hoje.startswith(comeco),
         f"\n  API:   {texto_hoje[:160]}\n  Norte: {msg[:160]}")
conferir("comparativo: locais, palavras e tempo no ar do aviso de hoje; o Norte bem mais curto",
         hoje.get("locais", 0) > 50 and hoje.get("palavras") == len(texto_hoje.split()) and hoje.get("segundos", 0) > 5 * m["segundos_mensagem"]
         and not m.get("mesmo_tamanho"),
         json.dumps({k: v for k, v in hoje.items() if k not in ("texto", "lista")}) + f" norte {m['segundos_mensagem']} s")
hist_um = cli.get(f"/api/historico/{j['id']}").json()["municipios"][0]
imovel = next(l for l in D.locais_antigos(cad.loc[t["uc"]].reset_index()) if l.startswith("Sitio"))
conferir("histórico: do aviso de hoje só as contagens (sem o texto, sem imóveis)",
         set(hist_um.get("hoje") or {}) == {"locais", "palavras", "segundos"} and imovel not in json.dumps(hist_um, ensure_ascii=False),
         json.dumps(hist_um.get("hoje")))
sem_local = enviar(csv_bytes(t.drop(columns="local"))).json()
conferir("sem a coluna local: sem aviso de hoje (o comparativo explica o que falta)", all(mm["hoje"] is None for mm in sem_local["municipios"]))
# formato da base da distribuidora: NUMCDC, ENDERECO completo e LOCAL = URBANO/RURAL
dist = t.rename(columns={"uc": "NUMCDC", "latitude": "LATITUDE", "longitude": "LONGITUDE"}).drop(columns="local")
dist["ENDERECO"] = [f"{l}, {100 + i}, casa {i % 4 + 1} - CEP 36700-{i % 1000:03d}" for i, l in enumerate(t["local"])]
dist["LOCAL"] = ["RURAL" if str(l).upper().startswith(("SITIO", "FAZENDA", "CHACARA")) else "URBANO" for l in t["local"]]
rd = enviar(csv_bytes(dist))
jd = rd.json()
textos_hoje = " ".join((mm.get("hoje") or {}).get("texto", "") for mm in jd.get("municipios", []))
conferir("planilha da distribuidora (NUMCDC, ENDERECO, LOCAL URBANO/RURAL) aceita, com as mesmas UCs",
         rd.status_code == 200 and jd["planilha"]["validas"] == j["planilha"]["validas"] == 758
         and [(mm["nome"], mm["ucs"]) for mm in jd["municipios"]] == [(mm["nome"], mm["ucs"]) for mm in j["municipios"]],
         f"{rd.status_code} {str(jd)[:160]}")
conferir("aviso de hoje pelo ENDERECO: sem número de casa nem CEP", bool(textos_hoje) and not numero_de_casa_ou_cep(textos_hoje),
         str(numero_de_casa_ou_cep(textos_hoje)[:5]))
conferir("aviso de hoje pelo ENDERECO: cita ruas e imóveis, não URBANO/RURAL",
         not re.search(r"\b(urbano|rural)\b", textos_hoje, re.I) and imovel in textos_hoje, textos_hoje[:200])

# ---------- 3a. Dashboard: os números batem com o histórico ----------
hist = cli.get("/api/historico").json()["avisos"]
pn = cli.get("/api/painel").json()
tot = pn["totais"]
ucs_hist = sum(mm["ucs"] for a in hist for mm in a["municipios"])
mun_hist = {mm["codigo_ibge"] for a in hist for mm in a["municipios"]}
com_hist = {(mm["codigo_ibge"], c["nome"]) for a in hist for mm in a["municipios"] for c in mm["comunidades"]}
conferir("dashboard: avisos, UCs, municípios e comunidades iguais aos do histórico",
         tot["avisos"] == len(hist) == tot["ultimos_30_dias"] and tot["ucs"] == ucs_hist
         and tot["municipios"] == len(mun_hist) and tot["comunidades"] == len(com_hist),
         json.dumps({"painel": tot, "historico": [len(hist), ucs_hist, len(mun_hist), len(com_hist)]}))
conferir("dashboard: 12 meses, este mês com todos os avisos, Leopoldina no topo",
         len(pn["por_mes"]) == 12 and pn["por_mes"][-1]["avisos"] == len(hist) and pn["municipios"][0]["nome"] == "Leopoldina"
         and pn["por_municipio"][cod_leo] == sum(any(mm["codigo_ibge"] == cod_leo for mm in a["municipios"]) for a in hist),
         json.dumps([pn["por_mes"][-1], pn["municipios"][:2]], ensure_ascii=False))
comp_hist = [mm for a in hist for mm in a["municipios"] if mm.get("hoje")]
conferir("dashboard: comparativo com os municípios que têm o aviso de hoje, tempo de hoje x Norte",
         pn["comparativo"]["municipios"] == len(comp_hist) > 0
         and pn["comparativo"]["segundos_hoje"] == sum(mm["hoje"]["segundos"] for mm in comp_hist)
         and pn["comparativo"]["segundos_farol"] == sum(mm.get("segundos_mensagem") or mm["segundos"] for mm in comp_hist), json.dumps(pn["comparativo"]))
conferir("dashboard: só agregados (nada de UC, coordenada ou texto de aviso)",
         not sem_dados_da_planilha(json.dumps(pn), t)
         and all(set(m) == {"codigo_ibge", "nome", "uf", "avisos", "ucs"} for m in pn["municipios"])
         and all(set(c) == {"nome", "municipio", "avisos", "ucs"} for c in pn["comunidades"])
         and all(m["aviso"][:40] not in json.dumps(pn, ensure_ascii=False) for a in hist for m in a["municipios"]))

# ---------- 3b. Rede fictícia (demonstração) ----------
import geopandas as gpd  # noqa: E402
from comunidades import config as C  # noqa: E402
rr = cli.get(f"/api/municipios/{cod_leo}/rede")
conferir("rede fictícia de Leopoldina: 200", rr.status_code == 200, rr.text[:120])
if rr.status_code == 200:
    rd = rr.json()
    ch_arq = gpd.read_file(C.SINTETICO / "chaves.gpkg")
    conferir("rede: as mesmas chaves e trafos de data/sintetico, marcada como fictícia",
             rd["ficticia"] and sorted(c[2] for c in rd["chaves"]) == sorted(ch_arq["COD_CHAVE"])
             and len(rd["trafos"]) == len(gpd.read_file(C.SINTETICO / "transformadores.gpkg"))
             and any(c[2] == "CF-0066" for c in rd["chaves"]), f"{len(rd['chaves'])} chaves x {len(ch_arq)}")
    conferir("rede: só traçado, códigos e contagens (nada de cliente)",
             set(rd) == {"ficticia", "subestacao", "alimentadores", "chaves", "trafos"}
             and all(set(f["properties"]) == {"alimentador"} for f in rd["alimentadores"]["features"]))
conferir("rede: sem login, 401", TestClient(app, base_url="http://farol.teste").get(f"/api/municipios/{cod_leo}/rede").status_code == 401)
conferir("rede: município fora da concessão ou inválido, 404/422", cli.get("/api/municipios/0000000/rede").status_code == 404
         and cli.get("/api/municipios/abc/rede").status_code == 422)
sem_rede = [c for c, _, _, _ in banco.contornos("EPSG:4674") if cli.get(f"/api/municipios/{c}/rede").json() is None][:1]
conferir("rede: município da concessão sem a rede fictícia, 200 com null (sem 404 no console do navegador)",
         all(cli.get(f"/api/municipios/{c}/rede").status_code == 200 for c in sem_rede), str(sem_rede))

# ---------- 4. Problemas por linha ----------
ruins = pd.DataFrame([
    {"uc": "", "latitude": "-21,53", "longitude": "-42,64"},              # linha 2: sem UC
    {"uc": "1000000001", "latitude": "", "longitude": "-42,64"},          # 3: sem coordenada
    {"uc": "1000000002", "latitude": "-42,64", "longitude": "-21,53"},    # 4: trocadas
    {"uc": "1000000003", "latitude": "40,0", "longitude": "-3,7"},        # 5: fora do Brasil
    {"uc": "1000000004", "latitude": "-21,5321", "longitude": "-42,6412"},  # 6: válida
    {"uc": "1000000004", "latitude": "-21,5322", "longitude": "-42,6413"},  # 7: repetida
    {"uc": "1000000005", "latitude": "-23,55", "longitude": "-46,63", "equipamento_vital": "talvez"},  # 8: São Paulo + vital inválido
])
r3 = enviar(ruins.to_csv(sep=";", index=False).encode("utf-8"))
j3 = r3.json() if r3.status_code == 200 else {}
probs = {p["linha"]: p["codigo"] for p in j3.get("planilha", {}).get("problemas", [])}
esperado = {2: "uc_vazia", 3: "coordenada_incompleta", 5: "fora_da_concessao", 7: "uc_repetida", 8: "fora_da_concessao"}
conferir("cada problema aponta a linha certa, com o código da lista fechada", r3.status_code == 200 and probs == esperado,
         json.dumps(probs, ensure_ascii=False))
conferir("os problemas trazem o texto da lista fechada", all(p["motivo"] == j3["traducao"]["textos"][p["codigo"]]
                                                           for p in j3.get("planilha", {}).get("problemas", [])))
tr = j3.get("traducao", {})
conferir("linha 4 (trocadas, dentro da concessão): corrigida, listada com o que mudou",
         tr.get("corrigidas") == [{"linha": 4, "codigo": "latitude_e_longitude_trocadas", "correcao": "latitude e longitude estavam trocadas"}],
         json.dumps(tr.get("corrigidas"), ensure_ascii=False))
conferir("vital inválido e UC repetida: avisos pela linha", {"linha": 6, "avisos": ["uc_repetida_em_outra_linha"]} in tr.get("avisos", [])
         and any(a["linha"] == 8 and "equipamento_vital_invalido" in a["avisos"] for a in tr.get("avisos", [])),
         json.dumps(tr.get("avisos"), ensure_ascii=False))
conferir("resumo da tradução: 7 linhas = 1 ok + 1 corrigida + 5 rejeitadas", {k: tr.get("resumo", {}).get(k) for k in
         ("total", "ok", "corrigidas", "rejeitadas")} == {"total": 7, "ok": 1, "corrigidas": 1, "rejeitadas": 5}, json.dumps(tr.get("resumo")))
conferir("Madri e São Paulo: fora da concessão, pela linha (5 e 8)", j3.get("fora_da_concessao") == {"ucs": 2, "linhas": [5, 8]}
         and len(j3.get("pontos_fora", [])) == 2, json.dumps(j3.get("fora_da_concessao"), ensure_ascii=False))
conferir("a válida (6) e a corrigida (4) entram em Leopoldina", [(mm["nome"], mm["ucs"]) for mm in j3.get("municipios", [])]
         == [("Leopoldina", 2)], json.dumps([(mm["nome"], mm["ucs"]) for mm in j3.get("municipios", [])], ensure_ascii=False))

# ---------- 5. Erros da planilha inteira e do formulário ----------
# exemplo oficial com duas abas que servem (Modelo e Postes): a API pede a escolha; com a aba, gera
POSTES = (Path(__file__).resolve().parents[1] / "planilha" / "exemplos" / "planilha_postes.xlsx").read_bytes()
r = enviar(POSTES, "planilha_postes.xlsx")
conferir("duas abas servem: 409 com a lista para escolher", r.status_code == 409 and r.json().get("abas") == ["Modelo", "Postes"],
         f"{r.status_code} {r.text[:160]}")
rm, rp = enviar(POSTES, "planilha_postes.xlsx", aba="Modelo"), enviar(POSTES, "planilha_postes.xlsx", aba="Postes")
# a aba Postes tem a SITUACAO da base de clientes: as inativas ficam fora da planilha inteira (nucleo/selecao.py)
conferir("aba escolhida (Modelo e Postes): 200 lidas; no Postes, as inativas fora", rm.status_code == rp.status_code == 200
         and rm.json()["escolha"]["conta"]["lidas"] == rp.json()["escolha"]["conta"]["lidas"] == 200 and rm.json()["planilha"]["validas"] == 200
         and rp.json()["planilha"]["validas"] == 200 - rp.json()["escolha"]["conta"]["inativas_fora"]
         and rp.json()["escolha"]["conta"]["inativas_fora"] > 0, f"{rm.status_code} {rp.status_code} {rp.text[:160]}")
r = enviar(POSTES, "planilha_postes.xlsx", aba="Notas")
conferir("aba que não serve: 422", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
saida = rp.text
rede = rp.json().get("rede", {})
conferir("aba Postes: agrupamento por circuito e por transformador (só códigos e contagens, somando as UCs válidas)",
         set(rede) == {"circuito", "transformador"} and all(sum(x["ucs"] for x in rede[k]["grupos"]) + rede[k]["sem_codigo"] <= 200
                                                            and rede[k]["total"] > 0 for k in rede)
         and set(rede["circuito"]["grupos"][0]) == {"codigo", "ucs"}, json.dumps(rede)[:200])
conferir("aba Postes: nada de NOME, NUM_CASA, MEDIDOR ou NUM_CONTA na resposta",
         not any(c in saida for c in ("NOME", "NUM_CASA", "MEDIDOR", "NUM_CONTA")), "")
# dupla conferência: se a releitura independente não bater, nada é gerado nem gravado
from comunidades.api import conferencia  # noqa: E402

contar_original = conferencia.contar
conferencia.contar = lambda c, f, a: {**contar_original(c, f, a), "vital_sim": -1}   # sabotagem: um número diferente
with conectar() as _c:
    avisos_antes = _c.execute("SELECT count(*) FROM aviso").fetchone()[0]
r = enviar(POSTES, "planilha_postes.xlsx", aba="Postes")
conferencia.contar = contar_original
with conectar() as _c:
    avisos_depois = _c.execute("SELECT count(*) FROM aviso").fetchone()[0]
    bloqueio = _c.execute("SELECT count(*) FROM registro WHERE acao = 'planilha bloqueada pela conferência independente'").fetchone()[0]
conferir("conferência independente divergente: 422 'Nada foi gerado', nada no histórico, bloqueio na auditoria",
         r.status_code == 422 and "Nada foi gerado" in r.json().get("detail", "") and avisos_depois == avisos_antes and bloqueio >= 1,
         f"{r.status_code} {r.text[:120]} avisos {avisos_antes}->{avisos_depois} registro {bloqueio}")
# limite de envios por usuário
app_mod._envios.clear()
pequena = "uc;latitude;longitude\n1;-21,53;-42,64\n".encode()
codigos = [cli.post("/api/planilha", files={"arquivo": ("p.csv", pequena)}, data={"data": "12/11", "horario": "8h"}).status_code
           for _ in range(app_mod.LIMITE_ENVIOS + 2)]
conferir(f"limite de {app_mod.LIMITE_ENVIOS} planilhas por hora por usuário: depois, 429", set(codigos[:app_mod.LIMITE_ENVIOS]) == {200}
         and codigos[app_mod.LIMITE_ENVIOS:] == [429, 429], str(codigos))
app_mod._envios.clear()
casos = {
    "arquivo vazio": enviar(b""),
    "sem a coluna longitude": enviar("uc;latitude\n1;-21,5\n".encode()),
    "mais de 10 MB": enviar(b"uc;latitude;longitude\n" + b"1;-21,5;-42,6\n" * 800_000),
    "xlsx corrompido": enviar(b"PK\x03\x04lixo", "x.xlsx"),
    "idioma inexistente": enviar(csv_bytes(t), idioma="fr"),
    "data longa demais": enviar(csv_bytes(t), data="x" * 41),
}
for nome, rr in casos.items():
    conferir(f"erro tratado ({nome}): 422 com mensagem", rr.status_code == 422 and "detail" in rr.json(), f"{rr.status_code} {rr.text[:120]}")

# ---------- 6. Conferência humana e travas (dois passos: Conferir -> Gerar aviso) ----------
import base64  # noqa: E402
import gzip  # noqa: E402
import time  # noqa: E402

from comunidades.api import pacote as pacote_  # noqa: E402


def contar(tabela: str) -> int:
    with conectar() as _c:
        return _c.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def registros(acao: str) -> list[str]:
    with conectar() as _c:
        return [d for (d,) in _c.execute("SELECT detalhe FROM registro WHERE acao = %s ORDER BY id", (acao,)).fetchall()]


antes = contar("aviso")
ri = importar(csv_bytes(t))
ji = ri.json()
conferir("conferir (1º passo): 200, nada no histórico, importação na auditoria com o sha256",
         ri.status_code == 200 and contar("aviso") == antes and any(ji["conferencia"]["sha256"] in d for d in registros("importou planilha")),
         f"{ri.status_code} {contar('aviso')} x {antes}")
conferir("conferir: números (clientes, municípios, comunidades, equipamento vital, corrigidas, rejeitadas)",
         ji["conferencia"]["numeros"] == {"clientes": 758, "municipios": 2, "comunidades": sum(len(mm["comunidades"]) for mm in ji["municipios"]),
                                          "equipamento_vital": sum(mm["equipamento_vital"]["sim"] for mm in ji["municipios"]),
                                          "vital_a_confirmar": 0, "corrigidas": 0, "rejeitadas": 0, "fora_da_concessao": 0,
                                          "fora_da_area": 0},
         json.dumps(ji["conferencia"]["numeros"]))
conferir("suspeito (amarelo): 4 UCs em São João Nepomuceno, município diferente da maioria",
         [(x["tipo"], x["municipio"], x["ucs"]) for x in ji["conferencia"]["suspeitos"] if x["tipo"] != "repeticao"]
         == [("municipio_diferente", "São João Nepomuceno/MG", 4)],
         json.dumps(ji["conferencia"]["suspeitos"], ensure_ascii=False))
# o pacote vai ao navegador: UCs trocadas por códigos opacos
dentro = json.loads(gzip.decompress(base64.urlsafe_b64decode(ji["pacote"].split(".")[1] + "==")))
conferir("pacote: nenhum número de UC (só códigos opacos u1, u2...)", not sem_dados_da_planilha(dentro["m"], sem_ucs)
         and json.loads(dentro["m"])["pontos"][0]["uc"] == "u1", str(sem_dados_da_planilha(dentro["m"], sem_ucs)))
sem_marcar = gerar(ji, conferi=False)
conferir("sem marcar 'Conferi os números e o mapa': 422, nada no histórico",
         sem_marcar.status_code == 422 and "Conferi" in sem_marcar.json()["detail"] and contar("aviso") == antes, sem_marcar.text[:120])
corpo = ji["pacote"].split(".")
adulterado = {**ji, "pacote": ".".join([corpo[0], corpo[1][:-3] + ("A" if corpo[1][-3] != "A" else "B") + corpo[1][-2:], corpo[2]])}
ra = gerar(adulterado)
conferir("pacote adulterado: 422 'alterado', nada no histórico", ra.status_code == 422 and "alterado" in ra.json()["detail"]
         and contar("aviso") == antes, ra.text[:120])
modelo_ok = pacote_.abrir(ji["pacote"], *[cli.get("/api/eu").json()["usuario"][k] for k in ("id", "empresa_id")])
uid, eid = (cli.get("/api/eu").json()["usuario"][k] for k in ("id", "empresa_id"))
vencido, _ = pacote_.assinar(modelo_ok, uid, eid, agora=time.time() - pacote_.VALIDADE - 5)
rv = gerar({"pacote": vencido})
conferir("pacote vencido (mais de 15 minutos): 422 'venceu'", rv.status_code == 422 and "venceu" in rv.json()["detail"], rv.text[:120])
adm = TestClient(app, base_url="http://farol.teste")
adm.post("/api/entrar", json={"email": "admin@emg.example", "senha": _temps["admin@emg.example"]})
adm.post("/api/senha", json={"atual": _temps["admin@emg.example"], "nova": "Lanterna-do-Farol-2026"})
ro = gerar(ji, c=adm)
conferir("pacote de outro usuário (mesma empresa): 422 'outro usuário'", ro.status_code == 422 and "outro usuário" in ro.json()["detail"], ro.text[:120])
falso = json.dumps({"u": uid, "e": eid, "vence": int(time.time()) + 600, "f": "escolha", "c": None,
                    "m": json.dumps({**json.loads(modelo_ok.model_dump_json()), "campo_extra": 1})})
corpo_falso = base64.urlsafe_b64encode(gzip.compress(falso.encode(), mtime=0)).decode().rstrip("=")
rf = gerar({"pacote": f"{pacote_.VERSAO}.{corpo_falso}.{pacote_._assinatura(corpo_falso)}"})
conferir("pacote assinado mas fora do esquema (campo extra): 422 'esquema'", rf.status_code == 422 and "esquema" in rf.json()["detail"], rf.text[:120])
rg = gerar(ji)
conferir("com 'Conferi' marcado: 200, entra no histórico, conferência na auditoria com o sha256",
         rg.status_code == 200 and contar("aviso") == antes + 1 and any(ji["conferencia"]["sha256"] in d for d in registros("conferiu os números e o mapa")),
         rg.text[:120])
conferir("gerar = conferir (mesmos municípios, comunidades e avisos)", rg.status_code == 200
         and rg.json()["municipios"] == ji["municipios"], "")

# equipamento vital: linha corrigida ou rejeitada com vital = sim bloqueia sempre (nem com justificativa)
vit = t.head(30).copy()
vit["equipamento_vital"] = "não"
vit.loc[3, "equipamento_vital"] = "sim"
vit.loc[3, "latitude"], vit.loc[3, "longitude"] = float(t.loc[3, "longitude"]), float(t.loc[3, "latitude"])   # trocadas: vira corrigida
vit.loc[7, "equipamento_vital"] = "sim"
vit.loc[7, ["latitude", "longitude"]] = [-23.55, -46.63]                                   # São Paulo: rejeitada
rvi = importar(csv_bytes(vit))
jv = rvi.json()
conferir("vital corrigida (linha 5) e rejeitada (linha 9): alerta vermelho pela linha, sem a UC",
         [(x["linha"], x["situacao"]) for x in jv["conferencia"]["vital_bloqueio"]] == [(5, "corrigida"), (9, "rejeitada")]
         and not sem_dados_da_planilha(json.dumps(jv["conferencia"]), vit.assign(latitude=0.0, longitude=0.0)),
         json.dumps(jv["conferencia"]["vital_bloqueio"], ensure_ascii=False))
conferir("a corrigida aparece nos pontos corrigidos do mapa (cor própria)", len(jv["pontos_corrigidos"]) == 1, str(jv["pontos_corrigidos"]))
antes = contar("aviso")
rb = gerar(jv, justificativa="tentando passar por cima")
conferir("vital bloqueia a geração: 422, nada no histórico, bloqueio na auditoria",
         rb.status_code == 422 and "equipamento vital" in rb.json()["detail"] and contar("aviso") == antes
         and registros("geração bloqueada (equipamento vital)"), rb.text[:160])

# limite de rejeição (2%): sem justificativa não gera; com ela, gera e a justificativa vai para a auditoria
rr = importar(ruins.to_csv(sep=";", index=False).encode("utf-8"))
jr = rr.json()
conferir("5 de 7 rejeitadas (71%): acima do limite de 2%", jr["conferencia"]["rejeicao"]["acima"] is True
         and jr["conferencia"]["rejeicao"]["limite"] == 0.02, json.dumps(jr["conferencia"]["rejeicao"]))
sem_just = gerar(jr)
conferir("acima do limite sem justificativa: 422", sem_just.status_code == 422 and "justificativa" in sem_just.json()["detail"], sem_just.text[:120])
longa = gerar(jr, justificativa="x" * 301)
conferir("justificativa com mais de 300 caracteres: 422", longa.status_code == 422, longa.text[:120])
com_just = gerar(jr, justificativa="Planilha de teste com\tlinhas ruins de propósito.")
conferir("com justificativa: 200 e a justificativa (limpa) na auditoria com as contagens",
         com_just.status_code == 200 and registros("justificou rejeições acima do limite")[-1]
         == "5 de 7 linhas: Planilha de teste com linhas ruins de propósito.", str(registros("justificou rejeições acima do limite")[-1:]))

# relatório (CSV) e JSON com as UCs
rel = cli.post("/api/planilha/relatorio", json={"pacote": jr["pacote"]})
linhas_rel = rel.content.decode("utf-8-sig").splitlines()
conferir("relatório CSV: uma linha por linha da planilha, com situação e motivo, sem UC",
         rel.status_code == 200 and len(linhas_rel) == 2 + 7 and linhas_rel[1] == "linha;situacao;motivo_ou_correcao;equipamento_vital;avisos"
         and "1000000004" not in rel.text and "4;corrigida;latitude e longitude estavam trocadas" in rel.text, rel.text[:300])
perigoso = importar(csv_bytes(t.head(5)), nome="=HYPERLINK(1).csv").json()
rel2 = cli.post("/api/planilha/relatorio", json={"pacote": perigoso["pacote"]}).content.decode("utf-8-sig")
conferir("relatório CSV: nome de arquivo com fórmula sai com apóstrofo", rel2.startswith("arquivo;'=HYPERLINK"), rel2[:60])
app_mod._envios.clear()
rj = cli.post("/api/planilha/json", files={"arquivo": ("planilha.csv", csv_bytes(t))})
conferir("Baixar JSON (Operador): 200, com os números de UC, registrado na auditoria",
         rj.status_code == 200 and rj.json()["pontos"][0]["uc"] == str(t["uc"].iloc[0])
         and "attachment" in rj.headers.get("content-disposition", "") and registros("baixou o JSON da planilha (com números de UC)"),
         rj.text[:100])
conferir("Baixar JSON: o mesmo arquivo dá o mesmo conteúdo (reprodutível) e o sha256 da conferência",
         rj.json()["arquivo"]["sha256"] == ji["conferencia"]["sha256"], "")

# erro inesperado: nada é gerado, código ERR-xxxx, sem dados da planilha na mensagem
sem_erro = TestClient(app, base_url="http://farol.teste", raise_server_exceptions=False)
sem_erro.cookies = cli.cookies
bases_original = app_mod._bases
import logging  # noqa: E402
_logs = []
_h = logging.Handler(); _h.emit = lambda rec: _logs.append(rec.getMessage())
logging.getLogger("farol.api").addHandler(_h)
app_mod._envios.clear()
pacote_novo = importar(csv_bytes(t)).json()["pacote"]   # uma conferência nova (o pacote já usado gera 409, Fase J)
app_mod._bases = lambda xy, area=None: (_ for _ in ()).throw(RuntimeError(f"vazou {t['uc'].iloc[0]}"))
antes = contar("aviso")
re_ = sem_erro.post("/api/avisos", json={"pacote": pacote_novo, "data": "12/11", "horario": "8h às 14h", "conferi": True})
app_mod._bases = bases_original
conferir("erro inesperado: 500 'nada foi gerado (código ERR-xxxx)', nada no histórico, nenhuma UC na resposta",
         re_.status_code == 500 and re.fullmatch(r"Ocorreu um erro e nada foi gerado \(código ERR-[0-9A-F]{6}\)\.", re_.json()["detail"])
         and contar("aviso") == antes and str(t["uc"].iloc[0]) not in re_.text, re_.text[:120])
conferir("erro inesperado: o log tem o código e onde foi, sem a mensagem nem a UC",
         len(_logs) == 1 and re_.json()["detail"][-12:-2] in _logs[0] and "RuntimeError" in _logs[0]
         and str(t["uc"].iloc[0]) not in _logs[0] and "vazou" not in _logs[0], str(_logs))

with conectar() as _c:
    _c.execute("DROP SCHEMA IF EXISTS teste_api CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
print("\nAviso da CF-0066 pela API:\n " + m.get("aviso", ""))
sys.exit(1 if falhas else 0)
