"""Hash de senha (Argon2id) e senha temporária: usados pela API (api/acesso.py) e pela semente.

- Argon2id com os parâmetros mínimos recomendados pela OWASP (Password Storage Cheat Sheet):
  19 MiB de memória, 2 passadas, 1 linha. Cabe no plano gratuito do Render (512 MB): cada hash
  usa ~19 MiB, e no máximo HASHES_SIMULTANEOS rodam ao mesmo tempo (os outros esperam a vez).
  O padrão do argon2-cffi (64 MiB, t=3, p=4) derrubaria o servidor com poucos logins ao mesmo tempo.
- Hashes antigos (de outros parâmetros) continuam valendo; no login certo, precisa_refazer() diz
  que o hash deve ser refeito com os parâmetros atuais.
- Nada de rede, arquivo ou banco aqui.
"""

import secrets
import threading

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MEMORIA_KIB, PASSADAS, LINHAS = 19 * 1024, 2, 1        # OWASP: m=19 MiB, t=2, p=1 (o mínimo)
HASHES_SIMULTANEOS = 4                                   # ~76 MiB no pior caso
ESPERA_MAXIMA = 10                                       # segundos na fila antes de desistir
HASHER = PasswordHasher(time_cost=PASSADAS, memory_cost=MEMORIA_KIB, parallelism=LINHAS, type=Type.ID)
_vez = threading.BoundedSemaphore(HASHES_SIMULTANEOS)


class Ocupado(RuntimeError):
    """Hashes demais ao mesmo tempo: a requisição deve ser recusada (tente de novo)."""


def _na_vez(f, *args):
    if not _vez.acquire(timeout=ESPERA_MAXIMA):
        raise Ocupado("Muitos acessos ao mesmo tempo. Tente de novo em instantes.")
    try:
        return f(*args)
    finally:
        _vez.release()


def hash_senha(senha: str) -> str:
    return _na_vez(HASHER.hash, senha)


def conferir(hash_: str, senha: str) -> bool:
    def _verificar(h, s):
        try:
            return HASHER.verify(h, s)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    return _na_vez(_verificar, hash_, senha)


def precisa_refazer(hash_: str) -> bool:
    return HASHER.check_needs_rehash(hash_)


# para e-mail desconhecido levar o mesmo tempo que senha errada
HASH_FALSO = HASHER.hash(secrets.token_urlsafe(16))


def senha_temporaria() -> str:
    """16 caracteres sem os ambíguos (0/O, 1/l/I), em 4 grupos para ditar: 'k7Pm-3xQa-...'"""
    alfabeto = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    s = "".join(secrets.choice(alfabeto) for _ in range(16))
    return "-".join(s[i:i + 4] for i in range(0, 16, 4))
