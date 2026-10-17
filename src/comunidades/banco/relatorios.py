"""Consultas dos relatórios: avisos e envios de um período e linhas da auditoria (só agregados e registros)."""

from datetime import date, datetime, time, timedelta, timezone

from psycopg.rows import dict_row

from .acesso import AVISO
from .conexao import conectar
from .radios import ENVIO

BRASILIA = timezone(timedelta(hours=-3))


def _todos(sql: str, args=()) -> list[dict]:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def _intervalo(inicio: date, fim: date) -> tuple[datetime, datetime]:
    """Do começo do primeiro dia ao fim do último, no horário de Brasília."""
    return datetime.combine(inicio, time.min, BRASILIA), datetime.combine(fim + timedelta(days=1), time.min, BRASILIA)


def avisos(empresa_id: int, inicio: date, fim: date) -> list[dict]:
    a, b = _intervalo(inicio, fim)
    return _todos(f"SELECT {AVISO} FROM aviso a LEFT JOIN usuario u ON u.id = a.usuario_id"
                  " WHERE a.empresa_id = %s AND a.criado_em >= %s AND a.criado_em < %s ORDER BY a.criado_em", (empresa_id, a, b))


def envios(empresa_id: int, aviso_ids: list[int]) -> list[dict]:
    if not aviso_ids:
        return []
    return _todos(f"SELECT {ENVIO} FROM envio e WHERE e.empresa_id = %s AND e.aviso_id = ANY(%s) ORDER BY e.id",
                  (empresa_id, list(aviso_ids)))


def guardar_via(empresa_id: int | None, usuario_id: int, usuario_nome: str, tipo: str, titulo: str, filtros: str, codigo: str,
                sha256: str, tamanho: int, cifrado: bytes) -> int:
    with conectar() as c:
        return c.execute("INSERT INTO relatorio_via (empresa_id, usuario_id, usuario_nome, tipo, titulo, filtros, codigo, sha256, tamanho, cifrado)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                         (empresa_id, usuario_id, usuario_nome, tipo, titulo, filtros, codigo, sha256, tamanho, cifrado)).fetchone()[0]


VIA = "v.id, v.empresa_id, v.usuario_nome, v.tipo, v.titulo, v.filtros, v.codigo, v.sha256, v.tamanho, v.criado_em"


def vias(empresa_id: int | None, tipos: tuple[str, ...], limite: int = 200) -> list[dict]:
    """As vias da empresa (ou as sem empresa, do Admin do Norte), dos tipos que o perfil pode ver."""
    filtro = "v.empresa_id = %s" if empresa_id is not None else "v.empresa_id IS NULL"
    args = (empresa_id,) if empresa_id is not None else ()
    return _todos(f"SELECT {VIA} FROM relatorio_via v WHERE {filtro} AND v.tipo = ANY(%s) ORDER BY v.id DESC LIMIT %s",
                  (*args, list(tipos), limite))


def via(id_: int, empresa_id: int | None) -> dict | None:
    filtro = "v.empresa_id = %s" if empresa_id is not None else "v.empresa_id IS NULL"
    args = (empresa_id,) if empresa_id is not None else ()
    r = _todos(f"SELECT {VIA}, v.cifrado FROM relatorio_via v WHERE v.id = %s AND {filtro}", (id_, *args))
    return r[0] if r else None


def via_por_codigo(codigo: str) -> dict | None:
    r = _todos(f"SELECT {VIA} FROM relatorio_via v WHERE v.codigo = %s", (codigo,))
    return r[0] if r else None


def avisos_futuros(empresa_id: int, desde: date) -> list[dict]:
    """Avisos gerados nos últimos 60 dias (os que podem ter desligamento nos próximos dias)."""
    return avisos(empresa_id, desde - timedelta(days=60), desde + timedelta(days=1))


def registros(empresa_id: int | None, inicio: date, fim: date, pessoa: str | None = None, acoes: tuple[str, ...] | None = None,
              empresa_sigla: str | None = None, limite: int = 5000) -> list[dict]:
    """Linhas da auditoria do período (da empresa, ou de todas com empresa_id None), da mais antiga à mais recente."""
    a, b = _intervalo(inicio, fim)
    filtros, args = ["r.quando >= %s", "r.quando < %s"], [a, b]
    if empresa_id is not None:
        filtros.append("r.empresa_id = %s")
        args.append(empresa_id)
    if empresa_sigla:
        filtros.append("e.sigla = %s")
        args.append(empresa_sigla)
    if pessoa:
        filtros.append("r.usuario_nome = %s")
        args.append(pessoa)
    if acoes:
        filtros.append("r.acao = ANY(%s)")
        args.append(list(acoes))
    return _todos("SELECT r.id, r.quando, r.acao, r.detalhe, r.usuario_nome AS usuario, r.perfil, r.hash, e.sigla AS empresa"
                  " FROM registro r LEFT JOIN empresa e ON e.id = r.empresa_id WHERE " + " AND ".join(filtros)
                  + " ORDER BY r.id LIMIT %s", (*args, limite))
