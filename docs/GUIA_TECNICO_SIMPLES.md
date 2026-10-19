# Norte em uma página (guia técnico simples)

## A ideia em uma frase
Quando a energia vai ser desligada, o app descobre **quais comunidades** são afetadas e escreve um **aviso curto para o rádio**, em vez de listar fazenda por fazenda.

## Como funciona (o caminho do dado)
1. O operador envia uma **planilha** de UCs (unidade consumidora) com latitude e longitude.
2. O sistema vê em que **município** cada ponto cai (malha do IBGE).
3. Um algoritmo diz em que **comunidade** cada ponto cai.
4. O app monta o **aviso**, o **áudio** e o **PDF** para a rádio.
5. Tudo fica no **histórico**, com auditoria de quem fez o quê.

## Tecnologias (o que usamos e para quê)
| Peça | O que usamos | Em uma linha |
|---|---|---|
| Back-end / API | **Python + FastAPI** | Recebe a planilha, aplica as regras e responde ao navegador |
| Banco de dados | **PostgreSQL + PostGIS** | Guarda usuários, avisos e os desenhos (polígonos) das comunidades |
| Hospedagem do banco | **Neon** | Postgres na nuvem (plano grátis) |
| Hospedagem do app | **Render** | Sobe o app sozinho a cada push na `master` do GitHub |
| Telas | **JavaScript puro** (sem framework) | Uma página só, organizada em Model, View e Controller |
| Mapa | **Leaflet** | Biblioteca de mapa em JS; o fundo vem da Esri |
| Áudio do aviso | **Piper** | Voz sintetizada no próprio servidor, sem internet; gera MP3 |
| PDF | **fpdf2** | Gera o PDF para a rádio e os relatórios |

## De onde vêm os dados do mapa
- **IBGE – CNEFE / Censo 2022:** todos os endereços do Brasil. Deles saem as **comunidades** (contorno, nome e tamanho). Agrupamos os endereços e desenhamos cada comunidade.
- **IBGE – Malha de municípios:** diz em que município cada ponto está.
- **IBGE – Localidades oficiais:** 470 lugares nomeados nos 66 municípios. Aparecem como uma **camada opcional** no mapa e servem para **conferir os nomes** das nossas comunidades. Cobrem só ~12% dos endereços, então **não substituem** a base.
- **OpenStreetMap:** as ruas, usadas só para desenhar a rede elétrica fictícia.
- **O que é fictício:** a rede elétrica e os clientes. O resto (território, endereços, comunidades) é real.

## Como as camadas aparecem no mapa
- O mapa é feito em **JavaScript com Leaflet**. O navegador pede os dados à nossa API e **desenha por cima** do mapa-base.
- Cada coisa é uma **camada** com interruptor (comunidades, nomes, rede, clientes, localidades, calor, UCs da planilha). O que o usuário liga ou desliga fica lembrado no navegador.
- Os **contornos** das comunidades vêm do banco (PostGIS). De longe, os clientes aparecem como **densidade** (quadradinhos coloridos); de perto, como **pontos**.
- O mapa só conversa com **a nossa API** e com o servidor do mapa-base.

## O copiloto de IA (e a trava)
- Ajuda o operador a **reescrever o aviso**: mais curto, para WhatsApp, para SMS, tom mais acolhedor, ou um pedido livre.
- **Só o texto do aviso** vai para a IA. Nunca vai planilha, UC, coordenada ou pessoa.
- **A IA não tem a palavra final.** Um verificador em código confere o texto novo contra o original: mesmas comunidades, mesmo município, **mesmos números** (nenhum novo), sem e-mail ou link, dentro do limite do canal (SMS = 320 caracteres). Se reprovar, o texto antigo fica.
- Hoje roda em **modo simulado** (sem chave e sem internet). O modo real usa a API da Anthropic, ainda sem teste com chave real.
- Existe também o **"Pergunte ao painel"**: a IA só **escolhe uma consulta pronta** (por exemplo, "avisos por mês"). Quem calcula é o código, nunca um SQL escrito pela IA.

## Segurança e LGPD (o que perguntam)
- **Login com perfis:** Admin do Norte, Admin da empresa, Operador e Consulta. O **servidor** confere a permissão em toda rota.
- **Senhas:** guardadas com Argon2id (nunca em texto).
- **Planilha:** processada em memória e descartada. O banco guarda só o **resultado**: comunidades e contagens. Nunca número de UC, nome ou endereço.
- **Auditoria:** só inclui, nunca altera. Cada linha tem o **hash da anterior** (encadeada), então adulterar é detectável. Cada aviso tem um **código de verificação** (FRL-XXXX-XXXX-XXXX).
- **Pacote assinado:** entre "Conferir" e "Gerar", a planilha vira um pacote assinado (HMAC) que vale 15 minutos e é preso ao usuário.
- **Segredos:** só em variável de ambiente (`.env`), nunca no código.
- **Ainda falta antes de dados reais de clientes:** MFA no login e revisão LGPD.

## Em resumo (para contar a outra pessoa)
> "É um app web. O back-end é em Python (FastAPI) com Postgres/PostGIS no Neon. O mapa é em JavaScript com Leaflet e usa os dados do IBGE para achar as comunidades afetadas. O operador sobe uma planilha, o sistema gera o aviso, o áudio e o PDF para a rádio, e a IA só ajuda a reescrever o texto, sempre conferida por uma trava em código."

## Perguntas que podem aparecer
- **Por que comunidades e não fazenda por fazenda?** O aviso fica mais curto, então gasta menos tempo no ar (medimos 44 s contra 14 s).
- **Os dados são reais?** O território é real (IBGE). A rede e os clientes são fictícios.
- **A IA pode inventar algo no aviso?** Não passa: o verificador confere comunidades e números contra o original.
- **Onde ficam os dados?** No Postgres (Neon), só o resultado agregado. A planilha não é guardada.
- **E se o nome de uma comunidade estiver errado?** Por isso existem as localidades do IBGE: a conferência de nomes vai para o negócio aprovar antes de mudar o aviso.
