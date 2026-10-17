# Norte: cada comunidade avisada pelo nome

Desafio 3 da Maratona TIVIT-RPV (Grupo Energisa): **"Fazenda por fazenda, ou uma comunidade só?"**

Num desligamento programado, a distribuidora tem de avisar quem fica sem energia, e no rural o aviso vai pelo rádio. Hoje ele lista imóvel por imóvel ("Sítio Boa Vista, Fazenda Cruzeiro, ...") e fica longo, caro e difícil de entender. O Norte recebe a planilha das unidades consumidoras (UCs) afetadas, descobre **as comunidades** onde elas estão e monta um aviso curto ("moradores de Graminha, Boa Sorte e parte de Tomé Nogueira"). Ele confere a planilha com travas de segurança, gera o PDF e o áudio para a rádio, manda o aviso por e-mail com confirmação de recebimento e mostra custo, economia e prazo nos relatórios.

> **Dados desta demonstração:** território, endereços e comunidades são **reais** (IBGE, Censo 2022). A rede elétrica, os clientes, as rádios e o histórico são **fictícios**. Nenhum dado de cliente real foi usado.

## Resultados

Números impressos pelo pipeline (`uv run comunidades --so-algoritmo`), iguais aos do passo 12:

| Métrica (Leopoldina/MG) | Só o cadastro digitado | Norte |
|---|---|---|
| Comunidade correta por UC, zona rural | 56,1% | **91,2%** |
| Comunidade correta por UC, zona urbana | 85,2% | **95,6%** |
| Cobertura média das comunidades atingidas (835 cenários de chave) | – | **88,3%** |
| Precisão média (835 cenários) | – | **95,0%** |
| Duração média do aviso no rádio | 44 s | **14 s** |

Exemplo da tela (chave fictícia CF-0066, 758 UCs): o aviso de hoje cita 120 locais em 358 palavras, cerca de 2 min 23 s no ar.

## O que o Norte faz

1. **Planilha → JSON validado.** A planilha (.xlsx ou .csv) passa por um portão contra arquivos maliciosos. Só as colunas do modelo são lidas (nome, número da casa e conta são descartados na hora). As coordenadas são corrigidas só quando é seguro, e cada linha sai como ok, corrigida ou rejeitada, com o motivo. Uma rotina independente relê o arquivo e confere os números.
2. **Conferência humana.** Números, mapa com as corrigidas em roxo, alerta vermelho para equipamento vital com problema (bloqueia), amarelo para pontos suspeitos, justificativa quando as rejeições passam do limite e a caixa "Conferi os números e o mapa". Sem isso, nada é gerado.
3. **Aviso por comunidade.** Algoritmo de comunidades sobre a base do IBGE. A mensagem sai pelo modelo editável da empresa, com o tipo de desligamento como motivo.
4. **Rádio.** O Norte sugere as rádios pelas comunidades afetadas e avisa as que ficam "sem rádio cadastrada". O valor do envio fica gravado, junto com a economia, calculada (por minuto no ar) ou informada. O e-mail leva PDF e MP3 (voz sintetizada no próprio servidor) e o botão "Confirmar recebimento". Também há WhatsApp e cópia.
5. **Auditoria e relatórios.** Toda ação fica registrada com o nome e o perfil de quem fez, numa corrente de hashes que não pode ser editada nem apagada. Há o relatório do período, o comprovante do aviso, a auditoria da empresa e a geral de acessos, em PDF e CSV com código de verificação.

## Perfis

| Perfil | O que faz | Menu |
|---|---|---|
| Admin do Norte | Cadastra e suspende empresas; vê a auditoria geral de acessos de todas as empresas | Empresas, Auditoria geral |
| Admin da empresa | Tudo do Operador, mais usuários da empresa, rádios (só ele cadastra, edita, desativa e define o valor padrão; atende ou recusa os pedidos de rádio), configurações (modelo da mensagem, limite de rejeição, fuso UTM, antecedência) e o relatório de auditoria | Novo aviso, Histórico, Relatórios, Usuários, Rádios, Configurações, Auditoria |
| Operador | Importa e confere a planilha, gera o aviso, baixa PDF e MP3, envia à rádio escolhida da lista informando o valor daquele envio, baixa o JSON com UCs (registrado) e, se faltar rádio, pede o cadastro ao Admin da empresa | Novo aviso, Histórico, Relatórios |
| Consulta | Vê o mapa, o histórico, os comprovantes e os relatórios; não gera nem envia | Mapa, Histórico, Relatórios |

A permissão é conferida **no servidor** em toda rota. O teste `testes/api/teste_matriz.py` percorre cada rota com cada perfil, e uma rota nova sem regra faz o teste falhar. Ninguém vê dados de outra empresa.

## Como rodar no Windows (passo a passo)

**Pré-requisitos:** [Git](https://git-scm.com/downloads), [uv](https://docs.astral.sh/uv/) (instala o Python certo sozinho), PostgreSQL 17 com PostGIS 3.6 (instalador da EDB + Stack Builder) e Node.js 22 com Edge ou Chrome (só para os testes de tela).

```powershell
# 1. uv (feche e abra o terminal depois)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. código e dependências
git clone <URL-DO-REPOSITORIO>; cd <pasta>
uv sync

# 3. banco: como superusuário, crie o banco fazendadb, a extensão postgis e um usuário do app sem privilégios de admin
#    (farol_app: só conecta, cria esquemas e tabelas). Depois, o arquivo .env na raiz (o git ignora):
#      DATABASE_URL=postgresql://farol_app:SENHA@127.0.0.1:5432/fazendadb
#      FAROL_CHAVE_PACOTE=<48+ caracteres aleatórios>
#      FAROL_CHAVE_ARQUIVOS=<saída de: uv run python -c "from comunidades import cofre; print(cofre.nova_chave())">
#      FAROL_URL_PUBLICA=http://127.0.0.1:8000
#      FAROL_SMTP_HOST=127.0.0.1
#      FAROL_SMTP_PORTA=1025
#      FAROL_SMTP_SEGURANCA=nenhuma

# 4. dados (primeira vez: baixa ~110 MB do IBGE)
uv run comunidades                        # Leopoldina: base, rede e clientes fictícios, algoritmo e mapa estático
uv run python -m comunidades.base_concessao   # base territorial dos 66 municípios da concessão no banco
uv run python -m comunidades.rede_concessao   # rede fictícia no banco (demonstração)

# 5. acesso e histórico de demonstração (as senhas temporárias aparecem uma vez)
uv run python -m comunidades.semente
uv run python -m comunidades.semente_demo

# 6. caixa de e-mail de teste (Mailpit, em outro terminal; caixa em http://127.0.0.1:8025)
data\raw\mailpit\mailpit.exe --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025

# 7. o app
uv run uvicorn comunidades.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
# abra http://127.0.0.1:8000 e entre com um dos usuários da semente
```

- **Só ver o mapa estático de demonstração:** abra `saida/mapa_comunidades.html` (ou `#CF-0066` no fim do endereço).
- **Planilhas de demonstração:** `testes/planilha/exemplos/demo/` (correta, coordenadas corrigidas, equipamento vital rejeitado, muitas rejeições e maliciosa). O roteiro de 5 minutos está em [docs/DEMO.md](docs/DEMO.md).
- **Todos os testes, com tabela no fim:** `powershell -ExecutionPolicy Bypass -File testes\rodar_testes.ps1` (`-Rapido` pula o navegador e o algoritmo).
- **Produção (Render + Neon):** [DEPLOY.md](DEPLOY.md).

## Idiomas

- **Aviso** em português, inglês e espanhol: o idioma se escolhe no passo 2 do Novo aviso (padrão: o da empresa, nas Configurações). A mensagem da rádio tem um modelo por idioma, editável pelo Admin da empresa com a prévia; data e horário no formato de cada idioma ("November 20, from 8 a.m. to 2 p.m."; "el 20 de noviembre, entre las 8:00 y las 14:00"). O português ficou idêntico ao de antes.
- **PDF da rádio, e-mail para a rádio, página de confirmação e comprovante** no idioma do aviso; o idioma fica gravado no aviso e aparece no histórico.
- **Áudio**: português (pt_BR-faber) e inglês (en_US-ljspeech, domínio público). **Espanhol sem áudio**: nenhuma voz em espanhol com licença clara (ver ORIGEM.md); a tela avisa.
- **Telas** em 3 idiomas (seletor no topo, também na tela de entrar; guardado no perfil do usuário): textos em `apresentacao/app/textos.js`, números, datas e moeda pelo `Intl`, `<html lang>` acompanha. Relatórios (tela, PDF, CSV) e mensagens de erro da API no idioma de quem pede.
- Testes: `testes/api/teste_idiomas.py` (34), `testes/navegador/teste_textos.mjs` (nenhum texto sem tradução) e `teste_idiomas_tela.mjs` (cada tela sem português sobrando).

## Acessibilidade

O botão **Acessibilidade** fica no topo de todas as telas, também na de entrar. Ele oferece:

- tamanho do texto até 200%;
- alto contraste;
- fonte Atkinson Hyperlegible;
- mais espaçamento;
- reduzir movimento;
- destacar links e foco;
- guia de leitura;
- modo simples;
- leitura em voz alta pela voz do aparelho.

As escolhas ficam no perfil. Há ainda o link "Pular para o conteúdo" e a Declaração de acessibilidade (WCAG 2.2 AA,
ABNT NBR 17225, LBI art. 63), com o formulário de relato que vai para a auditoria. O axe-core roda em todas as telas, nos
4 perfis, nos 2 temas e nos 3 idiomas. Detalhes e o roteiro de teste manual (NVDA, TalkBack, VoiceOver, teclado e zoom)
estão em [docs/ACESSIBILIDADE.md](docs/ACESSIBILIDADE.md).

## Arquitetura

Camadas, parentes do MVC, que também separam os dados reais dos fictícios:

| MVC | No projeto |
|---|---|
| Model | `nucleo/` (regras puras: tradutor da planilha, travas, mensagem, economia, prazo, auditoria, relatórios, algoritmo), `fontes/` (dados reais) e `simulacao/` (dados fictícios); no JavaScript da tela, o objeto `estado` e as regras puras |
| View | `apresentacao/` (tela do app em `app/`, PDF do roteiro e dos relatórios, e-mail, página de confirmação, mapa estático); no JavaScript, as funções `desenhar*` |
| Controller | `api/` (rotas FastAPI: planilha, aviso, rádio, relatórios, acesso) e `pipeline.py`; no JavaScript, os eventos |
| Dados | `banco/` (Postgres + PostGIS: acesso, auditoria, rádios, envios, relatórios, base territorial) |

O `nucleo/` não lê arquivo nem banco e não conhece o IBGE: recebe dados e devolve resultados, por isso é testado sem servidor.

## Segurança e LGPD (resumo)

A tabela completa "Ameaça → proteção → teste que prova" está em [SEGURANCA.md](SEGURANCA.md).

- **Minimização:** a planilha fica só na memória e é descartada. O banco guarda só agregados (municípios, comunidades, contagens, o aviso). Nenhum número de UC, endereço ou coordenada vai para tela, PDF, MP3, e-mail, relatório ou log. Os pontos do mapa ficam só na memória do navegador, sem o número da UC.
- **Planilha tratada como hostil:** portão por assinatura, limites de zip, sem macro, `defusedxml`, esquema fechado, conta fechada, dupla conferência e erro inesperado sem gerar nada.
- **Acesso:** Argon2id, senha temporária de uso único, bloqueio por tentativas, cookie HttpOnly/SameSite=Strict, permissão no servidor e isolamento por empresa.
- **Auditoria:** só inclusão, encadeada por hash, com o nome de quem fez vindo do login. Código de verificação em avisos e relatórios.
- **Segredos** só em variável de ambiente. Arquivos enviados às rádios ficam cifrados (AES-256-GCM).
- **Antes de dado real:** MFA no login, revisão LGPD (base legal, contrato de operador, registro das operações, prazo de descarte) e revisão de segurança independente.

## Validação

Última bateria completa (`testes/rodar_testes.ps1`, 14/10/2026): **21 de 21 testes passaram**, com 980 verificações. Entre eles:

| Teste | Verificações |
|---|---|
| Tela do app no navegador (4 perfis, tema escuro, celular, 44 px, CSP, nada de UC no HTML) | 108 |
| Coordenadas do tradutor / tradutor (Hypothesis, 50.000 linhas) | 105 / 67 |
| API / acesso / matriz rota x perfil | 77 / 46 / 5 (46 rotas x 4 perfis) |
| Rádio, e-mail no Mailpit, confirmação e cofre | 72 |
| Leitura segura (arquivos maliciosos) / travas e pacote assinado | 51 / 49 |
| Auditoria encadeada / relatórios e prazo | 45 / 44 |
| Varredura de minimização (Leopoldina e Muriaé) | 0 ocorrências |
| Algoritmo (`--so-algoritmo`) | métricas iguais às do passo 12 |

## Próximos passos

- **Mapa estático:** escolher um polígono pronto (comunidade ou distrito) para simular o desligamento e aceitar UTM/GMS na tela de simulação. Ficaram de fora porque o mapa estático tem testes de tela que exigem resultado idêntico ao do passo 12.
- **Mapa do app:** colorir os pontos das UCs por circuito ou transformador. Hoje a conferência mostra o agrupamento em tabela.
- **Prazo:** considerar os feriados nos 5 dias úteis. Hoje conta só segunda a sexta.
- **Antes de dado real:** MFA, revisão LGPD e de segurança, e o modelo oficial de planilha da distribuidora.
- **Rádio:** confirmação de entrega pelo provedor de e-mail. Hoje "entregue" quer dizer que o servidor de e-mail aceitou a mensagem; a rádio confirma pelo link.
- **Municípios do usuário:** hoje informam onde a pessoa atua; ainda não limitam o que ela pode gerar.

## Origem dos dados e licenças

Fontes (IBGE, OpenStreetMap, Esri, KML da Energisa), componentes (Leaflet, IBM Plex, Piper, Mailpit) e dependências, com licenças e hashes, em [ORIGEM.md](ORIGEM.md).
