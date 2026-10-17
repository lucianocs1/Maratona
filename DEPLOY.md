# Deploy do Farol (Render + Neon, planos gratuitos)

O app roda em produção igual à máquina local: a mesma API (FastAPI) e a mesma tela, num container
Docker no Render, com o banco Postgres + PostGIS no Neon. Diferenças em produção:

- **Sem o áudio do aviso** (`FAROL_AUDIO=0`): no plano gratuito do Render (512 MB) não cabe a voz, que
  pede cerca de 520 MB a mais. A tela esconde Ouvir e Baixar áudio; o PDF e o resto funcionam.
- **Só HTTPS** (`FAROL_PRODUCAO=1`): cookie de sessão `Secure`, HSTS e sem a documentação interativa (`/api/docs`).
- O serviço gratuito **dorme** depois de um tempo sem uso; o primeiro acesso depois disso leva cerca de um minuto.
- Rede elétrica e clientes continuam **fictícios**. Antes de dado real da distribuidora: login com MFA,
  usuário próprio do banco e a avaliação da LGPD sobre onde os dados ficam (art. 33, transferência internacional).

## 1. Banco no Neon (uma vez)

1. Entre em https://neon.tech (dá para entrar com o GitHub) e crie um projeto: nome `farol`,
   Postgres 17 e, se houver, a região **AWS South America (São Paulo)**.
2. No painel do projeto, **Connect**: copie a *connection string* (`postgresql://...sslmode=require`).
3. Na raiz do projeto, crie o arquivo `.env.producao` (o git ignora) com uma linha:
   `DATABASE_URL=postgresql://...` (a string copiada). Nunca no código nem no git.
4. Leve a base pública (municípios, comunidades, endereços de referência e a rede fictícia) do banco local:
   `uv run python -m comunidades.publicar_banco`
5. Crie o acesso de produção (empresa EMG de demonstração e um usuário de cada perfil, com senha temporária
   mostrada uma vez):
   `$env:FAROL_ENV=".env.producao"; uv run python -m comunidades.semente`
   Guarde as senhas temporárias: no primeiro acesso cada usuário cria a própria.

## 2. Serviço no Render (uma vez)

1. Em https://dashboard.render.com: **New** > **Blueprint**.
2. Conecte o GitHub e escolha o repositório `lucianocs1/Maratona`. O Render lê o `render.yaml`
   (serviço `farol`, Docker, plano free, branch `master`).
3. Ele pede o valor de `DATABASE_URL`: cole a mesma string do Neon. Confirme (**Apply**).
4. O primeiro build leva alguns minutos. Quando ficar *Live*, abra o endereço que o Render mostra
   (`https://farol-....onrender.com`) e entre com um dos usuários da semente.

## 3. Depois

- **Código novo:** `git push luciano melhorias:master` (ou o que estiver na `master`): o Render refaz o deploy sozinho.
- **Base territorial ou rede refeitas** (base_concessao, rede_concessao): rode de novo o passo 1.4.
- **Senha perdida:** `$env:FAROL_ENV=".env.producao"; uv run python -m comunidades.semente --nova-senha EMAIL`.
- **Saúde:** `https://farol-....onrender.com/api/saude` mostra quantos municípios o banco tem (66).

## 4. Variáveis do plano final (desde 14/10/2026)

O `render.yaml` já declara todas; nenhum valor vai para o git.

| Variável | O que é | Como preencher no Render |
|---|---|---|
| `FAROL_CHAVE_PACOTE` | Chave HMAC do pacote da conferência da planilha | Gerada pelo Render (`generateValue`); não mexa |
| `FAROL_CHAVE_ARQUIVOS` | Chave AES-256-GCM dos PDF e MP3 enviados às rádios | Gerada pelo Render; **não troque depois**: os arquivos já guardados deixariam de abrir |
| `FAROL_URL_PUBLICA` | Endereço público do Farol, para o link "Confirmar recebimento" do e-mail | `https://farol-....onrender.com` |
| `FAROL_SMTP_HOST`, `_PORTA`, `_USUARIO`, `_SENHA`, `_REMETENTE` (e `FAROL_SMTP_SEGURANCA`: starttls, ssl ou nenhuma) | Servidor de e-mail para mandar o aviso às rádios | Do provedor de e-mail da empresa; sem `FAROL_SMTP_HOST`, o envio por e-mail fica desligado (WhatsApp e cópia continuam) |

- O banco ganha as tabelas novas (auditoria encadeada, rádios, configuração da empresa, envios e arquivos cifrados) ao rodar a semente (passo 1.5), que pode rodar de novo.
- **Fase H** (relatórios completos): depois do deploy, rode a semente de novo no banco de produção para criar as colunas de orçamento, alerta de preço e repetição em `empresa_config` e a tabela `relatorio_via` (segunda via dos relatórios, cifrada com a mesma `FAROL_CHAVE_ARQUIVOS`); sem a chave, o PDF de relatório não é gerado (503). O usuário do app precisa de `SELECT` e `INSERT` em `relatorio_via`.
- **Mapa das empresas e área de atuação** (15/10/2026): carregue os municípios do Brasil no banco local (`uv run python -m comunidades.municipios_brasil`, uma vez) e publique a base (`uv run python -m comunidades.publicar_banco`, que agora leva também `municipio_ibge`). Depois rode a semente no banco de produção (com o dono do banco): ela cria `empresa_municipio` e a coluna `empresa.criada_por` e dá à EMG a área que já existia. O usuário do app precisa de `SELECT`, `INSERT` e `DELETE` em `empresa_municipio` e de `SELECT` em `municipio_ibge`. Sem área cadastrada, uma empresa não gera aviso.
- **Clientes fictícios** (17/10/2026): gere no banco local (`uv run python -m comunidades.clientes_concessao`, depois do `base_concessao` e do `rede_concessao`) e publique a base (`uv run python -m comunidades.publicar_banco`, que agora leva também `cliente_ficticio`, cerca de 590 mil linhas e 81 MB com o índice espacial). Confira o espaço livre no Neon antes: o banco local foi de 149 MB para 230 MB com os clientes, e o plano gratuito tem 512 MB. Depois rode a semente no banco de produção; o usuário do app precisa de `SELECT` em `cliente_ficticio`.
- **Localidades oficiais** (17/10/2026): gere no banco local (`uv run python -m comunidades.localidades_oficiais`, depois do `base_concessao`) e publique a base (`uv run python -m comunidades.publicar_banco`, que agora leva também `localidade_oficial`, 470 linhas, desprezível no espaço). O usuário do app precisa de `SELECT` em `localidade_oficial`.
- **Histórico de demonstração** para os relatórios (avisos, rádios e envios fictícios, uma vez só):
  `$env:FAROL_ENV=".env.producao"; uv run python -m comunidades.semente_demo` (precisa de `data/sintetico/` na máquina local). Roda as duas sementes: o mês e meio recente e o ano (de janeiro até ali), cada uma uma vez só.
- No banco de produção, o usuário do app deve poder só `SELECT` e `INSERT` na tabela `registro` (sem `UPDATE`, `DELETE` nem `TRUNCATE`), além dos gatilhos que já recusam essas operações.

- **E-mail só para domínios de teste** (15/10/2026): enquanto o Farol usa dados fictícios, deixe `FAROL_EMAIL_REAL` sem valor: o servidor só envia para domínios reservados (.example etc.) e recusa os outros antes de conectar ao SMTP. Só ligue (`FAROL_EMAIL_REAL=1`) quando entrarem dados e destinatários reais, depois da revisão LGPD.
