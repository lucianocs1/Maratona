# Checklist do plano final (docs/PLANO_FINAL.md)

Branch: sabrina/plano-final (a partir da sabrina/passo15-tradutor, commit ee9b030).
Uma sessão nova continua daqui: ler docs/PLANO_FINAL.md e a última fase sem [x].

- [x] Passo 0: plano salvo em docs/PLANO_FINAL.md e este checklist criados
- [x] Fase A: terminar o Passo 15 (tela de conferência, planilhas demo)
- [x] Fase B: tipo de desligamento e auditoria encadeada por hash
- [x] Fase C: rádios, modelo de mensagem, envio por e-mail, confirmação, arquivos criptografados
- [x] Fase D: comprovante, relatório mensal, relatórios de auditoria, painel do mês, semente de demonstração
- [x] Fase E: telas por perfil, visual único Farol, Ajuda
- [x] Fase F: só se sobrar tempo (filtros do mapa, polígono pronto, UTM/GMS na simulação, transformador/circuito) — parcial, ver resumo
- [x] Fase G: README, SEGURANCA.md, ORIGEM.md, docs/DEMO.md, testes/rodar_testes.ps1, PR para a melhorias
- [x] Fase H: relatórios completos, registro total, ficha da comunidade
  - [x] H0 regras dos relatórios (rodapé, segunda via, comparações, Como calculamos, PDF/CSV/Enviar, filtros, permissões)
  - [x] H1 mensal (diretoria)
  - [x] H2 custos por rádio
  - [x] H3 comunidades mais afetadas
  - [x] H4 prazos
  - [x] H5 auditoria e auditoria geral
  - [x] H6 registro total e linha do tempo do aviso
  - [x] H7 ficha da comunidade, mapa de calor, alerta de repetição
  - [x] Semente do ano, DEMO.md, PR atualizado
- [x] Fase J: verificação geral (todo botão funciona, tudo salva)
  - [x] J1 inventário (docs/VERIFICACAO.md)
  - [x] J2 teste de ponta a ponta por item e por perfil
  - [x] J3 erros corrigidos com teste
  - [x] J4 cadastro de rádio só do Admin da empresa + pedidos de rádio
- [x] Fase K: idiomas (pt-BR, en, es)
  - [x] K1 aviso, mensagem, tipos, PDF, e-mail, comprovante e áudio nos 3 idiomas
  - [x] K2 telas nos 3 idiomas
- [ ] Fase I: acessibilidade e todos os equipamentos
  - [x] I1 layout por tamanho de tela
  - [ ] I2 texto, cor e movimento
  - [ ] I3 teclado e leitor de tela
  - [ ] I4 tempo e trabalho perdido
  - [ ] I5 testes automáticos (axe, teclado, reflow, contraste)
  - [x] I6 botão Acessibilidade (Bloco D)
  - [ ] I7 Libras e voz (prioridade 2)
  - [x] I8 declaração e retorno (Bloco D; PDF marcado fica como limitação)

## Resumos por fase

### Passo 0 (14/10/2026)
- Plano salvo; checklist criado. Ficou fora deste commit, no diretório de trabalho, a etapa 4 do Passo 15 em andamento (api/conferencia.py e testes/planilha/teste_conferencia.py): ela entra na Fase A.

### Fase A (14/10/2026)
- Feito: dupla conferência independente (api/conferencia.py, etapa 4 do Passo 15); planilha em dois passos: POST /api/planilha (Conferir, nada no histórico) e POST /api/avisos (Gerar) com pacote assinado (api/pacote.py: HMAC, FAROL_CHAVE_PACOTE, 15 min, preso a usuário e empresa, UCs opacas); travas puras (nucleo/travas.py): equipamento vital rejeitado/corrigido/fora bloqueia sempre, limite de rejeição com justificativa (300 car.), suspeitos amarelos (isolado, muitas UCs na mesma coordenada, município diferente da maioria), caixa "Conferi os números e o mapa"; Baixar JSON com UCs (permissão baixar_json, auditado) e relatório CSV protegido contra fórmula; erro inesperado = "nada foi gerado (ERR-xxxx)", log sem dados; segredos.py (env ou .env); tela do passo 3 com a conferência, alertas, corrigidas em roxo no mapa, escolha de aba; 5 planilhas demo (simulacao/planilhas_demo.py, reprodutíveis byte a byte).
- Testes: teste_travas 48/48, teste_demo 6/6, teste_api 76/76, teste_acesso 36/36, navegador (rodar_teste_app) 76/76, coordenadas 105, tradutor 67, conferencia 15, nucleo/planilha 67, proxy 15, leitura 51, senhas 11, áudio 15, admin 182; minimização sem ocorrência nas duas cidades; --so-algoritmo igual ao passo 12 (Rural 0.561→0.912, Urbana 0.852→0.956, 835 cenários, 88.3%/95.0%, 44s→14s).
- Commit: ver git log ("Fase A").

### Fase B (14/10/2026)
- Feito: auditoria só inclusão (gatilhos UPDATE/DELETE/TRUNCATE no banco) e encadeada por hash (nucleo/auditoria.py), com nome e perfil copiados do login; migração das linhas antigas; /api/auditoria/verificar (Admin do Farol vê onde quebrou; Admin da empresa só se está íntegra); código de verificação FRL-… do aviso = hash da linha "gerou aviso" (mesma transação), /api/verificar/{codigo}; tipo de desligamento (lista + "Outro" sem dado pessoal), guardado no aviso; cancelar e mudar a data pelo histórico (auditoria com antes e depois); "gerou PDF", "editou a mensagem", "gerou MP3" na auditoria; "Solicitado por <nome> (<perfil>) em <data> às <hora> · código" no aviso, no histórico e no PDF; Consulta sem o PDF da rádio; aba "Auditoria" com "Conferir a integridade"; teste_matriz (toda rota x todo perfil, rota nova sem regra = falha); testes/rodar_testes.ps1.
- Testes: teste_auditoria 45/45, teste_matriz 5/5 (28 rotas fechadas x 4 perfis + sem login + isolamento), navegador 84/84, API 76/76, acesso 36/36 e o resto da bateria (rodar_testes.ps1: 19 de 19); --so-algoritmo igual ao passo 12.
- Próximo: Fase C. O PDF ainda sai da impressão do navegador; na Fase C ele passa a ser gerado no servidor (anexo do e-mail), e aí a permissão de gerar PDF fica garantida no servidor.

### Fase C (14/10/2026)
- Feito: rádios por empresa no banco (Admin cadastra e altera; Operador acrescenta "+ Nova rádio"); configuração da empresa no banco (modelo da mensagem com campos e trechos opcionais, nome falado, telefone, limite de rejeição, fuso UTM, antecedência) usada pelo tradutor e pelas travas; mensagem da rádio pelo modelo (nucleo/mensagem.py, sem sufixo de distrito, {codigo} preenchido depois de gravar); sugestão de rádio por comunidade com o distrito + "Sem rádio cadastrada para"; envio com valor gravado, cobrança fechada ou por minuto, custo antigo opcional, economia calculada/informada e tempo de ar economizado (nucleo/economia.py); PDF do roteiro gerado no servidor (fpdf2) e MP3 (Piper) anexos no e-mail (SMTP por variáveis; Mailpit local v1.31.3 conferido pelo SHA-256), guardados cifrados (AES-256-GCM, cofre.py) e baixáveis pelo histórico; link "Confirmar recebimento" (token de uso único, 7 dias, GET só mostra, POST confirma, origem conferida); WhatsApp (wa.me) e cópia registrados; limite de e-mails por hora; texto com número longo/e-mail/site recusado; FAROL_EMAIL=0 desliga o e-mail; painel e comparativo usam o tempo da mensagem.
- Dependências novas (PyPI, OSV sem vulnerabilidade aberta em 14/10/2026): fpdf2 2.8.9 (LGPL-3.0), cryptography 50.0.2 (Apache-2.0/BSD), fonttools 4.66.1 (MIT), pillow 12.3.0 (MIT-CMU).
- Testes: rodar_testes.ps1 20 de 20 (teste_radio 72/72 com o Mailpit; navegador 92/92; matriz com as rotas novas); --so-algoritmo igual ao passo 12.

### Fase D (14/10/2026)
- Feito: prazo do aviso (nucleo/prazo.py: 72 h ou 5 dias úteis com equipamento vital, até o primeiro envio à rádio); relatório do período (nucleo/relatorio.py: resumo, por tipo, por rádio, comunidades mais afetadas, fora do prazo, sem envio, como a economia foi calculada, lista detalhada, comparação com o mês anterior; filtros município, tipo, rádio e pessoa); comprovante do aviso; relatório de auditoria (Admin da empresa) e auditoria geral de acessos (Admin do Farol, filtro por empresa); PDF (apresentacao/pdf_relatorio.py) e CSV protegido contra fórmula, cada exportação na auditoria com quem gerou e o código FRL do relatório; painel do mês no dashboard; semente de demonstração (comunidades.semente_demo: 16 avisos, ~19 envios e 4 rádios fictícios, uma vez só); telas: aba Relatórios, comprovante no histórico, exportação da auditoria.
- Testes: rodar_testes.ps1 21 de 21 (teste_relatorios 44/44; navegador 97/97; matriz com 46 rotas fechadas); --so-algoritmo igual ao passo 12.

### Fase E (14/10/2026)
- Feito: menu por perfil conforme a matriz (Admin do Farol: Empresas e Auditoria geral; Admin da empresa: Novo aviso, Histórico, Relatórios, Usuários, Rádios, Configurações, Auditoria; Operador: Novo aviso, Histórico, Relatórios; Consulta: Mapa, Histórico, Relatórios; Relatórios com Painel do mês, Do período e Comparativo); telas de admin ligadas à API real: usuários com municípios (convite sem senha, senha temporária, último admin protegido), rádios (alcance por município e por comunidade com distrito, editar, desativar), configurações (modelo da mensagem com prévia, telefone, limite, fuso UTM, antecedência), empresas com CNPJ alfanumérico opcional (validação do protótipo do Lucas portada para Python) e suspender/reativar (sessões encerradas); visual único Farol (Âmbar, Noite, Maré, Névoa) em todas as telas, inclusive entrar e trocar a senha, tema claro e escuro (o fundo do mapa acompanha); botão Ajuda por perfil e "?" para UC, equipamento vital, corrigida, rejeitada, limite de rejeição, localidade vizinha, código de verificação e economia.
- Testes: rodar_testes.ps1 21 de 21 (acesso 46/46 com CNPJ, municípios e suspensão; matriz com PATCH /api/empresas; navegador 107/107 com rádios, configurações, ajuda, dicas, tema escuro e 44 px nas telas do Admin); --so-algoritmo igual ao passo 12.

### Fase F (14/10/2026, parcial)
- Feito: filtro do mapa por estado e município ("Ir para", aproxima no município) e agrupamento das UCs por circuito e por transformador na conferência (nucleo/agrupamento.py; só códigos da rede e contagens).
- Não feito (vai para "Próximos passos" no README): selecionar um polígono pronto (comunidade ou distrito) para simular o desligamento e aceitar UTM/GMS na tela de simulação. As duas ficam no mapa estático de demonstração (mapa_template.html), que tem testes de tela idênticos ao passo 12; mexer nele agora arriscaria a referência às vésperas da apresentação. Colorir os pontos por circuito no mapa também fica para depois.
- Testes: rodar_testes.ps1 21 de 21 (travas 49/49, API 77/77, navegador 108/108); --so-algoritmo igual ao passo 12.

### Fase G (14/10/2026)
- Feito: README completo (o que é, resultados do pipeline, passo a passo no Windows, perfis, arquitetura MVC, segurança/LGPD, validação, próximos passos); SEGURANCA.md com a tabela "Ameaça → proteção → teste que prova"; ORIGEM.md na raiz (dados, componentes, voz, Mailpit, dependências, licenças e hashes); docs/DEMO.md (roteiro de 5 minutos com o bloqueio do equipamento vital); DEPLOY.md com as variáveis novas; testes/rodar_testes.ps1 (desde a Fase B). Banco local migrado e com a semente de demonstração (16 avisos, 19 envios, 4 rádios; auditoria íntegra).
- Bateria final: rodar_testes.ps1 21 de 21 (980 verificações); --so-algoritmo igual ao passo 12.
- PR: sabrina/plano-final -> melhorias (link no fim da sessão).

## Decisões da Fase H (tomadas sem perguntar: a opção mais segura e mais simples)
- Atribuição: tudo conta no mês em que o aviso foi criado (envios, custo e prazo do aviso vão para o mês dele).
- Auditoria geral de acessos (Admin do Farol) não tem "Enviar": o Admin do Farol não tem domínio de empresa para restringir os destinatários.
- Equipamento vital por comunidade não é guardado (só a contagem por município): os relatórios mostram o vital por município.
- Não existe campo de justificativa de atraso: a coluna aparece com "—" até a distribuidora pedir esse campo.
- Ficha da comunidade, mapa de calor, linha do tempo, lista de vias e comprovante na tela só mostram: não vão para a auditoria. Todo relatório na tela vai, como "gerou relatório X (tela)"; todo PDF, CSV, via e envio também.
- Projeção do ano: acumulado + média dos meses fechados (contando meses fechados sem gasto como zero) x meses que faltam; o mês em andamento não entra na média. Sem mês fechado (janeiro), sem projeção.
- Setas ↑ ↓ no PDF viram + e - (as fontes do PDF são Latin-1); na tela e no CSV ficam as setas.
- A segunda via usa a mesma chave do cofre dos arquivos (FAROL_CHAVE_ARQUIVOS); sem a chave o PDF não é gerado (503), para nunca existir relatório sem via.
- Envio de relatório: 1 a 5 destinatários do domínio da empresa, 10 envios por hora por usuário (na memória do processo, como o limite de login).
- Confirmação de recebimento pela rádio (link do e-mail) fica na auditoria sem usuário: quem confirma é a rádio, não alguém do Farol.
- Alerta de repetição (padrão: 3 desligamentos em 30 dias, configurável): amarelo, não bloqueia; aparece na conferência e, ao gerar, vai para a auditoria.
- Registro total (H6) é conferido lendo o código das rotas (teste_registro_total.py) e, no banco, pelo teste_relatorios_h (nenhuma linha com usuário sem nome e perfil).
- Envio de aviso cancelado continua no gasto, nos pedidos e no tempo no ar (a rádio foi paga); o aviso cancelado não conta como desligamento nem entra no prazo.
- Semente do ano separada da semente de demonstração (semear_ano, marca "semente de demonstração (ano)"): os testes que contam a semente de demonstração não mudam; o comando da semente_demo roda as duas.
- O banco ganha as colunas e a tabela da Fase H pela semente (como nas fases anteriores), não na subida da API: no deploy, rodar a semente de novo (DEPLOY.md).
- Na tela, o relatório mensal antigo (por tipo, por rádio, lista) deu lugar ao documento da Fase H, o mesmo do PDF e do CSV; o JSON da API mantém os campos antigos para quem já os usa (painel do mês).
- Os testes que leem o texto dos PDFs passam a ler o fluxo até o "endstream" com zlib tolerante: antes, um \r no fim dos dados comprimidos (acaso do conteúdo) fazia o teste falhar de vez em quando.
- Bateria final da Fase H: rodar_testes.ps1 com 23 de 23 testes OK (Relatórios completos 69/69, Registro total 5/5, Tela do app 109/109, minimização 0 nas duas cidades); --so-algoritmo igual ao passo 12 (835 cenários, cobertura 88.3%, precisão 95.0%, aviso 44s -> 14s).
- Na tela, a coluna do painel ficou presa à largura dele (minmax(0, 1fr)); o teste da tela confere que nada passa da largura do painel.

### Fase J (15/10/2026)
- Feito: inventário de telas, botões, formulários e downloads por perfil com a rota da API (docs/VERIFICACAO.md); teste de ponta a
  ponta no navegador (testes/navegador/teste_verificacao.mjs, com Mailpit: e-mail, segunda via e confirmação de verdade) por
  perfil: salva e continua depois de recarregar e de sair e entrar, editar/desativar na lista, auditoria com o nome, erro no
  campo sem perder o digitado, clique duplo, duplicata recusada no servidor, sem conexão e erro 500, console e respostas sem erro.
  Antes: 8 de 28 verificações; depois: 110 de 110. 13 problemas corrigidos (tabela em docs/VERIFICACAO.md, J3): aviso gerado duas
  vezes com o mesmo pacote, nenhum "Salvando…", duplicatas aceitas, erro só na mensagem geral (e em inglês do Pydantic), "Failed
  to fetch", empresa sem admin pela metade, desativar rádio só editando, empresa e nome de usuário sem edição, mensagens do
  usuário anterior depois de sair, 404 da rede fictícia no console, rádio cadastrada com o aviso aberto sem valor sugerido.
  J4: só o Admin da empresa cadastra rádio; o Operador pede (pedidos de rádio, atender = cadastro preenchido, recusar com motivo).
- Testes: rodar_testes.ps1 24 de 24 (novo: Verificação geral 110/110; Tela do app 110/110; Rádio 79/79; API 78/78); --so-algoritmo
  igual ao passo 12 (835 cenários, 88.3%/95.0%, 44s -> 14s).

## Decisões da Fase J (tomadas sem perguntar: a opção mais segura e mais simples)
- Duplicata de envio = mesmo aviso, município, rádio, canal, texto, valor e cobrança em menos de 1 minuto (409); envio que falhou pode ser repetido na hora.
- Mudar a data para a mesma data e reativar o que já está ativo: 409 (nenhuma linha a mais na auditoria). Salvar rádio sem mudança: 200 sem linha na auditoria.
- Pedido de rádio: só o Operador pede (o Admin cadastra direto); o Operador vê só os pedidos que fez; contato = e-mail ou telefone da rádio; observação recusa número longo, e-mail e site.
- Editar empresa muda nome, domínio e CNPJ; a sigla e os e-mails já cadastrados não mudam.
- Município da concessão sem rede fictícia: 200 com null (antes 404).
- O banco ganha a coluna aviso.pacote_hash e a tabela pedido_radio pela semente (como nas fases anteriores): rodar `uv run python -m comunidades.semente` no banco local e no de produção.

### Fase K (15/10/2026)
- K1 (servidor, commit 96464f1): modelo da mensagem por idioma e idioma padrão da empresa; aviso do algoritmo e mensagem com data e
  hora no formato do idioma (português idêntico ao de antes); tipos, PDF da rádio, e-mail, página de confirmação e comprovante no
  idioma do aviso; voz en_US-ljspeech (domínio público, MD5 conferido); relatórios e erros da API no idioma de quem pede
  (X-Farol-Idioma); preferências do usuário (PUT /api/eu/preferencias). teste_idiomas 34/34.
- K2 (tela): dicionário apresentacao/app/textos.js (a chave é o texto em português; 680 textos en/es), index.html com data-t,
  seletor de idioma no topo (também em Entrar; sessão antes do login, perfil depois), Intl, <html lang>, lang no aviso e no
  comparativo, aviso na tela quando o idioma do aviso não tem voz. Testes: teste_textos (447 textos usados, nenhum sem tradução),
  teste_idiomas_tela 8/8 (todas as telas do Admin da empresa em en e es sem português sobrando), teste_app 110/110 e
  teste_verificacao 110/110 em português.

## Decisões da Fase K (tomadas sem perguntar: a opção mais segura e mais simples)
- Espanhol sem áudio: todas as vozes em espanhol do repositório oficial são ajustes da voz "lessac" (dados com licença só de
  pesquisa) ou não dizem de onde partiram; FAROL_VOZ_ES liga a davefx se a empresa aceitar. A voz pt_BR em uso tem a mesma origem
  lessac: registrado no ORIGEM.md para revisão antes de uso comercial.
- Inglês: en_US-ljspeech (dados LJ Speech em domínio público, treinada do zero).
- A data e o horário continuam guardados no formato brasileiro ("20/11", "8h às 14h"); o idioma do aviso só muda como saem.
- O aviso do algoritmo em espanhol mantém "20/11, de 8:00 a 14:00" (as regras do mapa, com testes de referência do passo 12);
  a mensagem da rádio em espanhol usa "20 de noviembre".
- Mensagens de erro da API: catálogo das fixas e das com partes variáveis (apresentacao/traducao.py); o que não estiver no catálogo
  fica em português. Relatórios: o documento pronto é traduzido por catálogo (as contas não mudam); em inglês, R$ e % com ponto decimal.
- Nomes de comunidade, município, pessoa e rádio nunca são traduzidos; o texto do "Outro" vai como foi digitado.
- O idioma da tela só usa a sessão do navegador antes do login (nada fica no computador) e depois o perfil do usuário.

### Fase K: bateria completa (15/10/2026)
- 27 de 28 na primeira rodada: "Telas nos 3 idiomas" achou "Esconder rede fictícia" em português (o rótulo só era escrito quando a rede carregava). Corrigido (`desenharBotaoRede` também ao trocar o idioma); 8/8. Métricas iguais: 835 cenários, cobertura 88.3%, precisão 95.0%, aviso 44s -> 14s.

### Correção: ERR-xxxx ao entrar num banco já existente (15/10/2026)
- Causa: as colunas e tabelas novas das fases J e K (usuario.preferencias, pedido_radio, idiomas da empresa) só eram criadas pela semente; a API não atualizava o banco ao subir e o login lia `preferencias` (UndefinedColumn).
- Correção: a API aplica `atualizar_esquema()` ao subir (só acréscimos, idempotente, com trava; nada apagado). Em produção, sem permissão de DDL, sobe e o log manda rodar a semente com o dono. Banco local atualizado: 208 linhas de auditoria e 51 avisos intactos.
- Regra nova na verificação da Fase J: teste_migracao (banco de versão anterior; os 4 perfis entram; auditoria intacta; colunas iguais às de um banco novo), na bateria inclusive no -Rapido.

### Fase I1 (15/10/2026)
- Decisões: uma coluna até 1023 px (tablet em pé e deitado até 1023), botão "Menu" (aria-expanded, aria-controls, Esc fecha e devolve o foco) no lugar das abas; painel com largura máxima de leitura de 860 px; telas grandes (1600+) com painel mais largo. Tabelas em cartões abaixo de 600 px (cada valor com o nome da coluna; role table/row/cell para o leitor de tela não perder a tabela); de 600 px para cima, rolam dentro de si com a 1ª coluna fixa. Janelas em tela cheia abaixo de 600 px com o Fechar fixo embaixo e env(safe-area-inset-*). Toque (pointer: coarse): alvos de 48 px. Mapa com altura clamp(280px, 55vh, 640px); nada exige arrastar (zoom por botões e teclado, "Ir para" município/UF). Impressão sem topo, menu, mapa e botões, em tema claro. Manifest sem service worker.
- 400% de zoom: equivale a 320 px de largura CSS em 1280 px; o teste confere 320 px.
- Dicas "?" já abriam por clique/toque/teclado; as dicas do mapa (tooltip do Leaflet) seguem o Leaflet (toque abre ao tocar).
- Teste: teste_telas.mjs 28/28 (9 vistas x 7 tamanhos sem rolagem horizontal, menu, cartões, tela cheia, 48 px, impressão, manifest). teste_app 110/110; verificação 110/110.
- Intermitente a investigar: numa de 3 rodadas, a verificação teve um 401 em /api/usuarios na seção do Admin da empresa (as outras duas passaram).

### Mapa das empresas e área de atuação (15/10/2026, pedido da usuária antes de I2)
- Decisões da usuária: baixar as malhas dos 27 estados (5.570 municípios, tabela `municipio_ibge`, contorno simplificado); UC fora da área vira linha rejeitada ("fora da área de atuação da empresa"), conta no limite de rejeição e, se for equipamento vital, bloqueia.
- Decisões minhas (a mais segura e simples): empresa sem área cadastrada não gera aviso (422 com a mensagem); o Admin do Farol não acessa comunidades nem rede (403), além de histórico, painel, relatórios operacionais, planilha e pacotes, que já eram fechados; a prévia da área é o próprio PUT sem `confirmar` (nada muda, nada na auditoria); importar arquivo registra "leu arquivo de área" ou "arquivo de área recusado" (sem o conteúdo); município entra na área pelo KML se tiver pelo menos metade da área dentro (o mesmo critério da concessão); a EMG recebe a área que já existia uma vez só (a auditoria "área de atuação: carga inicial" impede repetir, mesmo se a área for esvaziada depois).
- Download do IBGE: o Python desta máquina não reconhece a cadeia de certificados do IBGE; o `_baixar` usa então o curl do sistema, com a verificação ligada (nunca desligada).
- Testes: teste_area_atuacao 30/30; teste_mapa_empresas 24/24; teste_matriz 5/5 (75 rotas fechadas); teste_registro_total 5/5; teste_api 78/78; teste_app 110/110; verificação 110/110 (duas vezes); teste_telas 28/28; idiomas 8/8; dicionário 4/4. Métricas iguais: rural 91,2%, urbano 95,6%, 835 cenários, cobertura 88,3%, precisão 95,0%, aviso 44s -> 14s. Minimização: 0 nas duas cidades.
- Intermitentes resolvidos: o 401 da verificação (o teste saía com a lista ainda recarregando: agora espera a tela ficar quieta) e o "arquivo alterado no banco" do teste_radio (trocar um byte por 0x00 não muda nada quando ele já é zero: agora inverte os bits).
- No banco local há uma empresa ENRG sem área: aparece com "Área de atuação não cadastrada" e não gera aviso até o Admin do Farol cadastrar a área.

### Blocos A e B: tabelas do painel e textos (15/10/2026)
- Causa da quebra letra por letra: `overflow-wrap: anywhere` no painel (da I1) deixava as colunas encolherem até uma letra. Agora `break-word` (só quebra a palavra que não cabe sozinha) e o painel é um container: com até 640 px (o que inclui o painel lateral do computador), cada linha vira cartão "rótulo: valor", com role table/row/cell, caption e th scope mantidos. Cabeçalhos, siglas, códigos FRL, números, datas e botões sem quebra; só o Detalhe quebra (um hash pode quebrar em qualquer ponto; a quebra no hífen é permitida).
- Datas curtas ("15/10 14:59") com a completa no title e no aria-label, no idioma da tela (também nas datas dd/mm/aaaa hh:mm que vêm prontas nos relatórios). "Quem": nome em cima e perfil embaixo.
- "Ampliar painel": ~60% da tela (só no computador), Esc volta, guardado nas preferências (chave `painel` na lista fechada).
- Sem rolagem dupla: no computador, html e body não rolam; o painel é `position: relative`, para o cabeçalho escondido das tabelas (absolute) não esticar a página (ela media 2.422 px de altura).
- Tabela "Logins": sem o `min-width: 560px` das tabelas largas, não aparece barra de rolagem em tabela de 3 colunas.
- Teste (CDP, o mesmo executor dos outros testes do navegador; não Playwright): teste_tabelas.mjs 16/16, com 320, 400, 600, 640 (= 200% de zoom em 1280) e 1280 px, em pt-BR, en e es.
- Bloco B: "só acessos: True" vinha de `_filtros_texto` (o valor booleano ia cru): agora sim/não no idioma. teste_sem_booleanos 4/4 (8 relatórios x 3 idiomas x tela, CSV e PDF; nenhum True/False/None/null/undefined/NaN). Auditoria: com o relatório filtrado na tela, a lista sem filtro fica escondida (botão "Ver as últimas ações (sem filtro)", que é o título dela); 0 acessos com outras ações explica: "Nenhum acesso no período. Há N ação(ões) de outro tipo; desmarque "Só acessos" para vê-las."

### Bloco E: dados de demonstração (15/10/2026)
- Domínio real encontrado: a empresa de teste "Energisa" (ENRG, energisa.com.br, CNPJ real) com o admin carlos.silva@energisa.com.br, no banco local. Virou a fictícia "Distribuidora Exemplo (demonstração)" (DEX, exemplo.example, sem CNPJ), e o e-mail do admin passou para @exemplo.example; as trocas estão na auditoria com o antes e o depois (nada apagado). Área: 7 municípios do MS (Aquidauana, Campo Grande, Corumbá, Dourados, Naviraí, Ponta Porã, Três Lagoas). Está na semente de demonstração (`semente_demo.empresa_exemplo`, roda no `python -m comunidades.semente_demo`).
- Nenhum outro domínio real no código, nas configurações (.env, render.yaml) nem nas rádios do banco. O SMTP local é o Mailpit (127.0.0.1:1025).
- Trava nova: sem `FAROL_EMAIL_REAL=1`, só domínios reservados para teste recebem e-mail (recusa antes de conectar). teste_correio_demo 6/6.

### Blocos C e D: tema claro e acessibilidade visível (15/10/2026)
- C:
  - "Idioma da tela" no topo em branco nos dois temas (o topo é sempre a faixa da Noite).
  - O cartão de destaque do painel fica claro no tema claro, com a faixa âmbar, e continua Noite no escuro.
  - O retângulo ao clicar num município era o contorno de foco do navegador no SVG: tirado, e o destaque continua o contorno do Leaflet.
  - Aplicado o que estava pronto da I2: font-size em rem; borda dos campos com 3:1 (`--borda-campo`); `--acento-borda` #B07800 no claro; prefers-reduced-motion, prefers-contrast e forced-colors.
  - Achado do axe: no celular, a legenda do mapa cobria o "−" do zoom (target-size); agora ela rola dentro de si e não passa dos botões.
- axe-core 4.10.2: todas as telas × 4 perfis × 2 temas × 3 idiomas, os 7 tamanhos, o funil (passos 3 e 4), o painel aberto, o alto contraste e a Declaração. Nenhuma violação serious ou critical. O axe também confere o contraste de 4,5:1.
  - O executor deixa o Operador com senha temporária; o teste do axe cria a senha antes, porque antes testava a tela de troca no lugar das telas dele.
- D, painel Acessibilidade (botão no topo, também em Entrar):
  - A−/A/A+/A++ (90, 100, 150 e 200%);
  - alto contraste;
  - Atkinson Hyperlegible (OFL, 5.2.8, hospedada, SHA-256 no ORIGEM);
  - espaçamento 1.4.12;
  - reduzir movimento (também o mapa);
  - destacar links e foco;
  - guia de leitura;
  - modo simples (sem mapa e dicas);
  - ler em voz alta (speechSynthesis, só voz local; nada vai ao servidor);
  - Voltar ao padrão.
- Onde as escolhas ficam:
  - em `usuario.preferencias`, com chaves numa lista fechada;
  - a auditoria registra só os nomes das opções;
  - antes do login, só na sessão, e passam para o perfil ao entrar;
  - ao sair, voltam ao padrão.
- Correção: cliques seguidos sobrescreviam as preferências (cada PUT partia das antigas). Agora a junção é atômica no banco (`mesclar_preferencias`).
- "Pular para o conteúdo" (primeiro Tab, leva ao h1 da tela).
- Declaração de acessibilidade com o relato. A rota `POST /api/acessibilidade/relato` vale para todos os perfis, está na MATRIZ e vai para a auditoria com código FRL. Ela recusa texto com e-mail, telefone, número longo ou site.
- Testes: teste_acessibilidade 24/24; axe 0 serious/critical; dicionário 4/4; matriz 5/5; registro total 5/5; acesso 46/46.

### Privacidade da acessibilidade (15/10/2026, pedido da usuária)
- Ler em voz alta: só vozes com `localService === true` (voz on-line mandaria o texto a servidores de fora); sem voz local no idioma, botão desligado e o como instalar (Windows, Android, iPhone/iPad); na Declaração.
- Auditoria: só "alterou as preferências de acessibilidade" (e "alterou o idioma da tela"), sem quais opções: a combinação pode indicar deficiência (dado sensível, LGPD art. 11). As opções ficam só no perfil da pessoa; nenhum relatório nem Admin as vê.
- Testes: teste_acessibilidade 29/29 (voz local x on-line simulada; auditoria sem as opções); registro total 5/5; dicionário 4/4.

### Envio para a rádio: null, cobrança e economia (15/10/2026)
- "null" embaixo dos botões: com o e-mail ligado, o bloco "e-mail desligado" era `null` e o `replaceChildren` do navegador escreve null como texto. Os blocos vazios saem antes.
- Select "Cobrança" cortado: os campos do envio agora se ajeitam à largura (no celular, um por linha); o texto inteiro aparece nos 3 idiomas.
- Economia em frase clara:
  - sem o custo antigo, na prévia: "Economia: preencha "Quanto custaria do jeito antigo" para calcular";
  - com ele: "Economia: R$ X em relação ao jeito antigo";
  - pelo tempo no ar: "Economia: R$ X pelo tempo a menos no ar";
  - o "N s a menos no ar" continua.
- Teste novo teste_sem_null.mjs, 18/18: todas as vistas dos 4 perfis × 3 idiomas, com um aviso aberto e 570 cliques em botões que só mostram ou alternam. Nenhum null, undefined, NaN, True, False nem None. O select da cobrança cabe em 1280 e 360 px.
- teste_app 110/110 e verificação 110/110, com as frases novas.
