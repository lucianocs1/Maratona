"""Esquema fechado do JSON padronizado da planilha (formato "farol-planilha", versão 3).

Todo JSON da planilha passa por PlanilhaJSON antes de qualquer uso: o que o tradutor acabou de gerar
e o que volta da tela no segundo passo. Recusa campo a mais, tipo errado (sem conversão automática),
NaN e infinito, código fora das listas fechadas (nucleo/motivos.py) e conta que não fecha.

Reprodutibilidade: para o mesmo arquivo (mesmo sha256) e a mesma versão do tradutor, conteudo() dá os
mesmos bytes; o envelope (empresa, gerado_em, gerado_por) fica de fora dessa conta.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .motivos import Aviso, Correcao, Motivo

FORMATO, VERSAO = "farol-planilha", 3   # 3: conjunto, bairro e situação (base de clientes)
ENVELOPE = {"empresa", "gerado_em", "gerado_por"}
_FECHADO = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)


class Ponto(BaseModel):
    model_config = _FECHADO
    linha: int = Field(ge=2)
    uc: str | None = Field(default=None, max_length=40)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    equipamento_vital: bool | None = None
    classe: str | None = Field(default=None, max_length=40)
    local: str | None = Field(default=None, max_length=80)
    transformador: str | None = Field(default=None, max_length=40)
    circuito: str | None = Field(default=None, max_length=40)
    conjunto: str | None = Field(default=None, max_length=40)
    bairro: str | None = Field(default=None, max_length=60)
    situacao: str | None = Field(default=None, max_length=20)   # da base de clientes (ATIVO, INATIVO...)
    status: Literal["ok", "corrigida", "rejeitada"]
    motivo: Motivo | None = None
    correcao: Correcao | None = None
    original: tuple[float, float] | None = None        # (lat, lon) como veio, na corrigida
    repete_linha: int | None = Field(default=None, ge=2)  # na uc_repetida: a linha que entrou
    avisos: tuple[Aviso, ...] = ()

    @model_validator(mode="after")
    def _coerente(self):
        if self.status == "rejeitada":
            if self.motivo is None or self.correcao is not None:
                raise ValueError("rejeitada: precisa de motivo e não tem correção")
        else:
            if self.motivo is not None or self.uc is None or self.lat is None or self.lon is None:
                raise ValueError("ok/corrigida: precisa de uc e coordenada, sem motivo")
            if (self.status == "corrigida") != (self.correcao is not None):
                raise ValueError("só a corrigida tem correção")
        if (self.lat is None) != (self.lon is None):
            raise ValueError("latitude e longitude andam juntas")
        if (self.repete_linha is not None) != (self.motivo == Motivo.UC_REPETIDA):
            raise ValueError("repete_linha só na uc_repetida")
        return self


class Arquivo(BaseModel):
    model_config = _FECHADO
    nome: str = Field(max_length=100)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    formato: Literal["xlsx", "csv"]
    aba: str | None = Field(default=None, max_length=31)
    linhas: int = Field(ge=0)
    colunas_ignoradas: int = Field(ge=0)


class Vital(BaseModel):
    model_config = _FECHADO
    sim: int = Field(ge=0)
    nao: int = Field(ge=0)
    a_confirmar: int = Field(ge=0)


class Resumo(BaseModel):
    model_config = _FECHADO
    total: int = Field(ge=0)
    ok: int = Field(ge=0)
    corrigidas: int = Field(ge=0)
    rejeitadas: int = Field(ge=0)
    avisos: int = Field(ge=0)
    equipamento_vital: Vital                      # das linhas que entram (ok e corrigidas)


class PlanilhaJSON(BaseModel):
    model_config = _FECHADO
    formato: Literal["farol-planilha"]
    versao: Literal[3]
    tradutor: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    empresa: str = Field(max_length=120)
    gerado_em: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    gerado_por: str = Field(max_length=160)
    arquivo: Arquivo
    colunas: tuple[str, ...]                       # campos do modelo reconhecidos na planilha
    pontos: tuple[Ponto, ...]
    resumo: Resumo

    @model_validator(mode="after")
    def _conta_fechada(self):
        r, ps = self.resumo, self.pontos
        conta = {"ok": 0, "corrigida": 0, "rejeitada": 0}
        for p in ps:
            conta[p.status] += 1
        vital = {"sim": 0, "nao": 0, "a_confirmar": 0}
        for p in ps:
            if p.status != "rejeitada":
                vital["a_confirmar" if p.equipamento_vital is None else "sim" if p.equipamento_vital else "nao"] += 1
        if not (r.total == len(ps) == self.arquivo.linhas == r.ok + r.corrigidas + r.rejeitadas
                and (r.ok, r.corrigidas, r.rejeitadas) == (conta["ok"], conta["corrigida"], conta["rejeitada"])
                and r.avisos == sum(len(p.avisos) for p in ps)
                and r.equipamento_vital.model_dump() == vital):
            raise ValueError("a conta não fecha: linhas lidas, ok, corrigidas, rejeitadas, avisos ou equipamento vital")
        linhas = [p.linha for p in ps]
        if linhas != sorted(set(linhas)):
            raise ValueError("linhas fora de ordem ou repetidas")
        ucs = [p.uc for p in ps if p.status != "rejeitada"]
        if len(ucs) != len(set(ucs)):
            raise ValueError("a mesma UC entra mais de uma vez")
        return self


def validar_json(texto: str | bytes) -> PlanilhaJSON:
    """O JSON (texto) conferido pelo esquema; levanta pydantic.ValidationError se algo não bate."""
    return PlanilhaJSON.model_validate_json(texto)


def validar_dados(dados: dict) -> PlanilhaJSON:
    """O JSON já como dicionário (do próprio tradutor), conferido pelo esquema. Passa pelo texto JSON de
    propósito: o mesmo caminho do JSON que volta da tela (e NaN ou infinito param já no json.dumps)."""
    return PlanilhaJSON.model_validate_json(json.dumps(dados, ensure_ascii=False, allow_nan=False))


def texto(m: PlanilhaJSON) -> str:
    """O JSON inteiro, em texto (para baixar e para o segundo passo)."""
    return m.model_dump_json()


def conteudo(m: PlanilhaJSON) -> bytes:
    """Os bytes que não dependem de quem nem de quando: o que a reprodutibilidade compara."""
    return m.model_dump_json(exclude=ENVELOPE).encode("utf-8")
