# Roteiro da demonstração (5 minutos e meio)

Tudo com dados de demonstração: território real (IBGE), rede, clientes, rádios e histórico fictícios.

## Antes de começar (uma vez, na véspera)

1. Banco e dados prontos (README, passos 3 a 5), inclusive `uv run python -m comunidades.semente_demo` (para os relatórios terem o ano inteiro de histórico fictício: o mês e meio recente e, de janeiro até ali, uns 3 avisos por mês, uma rádio cara, um mês com preço fora da curva, repetições, avisos fora do prazo, envios sem confirmação e um orçamento anual de rádio de R$ 15.000). Banco antigo: rode antes `uv run python -m comunidades.semente` (cria as colunas e a tabela novas; não mexe no que existe).
2. Senhas: a semente mostra as senhas temporárias uma vez. Entre com cada usuário e crie a senha de cada um antes da apresentação. Senha perdida: `uv run python -m comunidades.semente --nova-senha EMAIL`.

| Perfil | E-mail |
|---|---|
| Operador | `operador@emg.example` |
| Admin da empresa | `admin@emg.example` |
| Consulta | `consulta@emg.example` |
| Admin do Farol | `admin@farol.example` |

3. Abra dois terminais: o Mailpit (`data\raw\mailpit\mailpit.exe --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025`) e a API (`uv run uvicorn comunidades.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers`).
4. Deixe abertas no navegador: `http://127.0.0.1:8000` (o Farol) e `http://127.0.0.1:8025` (a caixa de e-mail da rádio).
5. Planilhas em `testes/planilha/exemplos/demo/`. A base de clientes no formato da Energisa é a `6_base_clientes.xlsx` (400 UCs fictícias da rede fictícia de Leopoldina, as mesmas colunas da planilha da Energisa). A planilha que a Energisa mandou fica fora do git: se for usá-la, copie para `data/raw/energisa/BASE_CLIENTES.xlsx` (200 linhas, 104 inativas).

## O roteiro

| Tempo | O que mostrar | O que dizer |
|---|---|---|
| 0:00 | Tela de entrar (visual Farol) | "Hoje o aviso de rádio lista fazenda por fazenda. O Farol avisa por comunidade." |
| 0:15 | Entre como **Operador**. Clique em **Ajuda**. | "Cada perfil vê só o que pode fazer, e o servidor confere tudo." |
| 0:30 | **Novo aviso** → `3_vital_rejeitado.xlsx` → data, horário, tipo "Poda de árvores" → **Conferir a planilha** | **Momento-chave:** alerta vermelho com as 2 linhas de equipamento vital (uma sem coordenada, uma fora da concessão). "Conferi" e "Gerar aviso" ficam travados. "Quem depende de aparelho para viver não pode ficar sem aviso: o Farol não deixa passar." |
| 1:15 | Volte ao passo 1 → `2_coordenadas_corrigidas.xlsx` → Conferir | 6 linhas corrigidas em roxo no mapa; os "?" explicam corrigida e rejeitada. Marque **Conferi os números e o mapa** → **Gerar aviso**. |
| 1:45 | Passo 5 (Avisos): a mensagem pelo modelo da empresa, **Ouvir**, **Baixar PDF para a rádio** | "Solicitado por Operador da EMG (Operador) · código FRL-…": tudo fica na auditoria. |
| 2:10 | **Enviar para a rádio** → Rádio Leopoldina FM (sugerida pelo alcance), valor por minuto → prévia da economia → **Enviar por e-mail** (confirmação) | Na aba do Mailpit: o e-mail com PDF e MP3 → **Confirmar recebimento** → de volta ao Farol, o envio aparece como "a rádio confirmou". |
| 3:00 | **Enviar a base da Energisa e desenhar a área do desligamento:** **Novo desligamento** → `6_base_clientes.xlsx` → data e horário → **Conferir a planilha**. O passo 3 **Escolher** abre com "0 de 400 UCs selecionadas" e o aviso "71 UC(s) inativa(s) não entram no aviso" (**Ver quais**: só a contagem por bairro e por circuito). **Desenhar uma área no mapa** → clique em 4 cantos → **Concluir a área**: o contador e o mapa mudam ao vivo. Clique numa comunidade para incluir ou tirar; marque um circuito na lista (os filtros se somam) → **Conferir a escolha** | "A Energisa manda a base inteira de clientes, não a lista de um desligamento. O operador diz quem fica sem luz: desenha a área, clica nas comunidades ou marca circuitos e transformadores. As travas valem só para os escolhidos, e a auditoria guarda o critério com o nome de quem escolheu, nunca a lista de UCs." Na conferência: "Quem será desligado: área desenhada…" e a conta fechada (lidas = inativas fora + não escolhidas + escolhidas). |
| 3:30 | **Relatórios** → **Custos por rádio** (período: ano): gasto mês a mês com a projeção até dezembro (a conta escrita), orçamento usado, a rádio cara no ranking e o alerta de preço → **Baixar PDF** (rodapé com o seu nome, o código FRL e "página X de Y"; a última página é "Como calculamos") | "Nenhum número inventado: a projeção é o acumulado mais a média dos meses fechados vezes os meses que faltam, e a conta está no relatório." |
| 3:55 | No mapa, aproxime em Leopoldina → **Mapa de calor (12 meses)** → clique numa comunidade vermelha (ex.: Braúna) | A ficha da comunidade: desligamentos, horas sem luz, rádios que alcançam, último e próximo → **Relatório desta comunidade (PDF)**. "Na hora de gerar um aviso, o Farol avisa em amarelo se a comunidade já teve 3 desligamentos em 30 dias." |
| 4:10 | Entre como **Admin da empresa**: **Rádios** (alcance por comunidade com o distrito; em **Pedidos de rádio**, o pedido que o Operador fez no envio → **Atender** abre o cadastro já preenchido), **Configurações** (modelo da mensagem com a prévia), **Auditoria** → **Conferir a integridade** | "A auditoria não se apaga nem se edita: cada linha guarda o código da anterior." |
| 4:50 | Entre como **Consulta**: **Mapa**, um aviso do **Histórico** → **Comprovante (PDF)** e **Linha do tempo** | "Quem só consulta baixa comprovantes e relatórios, mas não gera aviso nem envia nada. A linha do tempo mostra tudo o que aconteceu com o aviso, com nome e perfil." |
| 5:10 | Entre como **Admin do Farol**: **Empresas** (CNPJ, suspender), **Auditoria geral** | "Várias distribuidoras no mesmo Farol, cada uma isolada." |
| 5:30 | Fim | "Tudo testado: 23 baterias de teste, a matriz de cada rota com cada perfil e um teste que confere que toda rota que muda, baixa ou gera grava na auditoria." |

## Se sobrar tempo ou alguém perguntar

- `4_muitas_rejeicoes.xlsx`: cerca de 8% rejeitadas, acima do limite de 2%. O aviso só sai com uma justificativa, que vai para a auditoria com o nome de quem escreveu.
- `5_maliciosa_macro.xlsx`: um .xlsx com macro, recusado na porta. Nada é lido nem gravado.
- `1_correta.xlsx`: nenhum alerta. O caminho feliz em 30 segundos.
- **Tema escuro**: botão no topo; o fundo do mapa acompanha.
- **Código de verificação**: copie o FRL-… de um relatório. Na API, `/api/verificar/FRL-...` mostra quem gerou, quando e o SHA-256 do PDF.
- **Segunda via**: em Relatórios, "Segundas vias" → **Baixar a via**: o mesmo PDF (mesmo SHA-256), guardado cifrado.
- **Enviar um relatório por e-mail** (Operador ou Admin da empresa): só para endereços `@emg.example`, até 5, com confirmação; chega no Mailpit com o PDF anexo e fica na auditoria com os destinatários. Um endereço de fora (ex.: `@gmail.com`) é recusado.
- **Outros relatórios**: Mensal (diretoria, com ↑↓ % contra o mês anterior e o mesmo mês do ano passado), Comunidades mais afetadas (rankings, repetição, evolução das 10 mais) e Prazos (% no prazo por mês, município, tipo e pessoa; atrasados e em risco).
- **Auditoria** (Admin da empresa): filtro por tipo de ação e pessoa, **Ver o relatório** (logins, antes → depois, resumo por pessoa, verificação da corrente), PDF, CSV, JSON e **Enviar**.
- **Aviso em espanhol** (Fase K): no topo, **Idioma da tela** → Español (a tela inteira muda; fica no perfil). No Novo aviso, passo 2 (**Cuándo**), **Idioma del aviso** → Español: a mensagem sai "Atención, oyentes… el 20 de noviembre, entre las 8:00 y las 14:00…", o PDF "Guion para la radio" e o e-mail em espanhol. O áudio em espanhol não existe (sem voz com licença clara; a tela avisa); em inglês há áudio.
