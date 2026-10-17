"""Pacote assinado da conferência: o JSON da planilha que vai ao navegador no 1º passo e volta no 2º.

O 1º passo (Conferir) traduz a planilha e devolve o JSON com as UCs trocadas por códigos opacos
(nucleo/travas.ucs_opacas), comprimido e assinado com HMAC-SHA256. O 2º passo (Gerar aviso) só
aceita o pacote se:
- a assinatura confere (nada foi mudado no navegador);
- ainda não venceu (15 minutos);
- é do mesmo usuário e da mesma empresa de quem importou;
- o JSON passa de novo no esquema fechado (nucleo/esquema_planilha.validar_json).
Assim a planilha não precisa ser enviada de novo nem guardada no servidor.

Desde a escolha de quem será desligado (nucleo/selecao.py), o pacote tem uma fase, também assinada:
"base" (a planilha lida, para escolher; não gera aviso) ou "escolha" (a planilha e o critério da escolha,
em forma canônica: o que foi conferido é exatamente o que gera o aviso).

A chave vem só da variável de ambiente FAROL_CHAVE_PACOTE (pelo menos 32 caracteres; .env local,
segredo no Render). Sem ela, uma chave aleatória vale enquanto o processo estiver no ar (os pacotes
abertos ficam inválidos quando o servidor reinicia: basta importar de novo).
"""

import base64
import gzip
import hashlib
import hmac
import json
import logging
import secrets
import time
import zlib

from pydantic import ValidationError

from ..nucleo import selecao
from ..nucleo.esquema_planilha import PlanilhaJSON, validar_json
from ..segredos import segredo

VALIDADE = 15 * 60                 # segundos
MAX_PACOTE = 30_000_000            # caracteres do pacote (50.000 linhas comprimidas cabem com folga)
MAX_DESCOMPACTADO = 80_000_000     # bytes do JSON depois de descomprimir
VERSAO = "v2"                      # v2: fase e critério da escolha
FASES = ("base", "escolha")
_log = logging.getLogger("farol.pacote")


def _chave() -> bytes:
    k = segredo("FAROL_CHAVE_PACOTE") or ""
    if len(k) >= 32:
        return k.encode()
    _log.warning("FAROL_CHAVE_PACOTE ausente ou curta: chave aleatória só deste processo.")
    return secrets.token_bytes(32)


CHAVE = _chave()


class PacoteRecusado(ValueError):
    """O pacote não serve (adulterado, vencido, de outro usuário ou fora do esquema): importar de novo."""


def _assinatura(corpo: str) -> str:
    return hmac.new(CHAVE, f"farol-pacote.{VERSAO}.{corpo}".encode(), hashlib.sha256).hexdigest()


def assinar(m: PlanilhaJSON, usuario_id: int, empresa_id: int | None, agora: float | None = None, *,
            fase: str = "escolha", criterio: selecao.Criterio | None = None) -> tuple[str, int]:
    """O pacote (texto) e quando vence (epoch). O JSON já deve estar com as UCs opacas. Na fase "escolha", o
    critério vai junto (sem critério: a planilha inteira)."""
    if fase not in FASES:
        raise ValueError("fase do pacote inválida")
    vence = int((agora or time.time()) + VALIDADE)
    c = selecao.texto_canonico(criterio or selecao.Criterio(modo="planilha")) if fase == "escolha" else None
    dados = json.dumps({"u": usuario_id, "e": empresa_id, "vence": vence, "f": fase, "c": c, "m": m.model_dump_json()},
                       ensure_ascii=False, separators=(",", ":"))
    corpo = base64.urlsafe_b64encode(gzip.compress(dados.encode(), mtime=0)).decode().rstrip("=")
    return f"{VERSAO}.{corpo}.{_assinatura(corpo)}", vence


def _descomprimir(b: bytes) -> bytes:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    saida = d.decompress(b, MAX_DESCOMPACTADO + 1)
    if len(saida) > MAX_DESCOMPACTADO or d.unconsumed_tail:
        raise PacoteRecusado("O pacote da conferência é grande demais.")
    return saida


def abrir(pacote: str, usuario_id: int, empresa_id: int | None, agora: float | None = None,
          fase: str | None = None) -> PlanilhaJSON:
    """O JSON da planilha, se o pacote vale para este usuário agora (e é da fase pedida); senão PacoteRecusado."""
    return _abrir(pacote, usuario_id, empresa_id, agora, fase)[0]


def abrir_escolha(pacote: str, usuario_id: int, empresa_id: int | None,
                  agora: float | None = None) -> tuple[PlanilhaJSON, selecao.Criterio]:
    """O JSON e o critério da escolha conferida (só o pacote da fase "escolha" gera aviso)."""
    return _abrir(pacote, usuario_id, empresa_id, agora, "escolha")


def _abrir(pacote, usuario_id, empresa_id, agora, fase):
    if not isinstance(pacote, str) or len(pacote) > MAX_PACOTE:
        raise PacoteRecusado("Pacote da conferência inválido. Importe a planilha de novo.")
    partes = pacote.split(".")
    if len(partes) != 3 or partes[0] != VERSAO or not hmac.compare_digest(partes[2], _assinatura(partes[1])):
        raise PacoteRecusado("O pacote da conferência foi alterado ou não é deste servidor. Importe a planilha de novo.")
    try:
        dados = json.loads(_descomprimir(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4))))
    except PacoteRecusado:
        raise
    except Exception:  # noqa: BLE001 (assinado por nós e ainda assim ilegível: recusa sem detalhe)
        raise PacoteRecusado("Pacote da conferência ilegível. Importe a planilha de novo.") from None
    if dados.get("u") != usuario_id or dados.get("e") != empresa_id:
        raise PacoteRecusado("Este pacote da conferência é de outro usuário. Importe a planilha de novo.")
    if (agora or time.time()) > dados.get("vence", 0):
        raise PacoteRecusado("A conferência venceu (vale 15 minutos). Importe a planilha de novo.")
    if fase and dados.get("f") != fase:
        raise PacoteRecusado("Escolha quem será desligado e confira antes de gerar o aviso." if fase == "escolha"
                             else "Este pacote não é o da planilha lida. Importe a planilha de novo.")
    try:
        m = validar_json(dados["m"])
        c = selecao.Criterio.model_validate_json(dados["c"]) if dados.get("f") == "escolha" else None
        return m, c
    except (ValidationError, KeyError, TypeError):
        raise PacoteRecusado("O JSON da conferência não passou no esquema. Importe a planilha de novo.") from None
