"""Teste da planilha de UCs (nucleo/planilha.py), puro: sem banco, sem API e sem arquivo.

Confere:
- endereço -> só a rua (so_rua): sem número da casa, complemento, bairro nem CEP; nomes de imóvel e
  nomes de via com número ("Estrada 267", "Rodovia BR 116", "Rua 27 de Abril") ficam iguais;
- sinônimos: NUMCDC é a UC; com endereco e local (URBANO/RURAL), o local do aviso de hoje é a rua do
  endereco; só com local, vale o local (sem limpar: é o nome do imóvel);
- o aviso de hoje montado a partir de endereços completos não leva número de casa nem CEP
  (validacao/minimizacao.numero_de_casa_ou_cep), e a varredura acha os que existirem.

Uso (na raiz): uv run python testes/nucleo/teste_planilha.py
"""

import sys

import pandas as pd

from comunidades import distribuidora as dist_
from comunidades.nucleo.desligamento import aviso_antigo_de_locais
from comunidades.nucleo import planilha as P
from comunidades.nucleo.planilha import colunas, so_rua
from comunidades.validacao.minimizacao import numero_de_casa_ou_cep

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


# --- endereço -> só a rua
casos = {
    "Rua das Flores, 123, casa 2 - CEP 36700-000": "Rua das Flores",
    "Av. Brasil nº 45": "Av. Brasil",
    "Fazenda Boa Vista": "Fazenda Boa Vista",
    "Sítio Boa Vista": "Sítio Boa Vista",
    "Rua 15, 230": "Rua 15",
    "Av. Brasil s/n": "Av. Brasil",
    "Estrada Real km 12": "Estrada Real",
    "Rua Sete de Setembro 120": "Rua Sete de Setembro",
    "Rua 27 de Abril, 50 - Centro": "Rua 27 de Abril",
    "RUA DA PAZ 12": "RUA DA PAZ",
    "Rua João Neto, 45 apto 301, Centro, Leopoldina - MG": "Rua João Neto",
    "Rua das Acácias n° 7 casa 3": "Rua das Acácias",
    "Rua Bahia número 88": "Rua Bahia",
    "Travessa do Rosário lote 4 quadra 2": "Travessa do Rosário",
    "Rua Minas Gerais (fundos), 10": "Rua Minas Gerais",
    "Estrada 267": "Estrada 267",
    "Rodovia BR 116": "Rodovia BR 116",
    "Rodovia MG-120, km 3": "Rodovia MG-120",
    "Rua Bom Jesus 36700000": "Rua Bom Jesus",
    "CEP 36700-000": "",
    "Beco Número 399": "Beco Número 399",              # nome de via do CNEFE (Leopoldina)
    "BECO NUMERO 399, 397 - CEP 36700-000": "BECO NUMERO 399",
    "  Rua   do   Rosário ,  9 ": "Rua do Rosário",
}
for entrada, esperado in casos.items():
    obtido = so_rua(entrada)
    conferir(f"so_rua({entrada!r}) == {esperado!r}", obtido == esperado, repr(obtido))
    conferir(f"so_rua({entrada!r}) sem número de casa nem CEP", not numero_de_casa_ou_cep(obtido),
             numero_de_casa_ou_cep(obtido))

# --- sinônimos (pelo tradutor: JSON validado -> as linhas que entram)
def planilha(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols, dtype=str)


class Traduzida:
    def __init__(self, t: pd.DataFrame):
        cab = list(t.columns)
        linhas = [(i + 2, list(r)) for i, r in enumerate(t.itertuples(index=False))]
        self.modelo = P.montar(P.campos_por_indice(cab), cab, linhas, P.Parametros(dentro=None),
                               arquivo={"nome": "teste.csv", "sha256": "0" * 64, "formato": "csv", "aba": None,
                                        "colunas_ignoradas": 0},
                               empresa="Teste", gerado_em="2026-10-13T12:00", gerado_por="Teste (Operador)")
        self.validas = P.validas(self.modelo)
        self.problemas = [pt for pt in self.modelo.pontos if pt.status == "rejeitada"]


validar = Traduzida


base = {"latitude": ["-21,5321", "-21,5410", "-21,5500"], "longitude": ["-42,6412", "-42,6503", "-42,6600"]}
p = validar(planilha(NUMCDC=["101", "102", "103"], **base))
conferir("NUMCDC reconhecida como UC", colunas(["NUMCDC", "latitude", "longitude"]).get("uc") == "NUMCDC")
conferir("planilha com NUMCDC é aceita (3 UCs, nenhum problema)", len(p.validas) == 3 and not p.problemas,
         f"{len(p.validas)} válidas, {len(p.problemas)} problemas")

enderecos = ["Rua das Flores, 123, casa 2 - CEP 36700-000", "Av. Brasil nº 45", "Rua das Flores, 98"]
p = validar(planilha(NUMCDC=["101", "102", "103"], ENDERECO=enderecos, LOCAL=["URBANO", "URBANO", "RURAL"], **base))
conferir("com endereco e local (URBANO/RURAL), a coluna usada é endereco",
         colunas(["NUMCDC", "ENDERECO", "LOCAL"]).get("local") == "ENDERECO")
conferir("o local de cada UC é só a rua do endereco",
         p.validas["LOCAL"].tolist() == ["Rua das Flores", "Av. Brasil", "Rua das Flores"], p.validas["LOCAL"].tolist())
conferir("nenhum local é URBANO ou RURAL", not set(p.validas["LOCAL"]) & {"URBANO", "RURAL"})

p = validar(planilha(uc=["1", "2"], local=["Fazenda Boa Vista, 3", "Sítio Santa Helena 2"],
                     latitude=base["latitude"][:2], longitude=base["longitude"][:2]))
conferir("só com local (nome do imóvel), o local vale como está",
         p.validas["LOCAL"].tolist() == ["Fazenda Boa Vista, 3", "Sítio Santa Helena 2"], p.validas["LOCAL"].tolist())

p = validar(planilha(uc=["1"], endereco=["CEP 36700-000"], latitude=base["latitude"][:1], longitude=base["longitude"][:1]))
conferir("endereço só com CEP: a UC fica sem local", p.validas["LOCAL"].tolist() == [None], p.validas["LOCAL"].tolist())

# --- varredura no aviso de hoje
regras = dist_.carregar().regras
todos = list(casos) + ["Rua X, 1", "Rua Y nº 2 apto 3", "Av. Z, 45 - Bairro Alto - CEP 36.700-000"]
p = validar(planilha(uc=[str(i) for i in range(len(todos))], endereco=todos,
                     latitude=["-21,53"] * len(todos), longitude=["-42,64"] * len(todos)))
aviso = aviso_antigo_de_locais(p.validas["LOCAL"], "20/11", "8h às 12h", regras)
conferir("aviso de hoje a partir de endereços completos: sem número de casa nem CEP",
         not numero_de_casa_ou_cep(aviso), numero_de_casa_ou_cep(aviso))
conferir("o aviso de hoje cita as ruas", "Rua Das Flores" in aviso and "Av. Brasil" in aviso, aviso[:200])
for errado in ["Rua das Flores, 123", "Av. Brasil nº 45", "casa 2", "CEP 36700-000", "36700-000", "Lote 4"]:
    conferir(f"a varredura acha {errado!r}", bool(numero_de_casa_ou_cep(f"atingindo: {errado}.")))
for certo in ["Estrada 267", "Rodovia BR 116", "Rua 27 de Abril", "Sítio Santa Helena 2", "no dia 20/11, das 8h às 12h",
              "Beco Numero 399"]:
    conferir(f"a varredura não acusa {certo!r}", not numero_de_casa_ou_cep(f"atingindo: {certo}."))

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
