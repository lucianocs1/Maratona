"""Listas fechadas do tradutor da planilha: motivo de rejeição, correção feita e aviso de cada linha.

O JSON da planilha guarda só o código (o valor do Enum), nunca texto livre; a tela e o relatório
mostram o texto de TEXTOS. Um código novo entra aqui, com o seu texto, e em nenhum outro lugar.
"""

from enum import Enum


class Motivo(str, Enum):
    """Por que a linha foi rejeitada."""
    # coordenada (nucleo/coordenadas.py)
    COORD_VAZIA = "coordenada_vazia"
    COORD_INCOMPLETA = "coordenada_incompleta"
    COORD_SEM_NUMERO = "coordenada_sem_numero"
    COORD_FORMATO = "coordenada_formato"
    COORD_DATA = "coordenada_data"
    COORD_FORMULA = "coordenada_formula_sem_valor"
    COORD_NAO_FINITA = "coordenada_nao_finita"
    COORD_LIMITES = "coordenada_fora_dos_limites"
    FORA_DA_CONCESSAO = "fora_da_concessao"
    FORA_DA_AREA = "fora_da_area_da_empresa"   # município fora da área de atuação da empresa (decidido na API)
    CORRECAO_AMBIGUA = "correcao_ambigua"
    # linha (nucleo/planilha.py)
    UC_VAZIA = "uc_vazia"
    UC_INVALIDA = "uc_invalida"
    UC_REPETIDA = "uc_repetida"
    CELULA_LONGA = "celula_longa"


class Correcao(str, Enum):
    """O que foi corrigido numa linha "corrigida" (só quando o ponto corrigido cai na concessão)."""
    TROCA = "latitude_e_longitude_trocadas"
    SINAL_LAT = "sinal_da_latitude"
    SINAL_LON = "sinal_da_longitude"
    SINAL_AMBOS = "sinal_da_latitude_e_da_longitude"
    TROCA_E_SINAL = "trocadas_e_sinal"
    UTM_TROCADO = "utm_x_e_y_trocados"


class Aviso(str, Enum):
    """Alerta que não rejeita a linha."""
    POUCAS_CASAS = "menos_de_4_casas_decimais"
    COORD_DUPLICADA = "coordenada_repetida"
    COORD_MUITAS_UCS = "mesma_coordenada_em_muitas_ucs"
    PONTO_ISOLADO = "ponto_isolado"
    UC_REPETIDA = "uc_repetida_em_outra_linha"
    VITAL_INVALIDO = "equipamento_vital_invalido"
    CAMPO_FORMULA = "formula_sem_valor_ignorada"
    TEXTO_CORTADO = "texto_cortado"


TEXTOS = {
    Motivo.COORD_VAZIA: "sem coordenada",
    Motivo.COORD_INCOMPLETA: "só a latitude ou só a longitude",
    Motivo.COORD_SEM_NUMERO: "coordenada sem número",
    Motivo.COORD_FORMATO: "coordenada num formato não reconhecido",
    Motivo.COORD_DATA: "coordenada numa célula de data",
    Motivo.COORD_FORMULA: "fórmula sem valor guardado na coordenada",
    Motivo.COORD_NAO_FINITA: "coordenada inválida (NaN ou infinito)",
    Motivo.COORD_LIMITES: "coordenada fora dos limites (latitude de -90 a 90, longitude de -180 a 180)",
    Motivo.FORA_DA_CONCESSAO: "fora da área de concessão",
    Motivo.FORA_DA_AREA: "fora da área de atuação da empresa",
    Motivo.CORRECAO_AMBIGUA: "mais de uma correção possível: nada foi adivinhado",
    Motivo.UC_VAZIA: "sem número de UC",
    Motivo.UC_INVALIDA: "número de UC inválido (fórmula, data ou mais de 40 caracteres)",
    Motivo.UC_REPETIDA: "UC repetida: só a primeira linha com ela entra",
    Motivo.CELULA_LONGA: "célula com mais de 200 caracteres",
    Correcao.TROCA: "latitude e longitude estavam trocadas",
    Correcao.SINAL_LAT: "faltava o sinal negativo da latitude",
    Correcao.SINAL_LON: "faltava o sinal negativo da longitude",
    Correcao.SINAL_AMBOS: "faltava o sinal negativo da latitude e da longitude",
    Correcao.TROCA_E_SINAL: "latitude e longitude trocadas e sem o sinal negativo",
    Correcao.UTM_TROCADO: "coordenadas UTM com X e Y trocados",
    Aviso.POUCAS_CASAS: "coordenada com menos de 4 casas decimais (cerca de 11 m de precisão ou pior)",
    Aviso.COORD_DUPLICADA: "mesma coordenada de outra linha",
    Aviso.COORD_MUITAS_UCS: "a mesma coordenada aparece em muitas UCs (suspeito)",
    Aviso.PONTO_ISOLADO: "ponto muito longe de todos os outros da planilha (suspeito)",
    Aviso.UC_REPETIDA: "esta UC aparece de novo em outra linha (só esta entra)",
    Aviso.VITAL_INVALIDO: "equipamento_vital com valor inválido (use sim ou não): fica \"a confirmar\"",
    Aviso.CAMPO_FORMULA: "fórmula sem valor guardado num campo opcional: o campo foi ignorado",
    Aviso.TEXTO_CORTADO: "texto longo cortado no limite do campo",
}


class FormulaSemValor:
    """Célula com fórmula e sem o valor calculado guardado no arquivo (quem lê o arquivo a marca assim)."""

    def __repr__(self) -> str:
        return "FormulaSemValor()"


FORMULA_SEM_VALOR = FormulaSemValor()
