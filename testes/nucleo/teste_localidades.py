"""Teste do casamento entre as localidades oficiais do IBGE e as comunidades do app (nucleo/localidades.py), puro, e do
relatório de conferência (validacao/localidades.conferir) em dados montados aqui (sem banco).

Confere:
- normalizar: sem acento, caixa, pontuação e as palavras que não distinguem (povoado, comunidade, vila, de, da...); "São" fica;
- sem_sufixo: tira o distrito entre parênteses que o app põe nos homônimos;
- casar: nome igual (com prefixo, acento ou distrito de diferença), parecido (erro de digitação) e sem par; nada com nome vazio;
- o relatório: o veredito, a posição do ponto no território, a comunidade onde o ponto cai, o aviso de nome repetido e de
  ponto longe do território, a sede ("Cidade") explicada, e as comunidades sem nome oficial com a localidade que cai dentro.

Uso (na raiz): uv run python -W ignore testes/nucleo/teste_localidades.py
"""

import sys

from shapely.geometry import Point, box

from comunidades.nucleo import localidades as L
from comunidades.validacao import localidades as V

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


# ---------- 1. Normalizar e tirar o sufixo ----------
conferir("normalizar: acento, caixa, pontuação e palavras vazias", L.normalizar("  Povoado  SÃO José-do Rio ") == "sao jose rio", L.normalizar("  Povoado  SÃO José-do Rio "))
conferir("normalizar: 'Santa Rita' e 'Comunidade Santa Rita' são o mesmo nome", L.normalizar("Comunidade Santa Rita") == L.normalizar("Santa Rita") == "santa rita")
conferir("normalizar: sao, santa e santo ficam (distinguem 'São João' de 'João')", L.normalizar("São João") != L.normalizar("João"))
conferir("normalizar: o distrito entre parênteses sai", L.normalizar("Bela Vista (Sede)") == "bela vista")
conferir("normalizar: nome só de palavras vazias vira vazio", L.normalizar("Vila de") == "" and L.normalizar("") == "")
conferir("sem_sufixo: 'Bela Vista (Sede)' -> 'Bela Vista'; sem parênteses não muda; 'A (B) (C)' tira o último",
         L.sem_sufixo("Bela Vista (Sede)") == "Bela Vista" and L.sem_sufixo("Barra") == "Barra" and L.sem_sufixo("A (B) (C)") == "A (B)")

# ---------- 2. Casar ----------
nomes = ["Aterrado", "São João (Sede)", "Bela Vista (Abaíba)", "Bela Vista (Tebas)", "Cachoeirinha"]
conferir("casar: nome igual", L.casar("Aterrado", nomes) == (L.IGUAL, 0))
conferir("casar: com prefixo e acento diferentes ('Vila São João' = 'São João (Sede)')", L.casar("Vila São João", nomes) == (L.IGUAL, 1))
conferir("casar: nome repetido devolve a primeira posição", L.casar("Bela Vista", nomes) == (L.IGUAL, 2))
conferir("casar: erro de digitação é 'parecido'", L.casar("Cachoeirinhas", nomes) == (L.PARECIDO, 4) and L.casar("Aterrdo", nomes)[0] == L.PARECIDO)
conferir("casar: outro nome é 'sem par'", L.casar("Pico do Boné", nomes) == (L.SEM_PAR, None))
conferir("casar: 'São João' não casa com 'João' (nem o contrário)", L.casar("São João", ["João"])[0] == L.SEM_PAR and L.casar("João", ["São João"])[0] == L.SEM_PAR)
conferir("casar: nome vazio ou lista vazia = sem par", L.casar("", nomes)[0] == L.SEM_PAR and L.casar("Aterrado", [])[0] == L.SEM_PAR)

# ---------- 3. O relatório em dados montados ----------
# graus: 0,01 grau ~ 1,1 km
def com(codigo, nome, distrito, enderecos, area):
    return {"codigo_ibge": codigo, "municipio": "Teste", "nome": nome, "distrito": distrito, "enderecos": enderecos, "territorio": area}


def of(nome, categoria, x, y, cod="1"):
    return {"codigo_ibge": "1", "municipio": "Teste", "uf": "MG", "codigo": cod, "nome": nome, "categoria": categoria, "ponto": Point(x, y)}


comunidades = [
    com("1", "Sede", "Teste", 900, box(0, 0, 1, 1)),                   # a sede
    com("1", "Aterrado", "Teste", 300, box(2, 0, 3, 1)),
    com("1", "Bela Vista (Norte)", "Norte", 120, box(4, 0, 5, 1)),
    com("1", "Bela Vista (Sul)", "Sul", 80, box(6, 0, 7, 1)),
    com("1", "Sem Terra", "Teste", 50, None),                           # sem território desenhado
    com("1", "Grande Sem Nome", "Teste", 5000, box(8, 0, 9, 1)),
]
oficiais = [
    of("Teste", "Cidade", 0.5, 0.5, "10"),                              # a sede cai na comunidade "Sede"
    of("Aterrado", "Povoado", 2.5, 0.5, "11"),                          # nome igual, dentro
    of("Aterrado Velho", "Lugarejo", 4.5, 0.9, "12"),                   # sem par (não é parecido o bastante); cai em "Bela Vista (Norte)"
    of("Bela Vista", "Outras Localidades", 8.5, 0.5, "13"),            # nome repetido (2) e o ponto está longe do território
    of("Sem Terra", "Povoado", 9.5, 9.5, "14"),                         # comunidade sem território
    of("Pico do Boné", "Outras Localidades", 8.2, 0.2, "15"),           # sem par; cai em "Grande Sem Nome"
]
r = V.conferir(oficiais, comunidades)
c = {l["codigo_localidade"]: l for l in r["conferencia"]}
conferir("relatório: uma linha por localidade, na ordem do banco", [l["codigo_localidade"] for l in r["conferencia"]] == ["10", "11", "12", "13", "14", "15"])
conferir("a sede (Cidade) sem par traz a explicação do 'Sede'", c["10"]["casamento"] == L.SEM_PAR and "Sede" in c["10"]["atencao"], c["10"]["atencao"])
conferir("nome igual com o ponto dentro: 'dentro', sem aviso", c["11"]["casamento"] == L.IGUAL and c["11"]["ponto_no_territorio_dela"] == "dentro"
         and c["11"]["comunidade_onde_o_ponto_cai"] == "Aterrado" and not c["11"]["atencao"], str(c["11"]))
conferir("sem par cujo ponto cai em comunidade de outro nome: avisa", c["12"]["casamento"] == L.SEM_PAR and "outro nome" in c["12"]["atencao"]
         and c["12"]["comunidade_onde_o_ponto_cai"] == "Bela Vista", str(c["12"]))
conferir("nome repetido com o ponto longe: avisa das duas coisas e diz a distância em metros",
         c["13"]["casamento"] == L.IGUAL and "há 2 comunidades" in c["13"]["atencao"] and "longe do território" in c["13"]["atencao"]
         and c["13"]["ponto_no_territorio_dela"].startswith("fora, a "), str(c["13"]))
conferir("comunidade sem território desenhado: diz", c["14"]["ponto_no_territorio_dela"] == "comunidade sem território desenhado" and "território" in c["14"]["atencao"])
conferir("as colunas de decisão do negócio saem em branco", all(l["decisao_negocio"] == "" and l["observacao_negocio"] == "" for l in r["conferencia"]))
sem = {x["comunidade_nossa"]: x for x in r["sem_nome_oficial"]}
conferir("comunidades sem nome oficial: ordem do maior para o menor número de endereços", [x["enderecos"] for x in r["sem_nome_oficial"]] == sorted((x["enderecos"] for x in r["sem_nome_oficial"]), reverse=True))
conferir("a maior sem nome oficial mostra a localidade do IBGE que cai dentro dela", r["sem_nome_oficial"][0]["comunidade_nossa"] == "Grande Sem Nome"
         and "Pico do Boné" in r["sem_nome_oficial"][0]["localidades_oficiais_dentro_dela"], str(r["sem_nome_oficial"][0]))
conferir("quem tem par não entra na lista das sem nome oficial (só Sede, Bela Vista (Sul) e a Grande Sem Nome)", set(sem) == {"Sede", "Bela Vista (Sul)", "Grande Sem Nome"}, str(sorted(sem)))
rs = r["resumo"][0]
conferir("resumo do município: 6 localidades, 3 casam, 3 sem par; 6 comunidades",
         rs["localidades_ibge"] == 6 and rs["nome_igual"] + rs["nome_parecido"] == 3 and rs["sem_par"] == 3 and rs["comunidades_nossas"] == 6, str(rs))
conferir("sem dado pessoal: nenhuma coluna de UC, titular ou endereço de pessoa",
         not any(k in " ".join(r["conferencia"][0]) + " ".join(r["sem_nome_oficial"][0]) for k in ("uc;", "titular", "cpf", "telefone", "rua")))

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
