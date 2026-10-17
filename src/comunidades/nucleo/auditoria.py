"""Auditoria encadeada: cada linha do registro guarda o hash da anterior. Puro (o banco grava em banco/acesso.py).

- Só inclusão: nada é alterado nem apagado (o banco também recusa UPDATE, DELETE e TRUNCATE); uma
  correção é uma linha nova.
- Cada linha tem quando, quem (nome e perfil copiados do login naquele momento, nunca digitados),
  a empresa, a ação, o detalhe, o hash da linha anterior e o próprio hash:
  hash = SHA-256 da forma canônica (JSON compacto, nesta ordem) de
  [id, quando (UTC, ISO com microssegundos), empresa_id, usuario_id, usuario_nome, perfil, acao, detalhe, hash_anterior].
- verificar() refaz a conta da primeira à última linha e aponta a primeira que não bate: uma linha
  alterada, apagada no meio ou fora de ordem quebra a corrente dali em diante.
- O código de verificação de um aviso (e de um relatório) sai do hash da linha que o registrou: quem
  tem o código acha a linha na auditoria e confere que ela está na corrente.
"""

import hashlib
import json
from datetime import datetime, timezone

INICIO = "0" * 64        # o "hash anterior" da primeira linha
CAMPOS = ("id", "quando", "empresa_id", "usuario_id", "usuario_nome", "perfil", "acao", "detalhe", "hash_anterior")


def _quando(q) -> str:
    if isinstance(q, datetime):
        return q.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return str(q)


def canonico(linha: dict) -> bytes:
    """Os campos da linha, na ordem fixa, em JSON compacto (o que o hash cobre)."""
    valores = [_quando(linha["quando"]) if c == "quando" else linha.get(c) for c in CAMPOS]
    return json.dumps(valores, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def hash_linha(linha: dict) -> str:
    return hashlib.sha256(canonico(linha)).hexdigest()


def verificar(linhas: list[dict]) -> dict:
    """Confere a corrente inteira (linhas em ordem de id). ok, quantas linhas e, se quebrou, onde e por quê."""
    anterior, ultimo_id = INICIO, None
    for n, ln in enumerate(linhas):
        if ultimo_id is not None and ln["id"] <= ultimo_id:
            return {"ok": False, "linhas": len(linhas), "conferidas": n, "quebra_id": ln["id"], "motivo": "fora de ordem"}
        if ln.get("hash_anterior") != anterior:
            return {"ok": False, "linhas": len(linhas), "conferidas": n, "quebra_id": ln["id"],
                    "motivo": "a linha não aponta para a anterior (linha apagada ou inserida)"}
        if ln.get("hash") != hash_linha(ln):
            return {"ok": False, "linhas": len(linhas), "conferidas": n, "quebra_id": ln["id"], "motivo": "conteúdo alterado"}
        anterior, ultimo_id = ln["hash"], ln["id"]
    return {"ok": True, "linhas": len(linhas), "conferidas": len(linhas), "quebra_id": None, "motivo": None,
            "ultimo_hash": anterior}


def codigo_verificacao(hash_: str) -> str:
    """'FRL-' e os 12 primeiros caracteres do hash, em 3 grupos (ex.: FRL-3F2A-91C0-7B44)."""
    h = hash_[:12].upper()
    return f"FRL-{h[:4]}-{h[4:8]}-{h[8:12]}"


def diferencas(antes: dict, depois: dict, rotulos: dict) -> str:
    """'valor padrão: 150.00 → 200.00; e-mail: a@x → b@x' (só o que mudou). Textos longos viram 'alterado (N → M caracteres)'."""
    partes = []
    for campo, rotulo in rotulos.items():
        a, d = antes.get(campo), depois.get(campo)
        if str(a) == str(d):
            continue
        if len(str(a)) > 60 or len(str(d)) > 60:
            partes.append(f"{rotulo}: alterado ({len(str(a or ''))} → {len(str(d or ''))} caracteres)")
        else:
            partes.append(f"{rotulo}: {'—' if a in (None, '') else a} → {'—' if d in (None, '') else d}")
    return "; ".join(partes) or "nada mudou"
