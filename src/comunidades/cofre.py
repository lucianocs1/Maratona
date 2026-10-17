"""Cofre dos arquivos enviados à rádio (PDF e MP3): AES-256-GCM, com a chave só em variável de ambiente.

- Chave: FAROL_CHAVE_ARQUIVOS, 32 bytes em base64 (urlsafe), no .env local e como segredo no Render;
  nunca no código nem no git. Um segredo de outro formato com 32 caracteres ou mais (o que o Render
  gera) vira a chave pelo SHA-256. Sem a chave, nada é guardado (o envio avisa).
- Cada arquivo leva um nonce aleatório de 12 bytes e é amarrado ao seu lugar (empresa, envio e tipo,
  como dado associado): trocar o arquivo de um envio por outro faz a abertura falhar.
- Formato: b"FAR1" + nonce + texto cifrado com a etiqueta do GCM.
"""

import base64
import binascii
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .segredos import segredo

PREFIXO = b"FAR1"


class SemChave(RuntimeError):
    """FAROL_CHAVE_ARQUIVOS não configurada (ou inválida)."""


class Violado(ValueError):
    """O arquivo cifrado não abre: foi alterado, trocado de lugar ou a chave é outra."""


def _chave() -> bytes:
    k = segredo("FAROL_CHAVE_ARQUIVOS") or ""
    try:
        b = base64.urlsafe_b64decode(k + "=" * (-len(k) % 4)) if k else b""
    except (binascii.Error, ValueError):
        b = b""
    if len(b) != 32 and len(k) >= 32:
        b = hashlib.sha256(k.encode()).digest()
    if len(b) != 32:
        raise SemChave("FAROL_CHAVE_ARQUIVOS ausente ou inválida (32 bytes em base64): os arquivos enviados não são guardados.")
    return b


def disponivel() -> bool:
    try:
        _chave()
        return True
    except SemChave:
        return False


def _contexto(empresa_id: int, envio_id: int, tipo: str) -> bytes:
    return f"farol-arquivo:{empresa_id}:{envio_id}:{tipo}".encode()


def cifrar(dados: bytes, empresa_id: int, envio_id: int, tipo: str) -> bytes:
    nonce = os.urandom(12)
    return PREFIXO + nonce + AESGCM(_chave()).encrypt(nonce, dados, _contexto(empresa_id, envio_id, tipo))


def decifrar(cifrado: bytes, empresa_id: int, envio_id: int, tipo: str) -> bytes:
    b = bytes(cifrado)
    if not b.startswith(PREFIXO) or len(b) < len(PREFIXO) + 12 + 16:
        raise Violado("arquivo cifrado inválido")
    try:
        return AESGCM(_chave()).decrypt(b[4:16], b[16:], _contexto(empresa_id, envio_id, tipo))
    except InvalidTag:
        raise Violado("o arquivo cifrado não confere (alterado, trocado ou outra chave)") from None


def nova_chave() -> str:
    """Uma chave nova para o .env (uv run python -c "from comunidades import cofre; print(cofre.nova_chave())")."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()
