"""Regras de acesso do Norte: perfis, permissões, senha e último admin da empresa.

Puro: não lê banco nem sabe de cookies. Quem guarda usuários e sessões é banco/acesso.py, e quem
confere cada requisição é api/acesso.py. Os perfis são os do protótipo da área administrativa.
"""

import re
from datetime import timedelta

PERFIS = {"admin_farol": "Admin do Norte", "admin_empresa": "Admin da empresa", "operador": "Operador", "consulta": "Consulta"}
PERFIS_EMPRESA = ("admin_empresa", "operador", "consulta")   # o Admin do Norte não pertence a empresa

# ação -> perfis que podem. Ações "da empresa" valem só dentro da empresa do usuário (a API confere).
PERMISSOES = {
    "gerar_aviso": {"admin_empresa", "operador"},
    "ver_historico": {"admin_empresa", "operador", "consulta"},
    "gerenciar_usuarios": {"admin_empresa"},
    "gerenciar_empresas": {"admin_farol"},
    "ver_registro": {"admin_farol", "admin_empresa"},
    "baixar_json": {"admin_empresa", "operador"},   # o JSON da planilha com os números de UC (auditado)
    "gerenciar_radios": {"admin_empresa"},          # cadastrar, alterar, desativar rádios e atender os pedidos (Fase J)
    "pedir_radio": {"operador"},                    # pedir ao Admin da empresa o cadastro de uma rádio que falta
    "configurar_empresa": {"admin_empresa"},        # modelo da mensagem, telefone, limite de rejeição, fuso UTM, antecedência
    "enviar_relatorio": {"admin_empresa", "operador"},   # mandar um relatório por e-mail (Consulta só gera e baixa)
    "relatorio_auditoria": {"admin_empresa"},       # relatório de auditoria da empresa (PDF e CSV)
    "auditoria_geral": {"admin_farol"},             # auditoria geral de acessos, de todas as empresas
}

SENHA_MIN, SENHA_MAX = 12, 128
MAX_TENTATIVAS = 5                       # senhas erradas seguidas até o bloqueio temporário
BLOQUEIO = timedelta(minutes=15)
SESSAO_INATIVA = timedelta(hours=8)      # sem uso por este tempo, a sessão acaba
SESSAO_MAXIMA = timedelta(hours=24)      # e acaba de qualquer jeito depois deste
EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$")


def pode(perfil: str, acao: str) -> bool:
    if acao not in PERMISSOES:
        raise ValueError(f"ação desconhecida: {acao}")
    return perfil in PERMISSOES[acao]


def acoes(perfil: str) -> list[str]:
    return [a for a, perfis in PERMISSOES.items() if perfil in perfis]


def normalizar_email(email: str) -> str:
    return str(email or "").strip().lower()


def problema_email(email: str, dominio: str | None = None) -> str | None:
    e = normalizar_email(email)
    if not EMAIL.match(e) or len(e) > 254:
        return "E-mail inválido."
    if dominio and not e.endswith("@" + dominio.lower()):
        return f"Só e-mails @{dominio} podem ser cadastrados nesta empresa."
    return None


def normalizar_cnpj(cnpj: str) -> str:
    return re.sub(r"[.\-/\s]", "", str(cnpj or "")).upper()


def cnpj_valido(cnpj: str) -> bool:
    """CNPJ numérico ou alfanumérico (Receita Federal, a partir de julho de 2026): 12 caracteres [0-9A-Z] e 2
    dígitos verificadores; o valor de cada caractere é o código ASCII - 48 (o mesmo do protótipo, admin_modelo.js)."""
    c = normalizar_cnpj(cnpj)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", c) or len(set(c)) == 1:
        return False

    def dv(base: str, pesos: list[int]) -> int:
        r = sum((ord(ch) - 48) * p for ch, p in zip(base, pesos)) % 11
        return 0 if r < 2 else 11 - r

    d1 = dv(c[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = dv(c[:12] + str(d1), [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return c[12:] == f"{d1}{d2}"


def formatar_cnpj(cnpj: str) -> str:
    c = normalizar_cnpj(cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else str(cnpj or "")


def problema_senha(senha: str, email: str = "") -> str | None:
    """Regra da senha nova (NIST SP 800-63B: comprimento acima de complexidade)."""
    if len(senha) < SENHA_MIN:
        return f"A senha precisa ter pelo menos {SENHA_MIN} caracteres."
    if len(senha) > SENHA_MAX:
        return f"A senha pode ter no máximo {SENHA_MAX} caracteres."
    if len(set(senha)) < 5:
        return "A senha repete caracteres demais."
    local = normalizar_email(email).split("@")[0]
    if local and len(local) >= 4 and local in senha.lower():
        return "A senha não pode conter o seu e-mail."
    return None


def deixa_sem_admin(admins_ativos_da_empresa: int, antes_admin_ativo: bool, depois_admin_ativo: bool) -> bool:
    """Mudar o perfil ou bloquear o último admin ativo deixaria a empresa sem ninguém para administrá-la."""
    return antes_admin_ativo and not depois_admin_ativo and admins_ativos_da_empresa <= 1
