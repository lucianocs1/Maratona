"""Rádios, configuração da empresa e envios do aviso, no banco (por empresa, nunca em TOML).

- empresa_config: modelo da mensagem, nome que a mensagem fala, telefone de atendimento, limite de
  rejeição da planilha, fuso UTM e antecedência; sem linha, valem os padrões da distribuidora.
- radio: nome, e-mail, WhatsApp, o que alcança (municípios inteiros e comunidades com o distrito) e o
  valor padrão. Contato de empresa (a rádio), não de cliente.
- envio: cada envio de um município do aviso para uma rádio, com o valor e a forma de cobrança
  gravados no envio (mudar o preço da rádio depois não muda o passado), o custo, a economia, quem
  informou, o canal e a situação. O token de confirmação fica só como hash, vale 7 dias e uma vez.
- arquivo_envio: o PDF e o MP3 enviados, cifrados (AES-256-GCM, cofre.py) para baixar de novo.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from psycopg.rows import dict_row

from .conexao import conectar

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresa_config (
    empresa_id        bigint PRIMARY KEY REFERENCES empresa ON DELETE RESTRICT,
    modelo_mensagem   text,
    nome_mensagem     text,
    telefone          text,
    limite_rejeicao   numeric(5, 4) CHECK (limite_rejeicao BETWEEN 0 AND 1),
    epsg_utm          integer CHECK (epsg_utm BETWEEN 31960 AND 31985),
    antecedencia_dias integer CHECK (antecedencia_dias BETWEEN 1 AND 90),
    atualizado_por    bigint REFERENCES usuario ON DELETE RESTRICT,
    atualizado_em     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS radio (
    id            bigserial PRIMARY KEY,
    empresa_id    bigint NOT NULL REFERENCES empresa ON DELETE RESTRICT,
    nome          text NOT NULL,
    email         text,
    whatsapp      text,
    alcance       jsonb NOT NULL DEFAULT '{"municipios": [], "comunidades": []}',
    valor_padrao  numeric(12, 2),
    cobranca      text NOT NULL DEFAULT 'fechado' CHECK (cobranca IN ('fechado', 'minuto')),
    ativa         boolean NOT NULL DEFAULT true,
    criada_por    bigint REFERENCES usuario ON DELETE RESTRICT,
    criada_em     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS envio (
    id                bigserial PRIMARY KEY,
    empresa_id        bigint NOT NULL REFERENCES empresa ON DELETE RESTRICT,
    aviso_id          bigint NOT NULL REFERENCES aviso ON DELETE RESTRICT,
    municipio         text NOT NULL,
    municipio_nome    text NOT NULL,
    radio_id          bigint NOT NULL REFERENCES radio ON DELETE RESTRICT,
    radio_nome        text NOT NULL,
    canal             text NOT NULL CHECK (canal IN ('email', 'whatsapp', 'copia')),
    destino           text NOT NULL DEFAULT '',
    texto             text NOT NULL,
    valor             numeric(12, 2) NOT NULL,
    cobranca          text NOT NULL CHECK (cobranca IN ('fechado', 'minuto')),
    custo             numeric(12, 2) NOT NULL,
    custo_antigo      numeric(12, 2),
    economia          numeric(12, 2),
    economia_tipo     text CHECK (economia_tipo IN ('calculada', 'informada')),
    segundos          integer NOT NULL,
    segundos_hoje     integer,
    tempo_economizado integer,
    status            text NOT NULL CHECK (status IN ('preparando', 'enviado', 'entregue', 'falhou', 'confirmado')),
    criado_por        bigint REFERENCES usuario ON DELETE RESTRICT,
    criado_por_nome   text NOT NULL,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    token_hash        bytea UNIQUE,
    token_expira      timestamptz,
    confirmado_em     timestamptz
);
CREATE TABLE IF NOT EXISTS arquivo_envio (
    id         bigserial PRIMARY KEY,
    envio_id   bigint NOT NULL REFERENCES envio ON DELETE RESTRICT,
    empresa_id bigint NOT NULL REFERENCES empresa ON DELETE RESTRICT,
    tipo       text NOT NULL CHECK (tipo IN ('pdf', 'mp3')),
    nome       text NOT NULL,
    tamanho    integer NOT NULL,
    cifrado    bytea NOT NULL,
    UNIQUE (envio_id, tipo)
);
-- Fase H: orçamento anual de rádio, alerta de preço e repetição (configuração da empresa)
ALTER TABLE empresa_config ADD COLUMN IF NOT EXISTS orcamento_radio numeric(14, 2) CHECK (orcamento_radio >= 0),
    ADD COLUMN IF NOT EXISTS alerta_preco numeric(5, 4) CHECK (alerta_preco BETWEEN 0 AND 5),
    ADD COLUMN IF NOT EXISTS repeticao_n integer CHECK (repeticao_n BETWEEN 2 AND 50),
    ADD COLUMN IF NOT EXISTS repeticao_dias integer CHECK (repeticao_dias BETWEEN 7 AND 365);
-- Fase H: segunda via de cada relatório em PDF, cifrada (o código FRL aponta a linha da auditoria; o SHA-256 confere o arquivo)
CREATE TABLE IF NOT EXISTS relatorio_via (
    id            bigserial PRIMARY KEY,
    empresa_id    bigint REFERENCES empresa ON DELETE RESTRICT,
    usuario_id    bigint REFERENCES usuario ON DELETE RESTRICT,
    usuario_nome  text NOT NULL,
    tipo          text NOT NULL,
    titulo        text NOT NULL,
    filtros       text NOT NULL DEFAULT '',
    codigo        text NOT NULL UNIQUE,
    sha256        text NOT NULL,
    tamanho       integer NOT NULL,
    cifrado       bytea NOT NULL,
    criado_em     timestamptz NOT NULL DEFAULT now()
);
-- Fase J: pedidos de cadastro de rádio (o Operador pede; o Admin da empresa atende, cadastrando a rádio, ou recusa com motivo).
-- Contato da rádio (empresa), nunca de cliente.
CREATE TABLE IF NOT EXISTS pedido_radio (
    id                 bigserial PRIMARY KEY,
    empresa_id         bigint NOT NULL REFERENCES empresa ON DELETE RESTRICT,
    nome               text NOT NULL,
    cidade             text NOT NULL,
    contato            text NOT NULL DEFAULT '',
    observacao         text NOT NULL DEFAULT '',
    status             text NOT NULL DEFAULT 'aberto' CHECK (status IN ('aberto', 'atendido', 'recusado')),
    motivo_recusa      text,
    radio_id           bigint REFERENCES radio ON DELETE RESTRICT,
    criado_por         bigint REFERENCES usuario ON DELETE RESTRICT,
    criado_por_nome    text NOT NULL,
    criado_em          timestamptz NOT NULL DEFAULT now(),
    resolvido_por_nome text,
    resolvido_em       timestamptz
);
-- Fase K: o modelo da mensagem em inglês e em espanhol e o idioma padrão do aviso da empresa
ALTER TABLE empresa_config ADD COLUMN IF NOT EXISTS modelo_mensagem_en text, ADD COLUMN IF NOT EXISTS modelo_mensagem_es text,
    ADD COLUMN IF NOT EXISTS idioma_padrao text CHECK (idioma_padrao IN ('pt-BR', 'en', 'es'));
-- Simulador de economia (Relatórios): gasto mensal com rádio (faixa mín-máx) e % do gasto cobrado por tempo
ALTER TABLE empresa_config ADD COLUMN IF NOT EXISTS simulador_gasto_min numeric(14, 2) CHECK (simulador_gasto_min >= 0),
    ADD COLUMN IF NOT EXISTS simulador_gasto_max numeric(14, 2) CHECK (simulador_gasto_max >= 0),
    ADD COLUMN IF NOT EXISTS simulador_pct_tempo numeric(5, 2) CHECK (simulador_pct_tempo BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS simulador_nota text CHECK (char_length(simulador_nota) <= 120);
CREATE INDEX IF NOT EXISTS pedido_radio_empresa ON pedido_radio (empresa_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS relatorio_via_empresa ON relatorio_via (empresa_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS radio_empresa ON radio (empresa_id);
CREATE INDEX IF NOT EXISTS envio_aviso ON envio (aviso_id);
CREATE INDEX IF NOT EXISTS envio_empresa ON envio (empresa_id, criado_em DESC);
"""
VALIDADE_TOKEN = timedelta(days=7)


def criar_esquema(c) -> None:
    c.execute(ESQUEMA)


def _um(sql: str, args=()) -> dict | None:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchone() if cur.description else None


def _todos(sql: str, args=()) -> list[dict]:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


# ---------- Configuração da empresa ----------
def config(empresa_id: int) -> dict:
    return _um("SELECT * FROM empresa_config WHERE empresa_id = %s", (empresa_id,)) or {}


def salvar_config(empresa_id: int, usuario_id: int, dados: dict) -> None:
    campos = ("modelo_mensagem", "nome_mensagem", "telefone", "limite_rejeicao", "epsg_utm", "antecedencia_dias", "orcamento_radio",
              "alerta_preco", "repeticao_n", "repeticao_dias", "modelo_mensagem_en", "modelo_mensagem_es", "idioma_padrao")
    _um("INSERT INTO empresa_config (empresa_id, atualizado_por, " + ", ".join(campos) + ") VALUES (%s, %s, "
        + ", ".join(["%s"] * len(campos)) + ") ON CONFLICT (empresa_id) DO UPDATE SET atualizado_por = EXCLUDED.atualizado_por,"
        " atualizado_em = now(), " + ", ".join(f"{c} = EXCLUDED.{c}" for c in campos),
        (empresa_id, usuario_id, *(dados.get(c) for c in campos)))



def salvar_simulador(empresa_id: int, usuario_id: int | None, gasto_min, gasto_max, pct_tempo, nota: str | None = None) -> None:
    """Só os valores do simulador de economia (o resto da configuração fica como está). usuario_id None: a semente."""
    _um("INSERT INTO empresa_config (empresa_id, atualizado_por, simulador_gasto_min, simulador_gasto_max, simulador_pct_tempo, simulador_nota)"
        " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (empresa_id) DO UPDATE SET atualizado_por = EXCLUDED.atualizado_por, atualizado_em = now(),"
        " simulador_gasto_min = EXCLUDED.simulador_gasto_min, simulador_gasto_max = EXCLUDED.simulador_gasto_max,"
        " simulador_pct_tempo = EXCLUDED.simulador_pct_tempo, simulador_nota = EXCLUDED.simulador_nota",
        (empresa_id, usuario_id, gasto_min, gasto_max, pct_tempo, nota))


# ---------- Rádios ----------
RADIO = ("r.id, r.nome, r.email, r.whatsapp, r.alcance, r.valor_padrao, r.cobranca, r.ativa, r.criada_em,"
         " (SELECT e.valor FROM envio e WHERE e.radio_id = r.id ORDER BY e.id DESC LIMIT 1) AS ultimo_valor,"
         " (SELECT e.cobranca FROM envio e WHERE e.radio_id = r.id ORDER BY e.id DESC LIMIT 1) AS ultima_cobranca")


def radios(empresa_id: int, so_ativas: bool = True) -> list[dict]:
    return _todos(f"SELECT {RADIO} FROM radio r WHERE r.empresa_id = %s" + (" AND r.ativa" if so_ativas else "")
                  + " ORDER BY r.nome", (empresa_id,))


def radio(id_: int, empresa_id: int) -> dict | None:
    return _um(f"SELECT {RADIO} FROM radio r WHERE r.id = %s AND r.empresa_id = %s", (id_, empresa_id))


def radio_com_nome(empresa_id: int, nome: str, exceto: int | None = None) -> dict | None:
    """Outra rádio da empresa com o mesmo nome (sem diferença de maiúsculas e espaços): duplicata."""
    return _um("SELECT id, nome FROM radio WHERE empresa_id = %s AND lower(regexp_replace(nome, '\\s+', ' ', 'g')) = lower(%s)"
               " AND id IS DISTINCT FROM %s", (empresa_id, " ".join(nome.split()), exceto))


class PedidoResolvido(Exception):
    """O pedido de rádio já foi atendido ou recusado (por outra pessoa, ou num clique duplo)."""


def criar_radio(empresa_id: int, usuario_id: int, d: dict, pedido_id: int | None = None, usuario_nome: str = "") -> int:
    """Cadastra a rádio; vinda de um pedido, o pedido fica atendido na mesma transação (nada pela metade)."""
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("INSERT INTO radio (empresa_id, nome, email, whatsapp, alcance, valor_padrao, cobranca, criada_por)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (empresa_id, d["nome"], d["email"], d["whatsapp"], json.dumps(d["alcance"], ensure_ascii=False),
                     d["valor_padrao"], d["cobranca"], usuario_id))
        id_ = cur.fetchone()["id"]
        if pedido_id is not None:
            cur.execute("UPDATE pedido_radio SET status = 'atendido', radio_id = %s, resolvido_por_nome = %s, resolvido_em = now()"
                        " WHERE id = %s AND empresa_id = %s AND status = 'aberto' RETURNING id", (id_, usuario_nome, pedido_id, empresa_id))
            if not cur.fetchone():
                raise PedidoResolvido()
        return id_


def alterar_radio(id_: int, empresa_id: int, d: dict) -> None:
    _um("UPDATE radio SET nome = %s, email = %s, whatsapp = %s, alcance = %s, valor_padrao = %s, cobranca = %s, ativa = %s"
        " WHERE id = %s AND empresa_id = %s",
        (d["nome"], d["email"], d["whatsapp"], json.dumps(d["alcance"], ensure_ascii=False), d["valor_padrao"],
         d["cobranca"], d["ativa"], id_, empresa_id))


# ---------- Pedidos de cadastro de rádio ----------
PEDIDO = ("p.id, p.nome, p.cidade, p.contato, p.observacao, p.status, p.motivo_recusa, p.radio_id, p.criado_por, p.criado_por_nome,"
          " p.criado_em, p.resolvido_por_nome, p.resolvido_em")


def criar_pedido(empresa_id: int, usuario_id: int, usuario_nome: str, d: dict) -> int:
    return _um("INSERT INTO pedido_radio (empresa_id, nome, cidade, contato, observacao, criado_por, criado_por_nome)"
               " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (empresa_id, d["nome"], d["cidade"], d["contato"], d["observacao"], usuario_id, usuario_nome))["id"]


def pedidos(empresa_id: int, usuario_id: int | None = None, limite: int = 100) -> list[dict]:
    """Os pedidos da empresa (os abertos primeiro); com usuario_id, só os que essa pessoa fez."""
    filtro = " AND p.criado_por = %s" if usuario_id is not None else ""
    return _todos(f"SELECT {PEDIDO} FROM pedido_radio p WHERE p.empresa_id = %s{filtro}"
                  " ORDER BY (p.status = 'aberto') DESC, p.criado_em DESC LIMIT %s",
                  (empresa_id, usuario_id, limite) if usuario_id is not None else (empresa_id, limite))


def pedido(id_: int, empresa_id: int) -> dict | None:
    return _um(f"SELECT {PEDIDO} FROM pedido_radio p WHERE p.id = %s AND p.empresa_id = %s", (id_, empresa_id))


def pedido_aberto_igual(empresa_id: int, nome: str, cidade: str) -> dict | None:
    return _um("SELECT id FROM pedido_radio WHERE empresa_id = %s AND status = 'aberto' AND lower(nome) = lower(%s) AND lower(cidade) = lower(%s)",
               (empresa_id, nome, cidade))


def recusar_pedido(id_: int, empresa_id: int, motivo: str, usuario_nome: str) -> bool:
    return _um("UPDATE pedido_radio SET status = 'recusado', motivo_recusa = %s, resolvido_por_nome = %s, resolvido_em = now()"
               " WHERE id = %s AND empresa_id = %s AND status = 'aberto' RETURNING id", (motivo, usuario_nome, id_, empresa_id)) is not None


# ---------- Envios ----------
ENVIO = ("e.id, e.aviso_id, e.municipio, e.municipio_nome, e.radio_id, e.radio_nome, e.canal, e.destino, e.texto, e.valor,"
         " e.cobranca, e.custo, e.custo_antigo, e.economia, e.economia_tipo, e.segundos, e.segundos_hoje, e.tempo_economizado,"
         " e.status, e.criado_por_nome, e.criado_em, e.confirmado_em,"
         " (SELECT array_agg(a.tipo ORDER BY a.tipo) FROM arquivo_envio a WHERE a.envio_id = e.id) AS arquivos")


def criar_envio(d: dict) -> int:
    campos = ("empresa_id", "aviso_id", "municipio", "municipio_nome", "radio_id", "radio_nome", "canal", "destino", "texto",
              "valor", "cobranca", "custo", "custo_antigo", "economia", "economia_tipo", "segundos", "segundos_hoje",
              "tempo_economizado", "status", "criado_por", "criado_por_nome")
    return _um(f"INSERT INTO envio ({', '.join(campos)}) VALUES ({', '.join('%(' + c + ')s' for c in campos)}) RETURNING id", d)["id"]


def envio_repetido(d: dict, segundos: int = 60) -> int | None:
    """O mesmo envio (aviso, município, rádio, canal, texto, valor e cobrança) feito há menos de um minuto: clique duplo.
    Um envio que falhou não conta: tentar de novo logo depois é o certo."""
    r = _um("SELECT id FROM envio WHERE aviso_id = %(aviso_id)s AND municipio = %(municipio)s AND radio_id = %(radio_id)s"
            " AND canal = %(canal)s AND texto = %(texto)s AND valor = %(valor)s AND cobranca = %(cobranca)s"
            " AND status <> 'falhou' AND criado_em > now() - make_interval(secs => %(janela)s) ORDER BY id DESC LIMIT 1", {**d, "janela": segundos})
    return r["id"] if r else None


def definir_token(envio_id: int, token: str) -> datetime:
    expira = datetime.now(timezone.utc) + VALIDADE_TOKEN
    _um("UPDATE envio SET token_hash = %s, token_expira = %s WHERE id = %s", (hash_token(token), expira, envio_id))
    return expira


def mudar_status(envio_id: int, status: str) -> None:
    _um("UPDATE envio SET status = %s WHERE id = %s AND status <> 'confirmado'", (status, envio_id))


def envios(empresa_id: int, aviso_id: int | None = None) -> list[dict]:
    filtro = " AND e.aviso_id = %s" if aviso_id is not None else ""
    return _todos(f"SELECT {ENVIO} FROM envio e WHERE e.empresa_id = %s{filtro} ORDER BY e.id",
                  (empresa_id, aviso_id) if aviso_id is not None else (empresa_id,))


def envio(id_: int, empresa_id: int) -> dict | None:
    return _um(f"SELECT {ENVIO} FROM envio e WHERE e.id = %s AND e.empresa_id = %s", (id_, empresa_id))


def envio_pelo_token(token: str) -> dict | None:
    """O envio do token (só para mostrar a página de confirmação), com a validade e se já foi usado."""
    return _um("SELECT e.id, e.empresa_id, e.radio_nome, e.municipio_nome, e.status, e.token_expira, e.confirmado_em,"
               " a.data, a.horario, a.idioma FROM envio e JOIN aviso a ON a.id = e.aviso_id WHERE e.token_hash = %s", (hash_token(token),))


def confirmar(token: str) -> dict | None:
    """Usa o token uma vez, dentro da validade: o envio fica confirmado. None se não vale (vencido, usado, inexistente)."""
    return _um("UPDATE envio SET status = 'confirmado', confirmado_em = now() WHERE token_hash = %s AND confirmado_em IS NULL"
               " AND token_expira > now() RETURNING id, empresa_id, radio_nome, municipio_nome, aviso_id",
               (hash_token(token),))


# ---------- Arquivos cifrados ----------
def guardar_arquivo(envio_id: int, empresa_id: int, tipo: str, nome: str, tamanho: int, cifrado: bytes) -> None:
    _um("INSERT INTO arquivo_envio (envio_id, empresa_id, tipo, nome, tamanho, cifrado) VALUES (%s, %s, %s, %s, %s, %s)",
        (envio_id, empresa_id, tipo, nome, tamanho, cifrado))


def arquivo(envio_id: int, empresa_id: int, tipo: str) -> dict | None:
    return _um("SELECT nome, tamanho, cifrado FROM arquivo_envio WHERE envio_id = %s AND empresa_id = %s AND tipo = %s",
               (envio_id, empresa_id, tipo))
