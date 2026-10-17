# Verificação geral do app (Fase J)

Inventário de tudo o que se clica, preenche ou baixa no app (apresentacao/app), por perfil, com a rota da API
que cada item chama, e o resultado da verificação de ponta a ponta no navegador
(testes/navegador/teste_verificacao.mjs, pelo executor `uv run python testes/navegador/rodar_teste_app.py teste_verificacao.mjs`).

Perfis: **F** = Admin do Farol, **A** = Admin da empresa, **O** = Operador, **C** = Consulta.
"Servidor" = a permissão é conferida na rota (testes/api/teste_matriz.py), não só escondida na tela.

## J1 — Inventário

### Topo e acesso (todas as telas)

| Item | Perfis | O que faz | Rota da API |
|---|---|---|---|
| Entrar (e-mail, senha) | todos | abre a sessão; senha temporária leva à troca | POST /api/entrar |
| Trocar a senha (atual, nova, repetir) | todos | troca obrigatória da temporária | POST /api/senha |
| Sair | todos | encerra a sessão e limpa a página | POST /api/sair |
| Tema claro/escuro | todos (também antes de entrar) | troca o tema; lembrado no navegador | — |
| Ajuda | todos | o caminho do perfil; fecha com Esc e com Fechar | — |
| "?" ao lado dos termos | todos | explica UC, equipamento vital, corrigida, rejeitada, limite, vizinha, código, economia | — |
| Abas do menu | todos | Novo aviso, Histórico, Relatórios… conforme o perfil | — |
| Sessão (ao abrir a página) | todos | confere se já há sessão | GET /api/eu, GET /api/config, GET /api/concessao |

### Novo aviso (A, O) — funil em 4 passos

| Item | O que faz | Rota da API |
|---|---|---|
| 1. Planilha: escolher ou arrastar o arquivo | .csv/.xlsx até 10 MB (conferido na tela e no servidor) | — |
| 1. Baixar o modelo | modelo da planilha (CSV) | GET /api/modelo-planilha |
| 1. Avançar | vai para o passo 2 (sem planilha, diz por quê) | — |
| 2. Data, início, fim | o desligamento (fim depois do início) | — |
| 2. Tipo de desligamento (+ "Outro" com descrição) | vira o {motivo} da mensagem | — |
| 2. Idioma do aviso | pt-BR, en, es | — |
| 2. Aba da planilha | quando mais de uma aba serve (409 do servidor) | — |
| 2. Conferir a planilha | conferência, travas e pacote assinado (nada no histórico) | POST /api/planilha |
| 3. Caixa "Conferi os números e o mapa" | libera o Gerar | — |
| 3. Justificativa (acima do limite de rejeição) | até 300 caracteres, vai para a auditoria | — |
| 3. Baixar relatório (CSV) | linha, situação e motivo, sem UC | POST /api/planilha/relatorio |
| 3. Baixar JSON (com as UCs) | só A e O, reenviando o arquivo, auditado | POST /api/planilha/json |
| 3. Gerar aviso | grava o aviso (uma vez por pacote) | POST /api/avisos |
| 3/4. Voltar, Avançar para os avisos, passos do funil | navega no funil | — |
| 4. Mensagem da rádio (editar) | texto editável; tempo no ar recalculado | — |
| 4. Desfazer edição | volta ao texto gerado | — |
| 4. Copiar texto | copia e guarda o texto final | PUT /api/historico/{id}/municipios/{cod}/texto |
| 4. Ouvir / Baixar áudio (MP3) | voz do servidor | POST /api/audio (+ texto final) |
| 4. Baixar PDF para a rádio | PDF gerado no servidor, auditado | POST /api/historico/{id}/municipios/{cod}/pdf |
| 4. Ver comparativo | aviso de hoje x aviso por comunidade | GET /api/painel |
| 4. Novo desligamento | limpa a tela e o mapa | — |
| Mapa: Esconder/Mostrar UCs | pontos da planilha (só no navegador) | — |

### Enviar para a rádio (A, O; no passo 4 e no histórico)

| Item | O que faz | Rota da API |
|---|---|---|
| Rádio (lista, com o alcance) | sugere pelas comunidades; alerta "Sem rádio cadastrada para" | GET /api/historico/{id}/radios |
| Valor (R$), cobrança, custo antigo | prévia da economia (mesma conta do servidor) | — |
| Enviar por e-mail | PDF + MP3 anexos, link de confirmação | POST /api/historico/{id}/envios |
| Enviar por WhatsApp | abre wa.me e registra | POST /api/historico/{id}/envios |
| Copiar mensagem | copia e registra | POST /api/historico/{id}/envios |
| PDF enviado / MP3 enviado (baixar de novo) | decifra a via guardada (A, O, C) | GET /api/envios/{id}/arquivos/{pdf\|mp3} |
| Pedir cadastro de rádio (O) | pedido ao Admin da empresa (J4) | POST /api/radios/pedidos |
| Confirmar recebimento (rádio, sem login) | página do link do e-mail; o botão confirma | GET e POST /confirmar/{token} |

### Histórico (A, O, C)

| Item | O que faz | Rota da API |
|---|---|---|
| Lista (cartões) | avisos da empresa | GET /api/historico |
| Buscar (município ou comunidade) e Período | filtra na tela | — |
| Abrir um aviso | aviso, envios, quem pediu | GET /api/historico/{id}, GET /api/historico/{id}/envios |
| Comprovante (PDF) | comprovante do aviso, auditado | GET /api/historico/{id}/comprovante.pdf |
| Linha do tempo | o que aconteceu com o aviso, com nomes | GET /api/historico/{id}/linha-do-tempo |
| Mudar a data (A, O) | antes e depois na auditoria | POST /api/historico/{id}/data |
| Cancelar o desligamento (A, O) | com motivo, auditado | POST /api/historico/{id}/cancelar |

### Relatórios (A, O, C) — Painel do mês, Do período, Comparativo

| Item | O que faz | Rota da API |
|---|---|---|
| Painel do mês / Mapa (C) | números agregados e o mapa pintado | GET /api/painel |
| Relatório (mensal, custos, comunidades, prazos), período, filtros | | |
| Ver o relatório | documento na tela, auditado | GET /api/relatorios/{tipo} |
| Baixar PDF / Baixar CSV | com rodapé e código FRL; PDF ganha segunda via | GET /api/relatorios/{tipo}.{pdf\|csv} |
| Enviar (A, O) | até 5 e-mails do domínio da empresa | POST /api/relatorios/{tipo}/enviar |
| Segundas vias: Baixar a via | o mesmo PDF (SHA-256) | GET /api/relatorios/vias, GET /api/relatorios/vias/{id}.pdf |
| Comparativo: Ouvir (hoje e Farol) | áudio dos dois lados (A, O) | POST /api/audio |

### Mapa (todos com a tela do app)

| Item | O que faz | Rota da API |
|---|---|---|
| Ir para: Estado e Município | aproxima no município | — |
| Comunidades e nomes (de perto) | contornos e nomes | GET /api/municipios/{cod}/comunidades |
| Esconder/Mostrar rede fictícia | rede de demonstração | GET /api/municipios/{cod}/rede |
| Minimizar legenda | lembrada no navegador | — |
| Mapa de calor (A, O, C) | desligamentos por comunidade em 12 meses | GET /api/comunidades/calor |
| Ficha da comunidade (clique) | contagens, rádios | GET /api/comunidades/ficha |
| Relatório desta comunidade (PDF) / Enviar | auditado | GET /api/relatorios/comunidade.pdf, POST /api/relatorios/comunidade/enviar |

### Usuários (A)

| Item | O que faz | Rota da API |
|---|---|---|
| Convidar (nome, e-mail da empresa, perfil, municípios) | senha temporária aparece uma vez | POST /api/usuarios |
| Lista | usuários da empresa | GET /api/usuarios |
| Editar nome, perfil, municípios, situação (bloquear/reativar) + Salvar | o último admin não pode sair de admin nem ser bloqueado | PATCH /api/usuarios/{id} |
| Nova senha temporária | encerra as sessões da pessoa | POST /api/usuarios/{id}/senha-temporaria |
| Caixa da senha: Copiar, Fechar | a senha some da página ao fechar | — |

### Rádios (A)

| Item | O que faz | Rota da API |
|---|---|---|
| Cadastrar (nome, e-mail, WhatsApp, valor padrão, cobrança, municípios inteiros, comunidades de um município) | | POST /api/radios |
| Lista, Editar (+ Cancelar a edição) | | GET /api/radios, PATCH /api/radios/{id} |
| Desativar / Reativar | some ou volta no envio | PATCH /api/radios/{id} |
| Pedidos de rádio: Atender (abre o cadastro preenchido) / Recusar (motivo) | J4 | GET /api/radios/pedidos, POST /api/radios/pedidos/{id}/atender, POST /api/radios/pedidos/{id}/recusar |

### Configurações (A)

| Item | O que faz | Rota da API |
|---|---|---|
| Modelo da mensagem com prévia, nome falado, telefone | | GET e PUT /api/empresa/configuracao |
| Limite de rejeição, fuso UTM, antecedência | | idem |
| Orçamento anual de rádio, alerta de preço, repetição (N em D dias) | | idem |
| Voltar ao modelo padrão | só na tela, até Salvar | — |

### Empresas (F)

| Item | O que faz | Rota da API |
|---|---|---|
| Cadastrar (nome, CNPJ, sigla, domínio, primeiro admin) | senha temporária do primeiro admin | POST /api/empresas |
| Lista | | GET /api/empresas |
| Editar (nome, CNPJ, domínio) | antes e depois na auditoria | PATCH /api/empresas/{id} |
| Suspender / Reativar | suspensa: ninguém entra | PATCH /api/empresas/{id} |

### Auditoria (A: da empresa; F: geral de acessos)

| Item | O que faz | Rota da API |
|---|---|---|
| Lista das últimas ações | | GET /api/registro |
| Conferir a integridade | refaz a corrente de hashes | GET /api/auditoria/verificar |
| Filtros (mês, empresa (F), pessoa, tipo de ação, só acessos) + Ver o relatório | | GET /api/relatorios/{auditoria\|acessos} |
| Baixar PDF / CSV / JSON | auditado | GET /api/relatorios/{auditoria\|acessos}.{pdf\|csv}, GET /api/relatorios/{…} |
| Enviar (A) | domínio da empresa | POST /api/relatorios/auditoria/enviar |

## J2 — Verificação de ponta a ponta

`testes/navegador/teste_verificacao.mjs` (Edge sem tela, API de teste na porta 8001 com usuários de teste num esquema
próprio e o Mailpit, para o e-mail de verdade sem sair da máquina). Para cada perfil:

| Perfil | O que o teste faz e confere |
|---|---|
| Admin da empresa | entrar (vazio, senha errada), tema (continua depois de recarregar), Ajuda (Esc devolve o foco); Usuários: erro no campo (nome, e-mail de outro domínio), clique duplo, 409 do servidor, editar nome/perfil/municípios (recarregar), bloquear (sair e entrar) e reativar, último admin, nova senha temporária, auditoria com o nome; Rádios: erro no campo, clique duplo, 409, valor padrão, cobrança, alcance por município e por comunidade, editar (sair e entrar), desativar (recarregar) e reativar, auditoria; Configurações: erro no campo, prévia, tudo salvo (recarregar e sair e entrar), sem conexão, erro 500, nada pela metade, auditoria; Auditoria: filtro, Conferir a integridade, CSV, PDF e JSON |
| Operador | trocar a senha (curta, diferentes); Novo aviso: erro no campo (data, fim, "Outro"), muitas rejeições pedem a justificativa, clique duplo no Gerar, 409 do servidor, Baixar JSON; Envio: sem "+ Nova rádio", valor sugerido, valor/cobrança/custo antigo na prévia, e-mail (Mailpit) com clique duplo, 409 do servidor, WhatsApp, baixar de novo o PDF e o MP3 enviados, confirmação de recebimento pelo link; Pedir cadastro de rádio (erro no campo, clique duplo, 403 ao cadastrar direto); Histórico: busca, período, linha do tempo, mudar a data (erro no campo, clique duplo, 409, recarregar), comprovante; Relatórios: os 4 na tela, PDF e CSV, Enviar (erro no campo do domínio, e-mail chega), segunda via; Mapa: Ir para, mapa de calor, ficha da comunidade, relatório da comunidade |
| Admin da empresa (pedidos) | vê os pedidos com quem pediu, Atender abre o cadastro preenchido, recusar sem motivo (erro no campo) e com motivo, recarregar, auditoria com os nomes |
| Consulta | baixa de novo o PDF enviado; sem mudar data, cancelar, enviar nem pedir rádio; relatório e CSV sem "Enviar"; 403 do servidor ao enviar |
| Admin do Farol | Empresas: erro no campo (admin, CNPJ), clique duplo, editar (recarregar), suspender (sair e entrar) e reativar, 409 do servidor, auditoria; Auditoria geral: filtro por empresa, CSV, integridade |

Em todos: nenhuma resposta 4xx/5xx que não tenha sido provocada de propósito, console sem erros, nenhuma exceção nem
violação da CSP. O que já era coberto pelo teste da tela (testes/navegador/teste_app.mjs) não foi repetido: Ouvir e Baixar
áudio, PDF do roteiro com o texto editado, Copiar, comparativo com áudio, "Desfazer edição", demo com equipamento vital,
cancelar pelo histórico, dashboard, celular.

## J3 — O que estava quebrado, a causa e a correção

Antes das correções, o teste de verificação passou em 8 de 28 verificações (as seções paravam no primeiro botão que não
existia). Cada linha abaixo tem um teste que falhava antes e passa depois.

| # | O que estava quebrado | Causa | Correção | Teste |
|---|---|---|---|---|
| 1 | Gerar o aviso de novo com a mesma conferência (reenvio, ou clique duplo que passasse da tela) gravava **dois avisos** | o pacote assinado valia por 15 minutos para quantos avisos se quisesse | o aviso guarda o SHA-256 do pacote (índice único); a segunda vez é recusada com 409 "já foi gerado (aviso nº X)" | verificação: "Gerar aviso: o servidor recusa…"; teste_api |
| 2 | Nenhum botão de salvar mostrava "Salvando…" nem ignorava o segundo clique (usuários, empresas, rádios, configurações, mudar data, cancelar, envios, pedidos, relatórios) | só alguns botões eram desabilitados, sem texto | `ocupado()` no app.js: desabilita, mostra "Salvando…"/"Enviando…", `aria-busy`, ignora o segundo clique | verificação: "clique duplo…" em cada formulário |
| 3 | O servidor aceitava duplicatas: a mesma rádio duas vezes, o mesmo envio repetido em segundos, a mesma data de novo (linha a mais na auditoria), reativar empresa já ativa | sem conferência de duplicata nessas rotas | 409 com mensagem clara (o envio que **falhou** pode ser repetido na hora) | verificação e teste_radio |
| 4 | Dado inválido aparecia só numa mensagem geral, nunca no campo; número fora da faixa (ex.: limite de rejeição 99%) mostrava "Não foi possível concluir" (a mensagem do servidor vinha em inglês, do Pydantic) | as rotas devolviam só o texto; a tela não sabia qual campo | cabeçalho `X-Farol-Campo` nas rotas e no erro de validação (agora em português); a tela marca o campo (`aria-invalid` + `aria-describedby`), põe um resumo no topo com um link para cada campo e nunca apaga o que foi digitado | verificação: "erro no campo…" |
| 5 | Sem conexão aparecia "Failed to fetch"; erro 500 com corpo que não é JSON aparecia "Não foi possível concluir", sem dizer que nada foi salvo | o erro do `fetch` ia direto para a tela | mensagens claras: "Sem conexão com o servidor: o pedido não foi concluído…" e "O servidor teve um problema e nada foi salvo…" | verificação: sem conexão e erro 500 nas Configurações |
| 6 | A empresa podia ficar sem o primeiro admin (cadastro pela metade) | empresa e admin eram gravados em duas transações | uma transação só (`criar_empresa_com_admin`) | teste_acesso, verificação |
| 7 | Rádio: desativar e reativar só editando e desmarcando "ativa"; a auditoria dizia "alterou cadastro" | não havia botão nem ação própria | botões Desativar/Reativar na lista; auditoria "desativou rádio"/"reativou rádio"; salvar sem mudança não grava linha | verificação: Rádios |
| 8 | Empresas: não dava para corrigir nome, domínio nem CNPJ | a rota só mudava a situação | Editar (nome, domínio, CNPJ), com o antes e o depois na auditoria | verificação: Empresas |
| 9 | Usuários: não dava para corrigir o nome | a rota não recebia o nome | campo Nome na linha do usuário | verificação: Usuários |
| 10 | Ao sair, mensagens de status ("Fulana: alterações salvas") ficavam na página para quem entrasse depois | a limpeza da tela não apagava as mensagens | `limparTela` apaga as mensagens e os erros dos formulários | verificação (sair e entrar) |
| 11 | Município da concessão sem rede fictícia respondia 404 e enchia o console de erros a cada movimento do mapa | "sem rede" era tratado como erro | 200 com `null` (só código fora da concessão é 404) | verificação: "nenhuma resposta 4xx/5xx inesperada"; teste_api |
| 13 | Com o aviso aberto, uma rádio cadastrada depois (o caminho do pedido de rádio) aparecia na lista do envio sem o valor sugerido, e o envio dizia "Informe o valor" | a escolha do envio era criada uma vez, quando a lista ainda estava vazia, e não era refeita | se a rádio escolhida não está na lista, a escolha volta à primeira rádio com o valor sugerido dela | teste_app: "rádio cadastrada pelo Admin: sugerida com o valor padrão" |
| 12 | (regra nova, J4) o Operador cadastrava rádio direto no envio ("+ Nova rádio") | — | só o Admin da empresa cadastra; o Operador pede (ver J4) | verificação, teste_radio, teste_matriz |

| 14 | (achado pela usuária, 15/10/2026) Entrar no Farol num banco já existente dava "Ocorreu um erro e nada foi gerado (código ERR-…)" para todos os perfis | as colunas e tabelas novas das fases J e K (`usuario.preferencias`, `pedido_radio`, modelos por idioma e idioma padrão da empresa) só eram criadas pela semente; a API não atualizava o banco ao subir, e o login lê `preferencias` (UndefinedColumn) | a API, ao subir, aplica `atualizar_esquema()` (só acréscimos: `CREATE … IF NOT EXISTS` e `ADD COLUMN IF NOT EXISTS`, com trava para vários processos; nada é apagado). Sem permissão de alterar tabelas (produção), sobe assim mesmo e o log manda rodar a semente com o dono do banco | teste_migracao: banco de versão anterior → 500 sem atualizar; depois de subir, os 4 perfis entram, auditoria intacta e corrente íntegra; e toda coluna de um banco novo existe no atualizado |

**Regra (desde 15/10/2026):** depois de cada mudança de banco, "entrar com os 4 perfis" tem de funcionar num banco já
existente, não só no banco novo dos testes: `uv run python -W ignore testes/api/teste_migracao.py` (também na bateria,
inclusive no `-Rapido`). Coluna nova vai no `CREATE TABLE` **e** num `ALTER TABLE … ADD COLUMN IF NOT EXISTS`; o teste
compara as colunas de um banco criado do zero com as de um banco antigo atualizado.

## J4 — Cadastro de rádio só do Admin da empresa

- Só o Admin da empresa cadastra, edita, desativa, reativa e define o valor padrão (POST e PATCH /api/radios: `gerenciar_radios`).
- No envio, o Operador escolhe a rádio da lista e informa o valor daquele envio (sugerido pelo último valor usado ou pelo
  padrão) e a forma de cobrança. Não existe mais "+ Nova rádio".
- Falta rádio: "Pedir cadastro de rádio" (nome, cidade, contato da rádio e observação; sem dado pessoal: número longo,
  e-mail ou site na observação são recusados) → POST /api/radios/pedidos (`pedir_radio`, só o Operador). O Operador vê os
  pedidos que fez e a situação (aberto, atendido, recusado e o motivo).
- O Admin da empresa vê "Pedidos de rádio" na tela de Rádios: **Atender** abre o cadastro já preenchido; ao cadastrar, a
  rádio é criada e o pedido fica atendido na mesma transação (POST /api/radios com `pedido_id`); **Recusar** pede o motivo
  (POST /api/radios/pedidos/{id}/recusar). Pedido repetido aberto (mesma rádio e cidade) é recusado (409).
- Auditoria: "pediu cadastro de rádio" (Operador), "atendeu pedido de rádio" e "recusou pedido de rádio" (Admin), com os nomes.
- Matriz de perfis (testes/api/teste_matriz.py) com as rotas novas; Ajuda, README e docs/DEMO.md atualizados.
