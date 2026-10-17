"""Semente de acesso: tabelas, a empresa de demonstração e um usuário de cada perfil.

Roda no deploy (e localmente) e pode rodar de novo sem duplicar nada: só cria o que falta.
Cada usuário novo recebe uma senha temporária aleatória, mostrada UMA vez aqui, e tem de
trocá-la no primeiro acesso. Nenhuma senha fica no código nem no git. Os e-mails são do domínio
reservado .example (não recebem e-mail de verdade).

Uso:
  uv run python -m comunidades.semente                       # cria o que falta
  uv run python -m comunidades.semente --nova-senha EMAIL    # nova senha temporária para um usuário
"""

import sys

from .senhas import hash_senha, senha_temporaria
from .banco import acesso as banco
from .banco.conexao import conectar
from .nucleo.acesso import PERFIS

EMPRESA = {"nome": "Distribuidora EMG (demonstração)", "sigla": "EMG", "dominio": "emg.example"}
USUARIOS = [  # (perfil, e-mail, nome)
    ("admin_farol", "admin@farol.example", "Admin do Norte"),
    ("admin_empresa", "admin@emg.example", "Admin da EMG"),
    ("operador", "operador@emg.example", "Operador da EMG"),
    ("consulta", "consulta@emg.example", "Consulta da EMG"),
]


def semear() -> list[tuple[str, str, str]]:
    """Cria o que falta e devolve (perfil, e-mail, senha temporária) só dos usuários criados agora."""
    banco.criar_esquema()
    emp = banco.empresa_por_sigla(EMPRESA["sigla"])
    if not emp:
        emp = banco.criar_empresa(**EMPRESA)
        banco.registrar("semente: criou a empresa", EMPRESA["nome"], None, emp["id"])
    criados = []
    for perfil, email, nome in USUARIOS:
        if banco.usuario_por_email(email):
            continue
        temporaria = senha_temporaria()
        empresa_id = None if perfil == "admin_farol" else emp["id"]
        banco.criar_usuario(empresa_id, email, nome, perfil, hash_senha(temporaria), trocar_senha=True)
        banco.registrar("semente: criou usuário", f"{nome} ({PERFIS[perfil]})", None, empresa_id)
        criados.append((perfil, email, temporaria))
    semear_area_demo()
    return criados


def semear_area_demo() -> bool:
    """A EMG de demonstração recebe, uma vez só, a área que já existia: os municípios da base territorial (a concessão
    carregada pelo base_concessao). Roda na semente e ao subir a API (banco que já existia antes da área de atuação)."""
    try:
        with conectar() as c:
            codigos = [r[0] for r in c.execute("SELECT codigo_ibge FROM municipio").fetchall()]
    except Exception:   # sem base territorial carregada: nada a semear
        return False
    return banco.semear_area_inicial(EMPRESA["sigla"], codigos)


def nova_senha(email: str) -> str:
    u = banco.usuario_por_email(email.strip().lower())
    if not u:
        raise SystemExit(f"Usuário não encontrado: {email}")
    temporaria = senha_temporaria()
    banco.definir_senha(u["id"], hash_senha(temporaria), trocar_senha=True)
    banco.encerrar_sessoes(u["id"])
    banco.registrar("semente: nova senha temporária", u["nome"], None, u["empresa_id"])
    return temporaria


if __name__ == "__main__":
    if "--nova-senha" in sys.argv:
        email = sys.argv[sys.argv.index("--nova-senha") + 1]
        print(f"Nova senha temporária de {email}: {nova_senha(email)}  (troca obrigatória no primeiro acesso)")
    else:
        criados = semear()
        if not criados:
            print("Semente: nada a criar (a empresa e os 4 usuários já existem).")
        else:
            print("Semente: usuários criados. Anote as senhas temporárias: elas não aparecem de novo.")
            for perfil, email, temporaria in criados:
                print(f"  {PERFIS[perfil]:<17} {email:<24} {temporaria}")
            print("Cada um troca a senha no primeiro acesso. Senha perdida: --nova-senha EMAIL")
