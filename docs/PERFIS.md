# Matriz de perfis do Farol

A permissão de cada perfil é conferida **no servidor**, em toda rota (`nucleo/acesso.py` e as dependências da API).
A tela só esconde o que o perfil não pode usar. A matriz completa, rota por rota, é a `MATRIZ` de
`testes/api/teste_matriz.py`: cada rota é chamada com os 4 perfis e sem login, e uma rota nova sem regra faz o teste
falhar. Esta página resume o que cada perfil faz.

| O quê | Admin do Farol | Admin da empresa | Operador | Consulta |
|---|---|---|---|---|
| Empresas: cadastrar, editar, suspender e reativar | sim | — | — | — |
| **Mapa das empresas**: área de cada empresa, legenda, sobreposição e ficha (só cadastro e contagens) | sim | — | — | — |
| **Área de atuação**: cadastrar e mudar (lista do IBGE, clique no mapa, KML/GeoJSON), com resumo e auditoria | sim | — | — | — |
| Auditoria geral de acessos (todas as empresas) | sim | — | — | — |
| Auditoria da empresa e relatório de auditoria | — | sim | — | — |
| Usuários da empresa | — | sim | — | — |
| Rádios: cadastrar, alterar, desativar, atender pedidos | — | sim | — | — |
| Pedir o cadastro de uma rádio | — | — | sim | — |
| Configurações da empresa (modelo da mensagem etc.) | — | sim | — | — |
| Novo aviso (planilha, conferir, gerar), PDF, áudio, enviar à rádio | — | sim | sim | — |
| Histórico, painel, relatórios operacionais, comprovantes | — | sim | sim | sim |
| Mapa operacional (comunidades, rede fictícia, mapa de calor) | — | sim | sim | sim |

## Admin do Farol: nada operacional (desde 15/10/2026)

O Admin do Farol cuida do cadastro das empresas e da área de atuação. Ele vê, de cada empresa, só **contagens**:
usuários, avisos no mês e no total. Nunca vê o conteúdo de avisos, o histórico, as comunidades afetadas, os pacotes
da conferência, a planilha nem a rede. No servidor, essas rotas respondem **403** para ele:

- avisos, histórico, painel, relatórios operacionais, comprovantes e envios;
- `/api/planilha`, `/api/avisos`, `/api/planilha/json` e o pacote assinado;
- `/api/municipios/{codigo}/comunidades`, `/api/municipios/{codigo}/rede`, `/api/comunidades/ficha` e `/api/comunidades/calor`.

O mapa dele é o **mapa das empresas**: a área de atuação de cada empresa, com cor e hachura diferentes e a sigla
escrita no meio. Uma empresa suspensa aparece em cinza tracejado. Os municípios em mais de uma empresa aparecem com
borda vermelha tracejada.

## Área de atuação

A área de atuação são os municípios do IBGE onde a empresa pode criar avisos (tabela `empresa_municipio`). O que o
servidor faz com ela:

- No mapa operacional dos perfis da empresa, só os municípios da área aparecem.
- Na conferência da planilha, a UC de município fora da área é rejeitada com o motivo "fora da área de atuação da
  empresa". Ela entra no limite de rejeição e, se for equipamento vital, bloqueia a geração.
- Uma empresa sem área cadastrada não gera aviso.

Toda mudança da área vai para a auditoria com quem fez e o antes e o depois (a lista de municípios). O arquivo
KML/GeoJSON importado é lido em memória e descartado; só os códigos dos municípios ficam.

Testes: `testes/api/teste_area_atuacao.py`, `testes/api/teste_matriz.py` e `testes/navegador/teste_mapa_empresas.mjs`.
