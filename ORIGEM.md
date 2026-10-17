# Origem dos dados, componentes e licenças

Tudo o que o Farol usa e que não foi escrito pelo projeto: de onde vem, com que licença e como é conferido.
Os hashes foram calculados em 14/10/2026 (SHA-256, salvo onde está escrito outro).

## Dados reais (públicos)

| Dado | Fonte | Licença | Como é conferido |
|---|---|---|---|
| Malha de setores censitários 2022 (limites, distritos) | IBGE, `geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/setores/shp/UF/` | Dados públicos do IBGE (uso livre com citação da fonte) | Baixado pelo pipeline (`fontes/dados.py`) para `data/raw/` |
| Localidades 2022 | IBGE, `geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/` | Idem | Idem |
| CNEFE 2022 (endereços, sem nomes de pessoas: o campo que às vezes traz nomes é descartado) | IBGE, `ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/` | Idem | Idem; a base territorial dos 66 municípios da concessão vai para o Postgres (`base_concessao.py`) |
| Malhas de UFs e municípios (página de entrada) | API de malhas do IBGE (`servicodados.ibge.gov.br`) | Idem | Baixadas na geração da página, nunca pelo navegador |
| Vias (base da rede fictícia) | OpenStreetMap (OSMnx; extrato do Sudeste da Geofabrik, `download.geofabrik.de/south-america/brazil/sudeste-latest.osm.pbf`) | ODbL 1.0 (© colaboradores do OpenStreetMap; crédito no mapa enquanto a rede aparece) | O extrato da Geofabrik é conferido pelo MD5 publicado ao lado (`fontes/osm_regiao.py`) |
| Área de concessão EMG | KML da Energisa, `distribuidoras/concessao/EMG.kml` (só a geometria é lida) | Documento público da distribuidora | SHA-256 `28f4f083194ba7f58772ee7c702fc40b9ae017488296f009e7cddc36ee658c92` |
| Fundos de mapa | Esri World Light/Dark Gray Canvas (`server.arcgisonline.com`) | Termos de uso da Esri (crédito "Fundo © Esri" no mapa) | Só imagens; a CSP libera só este servidor |

## Dados fictícios (gerados pelo projeto)

| Dado | Onde | Observação |
|---|---|---|
| Rede elétrica (subestação, alimentadores, chaves, transformadores) | `simulacao/rede.py` | Traçada sobre as vias reais; não é a rede da distribuidora |
| Clientes (titular, UC, localidade digitada com ruído) | `simulacao/clientes.py` | Inventados |
| Planilhas de teste por chave | `simulacao/planilhas_teste.py` (`saida/planilhas_teste/`) | UCs fictícias a jusante de uma chave |
| Planilhas de demonstração | `simulacao/planilhas_demo.py` (`testes/planilha/exemplos/demo/`), reprodutíveis byte a byte | SHA-256: `1_correta` f3e0b198…9049, `2_coordenadas_corrigidas` 136e6d58…0737, `3_vital_rejeitado` dc45b304…f54a, `4_muitas_rejeicoes` 6c408284…8664, `5_maliciosa_macro` f98d7c7f…09f4 |
| Histórico de demonstração (avisos, rádios, envios) | `semente_demo.py` | Rádios com e-mail `@example.com` e WhatsApp fictício |
| Usuários de demonstração | `semente.py` | E-mails do domínio reservado `.example`; senhas temporárias geradas na hora, nunca no código |

## Componentes embutidos na tela (sem CDN)

| Componente | Versão e origem | Licença | Integridade |
|---|---|---|---|
| Leaflet | 1.9.4, `registry.npmjs.org/leaflet/-/leaflet-1.9.4.tgz` | BSD 2-Clause | Pacote `sha512-nxS1ynzJOmOlHp+iL3FyWqK89GtNL8U8rvlMOsQdTTssxZwCXh8N2NB3GDQOL+YR3XnWyZAxwQixURb+FA74PA==`; arquivos em `apresentacao/vendor/leaflet/ORIGEM.md` |
| IBM Plex Sans e Mono | 5.3.0 (Fontsource, npm) | SIL OFL 1.1 | Pacotes e arquivos em `apresentacao/vendor/ibm-plex/ORIGEM.md` |
| Atkinson Hyperlegible | 5.2.8 (Fontsource, npm) | SIL OFL 1.1 | Fonte de leitura facilitada do painel Acessibilidade; pacote e SHA-256 em `apresentacao/vendor/atkinson/ORIGEM.md` |
| axe-core (só nos testes) | 4.10.2 (npm, `testes/navegador/package.json`) | MPL-2.0 | Não vai para a tela nem para o servidor; `axe.min.js` SHA-256 b511cd9d…75e3 |
| Logo do Farol | Desenhado pelo projeto | Do projeto | `farol.svg` 7fed2103…6c03, `farol-pequeno.svg` 2b3b087a…f0f0 |

## Voz do aviso (MP3)

| Componente | Origem | Licença | Integridade |
|---|---|---|---|
| Piper (síntese de voz, no próprio servidor) | `piper-tts` 1.8.0 (PyPI) | GPL-3.0 (roda só no servidor do Farol; se o Farol for distribuído, o jurídico avalia) | Versão fixada no `uv.lock` |
| Voz pt_BR-faber-medium (padrão; também cadu e jeff) | `huggingface.co/rhasspy/piper-voices` | Dados de treino CC0 (ver o MODEL_CARD de cada voz no repositório) | Baixada uma vez para `data/raw/vozes/` e conferida pelo MD5 do catálogo do Piper (`apresentacao/audio.py`); SHA-256 do `.onnx` local: `858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7` |
| Voz en_US-ljspeech-medium (inglês, Fase K) | `huggingface.co/rhasspy/piper-voices` (`en/en_US/ljspeech/medium`) | MODEL_CARD: dados LJ Speech em **domínio público**; treinada do zero (sem base de terceiros) | Baixada uma vez para `data/raw/vozes/` e conferida pelo MD5 do catálogo do Piper: `.onnx` MD5 `109d552e9dd78d92d1169a7edd6de38d`, SHA-256 `6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22`; `.onnx.json` MD5 `0668112b8b3ac5bb4b12c2b1a366776a`, SHA-256 `141d612cc0a95ed7efc1ca936b845c2364967f2e9217c5dbfcf69fc4d6c65860` |
| Voz em espanhol: **nenhuma** (Fase K) | — | As vozes em espanhol do repositório (davefx, sharvard, ald, daniela) são ajustes da voz "lessac", cujos dados (Blizzard 2013, Lessac Technologies) têm licença **só de pesquisa**; a es_MX-claude não diz de onde partiu. Por segurança, o espanhol sai sem áudio e a tela avisa. Se a empresa aceitar o mesmo critério da voz em português (o MODEL_CARD da davefx diz dados CC0), basta `FAROL_VOZ_ES=es_ES-davefx-medium` | Atenção: a voz pt_BR-faber também é ajuste da lessac; revisar a licença antes de uso comercial |
| LAME (MP3) | `lameenc` 1.8.4 (PyPI) | LGPL | Versão fixada no `uv.lock` |

## Ferramenta de teste (só local)

| Ferramenta | Origem | Licença | Integridade |
|---|---|---|---|
| Mailpit (caixa de e-mail de teste; nada sai para a internet) | v1.31.3 (27/09/2026), `github.com/axllent/mailpit/releases/download/v1.31.3/mailpit-windows-amd64.zip`, em `data/raw/mailpit/` (fora do git) | MIT | SHA-256 do zip `863e9502d4e0f14a78c0f91c5091797b1c7b7b7e3fc7e5eab62e5770ce44b76e`, igual ao publicado pelo GitHub |

## Dependências Python principais

Todas com a versão fixada no `uv.lock` (instaladas pelo `uv sync`). As que entraram no plano final foram conferidas no OSV (`api.osv.dev`) em 14/10/2026, sem vulnerabilidade aberta.

| Pacote | Versão | Licença | Para quê |
|---|---|---|---|
| fastapi | 0.143.0 | MIT | API |
| uvicorn | 0.54.0 | BSD-3-Clause | Servidor da API |
| pydantic | 2.14.1 | MIT | Esquema fechado do JSON da planilha e dos pedidos |
| psycopg | 3.3.6 | LGPL-3.0 | Postgres |
| argon2-cffi | 25.1.0 | MIT | Hash das senhas (Argon2id) |
| defusedxml | 0.7.1 | PSF | Leitura segura do XML do .xlsx |
| openpyxl | 3.1.5 | MIT | Leitura do .xlsx (só leitura, sem fórmulas) |
| geopandas / shapely | 1.2.0 / 2.1.2 | BSD-3-Clause | Geometria |
| fpdf2 (novo) | 2.8.9 | LGPL-3.0 | PDF do roteiro e dos relatórios, no servidor |
| cryptography (novo) | 50.0.2 | Apache-2.0 / BSD | AES-256-GCM dos arquivos enviados às rádios |
| fonttools, pillow (dependências do fpdf2) | 4.66.1, 12.3.0 | MIT, MIT-CMU | — |
| hypothesis, coverage (só testes) | ver `uv.lock` | MPL-2.0, Apache-2.0 | Testes de tortura e cobertura do tradutor |
