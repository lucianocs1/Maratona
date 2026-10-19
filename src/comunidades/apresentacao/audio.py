"""Áudio do aviso para a rádio: voz sintetizada offline (Piper) e MP3.

- Voz: Piper (piper-tts, GPL-3.0) com as vozes pt-BR de qualidade média do repositório oficial
  rhasspy/piper-voices (dados de treino CC0). Roda no servidor, sem internet e sem chave: o texto
  do aviso não sai daqui. A voz é baixada uma vez para data/raw/vozes/ e conferida pelo MD5 publicado.
- MP3: 128 kbps, mono, 44,1 kHz, o padrão das rádios (lameenc, o LAME, LGPL). A voz sai a 22,05 kHz e o
  LAME converte; sem isso o arquivo seria MPEG-2, que alguns sistemas de automação de rádio recusam.
- Antes de falar, o texto passa por nucleo/locucao.py ("8h às 14h" -> "8 horas às 14 horas").
- Isolado neste módulo: trocar de motor não mexe no resto.
- Voz feminina (as vozes pt-BR do Piper são todas masculinas): serviço de nuvem opcional. Google Cloud (padrão
  pt-BR-Chirp3-HD-Aoede; FAROL_VOZ_NUVEM=google e GOOGLE_TTS_KEY) ou Azure Speech (FAROL_VOZ_NUVEM=azure, AZURE_SPEECH_KEY e
  AZURE_SPEECH_REGION), só no .env/ambiente. Só o texto do aviso (já público, sem nome de pessoa, UC ou coordenada)
  sai do servidor, e a chamada é do servidor, não do navegador. Sem a chave, ou se a nuvem falhar, vale o Piper local.

A voz padrão é FAROL_VOZ (padrão pt_BR-faber-medium). Fase K: inglês com en_US-ljspeech-medium (dados LJ Speech em domínio
público, treinada do zero). Espanhol: as vozes do repositório são ajustes da voz "lessac" (dados com licença só de pesquisa,
Blizzard 2013) ou não dizem de onde partiram; por segurança, o espanhol fica sem áudio, a não ser que a empresa aceite a
licença e defina FAROL_VOZ_ES=es_ES-davefx-medium (ORIGEM.md).
Uso (amostras das vozes): uv run python -m comunidades.apresentacao.audio
"""

import functools
import hashlib
import json
import os
import shutil
import threading
import urllib.request
from pathlib import Path

import lameenc

from .. import config as C
from ..nucleo.locucao import texto_para_fala

REPOSITORIO = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOZES = {  # nome -> caminho no repositório (qualidade média)
    "pt_BR-faber-medium": "pt/pt_BR/faber/medium",
    "pt_BR-cadu-medium": "pt/pt_BR/cadu/medium",
    "pt_BR-jeff-medium": "pt/pt_BR/jeff/medium",
    "en_US-ljspeech-medium": "en/en_US/ljspeech/medium",
    "es_ES-davefx-medium": "es/es_ES/davefx/medium",
}
VOZ_PADRAO = os.environ.get("FAROL_VOZ") or "pt_BR-faber-medium"
# a voz de cada idioma do aviso; None: o idioma fica sem áudio (a tela avisa)
VOZ_DO_IDIOMA = {"pt-BR": VOZ_PADRAO, "en": "en_US-ljspeech-medium", "es": os.environ.get("FAROL_VOZ_ES") or None}


# FAROL_VOZ_LOCAL=0: sem a voz local (Piper): só a de nuvem. É o caso do Render gratuito, sem memória para o modelo.
LOCAL = os.environ.get("FAROL_VOZ_LOCAL", "1") != "0"
# voz de nuvem por idioma: Google Cloud Text-to-Speech (FAROL_VOZ_NUVEM=google, a chave em GOOGLE_TTS_KEY) ou
# Azure Speech (azure, AZURE_SPEECH_KEY e AZURE_SPEECH_REGION); FAROL_VOZ_NUVEM_NOME troca a voz do pt-BR
NUVEM = (C.segredo("FAROL_VOZ_NUVEM") or "0").lower()
VOZES_NUVEM = {
    "google": {"pt-BR": "pt-BR-Chirp3-HD-Aoede", "en": "en-US-Neural2-F", "es": "es-ES-Neural2-A"},
    "azure": {"pt-BR": "pt-BR-FranciscaNeural", "en": "en-US-JennyNeural", "es": "es-ES-ElviraNeural"},
}
VOZ_NUVEM = dict(VOZES_NUVEM.get(NUVEM, {}))
if VOZ_NUVEM and (C.segredo("FAROL_VOZ_NUVEM_NOME") or C.segredo("FAROL_VOZ_AZURE")):
    VOZ_NUVEM["pt-BR"] = C.segredo("FAROL_VOZ_NUVEM_NOME") or C.segredo("FAROL_VOZ_AZURE")
LOCALE_NUVEM = {"pt-BR": "pt-BR", "en": "en-US", "es": "es-ES"}
TAXA_NUVEM = 24_000


def nuvem_ligada() -> bool:
    if NUVEM == "google":
        return bool(C.segredo("GOOGLE_TTS_KEY"))
    return NUVEM == "azure" and bool(C.segredo("AZURE_SPEECH_KEY")) and bool(C.segredo("AZURE_SPEECH_REGION"))


def idiomas_com_voz() -> list[str]:
    nuvem = list(VOZ_NUVEM) if nuvem_ligada() else []
    local = [i for i, v in VOZ_DO_IDIOMA.items() if v in VOZES] if LOCAL else []
    return list(dict.fromkeys(nuvem + local))


def _pcm_google(fala: str, idioma: str) -> bytes:
    """PCM 16 bits, 24 kHz, mono do Google Cloud Text-to-Speech (a chave vai no cabeçalho, nunca na URL)."""
    import base64
    corpo = json.dumps({"input": {"text": fala}, "voice": {"languageCode": LOCALE_NUVEM[idioma], "name": VOZ_NUVEM[idioma]},
                        "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": TAXA_NUVEM, "speakingRate": 0.95}}).encode("utf-8")
    req = urllib.request.Request("https://texttospeech.googleapis.com/v1/text:synthesize", data=corpo, method="POST",
                                 headers={"X-Goog-Api-Key": C.segredo("GOOGLE_TTS_KEY"), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        wav = base64.b64decode(json.loads(r.read())["audioContent"])
    return wav[44:] if wav[:4] == b"RIFF" else wav   # LINEAR16 vem com o cabeçalho WAV de 44 bytes


def _pcm_azure(fala: str, idioma: str) -> bytes:
    """PCM 16 bits, 24 kHz, mono do Azure Speech para o texto (SSML; o texto vai escapado)."""
    from xml.sax.saxutils import escape
    regiao = C.segredo("AZURE_SPEECH_REGION")
    ssml = (f"<speak version='1.0' xml:lang='{LOCALE_NUVEM[idioma]}'><voice name='{VOZ_NUVEM[idioma]}'>"
            f"<prosody rate='-5%'>{escape(fala)}</prosody></voice></speak>")
    req = urllib.request.Request(
        f"https://{regiao}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"), method="POST",
        headers={"Ocp-Apim-Subscription-Key": C.segredo("AZURE_SPEECH_KEY"), "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "raw-24khz-16bit-mono-pcm", "User-Agent": "norte-farol"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()
PASTA = C.RAW / "vozes"
KBPS = 128
TAXA_SAIDA = 44_100
MAX_CARACTERES = 3000
MAX_CARACTERES_COMPARATIVO = 30_000  # o aviso de hoje (fazenda a fazenda) no comparativo
_trava = threading.Lock()   # o modelo é um só por processo; uma síntese por vez


def _baixar(url: str, destino: Path) -> None:
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.replace(destino)


@functools.lru_cache(maxsize=1)
def _catalogo() -> dict:
    arq = PASTA / "voices.json"
    if not arq.exists():
        PASTA.mkdir(parents=True, exist_ok=True)
        _baixar(f"{REPOSITORIO}/voices.json", arq)
    return json.loads(arq.read_text(encoding="utf-8"))


def garantir_voz(nome: str = VOZ_PADRAO) -> Path:
    """Baixa o modelo (.onnx e .onnx.json) se faltar e confere o MD5 de cada arquivo com o catálogo."""
    if nome not in VOZES:
        raise ValueError(f"voz desconhecida: {nome} (use uma de {', '.join(VOZES)})")
    arquivos = _catalogo()[nome]["files"]
    for sufixo in (".onnx", ".onnx.json"):
        caminho = f"{VOZES[nome]}/{nome}{sufixo}"
        destino = PASTA / f"{nome}{sufixo}"
        if not destino.exists():
            print(f"  baixando a voz {destino.name}...", flush=True)
            _baixar(f"{REPOSITORIO}/{caminho}", destino)
        md5 = hashlib.md5(destino.read_bytes()).hexdigest()
        if md5 != arquivos[caminho]["md5_digest"]:
            destino.unlink()
            raise RuntimeError(f"{destino.name}: MD5 não confere com o catálogo do Piper (arquivo apagado; baixe de novo)")
    return PASTA / f"{nome}.onnx"


@functools.lru_cache(maxsize=3)
def _voz(nome: str):
    from piper import PiperVoice  # importa só quando o áudio é pedido (o modelo leva ~1 s para carregar)
    return PiperVoice.load(str(garantir_voz(nome)))


def _pcm_nuvem(fala: str, idioma: str) -> bytes:
    return (_pcm_google if NUVEM == "google" else _pcm_azure)(fala, idioma)


def _para_mp3(pcm: bytes, taxa: int) -> bytes:
    enc = lameenc.Encoder()
    enc.set_bit_rate(KBPS)
    enc.set_in_sample_rate(taxa)
    enc.set_out_sample_rate(TAXA_SAIDA)
    enc.set_channels(1)
    enc.set_quality(2)  # 2 = alta qualidade
    return bytes(enc.encode(pcm)) + bytes(enc.flush())


def mp3(texto: str, idioma: str = "pt-BR", voz: str | None = None, max_caracteres: int = MAX_CARACTERES) -> tuple[bytes, float]:
    """(MP3, duração em segundos) do texto falado, com a voz do idioma (ou a voz pedida, para as amostras).
    Com a nuvem ligada, a voz é a do Google ou do Azure; se ela falhar (rede, cota), cai para o Piper local, se houver voz."""
    usar_nuvem = voz is None and nuvem_ligada() and idioma in VOZ_NUVEM   # uma voz pedida (amostras) é sempre a local
    voz = voz or VOZ_DO_IDIOMA.get(idioma)
    if not usar_nuvem and (voz not in VOZES or not LOCAL):
        raise ValueError("Sem voz com licença adequada para este idioma: o aviso vai sem áudio (veja ORIGEM.md).")
    fala = texto_para_fala(texto, idioma)
    if not fala or len(fala) > max_caracteres:
        raise ValueError(f"O texto do áudio tem de ter de 1 a {max_caracteres:,} caracteres.".replace(",", "."))
    if usar_nuvem:
        try:
            pcm = _pcm_nuvem(fala, idioma)
            if pcm:
                return _para_mp3(pcm, TAXA_NUVEM), len(pcm) / 2 / TAXA_NUVEM
        except Exception as e:   # só o tipo do erro no log: nunca o texto nem a chave
            print(f"  voz de nuvem indisponível ({type(e).__name__}); usando a voz local", flush=True)
        if not LOCAL or VOZ_DO_IDIOMA.get(idioma) not in VOZES:
            raise ValueError("A voz de nuvem não respondeu e não há voz local para este idioma.")
        voz = VOZ_DO_IDIOMA[idioma]
    with _trava:
        v = _voz(voz)
        pedacos = list(v.synthesize(fala))
    taxa = pedacos[0].sample_rate
    pcm = b"".join(p.audio_int16_bytes for p in pedacos)
    return _para_mp3(pcm, taxa), len(pcm) / 2 / taxa


if __name__ == "__main__":
    exemplo = ("Atenção, moradores de Graminha, Boa Sorte e Piacatuba, e de parte de Tomé Nogueira, em Leopoldina "
               "(distritos Piacatuba e Sede): no dia 20/11, das 8h às 14h30, haverá desligamento programado de energia "
               "para manutenção na rede. Programe-se!")
    saida = C.SAIDA / "audio_amostras"
    saida.mkdir(parents=True, exist_ok=True)
    print(f"Texto falado: {texto_para_fala(exemplo)}")
    for nome in [v for v in VOZES if v.startswith("pt_BR")]:
        dados, seg = mp3(exemplo, voz=nome)
        (saida / f"{nome}.mp3").write_bytes(dados)
        print(f"{nome}: {seg:.1f} s, {len(dados) / 1024:.0f} KB -> {saida / (nome + '.mp3')}")
