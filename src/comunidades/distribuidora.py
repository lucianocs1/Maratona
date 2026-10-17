"""Configuração da distribuidora: lê distribuidoras/*.toml e entrega os valores prontos.

Tudo o que muda de uma distribuidora para outra (nome, telefone, município, prazos,
expediente, limites do aviso e perfis de sensibilidade) fica num único arquivo.
Este módulo lê o arquivo; o núcleo só recebe os valores, sem ler nada.
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import config as C
from .nucleo import idiomas
from .nucleo.custo import SPOT_SEGUNDOS, TabelaRadio
from .nucleo.desligamento import RegrasAviso
from .nucleo.perfis_carga import NIVEIS, TIPOS_DIA, Expediente, expediente_de_dict, perfis_de_dict

PASTA = C.RAIZ / "distribuidoras"
PADRAO = PASTA / "demo-leopoldina.toml"
VARIAVEL = "FAROL_DISTRIBUIDORA"  # caminho alternativo, se definido


@dataclass(frozen=True)
class Distribuidora:
    arquivo: Path
    nome: str
    telefone: str
    municipio: str
    uf: str
    idioma_padrao: str
    prazo_legal_horas: int
    prazo_vital_dias_uteis: int
    prazo_interno_dias: int
    norma: str
    regras: RegrasAviso
    expediente: Expediente
    razao_muito_pior: float
    raio_rede_m: float
    perfis: dict
    radio: TabelaRadio
    planilha: "ConfigPlanilha"

    def para_mapa(self) -> dict:
        """O que a apresentação precisa saber da distribuidora (nada de dados de clientes)."""
        return {"nome": self.nome, "telefone": self.telefone, "municipio": self.municipio, "uf": self.uf,
                "idiomaPadrao": self.idioma_padrao, "prazoLegalHoras": self.prazo_legal_horas,
                "prazoVitalDiasUteis": self.prazo_vital_dias_uteis, "prazoInternoDias": self.prazo_interno_dias,
                "norma": self.norma, "raioRedeM": self.raio_rede_m}


class ConfiguracaoInvalida(ValueError):
    pass


@dataclass(frozen=True)
class ConfigPlanilha:
    """[planilha] do .toml (opcional; sem a seção valem estes padrões)."""
    epsg_utm: int = 31983                    # fuso UTM das coordenadas X/Y (SIRGAS 2000 / UTM 23S)
    ponto_isolado_km: float = 20.0           # ponto mais longe que isso do vizinho mais próximo: aviso
    muitas_ucs_mesma_coordenada: int = 10    # a mesma coordenada em tantas UCs ou mais: aviso
    limite_rejeitadas: float = 0.02          # acima disso, o aviso só sai com justificativa


def _planilha(d: dict) -> ConfigPlanilha:
    s = d.get("planilha", {})
    tipos = {"epsg_utm": int, "ponto_isolado_km": (int, float), "muitas_ucs_mesma_coordenada": int,
             "limite_rejeitadas": (int, float)}
    for k, v in s.items():
        if k not in tipos:
            raise ConfiguracaoInvalida(f"planilha.{k}: campo desconhecido")
        if isinstance(v, bool) or not isinstance(v, tipos[k]):
            raise ConfiguracaoInvalida(f"planilha.{k}: tipo inválido")
    c = ConfigPlanilha(**s)
    if not (0 <= c.limite_rejeitadas <= 1 and c.ponto_isolado_km > 0 and c.muitas_ucs_mesma_coordenada >= 2
            and 31960 <= c.epsg_utm <= 31985):
        raise ConfiguracaoInvalida("planilha: valor fora da faixa (limite_rejeitadas 0 a 1; epsg_utm de 31960 a 31985)")
    return c


def _exigir(d: dict, caminho: str, tipo):
    """Busca 'secao.campo' e confere tipo e preenchimento, com mensagem clara."""
    atual = d
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            raise ConfiguracaoInvalida(f"campo obrigatório ausente: {caminho}")
        atual = atual[parte]
    if tipo is float and isinstance(atual, int) and not isinstance(atual, bool):
        atual = float(atual)
    if not isinstance(atual, tipo) or isinstance(atual, bool):
        raise ConfiguracaoInvalida(f"{caminho} deve ser {tipo.__name__}, veio {atual!r}")
    if (isinstance(atual, str) and not atual.strip()) or (isinstance(atual, (int, float)) and atual <= 0):
        raise ConfiguracaoInvalida(f"{caminho} está vazio ou zerado")
    return atual


def _validar_perfis(d: dict) -> dict:
    perfis = d.get("perfis")
    if not isinstance(perfis, dict) or not perfis:
        raise ConfiguracaoInvalida("nenhum perfil em [perfis.*]")
    for nome, p in perfis.items():
        for campo in ("singular", "plural"):
            _exigir(perfis, f"{nome}.{campo}", str)
        for t in TIPOS_DIA:
            if p.get("padrao", {}).get(t) not in NIVEIS:
                raise ConfiguracaoInvalida(f"perfis.{nome}.padrao.{t} deve ser um de {list(NIVEIS)}")
        for i, q in enumerate(p.get("periodos", [])):
            onde = f"perfis.{nome}.periodos[{i}]"
            if q.get("nivel") not in NIVEIS:
                raise ConfiguracaoInvalida(f"{onde}.nivel deve ser um de {list(NIVEIS)}")
            if not q.get("nome") or not q.get("dias") or any(x not in TIPOS_DIA for x in q["dias"]):
                raise ConfiguracaoInvalida(f"{onde}: precisa de nome e de dias entre {list(TIPOS_DIA)}")
            if not (0 <= q.get("inicio_h", -1) < q.get("fim_h", -1) <= 24):
                raise ConfiguracaoInvalida(f"{onde}: inicio_h e fim_h inválidos")
    return perfis


def _radio(d: dict) -> TabelaRadio:
    """[radio] é opcional: sem a seção, o preço fica 0 e a tela mostra os spots sem o valor em reais."""
    r = d.get("radio")
    if r is None:
        return TabelaRadio()
    if not isinstance(r, dict):
        raise ConfiguracaoInvalida("[radio] deve ser uma seção")
    spot = r.get("spot_segundos", SPOT_SEGUNDOS)
    preco = r.get("spot_reais", 0.0)
    vezes = r.get("veiculacoes", 1)
    fonte = r.get("fonte", "")
    if isinstance(spot, bool) or not isinstance(spot, int) or not 5 <= spot <= 120:
        raise ConfiguracaoInvalida(f"radio.spot_segundos deve ser um inteiro de 5 a 120, veio {spot!r}")
    if isinstance(preco, bool) or not isinstance(preco, (int, float)) or not 0 <= preco <= 100_000:
        raise ConfiguracaoInvalida(f"radio.spot_reais deve ser um número de 0 a 100000, veio {preco!r}")
    if isinstance(vezes, bool) or not isinstance(vezes, int) or not 1 <= vezes <= 100:
        raise ConfiguracaoInvalida(f"radio.veiculacoes deve ser um inteiro de 1 a 100, veio {vezes!r}")
    if not isinstance(fonte, str) or len(fonte) > 300:
        raise ConfiguracaoInvalida("radio.fonte deve ser um texto de até 300 caracteres")
    return TabelaRadio(spot, float(preco), vezes, fonte.strip())


def carregar(arquivo: str | Path | None = None) -> Distribuidora:
    caminho = Path(arquivo or os.environ.get(VARIAVEL) or PADRAO)
    with open(caminho, "rb") as f:
        d = tomllib.load(f)
    idioma = _exigir(d, "distribuidora.idioma_padrao", str)
    if idioma not in idiomas.IDIOMAS:
        raise ConfiguracaoInvalida(f"distribuidora.idioma_padrao deve ser um de {list(idiomas.IDIOMAS)}")
    municipio = _exigir(d, "distribuidora.municipio", str)
    return Distribuidora(
        arquivo=caminho,
        nome=_exigir(d, "distribuidora.nome", str),
        telefone=_exigir(d, "distribuidora.telefone", str),
        municipio=municipio,
        uf=_exigir(d, "distribuidora.uf", str),
        idioma_padrao=idioma,
        prazo_legal_horas=_exigir(d, "regulatorio.prazo_legal_horas", int),
        prazo_vital_dias_uteis=_exigir(d, "regulatorio.prazo_vital_dias_uteis", int),
        prazo_interno_dias=_exigir(d, "regulatorio.prazo_interno_dias", int),
        norma=_exigir(d, "regulatorio.norma", str),
        regras=RegrasAviso(
            limiar_total=_exigir(d, "aviso.limiar_total", float),
            limite_fragmento=_exigir(d, "aviso.limite_fragmento", int),
            limite_participacao=_exigir(d, "aviso.limite_participacao", float),
            municipio=municipio,
            assinatura_aviso_atual=_exigir(d, "distribuidora.assinatura_aviso_atual", str)),
        expediente=expediente_de_dict({k: _exigir(d, f"expediente.{k}", float if k != "passo_min" else int)
                                       for k in ("inicio_min_h", "ultimo_inicio_h", "fim_max_h", "passo_min")}),
        razao_muito_pior=_exigir(d, "janela.razao_muito_pior", float),
        raio_rede_m=_exigir(d, "obra.raio_rede_m", float),
        perfis=perfis_de_dict(_validar_perfis(d)),
        radio=_radio(d),
        planilha=_planilha(d),
    )
