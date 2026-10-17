"""Empresas e usuários FICTÍCIOS da área administrativa (protótipo, saida/admin.html).

Nenhuma marca ou pessoa real: nomes de exemplo, e-mails em subdomínios de example.com (reservado
para exemplos, RFC 2606) e CNPJs alfanuméricos (formato da Receita a partir de julho de 2026)
válidos no cálculo dos dígitos, com letras que deixam claro que são de demonstração.
Os municípios e códigos IBGE são reais (Leopoldina, Muriaé e Cataguases/MG).

Usuários só têm o mínimo para dar acesso (LGPD): nome, e-mail corporativo, cargo opcional,
perfil e municípios. Nada de CPF, data de nascimento, endereço ou telefone pessoal.
"""

CRIADO_POR = "Admin do Norte"
CRIADO_EM = "2026-09-01T12:00:00.000Z"

_PADRAO_EMPRESA = {
    "pais": "Brasil", "uf": "MG", "idioma": "pt-BR", "fuso": "America/Sao_Paulo",
    "criadoPor": CRIADO_POR, "criadoEm": CRIADO_EM, "alteradoPor": CRIADO_POR, "alteradoEm": CRIADO_EM,
}

EMPRESAS = [
    {**_PADRAO_EMPRESA,
     "id": "emp-1",
     "razaoSocial": "Distribuidora Demonstração de Energia S.A.",
     "nomeFantasia": "Distribuidora Demonstração MG",
     "cnpj": "FA.ROL.DEM/0001-19",
     "tipo": "distribuidora",
     "emailInstitucional": "contato@distribuidora.example.com",
     "telefone": "0800 000 0001",
     "site": "https://distribuidora.example.com",
     "gestorNome": "Gestora Exemplo",
     "gestorEmail": "gestora@distribuidora.example.com",
     "dpoNome": "Encarregado Exemplo",
     "dpoEmail": "dpo@distribuidora.example.com",
     "municipios": [{"codigo": "3138401", "nome": "Leopoldina"}, {"codigo": "3143906", "nome": "Muriaé"}],
     "antecedenciaHoras": 72,
     "motivoPadrao": "manutenção preventiva na rede",
     "status": "ativa",
     "contratoInicio": "2026-01-01", "contratoFim": "2027-12-31",
     "dominio": "distribuidora.example.com",
     "exige2Etapas": True},
    {**_PADRAO_EMPRESA,
     "id": "emp-2",
     "razaoSocial": "Cooperativa de Eletrificação Rural Exemplo",
     "nomeFantasia": "Cooperativa Rural Exemplo",
     "cnpj": "CO.OPE.XEM/0001-27",
     "tipo": "cooperativa",
     "emailInstitucional": "atendimento@cooperativa.example.com",
     "telefone": "0800 000 0002",
     "site": "",
     "gestorNome": "Gestor Exemplo",
     "gestorEmail": "gestor@cooperativa.example.com",
     "dpoNome": "Encarregada Exemplo",
     "dpoEmail": "privacidade@cooperativa.example.com",
     "municipios": [{"codigo": "3115300", "nome": "Cataguases"}],
     "antecedenciaHoras": 96,
     "motivoPadrao": "ampliação da rede rural",
     "status": "ativa",
     "contratoInicio": "2026-06-01", "contratoFim": "2027-05-31",
     "dominio": "cooperativa.example.com",
     "exige2Etapas": False},
]


def _usuario(id_, empresa, nome, email, perfil, municipios, status, dois_fatores, ultimo, cargo=""):
    return {"id": id_, "empresaId": empresa, "nome": nome, "email": email, "cargo": cargo, "perfil": perfil,
            "municipios": municipios, "status": status, "doisFatores": dois_fatores, "ultimoAcesso": ultimo,
            "criadoPor": CRIADO_POR, "criadoEm": CRIADO_EM, "alteradoPor": CRIADO_POR, "alteradoEm": CRIADO_EM}


USUARIOS = [
    _usuario("usu-1", "emp-1", "Ana Exemplo", "ana.exemplo@distribuidora.example.com", "admin_empresa",
             ["3138401", "3143906"], "ativo", True, "2026-10-08T13:20:00.000Z", "Coordenação de operação"),
    _usuario("usu-2", "emp-1", "Bruno Exemplo", "bruno.exemplo@distribuidora.example.com", "operador",
             ["3138401"], "ativo", True, "2026-10-09T10:05:00.000Z", "Centro de operação"),
    _usuario("usu-3", "emp-1", "Clara Exemplo", "clara.exemplo@distribuidora.example.com", "consulta",
             ["3143906"], "bloqueado", True, "2026-07-30T16:40:00.000Z"),
    _usuario("usu-4", "emp-2", "Diego Exemplo", "diego.exemplo@cooperativa.example.com", "admin_empresa",
             ["3115300"], "ativo", False, "2026-10-01T09:00:00.000Z", "Diretoria técnica"),
    _usuario("usu-5", "emp-2", "Elisa Exemplo", "elisa.exemplo@cooperativa.example.com", "operador",
             ["3115300"], "convidado", False, ""),
]


def dados() -> dict:
    return {"empresas": EMPRESAS, "usuarios": USUARIOS}
