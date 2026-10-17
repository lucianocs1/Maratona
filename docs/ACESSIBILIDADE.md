# Acessibilidade do Farol

Compromisso: **WCAG 2.2 nível AA** e **ABNT NBR 17225** no app (tela de entrar, troca de senha, todas as telas por
perfil), na página em que a rádio confirma o recebimento e nos e-mails. Público: pessoas com deficiência visual (cegueira
e baixa visão), auditiva e motora, pessoas com TDAH e outras neurodivergências e pessoas com dislexia.

Este documento tem duas partes: o que já é testado automaticamente (a cada `testes/rodar_testes.ps1`) e o **roteiro de
teste manual**, que precisa de gente e de leitores de tela de verdade.

## O que já existe (15/10/2026)

- **Botão Acessibilidade** no topo de todas as telas, também na de entrar. Ele abre um painel com:
  - tamanho do texto A− (90%), A (100%), A+ (150%) e A++ (200%), sem rolagem horizontal;
  - alto contraste (preto e branco, ou branco e preto no tema escuro);
  - fonte de leitura facilitada: Atkinson Hyperlegible, OFL, servida pelo Farol, sem CDN;
  - mais espaço entre letras, palavras e linhas (WCAG 1.4.12);
  - reduzir movimento (também no mapa);
  - destacar links e foco;
  - guia de leitura (uma faixa que acompanha o mouse e o foco);
  - modo simples (sem o mapa e as dicas);
  - ler a tela em voz alta, só com voz instalada no aparelho (`SpeechSynthesisVoice.localService === true`). Uma voz on-line mandaria o texto da tela a servidores de fora, por isso nunca é usada. Sem voz local no idioma da tela, o botão fica desligado e o painel diz como instalar uma voz no Windows, no Android e no iPhone ou iPad;
  - "Voltar ao padrão".
  As escolhas ficam só em `usuario.preferencias`, no perfil da própria pessoa. A auditoria registra apenas "alterou as preferências de acessibilidade", **sem dizer quais opções**: a combinação delas pode indicar uma deficiência, que é dado sensível pela LGPD (art. 11). Nenhum relatório nem Admin vê quais opções cada pessoa usa. Antes de entrar, valem só na sessão do navegador e passam para o perfil no login.
- **"Pular para o conteúdo"**: aparece no primeiro Tab e leva ao título da tela aberta.
- **Declaração de acessibilidade** (no painel): WCAG 2.2 AA, ABNT NBR 17225:2025, LBI (Lei 13.146/2015) art. 63, o que existe e as limitações conhecidas. Tem o formulário "Relatar um problema de acessibilidade": até 1.000 caracteres, sem dado pessoal, registrado na auditoria com código de verificação. O Admin do Farol vê os relatos na auditoria geral.
- **Telas:** do celular (320 px) à tela grande, com zoom de 400%. Menu, tabelas em cartões, janelas em tela cheia no celular e alvos de 48 px no toque.
- **Testes automáticos:**
  - `teste_axe.mjs` (axe-core 4.10.2): todas as telas × 4 perfis × 2 temas × 3 idiomas, os 7 tamanhos de tela, o funil e o painel aberto. Nenhuma violação serious ou critical.
  - `teste_acessibilidade.mjs`: o painel, o perfil e a Declaração.
  - `teste_tabelas.mjs`: tabelas em 320, 400, 600 e 640 px e no zoom de 200%.
  - `teste_telas.mjs`: os 7 tamanhos, menu, toque e impressão.

## Limitações conhecidas

- O fundo do mapa é imagem; os nomes e números do mapa estão nas listas e tabelas. A lista sincronizada com o mapa e o link "Pular o mapa" (I3) ainda faltam.
- O PDF ainda não é marcado (tagged PDF); a tela e o CSV trazem o mesmo conteúdo.
- Não há Libras dentro do app: use o VLibras (vlibras.gov.br).
- A voz do aviso em áudio existe em português e inglês, ainda não em espanhol.
- O aviso de tempo da sessão (I4) ainda falta.

## Roteiro de teste manual

Faça cada roteiro com a API local no ar (`http://127.0.0.1:8000`), com os usuários da semente de demonstração. Anote o
que travou, o que foi lido errado e onde o foco sumiu. Cada roteiro leva de 10 a 20 minutos.

### 1. Só teclado (sem mouse), no computador

1. Abra a tela de entrar. Aperte **Tab**: o primeiro foco é o link "Pular para o conteúdo".
2. Entre com o Operador só com Tab, digitação e Enter.
3. No menu, abra "Novo aviso" com Tab e Enter. Confira que o foco vai para o título da tela.
4. Escolha a planilha (Enter no campo de arquivo abre a janela do sistema), avance, preencha data, horário e tipo, e
   "Conferir a planilha".
5. Na conferência, marque "Conferi os números e o mapa" com a barra de espaço e gere o aviso.
6. No mapa: use os botões de zoom e o "Ir para" (estado e município) pelo teclado. O "Pular o mapa" e a lista de comunidades ainda faltam (I3).
7. Abra a Ajuda e feche com **Esc**: o foco volta ao botão Ajuda.
8. Confira em todas as telas: o foco é sempre visível (contorno), nunca fica escondido atrás do topo e nunca fica preso
   (Tab e Shift+Tab sempre saem de qualquer parte).

### 2. NVDA (Windows, gratuito) com Firefox ou Edge

1. Ligue o NVDA (Ctrl+Alt+N). Abra o Farol.
2. Aperte **H** para andar pelos títulos: a ordem tem de fazer sentido (um título principal por tela).
3. Aperte **D** para andar pelos marcos: topo, navegação, conteúdo principal e o mapa (região com nome).
4. No formulário de entrar, envie vazio: o NVDA tem de ler o resumo dos erros e, no campo, "inválido" e o texto do erro.
5. Gere um aviso: as mensagens de "pronto" e de erro têm de ser lidas sem você precisar procurar (região viva).
6. Abra uma tabela de relatório: com **Ctrl+Alt+setas**, o NVDA lê o cabeçalho da coluna junto com cada célula.
7. Troque o idioma da tela para English e para Español: o NVDA tem de trocar a pronúncia (atributo lang).
8. Num aviso em inglês ou espanhol, o texto do aviso tem de ser lido com a pronúncia do idioma do aviso.

### 3. TalkBack (Android) e VoiceOver (iPhone)

1. No celular, abra o Farol no navegador. Ligue o TalkBack (ou o VoiceOver).
2. Deslize para a direita para andar elemento por elemento: todo botão tem um nome que diz o que faz.
3. Abra o menu (botão "Menu"): o leitor diz se está aberto ou fechado.
4. Abra uma janela (Ajuda, senha temporária): ela ocupa a tela, tem "Fechar" e, ao fechar, o foco volta ao botão.
5. Gere um aviso só com o leitor e o toque duplo.

### 4. Zoom de 200% e 400%

1. No computador, Ctrl e + até 200%: nada some, nada se sobrepõe, o texto quebra linha.
2. Até 400% (equivale a uma tela de 320 px): a página não rola para o lado (só o mapa e as tabelas largas, dentro delas).
3. Aumente só o texto (configuração de fonte do navegador em "Muito grande"): o texto cresce junto.

### 5. Alto contraste do Windows (Temas de contraste)

1. Configurações > Acessibilidade > Temas de contraste > "Noite" ou "Deserto".
2. Abra o Farol: botões, campos, foco e alertas continuam visíveis; nada fica invisível (cor sobre cor).
3. Os estados (erro, alerta, cancelado, confirmado) continuam com ícone e texto, não só cor.

### 6. Movimento, cor e leitura

1. No sistema, ligue "Reduzir movimento" (Windows: Efeitos de animação desligados): o mapa não anima ao aproximar.
2. Confira que nenhum estado depende só da cor (mapa de calor tem legenda com números; alertas têm ícone e texto).
3. Leia um aviso inteiro: as frases são curtas, as ações têm verbo, há uma ação principal por tela.

## O que é testado automaticamente

(Atualizado no fim da Fase I: telas, perfis, temas, idiomas e tamanhos de tela verificados pelo axe-core, teste de teclado,
reflow a 320 px e 400%, texto a 200%, contraste dos pares de cores e emulação de movimento reduzido e alto contraste.)
