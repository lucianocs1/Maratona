"""Teste do áudio do aviso: locução do texto, MP3 e permissões (FastAPI em processo, Postgres local).

Roda num esquema próprio (FAROL_ESQUEMA=teste_audio), apagado no fim. Confere:
- a locução: "8h" vira "8 horas", "14h30" vira "14 horas e 30", "20/11" vira "20 de novembro";
- o MP3: quadros MPEG válidos, mono, e a duração coerente com o tamanho do texto;
- quem pode: Admin da empresa e Operador (quem gera o aviso); Consulta e Admin do Norte não; sem login, 401;
- erros: idioma sem voz, texto vazio ou longo demais, campos longos demais (422); nome do arquivo só em ASCII;
- o registro de atividade guarda que o áudio foi gerado (sem o texto).

Uso (na raiz): uv run python -W ignore testes/api/teste_audio.py
"""

import os
import sys

os.environ["FAROL_ESQUEMA"] = "teste_audio"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api import app as app_mod  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo.desligamento import PALAVRAS_POR_SEGUNDO  # noqa: E402
from comunidades.nucleo.locucao import texto_para_fala  # noqa: E402
from comunidades.semente import semear  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


# ---------- 1. Locução ----------
casos = {
    "no dia 20/11, das 8h às 14h": "no dia 20 de novembro, das 8 horas às 14 horas",
    "das 7h30 às 13h05": "das 7 horas e 30 às 13 horas e 5",
    "às 1h": "às 1 hora",
    "em 01/12/2026": "em primeiro de dezembro de 2026",
    "aviso nº 12": "aviso número 12",
    "33/13 fica como está": "33/13 fica como está",
}
assert texto_para_fala("*Desligamento* programado: **8h** às `14h`, _sem_ luz #1") == "Desligamento programado: 8 horas às 14 horas, sem luz 1"
erradas = {k: texto_para_fala(k) for k, v in casos.items() if texto_para_fala(k) != v}
conferir("locução: horas, datas e abreviações como o locutor diria", not erradas, str(erradas))

# ---------- 2. API ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_audio CASCADE")
senhas = {email: s for _, email, s in semear()}
NOVA = "Lanterna-do-Farol-2026"


def cliente(email=None) -> TestClient:
    api_acesso._tentativas_ip.clear()
    cli = TestClient(app, base_url="http://farol.teste")
    if email:
        cli.post("/api/entrar", json={"email": email, "senha": senhas[email]})
        cli.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
    return cli


AVISO = ("Atenção, moradores de Graminha, Boa Sorte, Córrego Espalhada, São Pedro e Piacatuba, e de parte de Tomé Nogueira, "
         "Braúna e Córrego do Sossego, além de localidades vizinhas, em Leopoldina (distritos Piacatuba, Sede e Tebas): "
         "no dia 20/11, das 8h às 14h, haverá desligamento programado de energia para manutenção na rede. Programe-se!")
pedido = {"texto": AVISO, "idioma": "pt-BR", "municipio": "São João Nepomuceno"}
conferir("sem login: 401", cliente().post("/api/audio", json=pedido).status_code == 401)

op = cliente("operador@emg.example")
r = op.post("/api/audio", json=pedido)
mp3 = r.content
conferir("Operador: 200, audio/mpeg", r.status_code == 200 and r.headers["content-type"] == "audio/mpeg", f"{r.status_code} {r.text[:100]}")


def quadros(b: bytes) -> tuple[int, set]:
    """Conta os quadros MPEG-1 Layer III seguidos desde o início e os modos de canal (3 = mono)."""
    taxas = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    amostragem = [44100, 48000, 32000, 0]
    i, n, modos = 0, 0, set()
    while i + 4 <= len(b):
        h = int.from_bytes(b[i:i + 4], "big")
        if (h >> 21) & 0x7FF != 0x7FF or (h >> 19) & 3 != 3 or (h >> 17) & 3 != 1:
            break
        kbps, sr, pad = taxas[(h >> 12) & 15], amostragem[(h >> 10) & 3], (h >> 9) & 1
        if not kbps or not sr:
            break
        modos.add((h >> 6) & 3)
        i += 144 * kbps * 1000 // sr + pad
        n += 1
    return n, modos


n, modos = quadros(mp3)
conferir("MP3 válido: quadros MPEG-1 Layer III do começo ao fim, mono", n > 100 and modos == {3}, f"{n} quadros, modos {modos}")
seg = float(r.headers.get("x-duracao-segundos", 0))
previsto = len(texto_para_fala(AVISO).split()) / PALAVRAS_POR_SEGUNDO
conferir("duração coerente com o texto (entre metade e o dobro da estimativa de locução)", previsto / 2 <= seg <= previsto * 2,
         f"{seg:.1f} s (estimativa {previsto:.1f} s)")
disp = r.headers.get("content-disposition", "")
conferir("nome do arquivo só em ASCII", disp == 'attachment; filename="farol-aviso-sao-joao-nepomuceno.mp3"', disp)

consulta = cliente("consulta@emg.example")
conferir("Consulta: não gera o áudio (403, só quem gera o aviso)", consulta.post("/api/audio", json=pedido).status_code == 403)
conferir("Consulta: nem o do comparativo (403)", consulta.post("/api/audio", json={**pedido, "comparativo": True}).status_code == 403)
conferir("Admin da empresa: pode", cliente("admin@emg.example").post("/api/audio", json=pedido).status_code == 200)
conferir("Admin do Norte: não pode (403)", cliente("admin@farol.example").post("/api/audio", json=pedido).status_code == 403)
ingles = op.post("/api/audio", json={**pedido, "idioma": "en", "texto": "Attention, listeners. On November 20, from 8 a.m. to 2 p.m., "
                                                                     "there will be a scheduled power outage in Graminha."})
conferir("inglês (Fase K): MP3 com a voz en_US-ljspeech (domínio público)", ingles.status_code == 200 and ingles.headers.get("content-type") == "audio/mpeg"
         and len(ingles.content) > 20_000, f"{ingles.status_code} {len(ingles.content)}")
erros = {"idioma es (sem voz com licença clara)": op.post("/api/audio", json={**pedido, "idioma": "es"}).status_code,
         "texto vazio": op.post("/api/audio", json={**pedido, "texto": "   "}).status_code,
         "texto longo": op.post("/api/audio", json={**pedido, "texto": "palavra " * 500}).status_code,
         "texto acima do limite do comparativo": op.post("/api/audio", json={**pedido, "comparativo": True,
                                                         "texto": "a" * (app_mod.audio.MAX_CARACTERES_COMPARATIVO + 1)}).status_code,
         "idioma longo": op.post("/api/audio", json={**pedido, "idioma": "x" * 11}).status_code,
         "município longo": op.post("/api/audio", json={**pedido, "municipio": "x" * 101}).status_code}
conferir("erros: idioma sem voz, texto vazio, texto longo demais, campos longos demais (422)",
         all(v == 422 for v in erros.values()), str(erros))
with conectar() as c, c.cursor() as cur:
    cur.execute("SELECT detalhe FROM registro WHERE acao = 'gerou MP3 do aviso'")
    reg = [d for (d,) in cur.fetchall()]
conferir("registro: áudio gerado (município e duração, sem o texto)", len(reg) == 3 and all("Graminha" not in d for d in reg), str(reg))
# produção no plano gratuito (FAROL_AUDIO=0): a tela é avisada e a API recusa, sem carregar a voz
app_mod.AUDIO = False
desligado = op.post("/api/audio", json=pedido)
conferir("FAROL_AUDIO=0: a API responde 503 e a configuração avisa a tela", desligado.status_code == 503
         and op.get("/api/config").json()["audio"] is False, f"{desligado.status_code} {desligado.text[:80]}")
app_mod.AUDIO = True
conferir("com o áudio ligado, a configuração diz que há áudio", op.get("/api/config").json()["audio"] is True)
longo = "Sítio Boa Vista, " * 220   # ~3.700 caracteres: passa do limite do aviso, cabe no do comparativo
r = op.post("/api/audio", json={**pedido, "texto": longo, "comparativo": True})
conferir("comparativo: o aviso de hoje, mais longo, gera o áudio (limite maior só aí)", r.status_code == 200 and len(r.content) > 100_000
         and op.post("/api/audio", json={**pedido, "texto": longo}).status_code == 422, f"{r.status_code} {len(r.content)}")

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_audio CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
