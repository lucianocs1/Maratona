'use strict';
// Norte: tela do aviso de desligamento. Entrar, enviar a planilha, ver os municípios e as
// comunidades no mapa, gerar o roteiro (PDF) para a rádio, consultar o histórico e administrar
// usuários e empresas, conforme o perfil. Só fala com a própria API; quem decide o que cada perfil
// pode é o servidor (a tela só esconde o que não serve ao perfil).
// Organização: Model (estado e regras puras), View (desenha a partir do estado) e Controller (eventos).

// ======================= Model: estado da tela e regras puras (não toca no HTML) =======================
// Idioma da tela (Fase K): a chave é o próprio texto em português; textos.js traz o inglês e o espanhol.
// Partes variáveis entre chaves: t('Planilha: {nome}', { nome }). Sem tradução, fica o português.
let IDIOMA = 'pt-BR';
const IDIOMAS_TELA = ['pt-BR', 'en', 'es'];
function t(chave, v = {}) {
  const texto = IDIOMA === 'pt-BR' ? chave : (TEXTOS[IDIOMA]?.[chave] ?? chave);
  return texto.replace(/\{(\w+)\}/g, (m, k) => (k in v ? String(v[k]) : m));
}

const estado = {
  usuario: null,           // /api/eu (perfil, empresa, ações permitidas)
  tela: 'carregando',      // carregando | entrar | senha | app
  vista: 'aviso',          // aviso | historico | painel | usuarios | empresas | registro
  passo: 1,                // funil do novo aviso: 1 planilha, 2 quando, 3 escolher quem será desligado, 4 conferir, 5 avisos
  leitura: null,           // resposta de /api/planilha: a base para escolher (linha a linha, sem a UC) e o pacote "base"
  selecao: null,           // a escolha de quem será desligado (passo 3): modo, filtros, comunidades, áreas, inativas
  chaveConferida: null,    // o critério da conferência que está na tela (mudou a escolha: confere de novo)
  sel: null,               // as linhas escolhidas (1 por linha da base), refeitas a cada mudança da escolha
  arquivoLido: null, abaLida: null, formularioLido: null,   // de que arquivo, aba e formulário é a leitura (para não ler de novo)
  config: null, concessao: null,
  arquivo: null, enviando: false,
  mensagem: '', erro: false,
  resultado: null,         // resposta de /api/planilha (conferência), de /api/avisos (gerado) ou um aviso do histórico
  conferi: false,          // a caixa "Conferi os números e o mapa" do passo 3
  radios: [],              // rádios da empresa (para o envio), com o valor sugerido
  sugestao: {},            // codigo_ibge -> { radios: [{ radio_id, comunidades, municipio_inteiro }], sem_radio: [...] }
  envios: [],              // envios do aviso aberto (e-mail, WhatsApp, cópia), com valor, economia e situação
  escolha: {},             // codigo_ibge -> { radioId, valor, cobranca, antigo, nova: {...} }: o formulário de envio
  justificativa: '',       // obrigatória quando as rejeitadas passam do limite da empresa
  abas: [], aba: '',       // quando mais de uma aba da planilha serve, a escolhida
  origem: null,            // 'novo' | 'historico'
  avisos: {},              // codigo_ibge -> texto do aviso (editável)
  finais: {},              // codigo_ibge -> texto final já guardado no histórico
  ia: {},                  // codigo_ibge -> { verificado, motivos, provedor, pedindo }: o último pedido ao copiloto de IA
  territorios: {},         // codigo_ibge -> GeoJSON das comunidades
  audios: {},              // codigo_ibge -> { texto, url (blob local), segundos }: o MP3 do texto atual
  audiosHoje: {},          // codigo_ibge -> { url, segundos }: o MP3 do aviso de hoje (comparativo)
  mapaEmpresas: null,      // Admin do Norte: empresas, áreas (códigos), contornos e sobreposição (só cadastro e contagens)
  empresasOcultas: new Set(), legendaEmpresasAberta: true, fichaEmpresa: null,
  area: null,              // editor da área de atuação: { empresaId, sigla, codigos: Set, uf, busca, resumo }
  municipiosIbge: null, ufGeo: null,
  a11y: { texto: 100, contraste: false, dislexia: false, espacamento: false, movimento: false, links: false, guia: false, simples: false },
  painelA11y: false, lendo: false,
  painelAmplo: false,      // "Ampliar painel": o painel com ~60% da tela (preferência do usuário)
  menuAberto: false,       // celular e tablet: o menu das seções aberto pelo botão "Menu"
  verUcs: true,            // camada dos pontos das UCs (só logo depois do envio; o histórico não tem pontos)
  verRede: true,           // rede elétrica FICTÍCIA (demonstração), de perto; o botão esconde
  evidencia: null,         // comunidade clicada no mapa: { chave } (borda branca e nome em destaque); clicar de novo ou no mapa tira
  legendaMinimizada: false, // lembrada neste navegador (só conveniência)
  redes: {},               // codigo_ibge -> rede fictícia do município (null: sem rede no banco)
  formulario: null,        // { data: '20/11', dataLonga: '20/11/2026', horario: '8h às 14h', idioma: 'pt-BR' }
  historico: [], usuarios: [], perfis: {}, empresas: [], registro: [],
  filtroHistorico: { busca: '', periodo: '' },
  radio: null,             // { preco, veiculacoes }: o preço do spot e as veiculações (começam na configuração; o operador pode mudar)
  pergunta: null,          // "Pergunte ao painel": { pedindo } | { resposta } | { erro }
  painel: null,            // /api/painel: números do histórico da empresa (e o bloco do mês)
  radiosAdmin: [],         // rádios da empresa (Admin da empresa), com as inativas
  radioEditando: null,     // a rádio no formulário (null: nova)
  alcanceComunidades: [],  // comunidades escolhidas no formulário da rádio: { municipio, nome, distrito }
  configuracao: null,      // /api/empresa/configuracao
  relatorio: null,         // /api/relatorios/{tipo}: o documento do relatório (o mesmo do PDF) com os filtros
  simulador: null,         // /api/relatorios/simulador: o documento do simulador de economia, os valores e se pode editar
  opcoesRelatorio: null,   // municípios, tipos, rádios e pessoas do ano (do relatório mensal), para os filtros
  vias: [],                // segundas vias dos relatórios em PDF (só título, quem, quando e código)
  ficha: null,             // ficha da comunidade clicada no mapa (só contagens)
  calor: null,             // mapa de calor: desligamentos por comunidade em 12 meses
  pedidos: [],             // pedidos de cadastro de rádio (Admin da empresa: da empresa)
  meusPedidos: [],         // os pedidos de rádio que o Operador fez
  pedidoAtendendo: null,   // o pedido que o Admin está atendendo (o formulário da rádio vem preenchido)
  empresaEditando: null,   // a empresa no formulário (null: nova)
};

// o menu de cada perfil (a matriz de perfis do plano); quem decide o que pode é o servidor, a tela só mostra o que serve
const MENUS = {
  admin_farol: [['empresas', 'Empresas'], ['registro', 'Auditoria geral']],
  admin_empresa: [['aviso', 'Novo aviso'], ['historico', 'Histórico'], ['relatorios', 'Relatórios'], ['usuarios', 'Usuários'],
    ['radios', 'Rádios'], ['configuracoes', 'Configurações'], ['registro', 'Auditoria']],
  operador: [['aviso', 'Novo aviso'], ['historico', 'Histórico'], ['relatorios', 'Relatórios']],
  consulta: [['painel', 'Mapa'], ['historico', 'Histórico'], ['relatorios', 'Relatórios']],
};
const RELATORIOS = [['painel', 'Painel do mês'], ['relatorios', 'Do período'], ['comparativo', 'Comparativo'], ['simulador', 'Simulador de economia']];
const VISTAS = ['aviso', 'historico', 'painel', 'relatorios', 'comparativo', 'simulador', 'usuarios', 'radios', 'configuracoes', 'empresas', 'registro'];
const pode = acao => !!estado.usuario?.acoes.includes(acao);
const vistasDoPerfil = () => MENUS[estado.usuario?.perfil] || [];
const menuAtual = v => vistasDoPerfil().some(([x]) => x === v) ? v : RELATORIOS.some(([x]) => x === v) ? 'relatorios' : v;

// a ajuda de cada perfil: o caminho, na ordem em que se usa (os textos são chaves do dicionário)
const AJUDA = {
  operador: [
    ['Novo aviso', 'Escolha a planilha das UCs afetadas (.xlsx ou .csv, até 10 MB) e, no passo 2, a data, o horário e o tipo do desligamento.'],
    ['Conferir', 'O Norte lê a planilha, corrige o que é seguro corrigir (em roxo no mapa) e mostra os números. Vermelho bloqueia (equipamento vital com problema); amarelo pede atenção. Marque "Conferi os números e o mapa" e gere o aviso.'],
    ['Avisos', 'Ajuste a mensagem da rádio, ouça, baixe o PDF e envie à rádio da lista (e-mail com confirmação, WhatsApp ou cópia), informando o valor daquele envio. Se faltar a rádio, use "Pedir cadastro de rádio": o Admin da empresa cadastra.'],
    ['Histórico e relatórios', 'No histórico ficam os avisos, os envios e os comprovantes; mude a data ou cancele quando preciso. Os relatórios mostram custo, economia e prazo do mês.'],
  ],
  consulta: [
    ['Mapa', 'Os municípios pintados pela quantidade de avisos e os próximos desligamentos.'],
    ['Histórico', 'Abra um aviso para ver as comunidades, a mensagem, quem pediu e os envios; baixe o comprovante.'],
    ['Relatórios', 'Os números do mês, por rádio e por comunidade, em PDF ou CSV com o código de verificação.'],
  ],
  admin_farol: [
    ['Empresas', 'Cadastre a empresa com o primeiro admin (a senha temporária aparece uma vez) e suspenda ou reative quando preciso.'],
    ['Auditoria geral', 'Os acessos de todas as empresas, com a conferência da integridade da corrente.'],
  ],
};
AJUDA.admin_empresa = [...AJUDA.operador,
  ['Usuários', 'Convide pessoas da empresa (só e-mail do domínio), escolha o perfil e os municípios; bloqueie quando sair. O último admin não pode ser bloqueado.'],
  ['Rádios e configurações', 'Só você cadastra as rádios, o que cada uma alcança e o valor padrão; desative ou reative pela lista. Em "Pedidos de rádio", atenda (o cadastro abre preenchido) ou recuse com o motivo o que o Operador pediu. Ajuste o modelo da mensagem, o telefone, o limite de rejeição, o fuso UTM e a antecedência.'],
  ['Auditoria', 'Tudo o que cada pessoa fez, com o nome e o perfil, sem nada apagado; baixe o relatório de auditoria.']];

// os termos que confundem: um "?" ao lado mostra a explicação
const DICAS = {
  uc: 'UC (unidade consumidora): cada ligação de energia (uma casa, um sítio, um comércio). A planilha traz uma linha por UC; o número nunca aparece na tela.',
  vital: 'Equipamento vital: alguém na UC depende de aparelho elétrico para viver. O aviso precisa de 5 dias úteis de antecedência (REN 1.000/2021, art. 436), e qualquer problema nessas linhas bloqueia o aviso.',
  corrigida: 'Corrigida: latitude e longitude vieram trocadas ou sem o sinal; o Norte corrigiu só porque o ponto corrigido cai na área de concessão. Fica em roxo no mapa.',
  rejeitada: 'Rejeitada: a linha não entra no aviso (sem UC, sem coordenada, fora da concessão, UC repetida…). O motivo aparece pela linha, sem a UC.',
  limite: 'Limite de rejeição: se mais linhas que o limite da empresa (padrão 2%) forem rejeitadas, o aviso só sai com uma justificativa, que fica na auditoria.',
  vizinha: 'Localidade vizinha: um pedaço pequeno de outra comunidade ficou na área; o aviso cita "localidades vizinhas" em vez de nomear uma por uma.',
  codigo: 'Código de verificação (FRL-…): sai do registro da auditoria que guardou o aviso ou o relatório. Com ele, a empresa confere quem gerou e quando, e que nada foi mudado.',
  economia: 'Economia calculada: pelo tempo no ar (aviso de hoje, fazenda a fazenda, menos a mensagem do Norte) vezes o valor por minuto. Informada: o custo antigo que quem enviou digitou. Sem um dos dois, o Norte não estima.',
};

// a mensagem pelo modelo (a mesma regra de nucleo/mensagem.py), para a prévia nas configurações
function montarMensagem(modelo, v) {
  const valor = c => String(v[c] ?? '').trim();
  return modelo.replace(/\[([^\[\]]*)\]/g, (_, trecho) => [...trecho.matchAll(/\{([^{}]*)\}/g)].some(m => !valor(m[1])) ? '' : trecho)
    .replace(/\{([^{}]*)\}/g, (_, c) => valor(c)).replace(/[ \t]+/g, ' ').replace(/ +([.,;:!?])/g, '$1').trim();
}
const FUSOS_UTM = [[31978, 'UTM 18S'], [31979, 'UTM 19S'], [31980, 'UTM 20S'], [31981, 'UTM 21S'], [31982, 'UTM 22S'], [31983, 'UTM 23S'],
  [31984, 'UTM 24S'], [31985, 'UTM 25S']];
const municipiosDaConcessao = () => (estado.concessao?.features || []).map(f => [f.properties.codigo_ibge, `${f.properties.nome}/${f.properties.uf}`])
  .sort((a, b) => a[1].localeCompare(b[1], IDIOMA));
const nomeMunicipio = cod => municipiosDaConcessao().find(([c]) => c === cod)?.[1] || cod;
const temaAtual = () => document.documentElement.dataset.tema || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');

// números, datas e moeda no formato do idioma da tela (Intl); o valor continua em reais
const fmt = n => Number(n).toLocaleString(IDIOMA);
const dataHora = iso => new Date(iso).toLocaleString(IDIOMA, { dateStyle: 'short', timeStyle: 'short' });

// "08:00" -> "8h", "08:30" -> "8h30" (como o aviso fala)
function horaTexto(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h}h${m ? String(m).padStart(2, '0') : ''}`;
}
// "2026-11-12" -> "12/11"
const dataTexto = iso => { const [, m, d] = iso.split('-'); return `${d}/${m}`; };
const dataLonga = iso => { const [a, m, d] = iso.split('-'); return `${d}/${m}/${a}`; };

function validarArquivo(arquivo) {
  if (!arquivo) return t('Escolha a planilha das UCs afetadas.');
  if (!/\.(csv|xlsx)$/i.test(arquivo.name)) return t('A planilha tem de ser .csv ou .xlsx.');
  if (estado.config && arquivo.size > estado.config.limites.bytes) return t('A planilha passa de 10 MB.');
  return null;
}

// os campos do passo 2 com problema: [[id do campo, texto], ...] (a planilha é conferida à parte, no passo 1)
function validarFormulario({ data, inicio, fim, tipo, tipoOutro }) {
  return [!data && ['data', t('Informe a data do desligamento.')], !inicio && ['inicio', t('Informe o horário de início.')],
    !fim && ['fim', t('Informe o horário de fim.')], inicio && fim && fim <= inicio && ['fim', t('O fim tem de ser depois do início.')],
    tipo === 'outro' && tipoOutro.trim().length < 3 && ['tipoOutro', t('Descreva o motivo do desligamento (de 3 a 200 caracteres).')]].filter(Boolean);
}

// "Solicitado por Fulana (Operador) em 14/10/2026 às 10:32 · código de verificação FRL-…" (o nome vem do login)
function solicitadoTexto(r) {
  if (!r?.id || !r.criado_em) return '';
  const q = new Date(r.criado_em);
  return t('Solicitado por {nome}{perfil} em {data} às {hora}{codigo}', { nome: r.usuario || '—', perfil: r.usuario_perfil ? ` (${t(r.usuario_perfil)})` : '',
    data: q.toLocaleDateString(IDIOMA), hora: q.toLocaleTimeString(IDIOMA, { hour: '2-digit', minute: '2-digit' }),
    codigo: r.codigo ? t(' · código de verificação {codigo}', { codigo: r.codigo }) : '' });
}

// [campo, problema] da senha nova, ou null
function validarSenhaNova(nova, repetida) {
  if (nova.length < 12) return ['senhaNova', t('A senha nova precisa ter pelo menos 12 caracteres.')];
  if (nova !== repetida) return ['senhaNova2', t('As duas senhas novas não são iguais.')];
  return null;
}
const EMAIL = /^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$/i;   // a mesma regra do servidor (nucleo/acesso.py)

// o áudio vale enquanto o texto não muda
const audioAtual = codigo => estado.audios[codigo]?.texto === estado.avisos[codigo] ? estado.audios[codigo] : null;
// o servidor pode estar sem a voz (FAROL_AUDIO=0, em produção no plano gratuito)
const audioLigado = () => estado.config?.audio !== false;
// a voz do idioma do aviso existe? (espanhol: sem voz com licença clara; a tela avisa)
const vozDoIdioma = idioma => (estado.config?.audio_idiomas || ['pt-BR']).includes(idioma);
// gerar o áudio é de quem gera o aviso (Consulta só lê; a API também recusa)
const temAudio = () => audioLigado() && pode('gerar_aviso') && vozDoIdioma(estado.formulario?.idioma || 'pt-BR');

// 754 s -> "12 min 34 s"
// a rádio cobra por inserção (spot) inteira: 100 s em spots de 30 s são 4 spots (as mesmas contas de nucleo/custo.py)
const spotsDe = s => s > 0 ? Math.ceil(s / estado.config.radio.spot_segundos) : 0;
const custoDe = s => Math.round(spotsDe(s) * estado.radio.preco * estado.radio.veiculacoes * 100) / 100;
const temPreco = () => !!estado.radio && estado.radio.preco > 0;
const reais = v => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const rotuloSpots = n => `${fmt(n)} spot${n === 1 ? '' : 's'}`;
const numeroDigitado = (texto, min, max, inteiro) => {
  const n = Number(String(texto).trim().replace(',', '.'));
  return Number.isFinite(n) && n >= min && n <= max && (!inteiro || Number.isInteger(n)) ? n : null;
};
const tempoNoAr = s => s < 60 ? t('{n} s', { n: fmt(s) }) : s % 60 ? t('{min} min {s} s', { min: fmt(Math.floor(s / 60)), s: s % 60 })
  : t('{min} min', { min: fmt(Math.floor(s / 60)) });

const palavras = texto => texto.trim().split(/\s+/).filter(Boolean).length;
const segundos = texto => Math.round(palavras(texto) / (estado.config?.palavras_por_segundo || 2.5));

// como a comunidade entra no aviso: inteira, parte ou localidade vizinha (fragmento)
const situacao = c => c.fragmento ? 'vizinha' : c.parcial ? 'parte' : 'inteira';
const ROTULO = { inteira: 'inteira', parte: 'parte', vizinha: 'localidade vizinha' };   // chaves do dicionário
// homônimos vêm como "Piacatuba (Tebas)"; na tela, o nome sem o sufixo e o distrito uma vez só
// (o distrito com o nome do município é a "Sede", como no aviso)
const semSufixo = nome => nome.replace(/ \(.*\)$/, '');
const distritoTexto = (c, m) => c.distrito === m.nome ? t('Sede') : c.distrito;
const nomeComDistrito = (c, m) => `${semSufixo(c.nome)} (${distritoTexto(c, m)})`;
const homonimo = c => / \(.*\)$/.test(c.nome);

// funil: até onde dá para ir (o 2 pede a planilha; o 3, a planilha lida; o 4, a conferência; o 5, o aviso já gerado)
const temResultadoNovo = () => !!estado.resultado && estado.origem === 'novo';
const gerado = () => temResultadoNovo() && !!estado.resultado.id;
const passoMaximo = () => gerado() ? 5 : temResultadoNovo() ? 4 : estado.leitura ? 3
  : estado.arquivo && !validarArquivo(estado.arquivo) ? 2 : 1;

// o mesmo que o servidor confere antes de gerar (nucleo/travas.problema_para_gerar); a tela só antecipa
const MAX_JUSTIFICATIVA = 300;
function problemaParaGerar() {
  const c = estado.resultado?.conferencia;
  if (!c || !estado.resultado.pacote) return t('Confira a planilha primeiro.');
  if (c.vital_bloqueio.length) return t('Bloqueado: há equipamento vital com problema. Corrija a planilha e importe de novo.');
  const j = estado.justificativa.trim();
  if (c.rejeicao.acima && !j) return t('Mais de {limite} das linhas foram rejeitadas: escreva a justificativa.', { limite: pct(c.rejeicao.limite) });
  if (j.length > MAX_JUSTIFICATIVA) return t('A justificativa pode ter no máximo {n} caracteres.', { n: MAX_JUSTIFICATIVA });
  if (!estado.conferi) return t('Marque "Conferi os números e o mapa" para gerar o aviso.');
  return null;
}
const pct = f => `${(f * 100).toLocaleString(IDIOMA, { maximumFractionDigits: 1 })}%`;

// ---- Escolher quem será desligado (passo 3): a planilha pode ser a base de clientes inteira. A mesma regra de
// nucleo/selecao.py, para o contador ao vivo e o mapa; quem decide é o servidor (/api/planilha/escolha). A base vem
// linha a linha sem a UC (posição, comunidade e os códigos como índices) e fica só na memória, como os pontos ----
const FILTROS = ['circuito', 'conjunto', 'transformador', 'bairro'];
const MAX_MARCAR = 300;            // itens mostrados numa lista de marcar (o resto aparece pela busca)
const MAX_VERTICES_AREA = 20000;   // como nucleo/area.MAX_VERTICES
// planilha com circuito, conjunto, transformador, bairro ou situação: é uma base de clientes, a pessoa escolhe;
// sem essas colunas, já é a lista do desligamento (o comportamento de antes)
const ehBaseDeClientes = b => b.colunas.length > 0;
function novaSelecao(b) {
  return { modo: ehBaseDeClientes(b) ? 'escolha' : 'planilha', filtros: Object.fromEntries(FILTROS.map(f => [f, new Set()])),
    comunidades: new Set(), poligonos: [], incluirInativas: false, buscas: {}, abertos: new Set(), desenho: null };
}
const temFiltroSel = s => FILTROS.some(f => s.filtros[f].size) || s.poligonos.length > 0 || s.comunidades.size > 0;
// ponto no anel (raio cruzando as bordas), a mesma conta de nucleo/abrangencia._no_anel; a área em [lon, lat]
function noAnelArea(lat, lon, anel) {
  let dentro = false;
  for (let i = 0, j = anel.length - 1; i < anel.length; j = i++) {
    const [xi, yi] = anel[i], [xj, yj] = anel[j];
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}
const naArea = (lat, lon, p) => noAnelArea(lat, lon, p[0]) && !p.slice(1).some(b => noAnelArea(lat, lon, b));
function caixaArea(p) {
  const xs = p[0].map(v => v[0]), ys = p[0].map(v => v[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
const verticesArea = polis => polis.reduce((s, p) => s + p.reduce((n, a) => n + a.length - 1, 0), 0);
// as linhas escolhidas (1) da base lida: inativas fora (salvo incluir); na escolha, todos os filtros usados (dentro de
// um filtro, qualquer valor marcado) e o mapa (dentro de uma área ou numa comunidade; vital sem posição entra)
function selecionadas(b, s) {
  const ln = b.linhas, n = b.lidas, sel = new Uint8Array(n);
  if (s.modo === 'escolha' && !temFiltroSel(s)) return sel;
  const marcados = FILTROS.filter(f => s.filtros[f].size), caixas = s.poligonos.map(caixaArea);
  const usaMapa = s.poligonos.length > 0 || s.comunidades.size > 0;
  for (let i = 0; i < n; i++) {
    if (ln.inativa[i] && !s.incluirInativas) continue;
    if (s.modo === 'escolha') {
      if (marcados.some(f => !s.filtros[f].has(ln[f][i]))) continue;
      if (usaMapa) {
        const lat = ln.lat[i], lon = ln.lon[i];
        const dentro = lat !== null && s.poligonos.some((p, k) => {
          const [x0, y0, x1, y1] = caixas[k];
          return x0 <= lon && lon <= x1 && y0 <= lat && lat <= y1 && naArea(lat, lon, p);
        });
        if (!(dentro || s.comunidades.has(ln.com[i]) || ln.vital_sem_posicao[i])) continue;
      }
    }
    sel[i] = 1;
  }
  return sel;
}
// "X de Y UCs selecionadas · Z comunidades" (e as inativas que ficaram fora)
function contaSelecao(b, s, sel) {
  const ln = b.linhas, coms = new Set();
  let x = 0, inativas = 0;
  for (let i = 0; i < b.lidas; i++) {
    if (sel[i]) { x++; if (ln.com[i] >= 0) coms.add(ln.com[i]); }
    else if (ln.inativa[i] && !s.incluirInativas) inativas++;
  }
  return { x, y: b.lidas, z: coms.size, inativas };
}
// o critério que vai ao servidor (os valores, nunca as linhas); o servidor deixa em forma canônica
function criterioDe(b, s) {
  if (s.modo === 'planilha') return { modo: 'planilha', incluir_inativas: s.incluirInativas };
  return { modo: 'escolha', incluir_inativas: s.incluirInativas,
    ...Object.fromEntries(FILTROS.map(f => [f, [...s.filtros[f]].map(i => b.valores[f][i]).sort()])), poligonos: s.poligonos,
    comunidades: [...s.comunidades].sort((a, c) => a - c).map(i => ({ municipio: b.municipios[b.comunidades[i].municipio].codigo_ibge,
      nome: b.comunidades[i].nome })) };
}
const chaveSelecao = (b, s) => JSON.stringify(criterioDe(b, s));
function problemaDaSelecao(s, conta) {
  if (s.desenho) return t('Conclua ou cancele o desenho da área.');
  if (s.modo === 'escolha' && !temFiltroSel(s)) return t('Escolha pelo menos um filtro, uma comunidade ou uma área no mapa.');
  if (!conta.x) return t('Nenhuma UC selecionada: mude a escolha.');
  return null;
}
// a escolha como o histórico guarda (nucleo/selecao.resumo), no idioma da tela: o critério, nunca as UCs
function descreverEscolha(r) {
  if (!r) return '';
  const lista = v => v.slice(0, 8).join(', ') + (v.length > 8 ? ` (+${fmt(v.length - 8)})` : '');
  const partes = r.modo === 'planilha' ? [t('a planilha inteira (lista do desligamento)')] : [];
  if (r.poligonos) partes.push(t('área desenhada ({n} polígono(s), {v} vértices)', { n: fmt(r.poligonos), v: fmt(r.vertices) }));
  if (r.comunidades?.length) partes.push(t('comunidade(s) {lista}', { lista: lista(r.comunidades.map(semSufixo)) }));
  for (const f of FILTROS) if (r[f]?.length) partes.push(t({ circuito: 'circuito(s) {lista}', conjunto: 'conjunto(s) {lista}',
    transformador: 'transformador(es) {lista}', bairro: 'bairro(s) {lista}' }[f], { lista: lista(r[f]) }));
  partes.push(t('{x} UC(s) · {z} comunidade(s)', { x: fmt(r.conta.escolhidas), z: fmt(r.comunidades_no_aviso) }));
  return partes.join(' · ') + (r.incluir_inativas ? ` · ${t('inativas incluídas')}` : '');
}

// o texto da rádio: o final guardado, a mensagem pelo modelo da empresa ou (em outro idioma) o aviso do algoritmo
const textoGerado = m => m.mensagem || m.aviso;
const textoAviso = m => m.texto_final || textoGerado(m);

// custo e economia do envio: a mesma conta do servidor (nucleo/economia.py); nunca inventa número
function reaisNumero(t) {
  const s = String(t ?? '').replace(/R\$|\s/g, '');
  if (!s) return null;
  const n = Number(s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s);
  return Number.isFinite(n) && n >= 0 && n <= 100000 ? Math.round(n * 100) / 100 : NaN;
}
function previaEconomia({ cobranca, valor, segundosFarol, segundosHoje, custoAntigo }) {
  const tempo = segundosHoje == null ? null : segundosHoje - segundosFarol;
  if (cobranca === 'minuto') {
    const custo = Math.round(valor * segundosFarol / 60 * 100) / 100;
    if (segundosHoje != null) return { custo, economia: Math.round((segundosHoje - segundosFarol) * valor / 60 * 100) / 100, tipo: 'calculada', tempo };
    if (custoAntigo != null) return { custo, economia: Math.round((custoAntigo - custo) * 100) / 100, tipo: 'informada', tempo };
    return { custo, economia: null, tipo: null, tempo };
  }
  return { custo: valor, economia: custoAntigo != null ? Math.round((custoAntigo - valor) * 100) / 100 : null,
    tipo: custoAntigo != null ? 'informada' : null, tempo };
}
const dinheiro = v => Number(v).toLocaleString(IDIOMA, { style: 'currency', currency: 'BRL' });
// os últimos 12 meses ("2026-10"), do mais recente ao mais antigo, para os filtros dos relatórios
function ultimosMeses(hoje = new Date()) {
  const saida = [];
  for (let i = 0; i < 12; i++) {
    const d = new Date(hoje.getFullYear(), hoje.getMonth() - i, 1);
    saida.push([`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`, d.toLocaleDateString(IDIOMA, { month: 'long', year: 'numeric' })]);
  }
  return saida;
}
// período do relatório: um mês, um ano ou um intervalo (início e fim)
const periodoRelatorio = () => ({ mes: [['mes', $('relMes').value]], ano: [['ano', $('relAno').value]],
  intervalo: [['inicio', $('relInicio').value], ['fim', $('relFim').value]] })[$('relModo').value] || [];
const filtrosRelatorio = () => Object.fromEntries([...periodoRelatorio(), ['municipio', $('relMunicipio').value], ['tipo', $('relTipo').value],
  ['radio', $('relRadio').value], ['pessoa', $('relPessoa').value]].filter(([, v]) => v));
const TIPOS_RELATORIO = { mensal: 'mes', custos: 'ano', comunidades: 'ano', prazos: 'mes' };   // tipo -> período padrão
const consulta = f => new URLSearchParams(f).toString();
// rótulos fixos: a chave em português, traduzida ao desenhar (t(COBRANCA[x]))
const COBRANCA = { fechado: 'valor fechado pelo aviso', minuto: 'por minuto no ar' };
const CANAL = { email: 'e-mail', whatsapp: 'WhatsApp', copia: 'cópia da mensagem' };
const SITUACAO_ENVIO = { preparando: 'preparando', enviado: 'enviado', entregue: 'entregue ao servidor de e-mail', falhou: 'falhou',
  confirmado: 'a rádio confirmou' };
const tempoArTexto = s => s == null ? '' : s >= 0 ? t('{tempo} a menos no ar', { tempo: tempoNoAr(s) }) : t('{tempo} a mais no ar', { tempo: tempoNoAr(-s) });
function economiaTexto(e, previa = false) {
  const partes = [t('custo {valor}', { valor: dinheiro(e.custo) })];
  const tipo = e.economia_tipo || e.tipo;
  if (e.economia != null) partes.push(tipo === 'informada' ? t('Economia: {valor} em relação ao jeito antigo', { valor: dinheiro(e.economia) })
    : t('Economia: {valor} pelo tempo a menos no ar', { valor: dinheiro(e.economia) }));
  else partes.push(previa ? t('Economia: preencha "Quanto custaria do jeito antigo" para calcular') : t('Economia: sem o custo do jeito antigo'));
  if ((e.tempo_economizado ?? e.tempo) != null) partes.push(tempoArTexto(e.tempo_economizado ?? e.tempo));
  return partes.join(' · ');
}

// histórico: busca por município ou comunidade (sem acento) e período pela data em que foi gerado
const normalizar = t => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
function historicoFiltrado() {
  const { busca, periodo } = estado.filtroHistorico, termo = normalizar(busca.trim());
  const desde = periodo ? Date.now() - Number(periodo) * 86400000 : 0;
  return estado.historico.filter(a => new Date(a.criado_em).getTime() >= desde && (!termo || a.municipios.some(m =>
    normalizar(m.nome).includes(termo) || m.comunidades.some(c => normalizar(semSufixo(c.nome)).includes(termo)))));
}

const MES_CURTO = mes => { const [a, m] = mes.split('-').map(Number);
  return `${new Date(a, m - 1, 1).toLocaleDateString(IDIOMA, { month: 'short' }).replace('.', '')}/${String(a).slice(2)}`; };

function grupos(m) {
  const g = { inteira: [], parte: [], vizinha: [] };
  for (const c of m.comunidades) g[situacao(c)].push(c);
  return g;
}

// um aviso do histórico no mesmo formato da resposta de /api/avisos
function doHistorico(a) {
  const r = a.resumo;
  return {
    id: a.id, aviso_ficticio: estado.config.aviso_ficticio, municipios: a.municipios, prazo: r.prazo,
    planilha: { linhas: r.linhas, validas: r.validas, total_problemas: r.problemas, problemas: [], problemas_por_motivo: {} },
    fora_da_concessao: { ucs: r.fora_da_concessao, linhas: [] },
    criado_em: a.criado_em, usuario: a.usuario, usuario_perfil: a.usuario_perfil, codigo: a.codigo, status: a.status,
    desligamento: a.desligamento, escolha: r.escolha || null,
  };
}

// ======================= View: desenha a partir do estado (não muda o estado) =======================
const $ = id => document.getElementById(id);

// todo texto vindo da API ou da planilha entra como texto, nunca como HTML
function no(tag, props = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'classe') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k === 'estilo') Object.assign(e.style, v);  // pelo CSSOM: a CSP não deixa atributo style
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  e.append(...filhos.flat().filter(f => f !== null && f !== undefined && f !== false));
  return e;
}

function desenharTema() {
  const escuro = temaAtual() === 'escuro';
  $('temaRotulo').textContent = escuro ? t('Tema claro') : t('Tema escuro');
  $('botaoTema').setAttribute('aria-pressed', String(escuro));
}

function desenharAjuda() {
  const passos = AJUDA[estado.usuario?.perfil] || [];
  $('ajudaTitulo').textContent = t('Ajuda · {perfil}', { perfil: t(estado.usuario?.perfil_nome || '') });
  $('ajudaCorpo').replaceChildren(no('ol', { classe: 'passos-ajuda' }, passos.map(([tit, d]) => no('li', {}, no('strong', { texto: t(tit) }), no('span', { texto: ` ${t(d)}` })))),
    no('p', { classe: 'ajuda', texto: t('Os botões "?" ao lado dos termos explicam cada um. Tudo o que você faz fica na auditoria com o seu nome.') }),
    no('p', { classe: 'ajuda', texto: t(estado.config?.aviso_ficticio || '') }));
}

// um "?" ao lado de um termo: o botão (alvo de 44 px) e a explicação em DICAS
const dica = (chave, termo) => no('button', { type: 'button', classe: 'dica', 'data-dica': chave, 'aria-label': t('O que é {termo}?', { termo: t(termo) }), texto: '?' });

function desenharTela() {
  $('telaEntrar').hidden = estado.tela !== 'entrar';
  $('telaSenha').hidden = estado.tela !== 'senha';
  $('telaApp').hidden = estado.tela !== 'app';
  $('conta').hidden = $('contaItens').hidden = !estado.usuario;
  $('itemCalor').hidden = !estado.usuario || !pode('ver_historico');
  desenharMenuConta();
}

// o botão do menu da conta: as iniciais e o primeiro nome (ou só "Menu" antes do login) e o cabeçalho do painel
function desenharMenuConta() {
  const u = estado.usuario, botao = $('botaoConta');
  botao.classList.toggle('com-usuario', !!u);
  if (!u) {
    $('contaRotulo').textContent = t('Menu');
    botao.setAttribute('aria-label', t('Menu'));
    return;
  }
  const partes = u.nome.trim().split(/\s+/).filter(Boolean);
  const iniciais = (partes[0]?.[0] || '') + (partes.length > 1 ? partes[partes.length - 1][0] : '');
  $('contaAvatar').textContent = $('contaAvatarGrande').textContent = iniciais.toUpperCase();
  $('contaRotulo').textContent = partes[0] || u.nome;
  $('contaNome').textContent = `${u.nome} · ${t(u.perfil_nome)}${u.empresa_sigla ? ' · ' + u.empresa_sigla : ''}`;
  botao.setAttribute('aria-label', `${t('Menu')}: ${u.nome}`);
}

// o painel do menu da conta: abre e fecha; setas movem entre os itens; Esc e o clique fora fecham
function alternarMenuConta(aberto = $('menuConta').hidden) {
  $('menuConta').hidden = !aberto;
  $('botaoConta').setAttribute('aria-expanded', String(aberto));
}
const itensDoMenuConta = () => [...$('menuConta').querySelectorAll('button, select')].filter(e => !e.closest('[hidden]') && !e.disabled);
function tecladoDoMenuConta(e) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  const doBotao = e.target === $('botaoConta');
  if (!doBotao && !e.target.closest('#menuConta')) return;
  if (e.target.tagName === 'SELECT') return;   // as setas do seletor de idioma trocam a opção
  e.preventDefault();
  if (doBotao) alternarMenuConta(true);
  const itens = itensDoMenuConta(), i = itens.indexOf(document.activeElement);
  const n = doBotao ? 0 : (i + (e.key === 'ArrowDown' ? 1 : -1) + itens.length) % itens.length;
  itens[n]?.focus();
}

function desenharAbas() {
  const atual = menuAtual(estado.vista);
  // celular e tablet: as seções ficam atrás do botão "Menu", que diz em qual se está
  $('abas').classList.toggle('aberto', estado.menuAberto);
  $('botaoMenu').setAttribute('aria-expanded', String(estado.menuAberto));
  const rotuloAtual = vistasDoPerfil().find(([v]) => v === atual)?.[1];
  $('menuAtual').textContent = rotuloAtual ? `· ${t(rotuloAtual)}` : '';
  $('abas').replaceChildren(...vistasDoPerfil().map(([v, rotulo]) =>
    no('button', { type: 'button', 'data-vista': v, 'aria-current': atual === v ? 'page' : null, texto: t(rotulo) })));
  const noGrupo = RELATORIOS.some(([v]) => v === estado.vista) && pode('ver_historico') && !(estado.usuario?.perfil === 'consulta' && estado.vista === 'painel');
  $('subabas').hidden = !noGrupo;
  $('subabas').replaceChildren(...(noGrupo ? RELATORIOS.map(([v, rotulo]) =>
    no('button', { type: 'button', 'data-vista': v, 'aria-current': estado.vista === v ? 'page' : null, texto: t(rotulo) })) : []));
  for (const v of VISTAS) $(`vista-${v}`).hidden = estado.vista !== v;
  // o resultado aparece só na vista de onde veio (um aviso novo em "Novo aviso", um antigo no "Histórico");
  // no funil, o passo 4 mostra a conferência e o 5, os avisos (o 3 é a escolha de quem será desligado)
  const vistaDoResultado = { novo: 'aviso', historico: 'historico' }[estado.origem];
  const r = $('resultado');
  if (vistaDoResultado && r.parentElement.id !== `lugar-${vistaDoResultado}`) $(`lugar-${vistaDoResultado}`).append(r);
  r.dataset.modo = estado.origem === 'novo' ? `passo${estado.passo}` : 'completo';
  r.hidden = !estado.resultado || estado.vista !== vistaDoResultado || (estado.origem === 'novo' && estado.passo < 4);
  desenharFunil();
}

function desenharFunil() {
  if (estado.passo > passoMaximo()) estado.passo = passoMaximo();
  const n = estado.passo, max = passoMaximo();
  for (const b of $('funil').querySelectorAll('button[data-passo]')) {
    const k = Number(b.dataset.passo);
    b.setAttribute('aria-current', k === n ? 'step' : 'false');
    b.classList.toggle('feito', k < n);
    b.disabled = k > max;
  }
  $('form').hidden = n >= 3;
  $('passo-1').hidden = n !== 1;
  $('passo-2').hidden = n !== 2;
  $('voltar').hidden = n !== 2;
  $('avancar').hidden = n !== 1;
  $('gerar').hidden = n !== 2;
  $('escolha').hidden = n !== 3 || !estado.leitura;
  $('navEscolha').hidden = $('motivoEscolha').hidden = n !== 3 || !estado.leitura;
  $('navResultado').hidden = n < 4 || !temResultadoNovo();
  $('avancarResultado').hidden = n !== 4;
  // passo 4: antes de gerar, o botão gera (se as travas deixarem); depois, só leva aos avisos
  $('avancarResultado').textContent = gerado() ? t('Avançar para os avisos') : estado.enviando ? t('Gerando…') : t('Gerar aviso');
  $('avancarResultado').disabled = !gerado() && (estado.enviando || !!problemaParaGerar());
  const motivo = $('motivoGerar');
  if (motivo) motivo.textContent = n === 4 && !gerado() ? (problemaParaGerar() || t('Tudo conferido: pode gerar o aviso.')) : '';
  $('abaRotulo').hidden = !estado.abas.length;
  $('novoAviso').hidden = n !== 5;
  $('verComparativo').hidden = n !== 5 || !pode('ver_historico');
  $('passo2Arquivo').textContent = estado.arquivo ? t('Planilha: {nome}', { nome: estado.arquivo.name }) : '';
  if (estado.resultado && estado.origem === 'novo') $('tituloResultado').textContent = tituloResultado();
}

function desenharEstado() {
  $('estado').textContent = estado.mensagem;
  $('estado').classList.toggle('erro', estado.erro);
  $('gerar').disabled = estado.enviando;
  $('gerar').textContent = estado.enviando ? t('Gerando…') : t('Conferir a planilha');
  $('arquivoNome').textContent = estado.arquivo
    ? t('{nome} ({kb} KB)', { nome: estado.arquivo.name, kb: fmt(Math.ceil(estado.arquivo.size / 1024)) })
    : t('Escolha ou arraste o arquivo (.csv ou .xlsx, até 10 MB)');
  $('zona').classList.toggle('escolhido', !!estado.arquivo);
  desenharFunil();
}

function mensagemEm(id, texto, erro) {
  $(id).textContent = texto;
  $(id).classList.toggle('erro', !!erro);
}

// ---- Erros nos campos: o erro fica ligado ao campo (aria-invalid + aria-describedby), com um resumo no topo
// do formulário (role="alert") e um link para cada campo; o que foi digitado nunca é apagado ----
function erroNoCampo(campo, texto) {
  const idErro = `${campo.id}-erro`;
  let p = $(idErro);
  if (!p) {
    p = no('p', { id: idErro, classe: 'erro-campo' });
    (campo.closest('label') || campo).after(p);
  }
  p.textContent = texto;
  campo.setAttribute('aria-invalid', 'true');
  const ids = (campo.getAttribute('aria-describedby') || '').split(/\s+/).filter(x => x && x !== idErro);
  campo.setAttribute('aria-describedby', [...ids, idErro].join(' '));
}

function limparErroCampo(campo) {
  if (!campo?.id) return;
  campo.removeAttribute('aria-invalid');
  $(`${campo.id}-erro`)?.remove();
  const ids = (campo.getAttribute('aria-describedby') || '').split(/\s+/).filter(x => x && x !== `${campo.id}-erro`);
  if (ids.length) campo.setAttribute('aria-describedby', ids.join(' ')); else campo.removeAttribute('aria-describedby');
  const resumo = campo.closest('form, .com-erros')?.querySelector(':scope > .resumo-erros');
  resumo?.querySelector(`a[href="#${CSS.escape(campo.id)}"]`)?.closest('li')?.remove();
  if (resumo && !resumo.querySelector('li')) resumo.remove();
}

function limparErros(lugar) {
  for (const c of lugar.querySelectorAll('[aria-invalid="true"]')) limparErroCampo(c);
  lugar.querySelector(':scope > .resumo-erros')?.remove();
}

// erros: [[id do campo, texto], ...]; o foco vai para o resumo (o leitor de tela lê) ou, com um erro só, para o campo
function mostrarErros(lugar, erros) {
  limparErros(lugar);
  const validos = erros.filter(([id]) => $(id));
  if (!validos.length) return false;
  for (const [id, texto] of validos) erroNoCampo($(id), texto);
  lugar.classList.add('com-erros');
  const resumo = no('div', { classe: 'resumo-erros', role: 'alert', tabindex: '-1' },
    no('p', { texto: validos.length === 1 ? t('Corrija o campo abaixo:') : t('Corrija os {n} campos abaixo:', { n: validos.length }) }),
    no('ul', {}, validos.map(([id, texto]) => no('li', {}, no('a', { href: `#${id}`, 'data-campo-erro': id, texto })))));
  lugar.prepend(resumo);
  (validos.length === 1 ? $(validos[0][0]) : resumo).focus();
  return true;
}

// o erro do servidor no campo que ele apontou (cabeçalho X-Farol-Campo), pelo mapa campo da API -> id na tela
function erroDoServidor(lugar, e, mapa) {
  const id = e.campo && mapa[e.campo];
  return id ? mostrarErros(lugar, [[id, e.message]]) : false;
}

function desenharResumo() {
  const r = estado.resultado, p = r.planilha;
  const ucs = r.municipios.reduce((s, m) => s + m.ucs, 0);
  const dl = no('dl', { classe: 'numeros' },
    [['linhas lidas', p.linhas], ['UCs localizadas', ucs], ['com problema', p.total_problemas], ['fora da concessão', r.fora_da_concessao.ucs]]
      .map(([rot, v]) => no('div', {}, no('dt', { texto: t(rot) }), no('dd', { texto: fmt(v) }))));
  const filhos = [dl, no('p', { classe: 'prazo', texto: t('Antecedência mínima do aviso: {prazo} ({norma}).', { prazo: r.prazo.antecedencia_minima, norma: r.prazo.norma }) })];
  if (!r.municipios.length) filhos.push(no('p', { classe: 'alerta', texto: t('Nenhuma UC da planilha caiu na área de concessão. Confira as coordenadas.') }));
  if (r.fora_da_concessao.ucs && r.fora_da_concessao.linhas.length) {
    const mais = r.fora_da_concessao.ucs > r.fora_da_concessao.linhas.length ? '…' : '';
    filhos.push(no('p', { classe: 'alerta', texto: t('{n} UC(s) fora da área de concessão, sem aviso: linha(s) {linhas}{mais}.',
      { n: fmt(r.fora_da_concessao.ucs), linhas: r.fora_da_concessao.linhas.join(', '), mais }) }));
  }
  if (r.escolha && estado.origem === 'historico')   // o critério de quem foi desligado (nunca as UCs)
    filhos.push(no('p', {}, no('strong', { texto: t('Quem foi desligado: ') }), no('span', { texto: descreverEscolha(r.escolha) })));
  filhos.push(no('p', { classe: 'ajuda', texto: t(r.aviso_ficticio) }));
  $('resumo').replaceChildren(...filhos);
}

const tempoTexto = texto => t('{palavras} palavras · cerca de {segundos} s no ar', { palavras: fmt(palavras(texto)), segundos: fmt(segundos(texto)) });
// o aviso no idioma em que foi gerado: o atributo lang faz o leitor de tela pronunciar certo (Fase K)
const idiomaDoAviso = () => estado.formulario?.idioma || 'pt-BR';

function desenharMunicipios() {
  const editavel = pode('gerar_aviso');
  const cartoes = estado.resultado.municipios.map(m => {
    const g = grupos(m), cod = m.codigo_ibge, texto = estado.avisos[cod];
    const area = no('textarea', { id: `aviso-${cod}`, 'data-codigo': cod, readonly: !editavel, lang: idiomaDoAviso() });
    area.value = texto;
    const vital = m.equipamento_vital;
    const listas = no('div', { classe: 'listas' },
      ['inteira', 'parte', 'vizinha'].filter(s => g[s].length).map(s => no('p', {},
        no('span', { classe: `etiqueta ${s}`, texto: t({ inteira: 'Inteiras', parte: 'Em parte', vizinha: 'Vizinhas' }[s]) }),
        g[s].map(c => `${homonimo(c) ? nomeComDistrito(c, m) : c.nome}: ${fmt(c.afetadas)}`).join(', '))),
      no('p', { classe: 'ajuda', texto: t('Equipamento vital: {sim} sim, {nao} não', { sim: fmt(vital.sim), nao: fmt(vital.nao) })
        + (vital.a_confirmar ? t(', {n} a confirmar', { n: fmt(vital.a_confirmar) }) : '') + t('. Depois do nome, UCs afetadas da comunidade.') }));
    return no('article', { classe: 'cartao municipio', 'data-codigo': cod },
      no('div', { classe: 'mun-cab' }, no('h3', { texto: `${m.nome}/${m.uf}` }),
        no('span', { classe: 'meta', texto: t('{ucs} UCs · {comunidades} comunidades', { ucs: fmt(m.ucs), comunidades: fmt(m.comunidades.length) }) })),
      listas,
      no('div', { classe: 'bloco-aviso' },
      no('label', { for: area.id, texto: editavel ? t('Aviso para a rádio (pode editar)') : t('Aviso para a rádio') }), area,
      no('p', { classe: 'tempo', id: `tempo-${cod}`, texto: tempoTexto(texto) }),
      blocoCopiloto(cod),
      no('p', { id: `final-${cod}`, classe: 'ajuda' }),
      no('div', { classe: 'acoes' },
        editavel && estado.resultado.id && no('button', { type: 'button', classe: 'prim', 'data-acao': 'pdf', 'data-codigo': cod, texto: t('Baixar PDF para a rádio') }),
        no('button', { type: 'button', 'data-acao': 'copiar', 'data-codigo': cod, texto: t('Copiar texto') }),
        temAudio() && no('button', { type: 'button', 'data-acao': 'ouvir', 'data-codigo': cod, texto: t('Ouvir') }),
        temAudio() && no('button', { type: 'button', 'data-acao': 'audio', 'data-codigo': cod, texto: t('Baixar áudio (MP3)') }),
        editavel && no('button', { type: 'button', 'data-acao': 'restaurar', 'data-codigo': cod, texto: t('Desfazer edição') })),
      no('div', { id: `tocador-${cod}`, classe: 'tocador' }),
      temAudio() || !pode('gerar_aviso') ? null : no('p', { classe: 'ajuda', texto: audioLigado()
        ? t('Áudio indisponível em espanhol: nenhuma voz em espanhol com licença clara (veja ORIGEM.md). Use o texto e o PDF.')
        : t('O áudio do aviso está desligado neste servidor.') }),
      no('section', { id: `envio-${cod}`, classe: 'envio-radio', 'data-codigo': cod, 'aria-label': t('Envio para a rádio: {nome}', { nome: m.nome }) })));
  });
  $('municipios').replaceChildren(...cartoes);
  for (const m of estado.resultado.municipios) { desenharFinal(m.codigo_ibge); desenharTocador(m.codigo_ibge); desenharEnvio(m); desenharCopiloto(m.codigo_ibge); }
}

// ---- Envio para a rádio (um município): a rádio, o valor, a economia e os envios já feitos ----
function desenharEnvio(m) {
  const cod = m.codigo_ibge, lugar = $(`envio-${cod}`), r = estado.resultado;
  if (!lugar) return;
  const feitos = estado.envios.filter(e => e.municipio === cod);
  const lista = feitos.length ? [no('h4', { texto: t('Envios para a rádio') }), no('ul', { classe: 'envios' }, feitos.map(e => no('li', {},
    no('span', { classe: `chip envio ${e.status}`, texto: t(SITUACAO_ENVIO[e.status]) + (e.confirmado_em ? t(' em {quando}', { quando: dataHora(e.confirmado_em) }) : '') }),
    no('span', { texto: `${e.radio_nome} · ${t(CANAL[e.canal])}${e.destino && e.canal !== 'copia' ? ` (${e.destino})` : ''}` }),
    no('span', { classe: 'meta', texto: t('{valor} ({cobranca}) · {economia} · por {nome} em {quando}', { valor: dinheiro(e.valor),
      cobranca: t(COBRANCA[e.cobranca]), economia: economiaTexto(e), nome: e.por, quando: dataHora(e.criado_em) }) }),
    e.arquivos.length ? no('span', { classe: 'acoes' }, e.arquivos.map(tipo => no('button', { type: 'button', 'data-arquivo': tipo, 'data-envio-id': e.id,
      texto: tipo === 'pdf' ? t('PDF enviado') : t('MP3 enviado') }))) : null)))] : [];
  if (!(r.id && pode('gerar_aviso') && r.status !== 'cancelado')) return lugar.replaceChildren(...lista);
  const s = estado.sugestao[cod] || { radios: [], sem_radio: [] }, cobrem = new Map(s.radios.map(x => [x.radio_id, x]));
  const ordem = [...estado.radios].sort((a, b) => (cobrem.has(b.id) - cobrem.has(a.id)) || a.nome.localeCompare(b.nome, IDIOMA));
  // a rádio escolhida saiu da lista, ou a lista chegou depois (rádio cadastrada com o aviso aberto): volta à primeira, com o valor dela
  if (estado.escolha[cod] && !ordem.some(x => String(x.id) === String(estado.escolha[cod].radioId)))
    estado.escolha[cod] = { ...escolhaPadrao(ordem[0]), pedido: estado.escolha[cod].pedido };
  const e = estado.escolha[cod] ||= escolhaPadrao(ordem[0]);
  const alcance = x => cobrem.has(x.id) ? (cobrem.get(x.id).municipio_inteiro ? t(' · alcança o município')
    : t(' · alcança {n} comunidade(s)', { n: cobrem.get(x.id).comunidades })) : t(' · fora do alcance cadastrado');
  const sel = no('select', { 'data-envio': 'radioId', id: `radio-${cod}` },
    ordem.map(x => no('option', { value: String(x.id), texto: x.nome + alcance(x), selected: String(x.id) === String(e.radioId) })));
  const campo = (rotulo, nome, extra = {}) => no('label', { texto: t(rotulo) }, no('input', { id: `${nome}-${cod}`, 'data-envio': nome, value: e[nome] ?? '',
    autocomplete: 'off', ...extra }));
  const blocos = [no('h4', { texto: t('Enviar para a rádio') })];
  if (s.sem_radio.length) blocos.push(no('p', { classe: 'alerta-amarelo', role: 'status' }, no('span', { 'aria-hidden': 'true', texto: '⚠ ' }),
    t('Sem rádio cadastrada para: {lista}.', { lista: s.sem_radio.join(', ') })));
  if (ordem.length) blocos.push(no('label', { for: `radio-${cod}`, texto: t('Rádio') }), sel,
    no('div', { classe: 'campos' }, campo('Valor deste envio (R$, obrigatório)', 'valor', { inputmode: 'decimal', placeholder: '0,00' }),
      no('label', { texto: t('Cobrança') }, no('select', { id: `cobranca-${cod}`, 'data-envio': 'cobranca' },
        Object.entries(COBRANCA).map(([k, rot]) => no('option', { value: k, texto: t(rot), selected: k === e.cobranca })))),
      campo('Quanto custaria do jeito antigo (R$, opcional)', 'antigo', { inputmode: 'decimal', placeholder: t('opcional') })),
    no('p', { classe: 'economia-linha' }, no('span', { classe: 'economia', id: `previa-${cod}`, 'aria-live': 'polite' }), dica('economia', 'economia calculada e informada')),
    no('div', { classe: 'acoes' },
      estado.config?.email !== false ? no('button', { type: 'button', classe: 'prim', 'data-envio-acao': 'email', texto: t('Enviar por e-mail') }) : null,
      no('button', { type: 'button', 'data-envio-acao': 'whatsapp', texto: t('Enviar por WhatsApp') }),
      no('button', { type: 'button', 'data-envio-acao': 'copia', texto: t('Copiar mensagem') })),
    estado.config?.email === false ? no('p', { classe: 'ajuda', texto: t('O envio por e-mail está desligado neste servidor.') }) : null);
  else blocos.push(no('p', { classe: 'ajuda', texto: pode('gerenciar_radios') ? t('Nenhuma rádio ativa cadastrada ainda: cadastre em Rádios.')
    : t('Nenhuma rádio ativa cadastrada ainda: peça o cadastro ao Admin da empresa.') }),
    pode('gerenciar_radios') ? no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-envio-acao': 'ir-radios', texto: t('Ir para Rádios') })) : null);
  if (pode('pedir_radio')) blocos.push(formPedidoRadio(m, e));
  // replaceChildren escreveria null como o texto "null": os blocos vazios saem antes
  lugar.replaceChildren(...blocos.filter(Boolean), ...lista);
  desenharPrevia(cod);
}

function escolhaPadrao(radio) {
  return radio ? { radioId: String(radio.id), valor: radio.valor_sugerido ? Number(radio.valor_sugerido).toFixed(2).replace('.', ',') : '',
    cobranca: radio.cobranca_sugerida || 'fechado', antigo: '' } : { radioId: '', valor: '', cobranca: 'fechado', antigo: '' };
}

// falta uma rádio: o Operador pede o cadastro ao Admin da empresa (contato da rádio, nunca de cliente)
function formPedidoRadio(m, e) {
  const cod = m.codigo_ibge, p = e.pedido ||= { aberto: false, nome: '', cidade: m.nome, contato: '', observacao: '' };
  const botao = no('button', { type: 'button', 'data-envio-acao': 'pedir', 'aria-expanded': String(p.aberto), 'aria-controls': `pedido-${cod}`,
    texto: t('Pedir cadastro de rádio') });
  if (!p.aberto) return no('div', { classe: 'acoes' }, botao);
  const campo = (rotulo, nome, extra = {}) => no('label', { texto: t(rotulo) }, no('input', { id: `pedido-${nome}-${cod}`, 'data-pedido-campo': nome,
    value: p[nome], autocomplete: 'off', ...extra }));
  const meus = (estado.meusPedidos || []).slice(0, 5);
  return no('div', { classe: 'pedido-radio com-erros', id: `pedido-${cod}` }, no('div', { classe: 'acoes' }, botao),
    no('p', { classe: 'ajuda', texto: t('O Admin da empresa recebe o pedido e cadastra a rádio (ou explica por que não). Só dados da rádio: nada de cliente.') }),
    campo('Nome da rádio (obrigatório)', 'nome', { maxlength: '80' }), campo('Cidade da rádio (obrigatória)', 'cidade', { maxlength: '80' }),
    campo('Contato da rádio: e-mail ou telefone (opcional)', 'contato', { maxlength: '120' }),
    campo('Observação (opcional)', 'observacao', { maxlength: '300' }),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', classe: 'prim', 'data-envio-acao': 'enviar-pedido', texto: t('Enviar o pedido') })),
    meus.length ? no('div', {}, no('h5', { texto: t('Seus pedidos de rádio') }), no('ul', { classe: 'envios' }, meus.map(x => no('li', {},
      no('span', { classe: `chip ${x.status === 'recusado' ? 'cancelado' : ''}`, texto: t(SITUACAO_PEDIDO[x.status]) }),
      no('span', { texto: t('{nome} ({cidade}) · {quando}', { nome: x.nome, cidade: x.cidade, quando: dataHora(x.criado_em) })
        + (x.motivo_recusa ? t(' · motivo: {motivo}', { motivo: x.motivo_recusa }) : '') }))))) : null);
}

function desenharPrevia(cod) {
  const lugar = $(`previa-${cod}`), e = estado.escolha[cod];
  if (!lugar || !e) return;
  const m = estado.resultado.municipios.find(x => x.codigo_ibge === cod), valor = reaisNumero(e.valor), antigo = reaisNumero(e.antigo);
  if (valor === null || Number.isNaN(valor)) return lugar.textContent = t('Informe o valor do envio em R$.');
  if (Number.isNaN(antigo)) return lugar.textContent = t('O custo antigo tem de ser um valor em R$.');
  lugar.textContent = economiaTexto(previaEconomia({ cobranca: e.cobranca, valor, segundosFarol: segundos(estado.avisos[cod]),
    segundosHoje: m.hoje?.segundos ?? null, custoAntigo: antigo }), true);
}

// copiloto de IA: pede ao servidor uma versão do aviso (mais curto, WhatsApp...); o servidor confere o resultado
// contra o aviso original e a tela mostra se foi aprovado
const iaConfig = () => estado.config?.ia;
const copilotoLigado = () => !!iaConfig()?.ativa && pode('gerar_aviso') && !!estado.resultado?.id;

function blocoCopiloto(cod) {
  if (!copilotoLigado()) return null;
  const c = iaConfig();
  return no('div', { classe: 'copiloto' },
    no('p', { classe: 'ajuda', texto: c.provedor === 'simulado' ? 'Copiloto de IA (simulado nesta demonstração)' : 'Copiloto de IA' }),
    no('div', { classe: 'acoes' }, Object.entries(c.pedidos).map(([k, rotulo]) =>
      no('button', { type: 'button', 'data-acao': 'ia', 'data-pedido': k, 'data-codigo': cod, texto: rotulo }))),
    no('div', { classe: 'ia-livre' },
      no('input', { id: `ia-livre-${cod}`, maxlength: c.max_livre, placeholder: 'Ou escreva um pedido…', 'aria-label': 'Pedido livre ao copiloto' }),
      no('button', { type: 'button', 'data-acao': 'ia', 'data-pedido': 'livre', 'data-codigo': cod, texto: 'Pedir' })),
    no('p', { id: `ia-status-${cod}`, classe: 'ajuda', role: 'status' }));
}

function desenharCopiloto(codigo) {
  const lugar = $(`ia-status-${codigo}`), r = estado.ia[codigo];
  if (!lugar) return;
  lugar.replaceChildren(...(!r ? [] : r.pedindo ? ['Pensando…'] : r.verificado
    ? [no('span', { classe: 'selo final', texto: 'Verificado' }), ' mantém todas as comunidades, a data, o horário e o telefone do aviso. Confira antes de usar.']
    : [no('span', { classe: 'selo recusado', texto: 'Recusado' }), ` ${r.motivos.length ? r.motivos.join('; ') : r.erro}. O texto anterior foi mantido.`]));
  for (const b of document.querySelectorAll(`button[data-acao="ia"][data-codigo="${codigo}"]`)) b.disabled = !!r?.pedindo;
}

function desenharFinal(codigo) {
  const f = estado.finais[codigo];
  $(`final-${codigo}`).replaceChildren(...(f ? [no('span', { classe: 'selo final', texto: t('Texto final guardado no histórico') }),
    f !== estado.avisos[codigo] ? t(' (o texto mudou depois; baixe o PDF ou copie de novo para guardar)') : ''] : []));
}

function desenharTempo(codigo) {
  $(`tempo-${codigo}`).textContent = tempoTexto(estado.avisos[codigo]);
  desenharFinal(codigo);
  desenharTocador(codigo);
  desenharPrevia(codigo);
}

// o tocador aparece com o áudio do texto atual; se o texto mudou, some (o áudio antigo não vale mais)
function desenharTocador(codigo) {
  const a = audioAtual(codigo), lugar = $(`tocador-${codigo}`);
  if (!lugar) return;
  if (!a) return lugar.replaceChildren();
  if (lugar.querySelector('audio')?.src === a.url) return;
  lugar.replaceChildren(no('audio', { controls: true, src: a.url, preload: 'auto', 'aria-label': t('Áudio do aviso') }),
    no('span', { classe: 'ajuda', texto: t('{s} s de áudio (voz sintetizada)', { s: fmt(Math.round(a.segundos)) }) }));
}

function desenharProblemas() {
  const p = estado.resultado.planilha;
  $('problemas').hidden = !p.problemas.length;
  if (!p.problemas.length) return;
  $('problemasTitulo').textContent = t('{n} linha(s) com problema', { n: fmt(p.total_problemas) });
  const motivos = no('ul', {}, Object.entries(p.problemas_por_motivo).map(([m, n]) => no('li', { texto: `${m}: ${fmt(n)}` })));
  const tabela = no('table', {}, no('thead', {}, no('tr', {}, no('th', { scope: 'col', texto: t('Linha') }), no('th', { scope: 'col', texto: t('Problema') }))),
    no('tbody', {}, p.problemas.map(x => no('tr', {}, no('td', { texto: String(x.linha) }), no('td', { texto: x.motivo })))));
  $('problemasCorpo').replaceChildren(motivos, tabela,
    p.total_problemas > p.problemas.length ? no('p', { classe: 'ajuda', texto: t('Mostrando as primeiras {n}.', { n: fmt(p.problemas.length) }) }) : '');
}

// ---- Conferência humana (passo 4 de um aviso novo): quem será desligado, números, travas, correções e a caixa "Conferi" ----
function desenharConferencia() {
  const r = estado.resultado, c = r?.conferencia, lugar = $('conferencia');
  lugar.hidden = !c || estado.origem !== 'novo';
  if (lugar.hidden) return lugar.replaceChildren();
  const tr = r.traducao, n = c.numeros, ja = gerado();
  const numeros = no('dl', { classe: 'numeros' }, [['clientes no aviso', n.clientes], ['municípios', n.municipios], ['comunidades', n.comunidades],
    ['com equipamento vital', n.equipamento_vital], ['corrigidas', n.corrigidas], ['rejeitadas', n.rejeitadas]]
    .map(([rot, v]) => no('div', {}, no('dt', { texto: t(rot) }), no('dd', { texto: fmt(v) }))));
  const arquivo = no('p', { classe: 'ajuda', texto: t('Arquivo {nome}', { nome: tr.arquivo.nome }) + (tr.arquivo.aba ? t(', aba {aba}', { aba: tr.arquivo.aba }) : '')
    + t(' · {linhas} linhas · colunas reconhecidas: {colunas} · {ignoradas} coluna(s) ignorada(s)', { linhas: fmt(tr.arquivo.linhas),
      colunas: tr.colunas.join(', '), ignoradas: fmt(tr.arquivo.colunas_ignoradas) }) + t(' · tradutor {versao}', { versao: tr.versao }) });
  // a escolha: o critério e a conta fechada (lidas = inativas fora + não escolhidas + escolhidas = ok + corrigidas + rejeitadas)
  const k = r.escolha?.conta;
  const escolha = k ? no('div', { classe: 'conta-fechada' },
    no('p', {}, no('strong', { texto: t('Quem será desligado: ') }), no('span', { texto: descreverEscolha(r.escolha) })),
    no('p', { classe: 'ajuda', texto: t('Conta fechada: {lidas} lidas = {inativas} inativas fora + {nao} não escolhidas + {escolhidas} escolhidas; escolhidas = {ok} ok + {corrigidas} corrigidas + {rejeitadas} rejeitadas.',
      { lidas: fmt(k.lidas), inativas: fmt(k.inativas_fora), nao: fmt(k.nao_escolhidas), escolhidas: fmt(k.escolhidas), ok: fmt(k.ok),
        corrigidas: fmt(k.corrigidas), rejeitadas: fmt(k.rejeitadas) }) }),
    no('p', { classe: 'ajuda', texto: t('As travas abaixo (equipamento vital, pontos suspeitos, limite de rejeição e área de atuação) valem só para as escolhidas.') })) : null;
  const blocos = [no('h3', { texto: t('Conferência da planilha') }), arquivo, escolha, numeros,
    no('p', { classe: 'dicas' }, no('span', { classe: 'ajuda', texto: t('O que é: ') }),
      no('span', { texto: t('UC') }), dica('uc', 'UC'), no('span', { texto: t('equipamento vital') }), dica('vital', 'equipamento vital'),
      no('span', { texto: t('corrigida') }), dica('corrigida', 'linha corrigida'), no('span', { texto: t('rejeitada') }), dica('rejeitada', 'linha rejeitada'),
      no('span', { texto: t('limite de rejeição') }), dica('limite', 'limite de rejeição'))];
  if (n.vital_a_confirmar) blocos.push(no('p', { classe: 'ajuda', texto: t('{n} cliente(s) sem a informação de equipamento vital (a confirmar).', { n: fmt(n.vital_a_confirmar) }) }));
  if (c.vital_bloqueio.length) blocos.push(no('div', { classe: 'alerta-vermelho', role: 'alert' },
    no('strong', {}, no('span', { 'aria-hidden': 'true', texto: '⛔ ' }), t('Bloqueado: {n} linha(s) com equipamento vital rejeitada(s), corrigida(s) ou fora da concessão',
      { n: fmt(c.vital_bloqueio.length) })),
    no('ul', {}, c.vital_bloqueio.map(x => no('li', { texto: t('Linha {linha}: {texto}', { linha: x.linha, texto: x.texto }) + (x.motivo ? ` (${x.motivo})` : '') }))),
    no('p', { texto: t('Quem usa equipamento vital tem de ser avisado com certeza. Corrija essas linhas na planilha e importe de novo.') })));
  if (c.suspeitos.length) blocos.push(no('div', { classe: 'alerta-amarelo' },
    no('strong', {}, no('span', { 'aria-hidden': 'true', texto: '⚠ ' }), t('Pontos suspeitos: confira no mapa antes de marcar "Conferi"')),
    no('ul', {}, c.suspeitos.map(x => no('li', { texto: x.tipo === 'repeticao' ? `${x.texto}: ${x.comunidades.join('; ')}`
      : `${x.texto}${x.municipio ? t(' · {municipio} (a maioria em {maioria})', { municipio: x.municipio, maioria: x.maioria }) : ''}: `
      + t('{n} UC(s), linha(s) {linhas}', { n: fmt(x.ucs), linhas: x.linhas.slice(0, 30).join(', ') + (x.linhas.length > 30 ? '…' : '') }) })))));
  for (const [campo, rotulo] of [['circuito', 'circuito'], ['transformador', 'transformador']]) {
    const g = r.rede?.[campo];
    if (!g || !g.total) continue;
    blocos.push(no('details', { classe: 'corrigidas' },
      no('summary', { texto: t('Por {rotulo}: {n} código(s)', { rotulo: t(rotulo), n: fmt(g.total) }) + (g.sem_codigo ? t(', {n} UC(s) sem código', { n: fmt(g.sem_codigo) }) : '') }),
      no('p', { classe: 'ajuda', texto: t('Confira se bate com a parte da rede que vai ser desligada.') + (g.total > g.grupos.length ? ` ${t('Os {n} maiores.', { n: g.grupos.length })}` : '') }),
      no('div', { classe: 'rolagem' }, no('table', { classe: 'tabela' }, no('thead', {}, no('tr', {}, no('th', { scope: 'col', texto: t(rotulo[0].toUpperCase() + rotulo.slice(1)) }),
        no('th', { scope: 'col', texto: t('UCs') }))),
        no('tbody', {}, g.grupos.map(x => no('tr', {}, no('td', { texto: x.codigo }), no('td', { texto: fmt(x.ucs) }))))))));
  }
  if (tr.corrigidas.length) blocos.push(no('details', { classe: 'corrigidas' },
    no('summary', { texto: t('{n} linha(s) com a coordenada corrigida (em roxo no mapa)', { n: fmt(n.corrigidas) }) }),
    no('ul', {}, tr.corrigidas.map(x => no('li', { texto: t('Linha {linha}: {texto}', { linha: x.linha, texto: x.correcao }) })))));
  if (c.rejeicao.acima) {
    const area = no('textarea', { id: 'justificativa', maxlength: String(MAX_JUSTIFICATIVA), rows: '3', readonly: ja,
      'aria-describedby': 'contaJustificativa' });
    area.value = estado.justificativa;
    blocos.push(no('div', { classe: 'alerta-amarelo' },
      no('strong', {}, no('span', { 'aria-hidden': 'true', texto: '⚠ ' }), t('{rejeitadas} de {total} linhas rejeitadas ({fracao}), acima do limite de {limite}',
        { rejeitadas: fmt(c.rejeicao.rejeitadas), total: fmt(c.rejeicao.total), fracao: pct(c.rejeicao.fracao), limite: pct(c.rejeicao.limite) })),
      no('label', { for: 'justificativa', texto: t('Justificativa para continuar (fica na auditoria com o seu nome)') }), area,
      no('p', { classe: 'ajuda', id: 'contaJustificativa', texto: t('{n} de {max} caracteres', { n: estado.justificativa.length, max: MAX_JUSTIFICATIVA }) })));
  }
  const caixa = no('input', { type: 'checkbox', id: 'conferi', disabled: ja || !!c.vital_bloqueio.length });
  caixa.checked = estado.conferi || ja;
  blocos.push(no('label', { classe: 'confirmar', for: 'conferi' }, caixa, no('span', { texto: t('Conferi os números e o mapa') })));
  blocos.push(no('p', { classe: 'ajuda', id: 'motivoGerar', 'aria-live': 'polite' }));
  blocos.push(no('div', { classe: 'acoes' },
    ja ? null : no('button', { type: 'button', 'data-conf': 'relatorio', texto: t('Baixar relatório (CSV)') }),
    pode('baixar_json') ? no('button', { type: 'button', 'data-conf': 'json', texto: t('Baixar JSON (com as UCs)') }) : null));
  if (!ja && r.pacote_vence) blocos.push(no('p', { classe: 'ajuda', texto: t('A conferência vale até {hora}; depois, importe a planilha de novo.',
    { hora: new Date(r.pacote_vence).toLocaleTimeString(IDIOMA, { hour: '2-digit', minute: '2-digit' }) }) }));
  lugar.replaceChildren(...blocos);
  desenharFunil();
}

// ---- Escolher quem será desligado (passo 3): o modo, as inativas, o mapa (áreas e comunidades) e os filtros. O mapa
// tem alternativa em lista: pelo teclado, a lista de comunidades e os filtros fazem o mesmo que os cliques ----
function desenharEscolha() {
  const lugar = $('escolhaCorpo'), b = estado.leitura?.base, s = estado.selecao;
  if (!b || !s) { lugar.replaceChildren(); return desenharContaEscolha(); }
  if (gerado()) {
    lugar.replaceChildren(no('p', { texto: t('Escolha usada no aviso: {texto}', { texto: descreverEscolha(estado.resultado.escolha) }) }));
    return desenharContaEscolha();
  }
  const radio = (valor, texto) => {
    const r = no('input', { type: 'radio', name: 'modoEscolha', id: `modo-${valor}`, value: valor });
    r.checked = s.modo === valor;
    return no('label', { classe: 'opcao', for: `modo-${valor}` }, r, no('span', { texto }));
  };
  const blocos = [no('p', { classe: 'ajuda', texto: t('A planilha pode ser a base de clientes inteira: escolha quem fica sem luz neste desligamento. Só as UCs escolhidas seguem para a conferência e o aviso.') }),
    no('fieldset', { classe: 'modo-escolha' }, no('legend', { texto: t('Como escolher') }),
      radio('escolha', t('Escolher no mapa e pelos filtros')), radio('planilha', t('A planilha já é a lista do desligamento (veio do sistema de manobras)')))];
  const inativas = b.linhas.inativa.reduce((n, v) => n + v, 0);
  if (inativas) blocos.push(blocoInativas(b, s, inativas));
  if (s.modo === 'escolha') {
    blocos.push(no('p', { classe: 'ajuda', texto: t('Os filtros se somam: a UC entra se atender a todos os filtros usados; dentro de um filtro, vale qualquer um dos marcados. O mapa (áreas e comunidades) conta como mais um filtro.') }));
    blocos.push(blocoMapa(b, s), blocoLista(b, s, 'comunidade'));
    for (const f of FILTROS) if (b.colunas.includes(f)) blocos.push(blocoLista(b, s, f));
    const semPosicao = b.linhas.vital_sem_posicao.reduce((n, v) => n + v, 0);
    if (semPosicao) blocos.push(no('p', { classe: 'ajuda', texto: t('{n} linha(s) com equipamento vital sem coordenada: com o mapa, entram na escolha (não dá para saber se estão na área) e bloqueiam o aviso até a planilha ser corrigida.', { n: fmt(semPosicao) }) }));
  }
  lugar.replaceChildren(...blocos);
  desenharContaEscolha();
}

// as inativas (SITUACAO = INATIVO...) ficam fora por padrão: a contagem e, ao abrir, por bairro e por circuito (nunca a UC)
function blocoInativas(b, s, n) {
  const caixa = no('input', { type: 'checkbox', id: 'incluirInativas' });
  caixa.checked = s.incluirInativas;
  const tabela = campo => {
    const conta = new Map();
    b.linhas[campo].forEach((v, i) => {
      if (!b.linhas.inativa[i]) return;
      const k = v >= 0 ? b.valores[campo][v] : t('não informado');
      conta.set(k, (conta.get(k) || 0) + 1);
    });
    return no('div', { classe: 'rolagem' }, no('table', { classe: 'tabela' },
      no('thead', {}, no('tr', {}, no('th', { scope: 'col', texto: t({ bairro: 'Bairro', circuito: 'Circuito' }[campo]) }), no('th', { scope: 'col', texto: t('UCs inativas') }))),
      no('tbody', {}, [...conta].sort((a, c) => c[1] - a[1] || (a[0] < c[0] ? -1 : 1)).map(([k, v]) => no('tr', {}, no('td', { texto: k }), no('td', { texto: fmt(v) }))))));
  };
  const campos = ['bairro', 'circuito'].filter(c => b.colunas.includes(c));
  return no('div', { classe: 'alerta-amarelo inativas' },
    no('strong', { texto: s.incluirInativas ? t('{n} UC(s) inativa(s) incluída(s) no aviso', { n: fmt(n) }) : t('{n} UC(s) inativa(s) não entram no aviso', { n: fmt(n) }) }),
    campos.length ? no('details', {}, no('summary', { texto: t('Ver quais (contagem por bairro e por circuito, sem o número da UC)') }),
      no('div', { classe: 'tabelas-inativas' }, campos.map(tabela))) : null,
    no('label', { classe: 'confirmar', for: 'incluirInativas' }, caixa, no('span', { texto: t('Incluir as inativas no aviso') })));
}

// desenhar uma área (cliques nos cantos) e as áreas já desenhadas, com as UCs dentro de cada uma
function blocoMapa(b, s) {
  const d = s.desenho, ln = b.linhas;
  const dentro = p => { const [x0, y0, x1, y1] = caixaArea(p); let n = 0;
    for (let i = 0; i < b.lidas; i++) { const lat = ln.lat[i], lon = ln.lon[i];
      if (lat !== null && (!ln.inativa[i] || s.incluirInativas) && x0 <= lon && lon <= x1 && y0 <= lat && lat <= y1 && naArea(lat, lon, p)) n++; }
    return n; };
  const acoes = d ? [no('p', { classe: 'ajuda', id: 'passosDesenho', texto: d.length === 0 ? t('Clique no mapa para marcar o primeiro canto da área.')
      : d.length < 3 ? t('{n} ponto(s) marcado(s). Marque pelo menos 3 para concluir.', { n: fmt(d.length) })
        : t('{n} pontos marcados. Continue clicando nos cantos ou conclua a área.', { n: fmt(d.length) }) }),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-sel': 'desfazer', disabled: !d.length, texto: t('Desfazer o último ponto') }),
      no('button', { type: 'button', classe: 'prim', 'data-sel': 'concluir', disabled: d.length < 3, texto: t('Concluir a área') }),
      no('button', { type: 'button', 'data-sel': 'cancelar', texto: t('Cancelar o desenho') }))]
    : [no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-sel': 'desenhar', texto: t('Desenhar uma área no mapa') }))];
  const areas = s.poligonos.map((p, k) => no('li', {}, no('span', { texto: t('Área {n} · {v} vértices · {x} UC(s) dentro', { n: k + 1, v: fmt(p[0].length - 1), x: fmt(dentro(p)) }) }),
    no('button', { type: 'button', 'data-sel': 'remover', 'data-area': String(k), 'aria-label': t('Remover a área {n}', { n: k + 1 }), texto: t('Remover') })));
  return no('div', { classe: 'bloco-mapa', id: 'blocoMapa' }, no('h3', { texto: t('No mapa') }),
    no('p', { classe: 'ajuda', texto: t('Clique numa comunidade no mapa para incluir ou tirar, ou desenhe uma área clicando nos cantos. Sem mouse, use a lista de comunidades e os filtros abaixo: eles fazem o mesmo.') }),
    ...acoes, areas.length ? no('ul', { classe: 'areas-escolha' }, areas) : null);
}

const rotuloComunidadeBase = (b, i) => {
  const c = b.comunidades[i], m = b.municipios[c.municipio];
  return `${semSufixo(c.nome)} (${distritoDe(c.distrito, m.nome)}) · ${m.nome}`;
};
const TITULO_LISTA = tipo => t({ comunidade: 'Comunidades', circuito: 'Circuito', conjunto: 'Conjunto', transformador: 'Transformador', bairro: 'Bairro' }[tipo]);
const marcadosDe = (s, tipo) => tipo === 'comunidade' ? s.comunidades : s.filtros[tipo];
// [índice, rótulo, UCs] de cada valor (as UCs que podem entrar: sem as inativas, salvo incluir)
function itensDaLista(b, s, tipo) {
  const ln = b.linhas, campo = tipo === 'comunidade' ? 'com' : tipo;
  const n = new Array(tipo === 'comunidade' ? b.comunidades.length : b.valores[tipo].length).fill(0);
  for (let i = 0; i < b.lidas; i++) if (ln[campo][i] >= 0 && (!ln.inativa[i] || s.incluirInativas)) n[ln[campo][i]]++;
  return n.map((x, i) => [i, tipo === 'comunidade' ? rotuloComunidadeBase(b, i) : b.valores[tipo][i], x]);
}
const itensBuscados = (b, s, tipo) => { const busca = normalizar((s.buscas[tipo] || '').trim());
  return itensDaLista(b, s, tipo).filter(([, r]) => !busca || normalizar(r).includes(busca)); };

// uma lista de marcar com busca (comunidades, circuitos, conjuntos, transformadores, bairros)
function blocoLista(b, s, tipo) {
  const titulo = TITULO_LISTA(tipo);
  const busca = no('input', { type: 'search', id: `busca-${tipo}`, 'data-busca': tipo, autocomplete: 'off', placeholder: t('Buscar'),
    'aria-label': t('Buscar em {lista}', { lista: titulo }) });
  busca.value = s.buscas[tipo] || '';
  const itens = no('div', { classe: 'itens-marcar', id: `itens-${tipo}`, role: 'group', 'aria-label': titulo });
  const det = no('details', { classe: 'lista-escolha', 'data-lista': tipo, open: s.abertos.has(tipo) || marcadosDe(s, tipo).size > 0 },
    no('summary', {}, no('span', { texto: titulo }), no('span', { classe: 'marcados', id: `marcados-${tipo}` })),
    busca, no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-sel': 'marcar', 'data-tipo': tipo, texto: t('Marcar os mostrados') }),
      no('button', { type: 'button', 'data-sel': 'desmarcar', 'data-tipo': tipo, texto: t('Desmarcar todos') })), itens);
  desenharItens(itens, b, s, tipo);
  return det;
}
function desenharItens(lugar, b, s, tipo) {
  const marcados = marcadosDe(s, tipo), itens = itensBuscados(b, s, tipo);
  lugar.replaceChildren(...itens.slice(0, MAX_MARCAR).map(([i, rotulo, n]) => {
    const c = no('input', { type: 'checkbox', id: `sel-${tipo}-${i}`, 'data-sel-tipo': tipo, value: String(i) });
    c.checked = marcados.has(i);
    return no('label', { classe: 'item-marcar', for: c.id }, c, no('span', { texto: rotulo }), no('span', { classe: 'ajuda', texto: t('{n} UC(s)', { n: fmt(n) }) }));
  }), itens.length > MAX_MARCAR ? no('p', { classe: 'ajuda', texto: t('Mostrando {n} de {total}: use a busca.', { n: fmt(MAX_MARCAR), total: fmt(itens.length) }) }) : null,
  itens.length ? null : no('p', { classe: 'ajuda', texto: t('Nada encontrado.') }));
}

// o contador ao vivo ("X de Y UCs selecionadas · Z comunidades"), o que falta para conferir e quantos marcados em cada lista
function desenharContaEscolha() {
  const b = estado.leitura?.base, s = estado.selecao, mostra = estado.passo === 3 && !!b && !!s;
  $('motivoEscolha').hidden = !mostra;
  if (!mostra) { $('contaEscolha').textContent = ''; return; }
  const r = gerado() ? estado.resultado.escolha?.conta : null;
  const c = r ? { x: r.escolhidas, y: r.lidas, z: estado.resultado.escolha.comunidades_no_aviso } : contaSelecao(b, s, estado.sel);
  $('contaEscolha').textContent = t('{x} de {y} UCs selecionadas · {z} comunidade(s)', { x: fmt(c.x), y: fmt(c.y), z: fmt(c.z) });
  const problema = gerado() ? null : problemaDaSelecao(s, c);
  $('motivoEscolha').textContent = gerado() ? '' : problema || t('Pronto para conferir: as travas e o aviso valem só para as UCs escolhidas.');
  $('conferirEscolha').textContent = gerado() ? t('Avançar para a conferência') : estado.enviando ? t('Conferindo…') : t('Conferir a escolha');
  $('conferirEscolha').disabled = !gerado() && (estado.enviando || !!problema);
  for (const tipo of ['comunidade', ...FILTROS]) {
    const lugar = $(`marcados-${tipo}`);
    if (lugar) lugar.textContent = marcadosDe(s, tipo).size ? t(' · {n} marcado(s)', { n: fmt(marcadosDe(s, tipo).size) }) : '';
  }
}

// quem pediu, quando e o código; no histórico, mudar a data ou cancelar (quem gera aviso)
function desenharSolicitado() {
  const r = estado.resultado;
  const tipoRot = r?.desligamento ? (estado.config?.tipos?.[r.desligamento.tipo] || r.desligamento.rotulo) : '';
  const partes = r ? [solicitadoTexto(r), r.desligamento ? t('Tipo: {rotulo} ({motivo})', { rotulo: tipoRot, motivo: r.desligamento.motivo }) : '',
    r.id && estado.formulario?.idioma ? t('Idioma: {idioma}', { idioma: estado.config?.idiomas?.[estado.formulario.idioma] || estado.formulario.idioma }) : ''].filter(Boolean) : [];
  $('solicitado').replaceChildren(...partes.map(x => no('span', { texto: x })), r?.codigo ? dica('codigo', 'código de verificação') : '',
    r?.status === 'cancelado' ? no('span', { classe: 'chip cancelado' }, no('span', { 'aria-hidden': 'true', texto: '✕ ' }), t('Desligamento cancelado')) : '');
  if (r?.id && pode('ver_historico')) $('solicitado').append(no('button', { type: 'button', id: 'baixarComprovante', texto: t('Comprovante (PDF)') }),
    no('button', { type: 'button', id: 'verLinhaTempo', 'aria-controls': 'linhaTempo', texto: t('Linha do tempo') }));
  if (!r?.id || estado.linhaTempo?.aviso !== r.id) { estado.linhaTempo = null; $('linhaTempo').hidden = true; $('linhaTempo').replaceChildren(); }
  const lugar = $('acoesAviso');
  lugar.hidden = !(r && estado.origem === 'historico' && pode('gerar_aviso') && r.status !== 'cancelado');
  if (lugar.hidden) return lugar.replaceChildren();
  lugar.replaceChildren(no('h3', { texto: t('Mudou alguma coisa?') }),
    no('div', { classe: 'campos' },
      no('label', {}, no('span', { texto: t('Nova data') }), ' ', no('input', { type: 'date', id: 'novaData' })),
      no('label', {}, no('span', { texto: t('Início') }), ' ', no('input', { type: 'time', id: 'novoInicio', value: '08:00', step: '900' })),
      no('label', {}, no('span', { texto: t('Fim') }), ' ', no('input', { type: 'time', id: 'novoFim', value: '14:00', step: '900' }))),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-aviso': 'data', texto: t('Mudar a data') })),
    no('label', { texto: t('Motivo do cancelamento (vai para a auditoria; sem nome de cliente)') },
      no('input', { id: 'motivoCancelar', maxlength: '200', autocomplete: 'off' })),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', classe: 'perigo', 'data-aviso': 'cancelar', texto: t('Cancelar o desligamento') })));
}

function desenharResultado() {
  desenharAbas();
  desenharConferencia();
  desenharSolicitado();
  if (!estado.resultado) return;
  const r = estado.resultado, f = estado.formulario;
  $('tituloResultado').textContent = estado.origem === 'historico'
    ? t('Aviso de {data}, {horario} · gerado em {quando}', { data: f.data, horario: f.horario, quando: dataHora(r.criado_em) })
      + (r.usuario ? t(' por {nome}', { nome: r.usuario }) : '')
    : tituloResultado();
  desenharResumo(); desenharMunicipios(); desenharProblemas(); desenharComparativo();
}

function tituloResultado() {
  const f = estado.formulario;
  return t('{titulo} · {data}, {horario}', { titulo: estado.passo === 5 ? t('Avisos para a rádio') : t('Conferir o resultado'), data: f.data, horario: f.horario })
    + (estado.resultado?.id ? t(' · aviso nº {id}', { id: estado.resultado.id }) : '');
}

function desenharHistorico() {
  const lista = historicoFiltrado();
  const itens = lista.map(a => {
    const ucs = a.municipios.reduce((s, m) => s + m.ucs, 0), com = a.municipios.reduce((s, m) => s + m.comunidades.length, 0);
    const seg = a.municipios.reduce((s, m) => s + (m.segundos || 0), 0), [dia, mes] = a.data.split('/');
    return no('button', { type: 'button', classe: 'item item-hist', 'data-historico': a.id,
      'aria-current': estado.resultado?.id === a.id && estado.origem === 'historico' ? 'true' : null },
      no('span', { classe: 'data-bloco', 'aria-hidden': 'true' }, no('span', { classe: 'dia', texto: dia || a.data }),
        mes ? no('span', { classe: 'mes', texto: MES_CURTO(`2000-${mes}`).split('/')[0] }) : null),
      no('span', { classe: 'hist-corpo' },
        no('strong', { texto: `${a.data}, ${a.horario}` }),
        no('span', { classe: 'chips' }, a.municipios.length ? a.municipios.map(m => no('span', { classe: 'chip', texto: `${m.nome}/${m.uf}` }))
          : no('span', { classe: 'chip vazio', texto: t('nenhum município') })),
        no('span', { classe: 'meta', texto: t('{ucs} UCs · {comunidades} comunidades · cerca de {segundos} s no ar', { ucs: fmt(ucs), comunidades: fmt(com), segundos: fmt(seg) }) }),
        no('span', { classe: 'meta', texto: t('{texto} · aviso nº {id}', { texto: solicitadoTexto(a) || t('Gerado em {quando}', { quando: dataHora(a.criado_em) }), id: a.id }) }),
        no('span', { classe: 'chips' }, a.desligamento ? no('span', { classe: 'chip tipo', texto: estado.config?.tipos?.[a.desligamento.tipo] || a.desligamento.rotulo }) : null,
          a.idioma && a.idioma !== 'pt-BR' ? no('span', { classe: 'chip', lang: a.idioma, texto: estado.config?.idiomas?.[a.idioma] || a.idioma }) : null,
          a.status === 'cancelado' ? no('span', { classe: 'chip cancelado' }, no('span', { 'aria-hidden': 'true', texto: '✕ ' }), t('Cancelado')) : null,
          a.municipios.some(m => m.texto_final) ? no('span', { classe: 'selo final' }, no('span', { 'aria-hidden': 'true', texto: '✓ ' }), t('Texto final guardado')) : null)));
  });
  const total = estado.historico.length;
  $('contagemHistorico').textContent = total ? (lista.length === total ? t('{n} aviso(s).', { n: fmt(total) }) : t('{n} de {total} aviso(s).', { n: fmt(lista.length), total: fmt(total) })) : '';
  $('listaHistorico').replaceChildren(...(itens.length ? itens
    : [no('p', { classe: 'ajuda', texto: total ? t('Nenhum aviso com esse filtro.') : t('Nenhum aviso gerado ainda.') })]));
}

// ---- Comparativo: o aviso de hoje (fazenda a fazenda) x o aviso por comunidade ----
function linhaCusto(spotsHoje, spotsFarol) {
  const p = temPreco(), v = estado.radio.veiculacoes;
  const parte = n => `${rotuloSpots(n)}${p ? ` · ${reais(n * estado.radio.preco * v)}` : ''}`;
  const sufixo = v > 1 ? ` em ${fmt(v)} veiculações` : ' por veiculação';
  return `Rádio (spots de ${estado.config.radio.spot_segundos} s): ` + (spotsHoje === null ? `Farol ${parte(spotsFarol)}.`
    : `hoje ${parte(spotsHoje)} · Farol ${parte(spotsFarol)}` + (p ? ` · economia de ${reais((spotsHoje - spotsFarol) * estado.radio.preco * v)}${sufixo}.` : '.'));
}

function desenharCusto() {
  const ligado = !!estado.config?.radio && !!estado.radio;
  $('custoRadio').hidden = !ligado;
  if (!ligado) return;
  const c = estado.config.radio;
  $('custoRadioAjuda').textContent = `A rádio cobra por inserção (spot) de ${c.spot_segundos} s, não por segundo. ` +
    (c.preco_spot > 0 ? `Preço de referência, a confirmar com a emissora${c.fonte ? `: ${c.fonte}` : '.'} Mude o valor para recalcular.` : 'Informe o preço do spot para ver o valor em reais.');
}

function desenharComparativo() {
  const c = estado.painel?.comparativo;
  $('comparativoTotal').replaceChildren(...(c && c.municipios ? [no('div', { classe: 'cartao comp-total' },
    no('h2', { texto: t('Em todo o histórico da empresa') }),
    no('p', { texto: t('{n} aviso(s) por município com o aviso de hoje: {hoje} no ar fazenda a fazenda ({locais} locais citados) contra {farol} por comunidade ({comunidades} comunidades).',
      { n: fmt(c.municipios), hoje: tempoNoAr(c.segundos_hoje), locais: fmt(c.locais), farol: tempoNoAr(c.segundos_farol), comunidades: fmt(c.comunidades) }) }),
    c.segundos_farol < c.segundos_hoje ? no('p', { classe: 'comp-economia', texto: t('{pct}% menos tempo no ar', { pct: fmt(Math.round(100 * (1 - c.segundos_farol / c.segundos_hoje))) }) }) : null,
    estado.radio ? no('p', { classe: 'comp-custo', texto: linhaCusto(c.spots_hoje, c.spots_farol) }) : null)] : []));
  const r = estado.resultado;
  if (!r) return $('comparativo').replaceChildren(no('p', { classe: 'ajuda cartao',
    texto: t('Gere um aviso em "Novo aviso" (com a coluna local na planilha) ou abra um aviso do Histórico para comparar.') }));
  $('comparativo').replaceChildren(...r.municipios.map(m => {
    const cod = m.codigo_ibge, hoje = m.hoje, texto = estado.avisos[cod], seg = segundos(texto);
    const lado = (classe, titulo, numeros, corpo, acao) => no('section', { classe: `comp-lado ${classe}` },
      no('h3', { texto: titulo }), no('p', { classe: 'comp-numeros', texto: numeros }), corpo,
      acao && temAudio() && (acao === 'farol' || vozDoIdioma('pt-BR')) ? no('button', { type: 'button', 'data-comp': acao, 'data-codigo': cod, texto: t('Ouvir') }) : null,
      acao ? no('div', { id: `tocador-${acao}-${cod}`, classe: 'tocador' }) : null);
    // o aviso de hoje é sempre em português; o do Norte, no idioma do aviso (lang para o leitor de tela)
    const caixa = (txt, lang) => no('div', { classe: 'texto-longo', tabindex: '0', texto: txt, lang });
    const ladoHoje = hoje
      ? lado('hoje', t('Hoje: fazenda a fazenda'), t('{locais} locais · {palavras} palavras · cerca de {tempo} no ar',
          { locais: fmt(hoje.locais), palavras: fmt(hoje.palavras), tempo: tempoNoAr(hoje.segundos) }),
        hoje.texto ? caixa(hoje.texto, idiomaDoAviso()) : no('p', { classe: 'ajuda', texto: t('O histórico guarda só as contagens do aviso de hoje (o texto lista imóveis e ruas).') }),
        hoje.texto ? 'hoje' : null)
      : lado('hoje', t('Hoje: fazenda a fazenda'), t('sem o aviso de hoje'),
        no('p', { classe: 'ajuda', texto: t('A planilha não trouxe a coluna local (o que o aviso de hoje cita para cada UC: o imóvel no rural, a rua no urbano). Sem ela não dá para montar o aviso de hoje.') }), null);
    const ladoFarol = lado('farol', t('Norte: por comunidade'), t('{comunidades} comunidades · {palavras} palavras · cerca de {tempo} no ar',
      { comunidades: fmt(m.comunidades.length), palavras: fmt(palavras(texto)), tempo: tempoNoAr(seg) }), caixa(texto, idiomaDoAviso()), 'farol');
    const barras = hoje ? no('div', { classe: 'comp-barras', role: 'img', 'aria-label': t('Hoje {hoje}, Norte {farol}', { hoje: tempoNoAr(hoje.segundos), farol: tempoNoAr(seg) }) },
      no('span', { classe: 'comp-rotulo', texto: t('Hoje') }), no('span', { classe: 'comp-barra hoje' }, no('span', { estilo: { width: '100%' } })),
      no('span', { classe: 'comp-tempo', texto: tempoNoAr(hoje.segundos) }),
      no('span', { classe: 'comp-rotulo', texto: 'Norte' }),
      no('span', { classe: 'comp-barra farol' }, no('span', { estilo: { width: `${Math.max(1, Math.round(100 * seg / Math.max(1, hoje.segundos)))}%` } })),
      no('span', { classe: 'comp-tempo', texto: tempoNoAr(seg) })) : null;
    return no('article', { classe: 'cartao comp', 'data-codigo': cod },
      no('div', { classe: 'mun-cab' }, no('h2', { texto: `${m.nome}/${m.uf}` }),
        // o selo sai dos mesmos segundos das barras; verde só quando o Norte é mais curto
        hoje && seg < hoje.segundos ? no('span', { classe: 'comp-economia', texto: t('{pct}% menos tempo no ar', { pct: fmt(Math.round(100 * (1 - seg / hoje.segundos))) }) })
          : hoje && m.mesmo_tamanho ? no('span', { classe: 'chip', texto: t('mesmo tamanho: poucos locais') }) : null),
      barras, estado.radio ? no('p', { classe: 'comp-custo', texto: linhaCusto(hoje ? spotsDe(hoje.segundos) : null, spotsDe(seg)) }) : null,
      no('div', { classe: 'comp-lados' }, ladoHoje, ladoFarol));
  }));
}

// ---- Relatório do período (mensal) ----
function desenharFiltrosRelatorio() {
  const op = estado.opcoesRelatorio;
  if (!$('relMes').options.length) $('relMes').replaceChildren(...ultimosMeses().map(([v, rot]) => no('option', { value: v, texto: rot })));
  if (!$('relAno').options.length) {
    const ano = new Date().getFullYear();
    $('relAno').replaceChildren(...[ano, ano - 1, ano - 2].map(a => no('option', { value: String(a), texto: String(a) })));
  }
  const modo = $('relModo').value;
  $('relMesRotulo').hidden = modo !== 'mes'; $('relAnoRotulo').hidden = modo !== 'ano';
  $('relInicioRotulo').hidden = $('relFimRotulo').hidden = modo !== 'intervalo';
  $('relEnviar').hidden = !pode('enviar_relatorio');
  if (!op) return;
  const preencher = (id, todos, itens) => {
    const atual = $(id).value;
    $(id).replaceChildren(no('option', { value: '', texto: t(todos) }), ...itens.map(([v, rot]) => no('option', { value: String(v), texto: rot, selected: String(v) === atual })));
  };
  preencher('relMunicipio', 'Todos', op.municipios);
  preencher('relTipo', 'Todos', op.tipos.map(x => [x, estado.config?.tipos?.[x] || op.rotulos_tipos[x] || x]));
  preencher('relRadio', 'Todas', op.radios);
  preencher('relPessoa', 'Todas', op.pessoas.map(p => [p, p]));
}

// o documento do relatório (o mesmo do PDF e do CSV): alertas, resumo com as comparações (↑↓ %), seções e "Como calculamos"
function documentoNaTela(doc, subtitulo) {
  const tabela = (cab, linhas, titulo = '') => linhas.length
    ? no('div', { classe: 'rolagem', tabindex: '0', role: 'region', 'aria-label': titulo }, no('table', { classe: 'tabela' }, no('caption', { classe: 'visualmente-oculto', texto: titulo }),
      no('thead', {}, no('tr', {}, cab.map(c => no('th', { scope: 'col', texto: c })))),
      no('tbody', {}, linhas.map(l => no('tr', {}, l.map((v, i) => no(i ? 'td' : 'th', { scope: i ? null : 'row', texto: v == null || v === '' ? '—' : String(v) })))))))
    : no('p', { classe: 'ajuda', texto: t('Nada neste período.') });
  const grafico = s => {
    const f = v => s.formato === 'dinheiro' ? dinheiro(v) : fmt(v);
    const itens = s.rotulos.map((r, i) => {
      const projetado = s.valores[i] == null && s.projecao?.[i] != null;
      return { r, v: Number((projetado ? s.projecao[i] : s.valores[i]) || 0), projetado };
    });
    const max = Math.max(1, ...itens.map(x => x.v));
    if (!itens.length) return no('p', { classe: 'ajuda', texto: t('Nada neste período.') });
    return no('div', { classe: 'barras grafico-doc', estilo: { gridTemplateColumns: `repeat(${itens.length}, minmax(0, 1fr))` }, role: 'img',
      'aria-label': itens.map(x => `${x.r}: ${f(x.v)}${x.projetado ? t(' (projeção)') : ''}`).join(', ') },
      itens.map(x => no('div', { classe: 'barra-mes', title: `${x.r}: ${f(x.v)}${x.projetado ? t(' (projeção)') : ''}` },
        no('span', { classe: 'barra-valor', texto: x.v && s.formato !== 'dinheiro' ? f(x.v) : '' }),
        no('span', { classe: `barra${x.projetado ? ' barra-projecao' : ''}`, estilo: { height: `${Math.round(x.v / max * 100)}%` } }),
        no('span', { classe: 'barra-mes-rotulo', texto: x.r }))));
  };
  const conteudo = s => s.tipo === 'tabela' ? tabela(s.colunas, s.linhas, s.titulo) : s.tipo === 'grafico' ? grafico(s)
    : s.tipo === 'lista' ? (s.itens.length ? no('ul', { classe: 'como' }, s.itens.map(x => no('li', { texto: x }))) : no('p', { classe: 'ajuda', texto: t('Nada.') }))
    : no('p', { texto: s.texto });
  const chip = c => no('span', { classe: `chip comp ${c.texto[0] === '↑' ? 'sobe' : c.texto[0] === '↓' ? 'desce' : ''}`, texto: t('{texto} vs {contra}', c) });
  return [
    no('h2', { classe: 'subtitulo', texto: doc.titulo }),
    subtitulo ? no('p', { classe: 'ajuda', texto: subtitulo }) : null,
    ...(doc.alertas || []).map(a => no('div', { classe: 'alerta-amarelo', role: 'status' }, no('strong', {}, no('span', { 'aria-hidden': 'true', texto: '⚠ ' }), a))),
    no('div', { classe: 'kpis' }, doc.resumo.map(i => no('div', { classe: 'kpi' }, no('span', { classe: 'kpi-rotulo', texto: i.rotulo }),
      no('strong', { classe: 'kpi-valor', texto: i.valor }),
      i.comparacoes?.length ? no('span', { classe: 'kpi-extra comps' }, i.comparacoes.map(chip)) : null))),
    ...doc.secoes.map(s => no('section', { classe: 'cartao dash-bloco' }, no('h2', { texto: s.titulo }), conteudo(s))),
    no('section', { classe: 'cartao dash-bloco' }, no('h2', { texto: t('Como calculamos') }),
      no('ul', { classe: 'como' }, doc.como_calculamos.map(x => no('li', { texto: x })))),
  ];
}

function desenharRelatorio() {
  desenharFiltrosRelatorio();
  const r = estado.relatorio;
  $('relatorio').replaceChildren(...(r ? documentoNaTela(r.documento, r.subtitulo) : []));
  desenharVias();
}

function desenharVias() {
  const vias = estado.vias || [];
  $('listaVias').replaceChildren(vias.length ? no('div', { classe: 'rolagem', tabindex: '0', role: 'region', 'aria-label': t('Segundas vias') }, no('table', { classe: 'tabela' },
    no('caption', { classe: 'visualmente-oculto', texto: t('Segundas vias') }),
    no('thead', {}, no('tr', {}, ['Relatório', 'Gerado por', 'Quando', 'Código', 'Ações'].map(c => no('th', { scope: 'col', texto: t(c) })))),
    no('tbody', {}, vias.slice(0, 30).map(v => no('tr', {}, no('th', { scope: 'row', texto: v.titulo }), no('td', { texto: v.por }),
      no('td', { texto: dataHora(v.criado_em) }), no('td', { texto: v.codigo }),
      no('td', {}, no('button', { type: 'button', 'data-via': String(v.id), 'aria-label': `${t('Baixar a via')}: ${v.titulo}`, texto: t('Baixar a via') })))))))
    : no('p', { classe: 'ajuda', texto: t('Nenhum relatório em PDF ainda. Cada PDF gerado ganha uma segunda via guardada, igual (mesmo SHA-256).') }));
}

// ---- Simulador de economia (Relatórios): o documento do servidor; o formulário só para quem altera (Admin da empresa) ----
function desenharSimulador() {
  if (!$('simPeriodo').options.length) {
    const ano = new Date().getFullYear();
    $('simPeriodo').replaceChildren(...[ano, ano - 1].map(a => no('option', { value: `ano:${a}`, texto: t('Ano de {ano}', { ano: a }) })),
      ...ultimosMeses().map(([v, rot]) => no('option', { value: `mes:${v}`, texto: rot })));
  }
  const s = estado.simulador, form = $('formSimulador');
  $('vista-simulador').append(form);   // o formulário volta para fora antes de redesenhar (ele muda de lugar)
  form.hidden = !s?.pode_editar;
  if (s?.pode_editar && !form.contains(document.activeElement)) {
    $('simGastoMin').value = s.valores.gasto_min ?? '';
    $('simGastoMax').value = s.valores.gasto_max ?? '';
    $('simPct').value = s.valores.pct_tempo != null ? Number(s.valores.pct_tempo) : 100;
    $('simNota').value = s.valores.nota ?? '';
  }
  if (!s) return $('simulador').replaceChildren();
  const n = s.documento.numeros, est = n.estimativa, real = n.realizado;
  // cartão: rótulo pequeno, número grande numa linha (o completo no title e para o leitor de tela) e uma legenda curta
  const cartao = (rotulo, curto, completo, legenda, classe = '') => no('div', { classe: `sim-cartao ${classe}` },
    no('span', { classe: 'sim-rotulo', texto: rotulo }),
    no('strong', { classe: 'sim-numero', title: completo }, no('span', { 'aria-hidden': 'true', texto: curto }), no('span', { classe: 'visualmente-oculto', texto: completo })),
    legenda ? no('span', { classe: 'sim-legenda', texto: legenda }) : null);
  const valor = ([a, b]) => { a = Number(a); b = Number(b);
    return a === b ? [a < 1e6 ? dinheiro(a) : moedaCurta(a), dinheiro(a)] : [moedaCurta(a, b), t('{a} a {b}', { a: dinheiro(a), b: dinheiro(b) })]; };
  const pct = Number(n.reducao_pct).toLocaleString(IDIOMA, { maximumFractionDigits: 1 }) + '%';
  const fonte = n.fonte !== 'empresa' ? t('medição de validação (Leopoldina)')
    : n.avisos === 1 ? t('média real de 1 aviso da empresa') : t('média real de {n} avisos da empresa', { n: fmt(n.avisos) });
  const pctTempo = Number(n.pct_tempo).toLocaleString(IDIOMA, { maximumFractionDigits: 2 });
  const grupo = (titulo, ...filhos) => no('section', { classe: 'sim-grupo', 'aria-label': titulo }, no('h2', { classe: 'sim-titulo', texto: titulo }), ...filhos);
  const reducao = cartao(t('Redução do tempo no ar'), pct, pct, fonte, 'destaque');
  const estimativa = est
    ? grupo(t('Estimativa'),
      no('p', { classe: 'sim-gasto', texto: t('Gasto mensal informado: {gasto}', { gasto: valor([n.gasto_min, n.gasto_max ?? n.gasto_min])[1] }) + (n.nota ? ` · ${n.nota}` : '') }),
      no('div', { classe: 'sim-cartoes quatro' }, reducao,
        cartao(t('Economia mensal estimada'), ...valor(est.mensal), t('{pct}% do gasto cobrado por tempo', { pct: pctTempo })),
        cartao(t('Economia anual estimada'), ...valor(est.anual), t('economia mensal × 12')),
        cartao(t('Anual, cenário conservador'), ...valor(est.conservador_anual), t('50% do gasto cobrado por tempo'))))
    : grupo(t('Estimativa'), no('div', { classe: 'sim-cartoes' }, reducao),
      no('div', { classe: 'sim-destaque', id: 'simDestaque' }, no('p', { classe: 'sim-destaque-texto', texto: t('Informe o gasto mensal com rádio para ver a economia estimada') }),
        s.pode_editar ? null : no('p', { classe: 'ajuda', texto: t('O Admin da empresa informa o gasto mensal com rádio aqui no simulador.') })));
  const realizado = grupo(t('Realizado'), no('div', { classe: 'sim-cartoes' },
    cartao(t('Já economizado'), ...valor([real.total, real.total]), t('calculada + informada')),
    cartao(t('Envios registrados'), fmt(real.envios), fmt(real.envios), t('no período'))));
  const como = no('section', { classe: 'cartao dash-bloco' }, no('h2', { texto: t('Como calculamos') }),
    no('ul', { classe: 'como' }, s.documento.como_calculamos.map(x => no('li', { texto: x }))));
  $('simulador').replaceChildren(no('p', { classe: 'ajuda', texto: s.subtitulo }), estimativa, realizado, como);
  // sem o gasto, os campos ficam no bloco de destaque (botão Calcular); com o gasto, o formulário vai para depois dos cartões
  const vazio = !est, titulo = $('simFormTitulo'), botao = $('simSalvar');
  titulo.hidden = vazio;
  botao.dataset.t = vazio ? 'Calcular' : 'Salvar'; botao.textContent = t(botao.dataset.t);
  if (s.pode_editar) vazio ? $('simDestaque').append(form) : realizado.after(form);
}

// moeda curta para os cartões ("R$ 1,31 mi", "R$ 109–205 mil"); o valor completo vai no title e no texto do leitor de tela
function moedaCurta(a, b = a) {
  const max = Math.max(Math.abs(a), Math.abs(b));
  const [div, sufixo, casas] = max >= 1e6 ? [1e6, t('mi'), 2] : max >= 1e4 ? [1e3, t('mil'), 0] : [1, '', 2];
  const n = v => (v / div).toLocaleString(IDIOMA, { minimumFractionDigits: casas, maximumFractionDigits: casas });
  return `R$ ${a === b ? n(a) : `${n(a)}–${n(b)}`}${sufixo ? ` ${sufixo}` : ''}`;
}

// ---- Dashboard: só números do histórico da empresa ----
function desenharPainel() {
  const d = estado.painel;
  if (!d) return $('painelDash').replaceChildren();
  const tot = d.totais;
  const kpi = (rotulo, valor, extra) => no('div', { classe: 'kpi' }, no('span', { classe: 'kpi-rotulo', texto: t(rotulo) }),
    no('strong', { classe: 'kpi-valor', texto: valor }), extra ? no('span', { classe: 'kpi-extra', texto: extra }) : null);
  const mesKpi = d.mes ? no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: t('Este mês ({mes})', { mes: d.mes.mes }) }),
    no('div', { classe: 'kpis' },
      kpi('Gasto com rádio', dinheiro(d.mes.gasto), t('{envios} envio(s), {confirmados} confirmado(s)', { envios: fmt(d.mes.envios), confirmados: fmt(d.mes.confirmados) })),
      kpi('Economizado', dinheiro(Number(d.mes.economia_calculada) + Number(d.mes.economia_informada)),
        t('{calculada} calculada · {informada} informada', { calculada: dinheiro(d.mes.economia_calculada), informada: dinheiro(d.mes.economia_informada) })),
      kpi('Desligamentos', fmt(d.mes.desligamentos), tempoArTexto(d.mes.tempo_economizado)),
      kpi('No prazo', d.mes.pct_no_prazo == null ? '—' : `${d.mes.pct_no_prazo.toLocaleString(IDIOMA)}%`, t('{n} com envio', { n: fmt(d.mes.com_envio) })))) : null;
  const kpis = no('div', { classe: 'kpis' },
    kpi('Avisos gerados', fmt(tot.avisos), t('{n} nos últimos 30 dias', { n: fmt(tot.ultimos_30_dias) })),
    kpi('UCs avisadas', fmt(tot.ucs)),
    kpi('Comunidades citadas', fmt(tot.comunidades)),
    kpi('Municípios', fmt(tot.municipios)),
    kpi('Com equipamento vital', fmt(tot.com_equipamento_vital), t('avisos com prazo de 5 dias úteis')),
    kpi('Tempo médio no ar', t('{n} s', { n: fmt(tot.segundos_medio) }), t('{n} de {total} textos finais guardados', { n: fmt(tot.textos_finais), total: fmt(tot.avisos_municipio) })));
  const maxMes = Math.max(1, ...d.por_mes.map(m => m.avisos));
  const meses = no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: t('Avisos por mês') }),
    no('div', { classe: 'barras', role: 'img', 'aria-label': d.por_mes.map(m => t('{mes}: {n}', { mes: MES_CURTO(m.mes), n: m.avisos })).join(', ') },
      d.por_mes.map(m => no('div', { classe: 'barra-mes', title: t('{mes}: {n} aviso(s), {ucs} UCs', { mes: MES_CURTO(m.mes), n: fmt(m.avisos), ucs: fmt(m.ucs) }) },
        no('span', { classe: 'barra-valor', texto: m.avisos ? fmt(m.avisos) : '' }),
        no('span', { classe: 'barra', estilo: { height: `${Math.round(m.avisos / maxMes * 100)}%` } }),
        no('span', { classe: 'barra-mes-rotulo', texto: MES_CURTO(m.mes) })))));
  const ranking = (titulo, itens, rotulo, vazio) => {
    const max = Math.max(1, ...itens.map(i => i.avisos));
    return no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: t(titulo) }),
      itens.length ? no('ol', { classe: 'ranking' }, itens.map(i => no('li', {},
        no('span', { classe: 'ranking-nome', texto: rotulo(i) }),
        no('span', { classe: 'ranking-barra', 'aria-hidden': 'true' }, no('span', { estilo: { width: `${Math.round(i.avisos / max * 100)}%` } })),
        no('span', { classe: 'ranking-valor', texto: t('{n} · {ucs} UCs', { n: fmt(i.avisos), ucs: fmt(i.ucs) }) }))))
        : no('p', { classe: 'ajuda', texto: t(vazio) }));
  };
  const proximos = no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: t('Próximos desligamentos') }),
    d.proximos.length ? no('ul', { classe: 'proximos' }, d.proximos.map(x => no('li', {},
      no('span', { classe: 'chip', texto: dataLonga(x.data) }),
      no('span', { texto: t('{horario} · {municipios} · {ucs} UCs', { horario: x.horario, municipios: x.municipios.join(', ') || t('nenhum município'), ucs: fmt(x.ucs) }) }))))
      : no('p', { classe: 'ajuda', texto: t('Nenhum desligamento com data a partir de hoje.') }));
  $('painelDash').replaceChildren(...[mesKpi].filter(Boolean), kpis, meses, proximos,
    ranking('Municípios com mais avisos', d.municipios, i => `${i.nome}/${i.uf}`, 'Nenhum aviso ainda.'),
    ranking('Comunidades mais citadas', d.comunidades, i => `${semSufixo(i.nome)} (${i.municipio})`, 'Nenhum aviso ainda.'));
}

// ---- Pergunte ao painel: a IA escolhe uma consulta fixa; os números vêm do histórico da empresa ----
const perguntaLigada = () => !!estado.config?.ia?.ativa;

function descreverConsulta(r) {
  const p = r.parametros, partes = [p.periodo_dias ? `últimos ${fmt(p.periodo_dias)} dias` : 'todo o histórico'];
  if (p.municipio) partes.push(p.municipio);
  return `${r.rotulo} · ${partes.join(' · ')}`;
}

function respostaDaPergunta(p) {
  if (!p) return [];
  if (p.pedindo) return [no('p', { classe: 'ajuda', texto: 'Consultando o histórico…' })];
  if (p.erro) return [no('p', { classe: 'alerta', texto: p.erro })];
  const r = p.resposta;
  if (!r.entendida) return [no('p', { classe: 'resposta-texto', texto: r.resposta }),
    no('ul', { classe: 'proximos' }, r.exemplos.map(t => no('li', { texto: t })))];
  const t = r.tabela;
  return [no('p', { classe: 'resposta-texto', texto: r.resposta }),
    t.linhas.length ? no('div', { classe: 'tabela-rolavel' }, no('table', { classe: 'tabela-pergunta' },
      no('thead', {}, no('tr', {}, t.colunas.map(c => no('th', { texto: c })))),
      no('tbody', {}, t.linhas.map(l => no('tr', {}, l.map(v => no('td', { texto: typeof v === 'number' ? fmt(v) : v }))))))) : null,
    no('p', { classe: 'ajuda' }, no('span', { classe: 'selo final', texto: 'Conferido' }),
      ` Consulta: ${descreverConsulta(r)}. ` + (r.resposta_por === 'ia'
        ? 'Texto escrito pela IA; todos os números dele estão na tabela.' : 'Texto montado a partir da tabela.'))];
}

function desenharPergunta() {
  $('perguntaPainel').hidden = !perguntaLigada();
  if (!perguntaLigada()) return;
  const c = estado.config.ia;
  $('perguntaAjuda').textContent = (c.provedor === 'simulado' ? 'IA simulada nesta demonstração (entende perguntas simples). ' : '')
    + 'Escreva a pergunta em português. A IA só escolhe a consulta; os números vêm sempre do histórico da empresa.';
  $('textoPergunta').maxLength = c.max_pergunta;
  $('botaoPergunta').disabled = !!estado.pergunta?.pedindo;
  $('exemplosPergunta').replaceChildren(...c.perguntas_exemplo.map(t => no('button', { type: 'button', classe: 'chip-pergunta', 'data-pergunta': t, texto: t })));
  $('respostaPergunta').replaceChildren(...respostaDaPergunta(estado.pergunta));
}

function desenharUsuarios() {
  $('novoPerfil').replaceChildren(...Object.entries(estado.perfis).map(([k, n]) => no('option', { value: k, texto: t(n), selected: k === 'operador' })));
  if (!$('novoMunicipios').options.length) $('novoMunicipios').replaceChildren(...municipiosDaConcessao().map(([c, n]) => no('option', { value: c, texto: n })));
  const campo = (rotulo, el) => no('label', { classe: 'campo-linha' }, no('span', { texto: rotulo }), el);
  $('listaUsuarios').replaceChildren(...estado.usuarios.map(x => {
    const nome = no('input', { id: `usu-${x.id}-nome`, 'data-campo': 'nome', maxlength: '120', autocomplete: 'off', required: true });
    nome.value = x.nome;
    return no('div', { classe: 'item usuario-linha com-erros', 'data-usuario': x.id },
      no('div', {}, no('strong', { texto: x.nome }), no('br'),
        no('span', { classe: 'meta', texto: t('{email} · {acesso}', { email: x.email, acesso: x.ultimo_acesso ? t('último acesso {quando}', { quando: dataHora(x.ultimo_acesso) }) : t('nunca entrou') })
          + (x.trocar_senha ? t(' · senha temporária') : '') }), no('br'),
        no('span', { classe: 'meta', texto: t('Municípios: {lista}', { lista: x.municipios.length ? x.municipios.map(nomeMunicipio).join(', ') : t('todos (nenhum escolhido)') }) }),
        x.status === 'bloqueado' ? no('span', { classe: 'chip cancelado' }, no('span', { 'aria-hidden': 'true', texto: '✕ ' }), t('Bloqueado')) : null),
      no('div', { classe: 'controles' },
        campo(t('Nome de {nome}', { nome: x.nome }), nome),
        campo(t('Perfil de {nome}', { nome: x.nome }), no('select', { id: `usu-${x.id}-perfil`, 'data-campo': 'perfil' },
          Object.entries(estado.perfis).map(([k, n]) => no('option', { value: k, texto: t(n), selected: k === x.perfil })))),
        campo(t('Situação de {nome}', { nome: x.nome }), no('select', { id: `usu-${x.id}-status`, 'data-campo': 'status' },
          [['ativo', 'Ativo'], ['bloqueado', 'Bloqueado']].map(([k, n]) => no('option', { value: k, texto: t(n), selected: k === x.status })))),
        campo(t('Municípios de {nome} (Ctrl para vários)', { nome: x.nome }), no('select', { id: `usu-${x.id}-municipios`, 'data-campo': 'municipios', multiple: true, size: '3' },
          municipiosDaConcessao().map(([c, n]) => no('option', { value: c, texto: n, selected: x.municipios.includes(c) })))),
        no('button', { type: 'button', 'data-acao-usuario': 'salvar', 'aria-label': `${t('Salvar')}: ${x.nome}`, texto: t('Salvar') }),
        no('button', { type: 'button', 'data-acao-usuario': 'senha', 'aria-label': `${t('Nova senha temporária')}: ${x.nome}`, texto: t('Nova senha temporária') })));
  }));
}

function desenharEmpresas() {
  const area = id => estado.mapaEmpresas?.empresas.find(x => x.id === id)?.municipios.length || 0;
  const linhas = estado.empresas.map(e => no('tr', { 'data-empresa': e.id },
    no('th', { scope: 'row' }, no('button', { type: 'button', classe: 'link', 'data-empresa-acao': 'ficha', 'aria-label': t('Ficha de {nome} (e a área no mapa)', { nome: e.nome }), texto: e.nome })),
    no('td', { texto: e.sigla }),
    no('td', { classe: 'codigo', texto: e.cnpj || '—' }), no('td', { texto: e.dominio }),
    no('td', {}, no('span', { classe: `chip ${e.status === 'suspensa' ? 'cancelado' : ''}` }, no('span', { 'aria-hidden': 'true', texto: e.status === 'suspensa' ? '✕ ' : '✓ ' }),
      e.status === 'suspensa' ? t('Suspensa') : t('Ativa'))),
    no('td', { texto: fmt(e.usuarios) }), no('td', { texto: fmt(e.avisos) }),
    no('td', { texto: area(e.id) ? fmt(area(e.id)) : '⚠ ' + t('Área de atuação não cadastrada') }),
    no('td', {}, no('span', { classe: 'acoes' }, no('button', { type: 'button', 'data-empresa-acao': 'area', 'aria-label': t('Área de atuação de {nome}', { nome: e.nome }), texto: t('Área') }),
      no('button', { type: 'button', 'data-empresa-acao': 'editar', 'aria-label': t('Editar {nome}', { nome: e.nome }), texto: t('Editar') }),
      no('button', { type: 'button', classe: e.status === 'ativa' ? 'perigo' : '', 'data-empresa-acao': e.status === 'ativa' ? 'suspensa' : 'ativa',
        'aria-label': t(e.status === 'ativa' ? 'Suspender {nome}' : 'Reativar {nome}', { nome: e.nome }), texto: e.status === 'ativa' ? t('Suspender') : t('Reativar') })))));
  $('listaEmpresas').replaceChildren(no('div', { classe: 'rolagem', tabindex: '0', role: 'region', 'aria-label': t('Empresas') }, no('table', { classe: 'tabela' },
    no('caption', { classe: 'visualmente-oculto', texto: t('Empresas') }),
    no('thead', {}, no('tr', {}, ['Empresa', 'Sigla', 'CNPJ', 'Domínio', 'Situação', 'Usuários', 'Avisos', 'Municípios', 'Ações'].map(c => no('th', { scope: 'col', texto: t(c) })))),
    no('tbody', {}, linhas))));
}

// ---- Mapa das empresas e área de atuação (Admin do Norte; só cadastro, área e contagens) ----
// cada empresa: uma cor e uma hachura diferentes (nunca só a cor); a suspensa, cinza tracejado
const COR_EMPRESA = ['#1663C7', '#B07800', '#1B7D4B', '#7A4FD1', '#C2410C', '#0E7490', '#BE185D', '#4D7C0F'];
const HACHURA = ['diagonal', 'contra', 'horizontal', 'vertical', 'xadrez', 'pontos', 'cruz', 'larga'];
const COR_SUSPENSA = '#6B7A88', COR_SOBREPOSICAO = '#B42318';
const ehFarol = () => estado.usuario?.perfil === 'admin_farol';
const corDaEmpresa = (e, i) => e.status === 'suspensa' ? COR_SUSPENSA : COR_EMPRESA[i % COR_EMPRESA.length];
const hachuraDaEmpresa = (e, i) => e.status === 'suspensa' ? 'suspensa' : HACHURA[i % HACHURA.length];
let camadaEmpresas, camadaEditorArea;
const SVG = 'http://www.w3.org/2000/svg';
const svg = (tag, atributos = {}, ...filhos) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(atributos)) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
};
// o desenho de cada hachura (12 x 12, repetido), na cor da empresa
function padrao(id, tipo, cor) {
  const linha = (x1, y1, x2, y2, w = 1.6) => svg('line', { x1, y1, x2, y2, stroke: cor, 'stroke-width': w, 'stroke-opacity': .75 });
  const desenho = {
    diagonal: [linha(0, 12, 12, 0), linha(-3, 3, 3, -3), linha(9, 15, 15, 9)],
    contra: [linha(0, 0, 12, 12), linha(-3, 9, 3, 15), linha(9, -3, 15, 3)],
    horizontal: [linha(0, 6, 12, 6)],
    vertical: [linha(6, 0, 6, 12)],
    xadrez: [linha(0, 6, 12, 6, 1.2), linha(6, 0, 6, 12, 1.2)],
    pontos: [svg('circle', { cx: 6, cy: 6, r: 1.8, fill: cor, 'fill-opacity': .8 })],
    cruz: [linha(0, 12, 12, 0, 1.2), linha(0, 0, 12, 12, 1.2)],
    larga: [linha(0, 12, 12, 0, 3.2)],
    suspensa: [linha(0, 12, 12, 0, 1), linha(6, 18, 18, 6, 1)],
  }[tipo];
  return svg('pattern', { id, width: 12, height: 12, patternUnits: 'userSpaceOnUse' },
    svg('rect', { width: 12, height: 12, fill: cor, 'fill-opacity': .14 }), ...desenho);
}
// as hachuras ficam no SVG do mapa (o Leaflet desenha os polígonos nele); fill: url(#hachura-…)
function garantirHachuras() {
  const raiz = mapa?.getPanes().overlayPane.querySelector('svg');
  if (!raiz || !estado.mapaEmpresas) return;
  raiz.querySelector('defs.hachuras')?.remove();
  raiz.prepend(svg('defs', { class: 'hachuras' }, ...estado.mapaEmpresas.empresas.map((e, i) => padrao(`hachura-${e.id}`, hachuraDaEmpresa(e, i), corDaEmpresa(e, i)))));
}
const amostraEmpresa = (e, i) => svg('svg', { width: 22, height: 16, viewBox: '0 0 22 16', 'aria-hidden': 'true', class: 'amostra-empresa' },
  svg('defs', {}, padrao(`amostra-${e.id}`, hachuraDaEmpresa(e, i), corDaEmpresa(e, i))),
  svg('rect', { x: 1, y: 1, width: 20, height: 14, rx: 3, fill: `url(#amostra-${e.id})`, stroke: corDaEmpresa(e, i), 'stroke-width': 1.5,
    ...(e.status === 'suspensa' ? { 'stroke-dasharray': '3 2' } : {}) }));

// Model: as feições de cada município de alguma área, pelo código
const feicaoDe = c => estado.mapaEmpresas?.porCodigo?.[c];
const nomeDoMunicipio = c => feicaoDe(c) ? `${feicaoDe(c).properties.nome}/${feicaoDe(c).properties.uf}` : c;
// onde escrever a sigla: o ponto (sempre dentro de um município) mais perto do meio da área
function pontoDaSigla(codigos) {
  const pts = codigos.map(c => feicaoDe(c)?.properties.ponto).filter(Boolean);
  if (!pts.length) return null;
  const meio = [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
  return pts.reduce((m, p) => (p[0] - meio[0]) ** 2 + (p[1] - meio[1]) ** 2 < (m[0] - meio[0]) ** 2 + (m[1] - meio[1]) ** 2 ? p : m);
}

async function carregarMapaEmpresas() {
  const m = await api('/api/empresas/mapa');
  m.porCodigo = Object.fromEntries(m.municipios.features.map(f => [f.properties.codigo_ibge, f]));
  estado.mapaEmpresas = m;
  desenharMapaEmpresas(); desenharLegendaEmpresas(); desenharSobreposicao();
}

// View: as áreas (cor + hachura + contorno), a sigla no meio, a sobreposição em vermelho tracejado
function desenharMapaEmpresas() {
  camadaEmpresas?.remove();
  camadaEmpresas = null;
  const m = estado.mapaEmpresas;
  if (!mapa || !m || !ehFarol()) return;
  const camadas = [];
  m.empresas.forEach((e, i) => {
    if (estado.empresasOcultas.has(e.id) || !e.municipios.length) return;
    const cor = corDaEmpresa(e, i);
    camadas.push(L.geoJSON({ type: 'FeatureCollection', features: e.municipios.map(feicaoDe).filter(Boolean) }, {
      style: () => ({ color: cor, weight: 1.4, opacity: .9, dashArray: e.status === 'suspensa' ? '6 4' : null, fillColor: `url(#hachura-${e.id})`, fillOpacity: 1 }),
      onEachFeature: (f, l) => {
        l.bindTooltip(() => no('span', { texto: `${e.sigla} · ${f.properties.nome}/${f.properties.uf}`
          + (e.status === 'suspensa' ? ` · ${t('Suspensa')}` : '') }), { sticky: true });
        l.on('click', () => abrirFichaEmpresa(e.id, false));
      },
    }));
    const p = pontoDaSigla(e.municipios);
    if (p) camadas.push(L.marker(p, { interactive: false, keyboard: false,
      icon: L.divIcon({ className: `rotulo-empresa${e.status === 'suspensa' ? ' suspensa' : ''}`, html: no('span', { texto: e.sigla }), iconSize: null }) }));
  });
  const sobre = Object.keys(m.sobreposicao).map(feicaoDe).filter(Boolean);
  if (sobre.length) camadas.push(L.geoJSON({ type: 'FeatureCollection', features: sobre }, {
    style: () => ({ color: COR_SOBREPOSICAO, weight: 3, dashArray: '2 5', fill: false }),
    onEachFeature: (f, l) => l.bindTooltip(() => no('span', { texto: t('Sobreposição: {nome} em {empresas}',
      { nome: `${f.properties.nome}/${f.properties.uf}`, empresas: m.sobreposicao[f.properties.codigo_ibge].join(', ') }) }), { sticky: true }),
  }));
  camadaEmpresas = L.featureGroup(camadas).addTo(mapa);
  garantirHachuras();
  camadaEditorArea?.bringToFront();
}

// a legenda: sigla, nome, situação e municípios; cada empresa liga e desliga no mapa; a sem área, com o botão de cadastrar
function desenharLegendaEmpresas() {
  const m = estado.mapaEmpresas;
  $('legendaEmpresas').hidden = !ehFarol() || !m;
  $('legenda').hidden = ehFarol();
  if (!m || !ehFarol()) return;
  const itens = m.empresas.map((e, i) => {
    const visivel = !estado.empresasOcultas.has(e.id);
    return no('li', { classe: 'legenda-empresa' },
      no('button', { type: 'button', classe: 'alternar-empresa', 'data-empresa-mapa': e.id, 'aria-pressed': String(visivel),
        'aria-label': t(visivel ? 'Esconder {sigla} no mapa' : 'Mostrar {sigla} no mapa', { sigla: e.sigla }) },
        amostraEmpresa(e, i), no('span', { classe: 'legenda-sigla', texto: e.sigla }),
        no('span', { classe: 'legenda-nome', texto: e.nome })),
      no('span', { classe: 'meta' },
        no('span', { classe: `chip ${e.status === 'suspensa' ? 'cancelado' : ''}`, texto: (e.status === 'suspensa' ? '✕ ' : '✓ ') + t(e.status === 'suspensa' ? 'Suspensa' : 'Ativa') }),
        ' ', e.municipios.length ? t('{n} município(s)', { n: fmt(e.municipios.length) }) : ''),
      e.municipios.length ? null : no('span', { classe: 'sem-area' }, no('span', { texto: '⚠ ' + t('Área de atuação não cadastrada') }),
        no('button', { type: 'button', 'data-empresa-area': e.id, texto: t('Cadastrar área') })));
  });
  const n = Object.keys(m.sobreposicao).length;
  if (n) itens.push(no('li', { classe: 'legenda-sobreposicao' }, svg('svg', { width: 22, height: 16, 'aria-hidden': 'true' },
    svg('rect', { x: 1.5, y: 1.5, width: 19, height: 13, fill: 'none', stroke: COR_SOBREPOSICAO, 'stroke-width': 2.5, 'stroke-dasharray': '2 3' })),
    no('span', { texto: '⚠ ' + t('{n} município(s) em mais de uma empresa (sobreposição)', { n: fmt(n) }) })));
  $('listaLegendaEmpresas').replaceChildren(...itens);
  const aberta = estado.legendaEmpresasAberta;
  $('listaLegendaEmpresas').hidden = !aberta;
  $('botaoLegendaEmpresas').setAttribute('aria-expanded', String(aberta));
  $('legendaEmpresas').classList.toggle('minimizada', !aberta);
}

// em lista também: os municípios em mais de uma empresa
function desenharSobreposicao() {
  const m = estado.mapaEmpresas, lista = Object.entries(m?.sobreposicao || {});
  $('sobreposicaoEmpresas').replaceChildren(...(lista.length ? [no('h2', { classe: 'subtitulo', texto: t('Municípios em mais de uma empresa') }),
    no('div', { classe: 'rolagem', tabindex: '0', role: 'region', 'aria-label': t('Municípios em mais de uma empresa') }, no('table', { classe: 'tabela' },
      no('caption', { classe: 'visualmente-oculto', texto: t('Municípios em mais de uma empresa') }),
      no('thead', {}, no('tr', {}, [t('Município'), t('Empresas')].map(c => no('th', { scope: 'col', texto: c })))),
      no('tbody', {}, lista.map(([c, s]) => no('tr', {}, no('th', { scope: 'row', texto: nomeDoMunicipio(c) }), no('td', { texto: s.join(', ') })))))),
  ] : []));
}

// a ficha da empresa (cadastro, contagens e municípios; nada de aviso); pela tabela, dá zoom na área
async function abrirFichaEmpresa(id, zoom = true) {
  try {
    estado.fichaEmpresa = (await api(`/api/empresas/${id}/ficha`)).empresa;
  } catch (e) { return avisar(e.message, true); }
  if (estado.vista !== 'empresas') await irPara('empresas');
  desenharFichaEmpresa();
  const e = estado.mapaEmpresas?.empresas.find(x => x.id === id);
  if (zoom && e?.municipios.length) {
    const g = L.geoJSON({ type: 'FeatureCollection', features: e.municipios.map(feicaoDe).filter(Boolean) });
    if (g.getLayers().length) mapa.fitBounds(g.getBounds(), { padding: [20, 20] });
  }
  $('fichaEmpresaTitulo')?.focus();
}

function desenharFichaEmpresa() {
  const f = estado.fichaEmpresa;
  $('fichaEmpresa').hidden = !f;
  if (!f) return $('fichaEmpresa').replaceChildren();
  const linha = (rotulo, valor) => [no('dt', { texto: t(rotulo) }), no('dd', { texto: valor })];
  $('fichaEmpresa').replaceChildren(
    no('h2', { id: 'fichaEmpresaTitulo', tabindex: '-1', texto: `${f.sigla} · ${f.nome}` }),
    no('p', { classe: 'ajuda', texto: t('Só o cadastro e contagens: o conteúdo dos avisos, o histórico e as comunidades afetadas ficam só com a empresa.') }),
    no('dl', { classe: 'ficha-dados' },
      ...linha('Sigla', f.sigla), ...linha('CNPJ', f.cnpj || '—'), ...linha('Domínio dos e-mails', f.dominio),
      ...linha('Situação', (f.status === 'suspensa' ? '✕ ' : '✓ ') + t(f.status === 'suspensa' ? 'Suspensa' : 'Ativa')),
      ...linha('Cadastrada em', dataHora(f.criada_em)), ...linha('Cadastrada por', f.criada_por || '—'),
      ...linha('Usuários', fmt(f.usuarios)), ...linha('Avisos no mês', fmt(f.avisos_mes)), ...linha('Avisos no total', fmt(f.avisos_total)),
      ...linha('Municípios', fmt(f.municipios.length))),
    f.municipios.length
      ? no('details', { classe: 'corrigidas' }, no('summary', { texto: t('Municípios atendidos ({n})', { n: fmt(f.municipios.length) }) }),
        no('ul', { classe: 'lista-municipios' }, f.municipios.map(x => no('li', { texto: `${x.nome}/${x.uf}` }))))
      : no('p', { classe: 'alerta', texto: '⚠ ' + t('Área de atuação não cadastrada') }),
    no('div', { classe: 'acoes' },
      no('button', { type: 'button', classe: 'prim', 'data-empresa-area': f.id, texto: f.municipios.length ? t('Editar a área de atuação') : t('Cadastrar área') }),
      no('button', { type: 'button', 'data-empresa-zoom': f.id, texto: t('Ver no mapa') }),
      no('button', { type: 'button', 'data-fechar-ficha': '1', texto: t('Fechar') })));
}

// ---- Editor da área de atuação ----
async function abrirEditorArea(id, focar = true) {
  const e = estado.mapaEmpresas?.empresas.find(x => x.id === Number(id));
  if (!e) return;
  if (!estado.municipiosIbge) {
    try { estado.municipiosIbge = (await api('/api/municipios-ibge')).municipios; } catch (x) { return avisar(x.message, true); }
  }
  const ufs = [...new Set(estado.municipiosIbge.map(m => m.uf))].sort();
  const daArea = estado.municipiosIbge.filter(m => e.municipios.includes(m.codigo_ibge));
  const uf = daArea.length ? Object.entries(daArea.reduce((n, m) => ({ ...n, [m.uf]: (n[m.uf] || 0) + 1 }), {})).sort((a, b) => b[1] - a[1])[0][0] : 'MG';
  estado.area = { empresaId: e.id, sigla: e.sigla, codigos: new Set(e.municipios), uf, busca: '', resumo: null, ufs };
  if (estado.vista !== 'empresas') await irPara('empresas');
  $('areaUf').replaceChildren(...ufs.map(u => no('option', { value: u, texto: u })));
  $('areaUf').value = uf; $('areaBusca').value = ''; $('areaArquivo').value = '';
  mensagemEm('estadoArea', '');
  desenharEditorArea();
  await desenharMapaDaUf();
  if (focar) { $('editorArea').scrollIntoView({ block: 'start' }); $('editorAreaTitulo').focus(); }
}

function fecharEditorArea() {
  estado.area = null;
  camadaEditorArea?.remove(); camadaEditorArea = null;
  desenharEditorArea();
}

function desenharEditorArea() {
  const a = estado.area;
  $('editorArea').hidden = !a;
  if (!a) return;
  $('editorAreaTitulo').textContent = t('Área de atuação: {sigla}', { sigla: a.sigla });
  const busca = normalizar(a.busca);
  const lista = estado.municipiosIbge.filter(m => m.uf === a.uf && (!busca || normalizar(m.nome).includes(busca)));
  $('areaListaTitulo').textContent = t('Municípios de {uf} ({n})', { uf: a.uf, n: fmt(lista.length) });
  $('areaLista').replaceChildren(...lista.map(m => no('label', { classe: 'check' },
    no('input', { type: 'checkbox', value: m.codigo_ibge, 'data-area-municipio': m.codigo_ibge, checked: a.codigos.has(m.codigo_ibge) }),
    no('span', { texto: m.nome }))));
  const porUf = {};
  for (const m of estado.municipiosIbge) if (a.codigos.has(m.codigo_ibge)) porUf[m.uf] = (porUf[m.uf] || 0) + 1;
  $('areaContagem').textContent = t('{n} município(s) marcado(s)', { n: fmt(a.codigos.size) })
    + (Object.keys(porUf).length ? ` · ${Object.entries(porUf).map(([u, n]) => `${u}: ${fmt(n)}`).join(' · ')}` : '');
  $('areaConfirmar').hidden = !a.resumo;
  desenharResumoArea();
  estiloEditorArea();
}

function desenharResumoArea() {
  const r = estado.area?.resumo;
  if (!r) return $('areaResumo').replaceChildren();
  const nomes = xs => xs.map(x => `${x.nome}/${x.uf}`).join(', ');
  $('areaResumo').replaceChildren(no('div', { classe: r.sobreposicao.length ? 'alerta-amarelo' : 'previa', role: 'status' },
    no('p', {}, no('strong', { texto: t('{x} municípios, {y} novos, {z} removidos, {w} em sobreposição com outra empresa',
      { x: fmt(r.municipios), y: fmt(r.novos.length), z: fmt(r.removidos.length), w: fmt(r.sobreposicao.length) }) })),
    r.novos.length ? no('details', {}, no('summary', { texto: t('Novos ({n})', { n: fmt(r.novos.length) }) }), no('p', { texto: nomes(r.novos) })) : null,
    r.removidos.length ? no('details', {}, no('summary', { texto: t('Removidos ({n})', { n: fmt(r.removidos.length) }) }), no('p', { texto: nomes(r.removidos) })) : null,
    r.sobreposicao.length ? no('details', {}, no('summary', { texto: t('Em sobreposição ({n})', { n: fmt(r.sobreposicao.length) }) }),
      no('p', { texto: r.sobreposicao.map(s => `${s.nome}/${s.uf} (${s.empresas.join(', ')})`).join('; ') })) : null,
    r.mudou ? null : no('p', { texto: t('Nada mudou na área de atuação.') })));
}

// os municípios da UF no mapa, para marcar clicando (o teclado e o leitor de tela usam a lista)
async function desenharMapaDaUf() {
  const a = estado.area;
  camadaEditorArea?.remove(); camadaEditorArea = null;
  if (!a) return;
  estado.ufGeo ||= {};
  if (!estado.ufGeo[a.uf]) {
    try { estado.ufGeo[a.uf] = await api(`/api/municipios-ibge/${a.uf}/mapa`); } catch (e) { return mensagemEm('estadoArea', e.message, true); }
  }
  if (estado.area !== a) return;
  camadaEditorArea = L.geoJSON(estado.ufGeo[a.uf], {
    style: f => estiloMunicipioArea(f.properties.codigo_ibge),
    onEachFeature: (f, l) => {
      l.bindTooltip(() => no('span', { texto: `${f.properties.nome}/${f.properties.uf} · ${estado.area?.codigos.has(f.properties.codigo_ibge) ? t('na área') : t('fora da área')}` }), { sticky: true });
      l.on('click', () => alternarMunicipioArea(f.properties.codigo_ibge));
    },
  }).addTo(mapa);
  if (camadaEditorArea.getLayers().length) mapa.fitBounds(camadaEditorArea.getBounds(), { padding: [20, 20] });
}
const estiloMunicipioArea = c => estado.area?.codigos.has(c)
  ? { color: '#B07800', weight: 1.5, fillColor: '#F5B83D', fillOpacity: .5 }
  : { color: '#6B7A88', weight: .8, fillColor: '#6B7A88', fillOpacity: .04 };
function estiloEditorArea() {
  camadaEditorArea?.eachLayer(l => l.setStyle(estiloMunicipioArea(l.feature.properties.codigo_ibge)));
}

// Controller do editor
function alternarMunicipioArea(codigo, marcar) {
  const a = estado.area;
  if (!a) return;
  const ligar = marcar ?? !a.codigos.has(codigo);
  if (ligar) a.codigos.add(codigo); else a.codigos.delete(codigo);
  a.resumo = null;
  desenharEditorArea();
}

function marcarUf(marcar) {
  const a = estado.area;
  const busca = normalizar(a.busca);
  for (const m of estado.municipiosIbge) if (m.uf === a.uf && (!busca || normalizar(m.nome).includes(busca))) {
    if (marcar) a.codigos.add(m.codigo_ibge); else a.codigos.delete(m.codigo_ibge);
  }
  a.resumo = null;
  desenharEditorArea();
}

async function importarArquivoArea(arquivo) {
  const a = estado.area;
  if (!a || !arquivo) return;
  const fd = new FormData();
  fd.append('arquivo', arquivo);
  try {
    const j = await api(`/api/empresas/${a.empresaId}/area/arquivo`, { method: 'POST', body: fd });
    a.codigos = new Set(j.codigos); a.resumo = null;
    mensagemEm('estadoArea', t('{n} município(s) do arquivo marcados. Confira e veja o resumo antes de salvar; o arquivo não foi guardado.', { n: fmt(j.codigos.length) }));
    desenharEditorArea();
  } catch (e) {
    mensagemEm('estadoArea', e.message, true);
  }
  $('areaArquivo').value = '';
}

async function salvarArea(confirmar) {
  const a = estado.area;
  if (!a) return;
  const botao = confirmar ? $('areaConfirmar') : $('areaVerResumo');
  await ocupado(botao, confirmar ? 'Salvando…' : 'Calculando…', async () => {
    try {
      const j = await api(`/api/empresas/${a.empresaId}/area`, { method: 'PUT', json: { codigos: [...a.codigos], confirmar } });
      if (!confirmar) {
        a.resumo = j.resumo;
        mensagemEm('estadoArea', '');
        desenharEditorArea();
        $('areaConfirmar').hidden = !j.resumo.mudou;
        return;
      }
      const id = a.empresaId;
      fecharEditorArea();
      await carregarMapaEmpresas();
      estado.empresas = (await api('/api/empresas')).empresas; desenharEmpresas();
      mensagemEm('estadoEmpresa', t('Área de atuação salva ({n} municípios).', { n: fmt(j.resumo.municipios) }));
      await abrirFichaEmpresa(id);
    } catch (e) {
      mensagemEm('estadoArea', e.message, true);
    }
  });
}

function acaoMapaEmpresas(evento) {
  const b = evento.target.closest('button');
  if (!b) return;
  if (b.dataset.empresaMapa) {
    const id = Number(b.dataset.empresaMapa);
    if (estado.empresasOcultas.has(id)) estado.empresasOcultas.delete(id); else estado.empresasOcultas.add(id);
    desenharMapaEmpresas(); desenharLegendaEmpresas();
    document.querySelector(`[data-empresa-mapa="${id}"]`)?.focus();
  } else if (b.dataset.empresaArea) abrirEditorArea(b.dataset.empresaArea);
  else if (b.dataset.empresaZoom) abrirFichaEmpresa(Number(b.dataset.empresaZoom));
  else if (b.dataset.fecharFicha) { estado.fichaEmpresa = null; desenharFichaEmpresa(); }
}

// ---- Rádios (Admin da empresa) ----
function desenharRadios() {
  const r = estado.radioEditando, p = estado.pedidoAtendendo;
  $('formRadioTitulo').textContent = r ? t('Editar {nome}', { nome: r.nome }) : p ? t('Cadastrar a rádio pedida por {nome}', { nome: p.por }) : t('Cadastrar rádio');
  $('radSalvar').textContent = r ? t('Salvar alterações') : t('Cadastrar rádio');
  $('radCancelar').hidden = !r && !p;
  desenharPedidos();
  if (!$('radMunicipios').options.length) {
    $('radMunicipios').replaceChildren(...municipiosDaConcessao().map(([c, n]) => no('option', { value: c, texto: n })));
    $('radMunCom').replaceChildren(no('option', { value: '', texto: t('Escolha o município') }), ...municipiosDaConcessao().map(([c, n]) => no('option', { value: c, texto: n })));
  }
  desenharComunidadesRadio();
  $('listaRadios').replaceChildren(...(estado.radiosAdmin.length ? estado.radiosAdmin.map(x => no('div', { classe: 'item', 'data-radio': x.id },
    no('strong', { texto: x.nome + (x.ativa ? '' : t(' (inativa)')) }),
    no('span', { classe: 'meta', texto: [x.email, x.whatsapp].filter(Boolean).join(' · ') }),
    no('span', { classe: 'meta', texto: t('{valor} ({cobranca}) · alcança {alcance}', { valor: x.valor_padrao ? dinheiro(x.valor_padrao) : t('sem valor padrão'),
      cobranca: t(COBRANCA[x.cobranca]), alcance: [x.alcance.municipios.map(nomeMunicipio).join(', '), x.alcance.comunidades.length
        ? t('{n} comunidade(s)', { n: x.alcance.comunidades.length }) : ''].filter(Boolean).join(t(' e ')) || t('nada cadastrado') }) }),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-radio-acao': 'editar', 'aria-label': t('Editar {nome}', { nome: x.nome }), texto: t('Editar') }),
      no('button', { type: 'button', 'data-radio-acao': x.ativa ? 'desativar' : 'reativar', classe: x.ativa ? 'perigo' : '',
        'aria-label': t(x.ativa ? 'Desativar {nome}' : 'Reativar {nome}', { nome: x.nome }), texto: x.ativa ? t('Desativar') : t('Reativar') }))))
    : [no('p', { classe: 'ajuda', texto: t('Nenhuma rádio cadastrada.') })]));
}

const SITUACAO_PEDIDO = { aberto: 'aberto', atendido: 'atendido', recusado: 'recusado' };
// pedidos de rádio do Operador: os abertos com Atender e Recusar (motivo); os resolvidos só para consulta
function desenharPedidos() {
  const pedidos = estado.pedidos || [];
  $('listaPedidos').replaceChildren(...(pedidos.length ? pedidos.slice(0, 30).map(p => {
    const aberto = p.status === 'aberto';
    return no('div', { classe: 'item com-erros', 'data-pedido': p.id },
      no('strong', { texto: `${p.nome} (${p.cidade})` }),
      no('span', { classe: `chip ${p.status === 'recusado' ? 'cancelado' : ''}`, texto: t(SITUACAO_PEDIDO[p.status]) }),
      no('span', { classe: 'meta', texto: [p.contato && t('contato da rádio: {contato}', { contato: p.contato }), p.observacao].filter(Boolean).join(' · ') || t('sem contato nem observação') }),
      no('span', { classe: 'meta', texto: t('pedido por {nome} em {quando}', { nome: p.por, quando: dataHora(p.criado_em) })
        + (p.resolvido_por ? t(' · {situacao} por {nome} em {quando}', { situacao: t(SITUACAO_PEDIDO[p.status]), nome: p.resolvido_por, quando: dataHora(p.resolvido_em) }) : '')
        + (p.motivo_recusa ? t(' · motivo: {motivo}', { motivo: p.motivo_recusa }) : '') }),
      aberto ? no('div', { classe: 'acoes' },
        no('button', { type: 'button', classe: 'prim', 'data-pedido-acao': 'atender', 'aria-label': t('Atender o pedido da {nome}', { nome: p.nome }), texto: t('Atender (cadastrar)') }),
        no('label', {}, no('span', { texto: t('Motivo da recusa (o Operador vê)') }), ' ', no('input', { id: `pedido-motivo-${p.id}`, 'data-pedido-motivo': '', maxlength: '300', autocomplete: 'off' })),
        no('button', { type: 'button', 'data-pedido-acao': 'recusar', 'aria-label': t('Recusar o pedido da {nome}', { nome: p.nome }), texto: t('Recusar') })) : null);
  }) : [no('p', { classe: 'ajuda', texto: t('Nenhum pedido de rádio.') })]));
}

function desenharComunidadesRadio() {
  const cod = $('radMunCom').value, terr = estado.territorios[cod];
  const marcadas = new Set(estado.alcanceComunidades.map(c => `${c.municipio}|${c.nome}|${c.distrito}`));
  const resumo = no('p', { classe: 'ajuda', id: 'radResumo', texto: resumoComunidades() });
  if (!cod || !terr) return $('radComunidades').replaceChildren(resumo);
  const vistas = new Set(), lista = [];
  for (const f of terr.features) {
    const nome = semSufixo(f.properties.nome), dist = f.properties.distrito, chave = `${cod}|${nome}|${dist}`;
    if (vistas.has(chave)) continue;
    vistas.add(chave);
    lista.push([chave, nome, dist]);
  }
  lista.sort((a, b) => a[1].localeCompare(b[1], IDIOMA));
  $('radComunidades').replaceChildren(resumo, ...lista.map(([chave, nome, dist]) => no('label', { classe: 'check' },
    no('input', { type: 'checkbox', 'data-comunidade': chave, checked: marcadas.has(chave) }),
    no('span', { texto: `${nome} (${dist === nomeMunicipio(cod).split('/')[0] ? t('Sede') : dist})` }))));
}

const resumoComunidades = () => estado.alcanceComunidades.length ? t('Comunidades escolhidas: {lista}.', { lista: estado.alcanceComunidades
  .map(c => `${c.nome} (${c.distrito === nomeMunicipio(c.municipio).split('/')[0] ? t('Sede') : c.distrito})`).join(', ') }) : '';

// ---- Configurações da empresa (Admin da empresa) ----
function desenharConfig() {
  const c = estado.configuracao;
  if (!c) return;
  if (!$('cfgFuso').options.length) $('cfgFuso').replaceChildren(...FUSOS_UTM.map(([k, rot]) => no('option', { value: String(k), texto: `${rot} (EPSG:${k})` })));
  $('cfgIdioma').replaceChildren(...Object.entries(estado.config?.idiomas || { 'pt-BR': 'Português' }).map(([k, nome]) => no('option', { value: k, lang: k, texto: nome })));
  $('cfgIdioma').value = c.idioma_padrao || 'pt-BR';
  $('cfgModelo').value = c.modelo_mensagem;
  $('cfgModeloEn').value = c.modelos?.en || '';
  $('cfgModeloEs').value = c.modelos?.es || '';
  $('cfgNome').value = c.nome_mensagem;
  $('cfgTelefone').value = c.telefone || '';
  $('cfgLimite').value = String(Math.round(c.limite_rejeicao * 1000) / 10);
  $('cfgFuso').value = String(c.epsg_utm);
  $('cfgAntecedencia').value = String(c.antecedencia_dias);
  $('cfgOrcamento').value = c.orcamento_radio == null ? '' : String(c.orcamento_radio);
  $('cfgAlertaPreco').value = String(Math.round((c.alerta_preco ?? 0.2) * 100));
  $('cfgRepN').value = String(c.repeticao_n ?? 3);
  $('cfgRepDias').value = String(c.repeticao_dias ?? 30);
  $('cfgCampos').textContent = t('Campos: {campos}. Trecho entre [colchetes] some se algum campo dentro dele ficar vazio.', { campos: c.campos.map(x => `{${x}}`).join(' ') });
  desenharPreviaConfig();
}

// a prévia de cada modelo, com um exemplo no formato do idioma (a mesma regra do servidor: nucleo/mensagem.py e nucleo/idiomas.py)
const EXEMPLOS_MENSAGEM = {
  'pt-BR': { data: '20/11', inicio: '8h', fim: '14h', motivo: 'manutenção preventiva na rede', comunidades: 'Graminha, Boa Sorte e São Pedro' },
  en: { data: 'November 20', inicio: '8 a.m.', fim: '2 p.m.', motivo: 'preventive maintenance on the power grid', comunidades: 'Graminha, Boa Sorte and São Pedro' },
  es: { data: '20 de noviembre', inicio: '8:00', fim: '14:00', motivo: 'mantenimiento preventivo de la red', comunidades: 'Graminha, Boa Sorte y São Pedro' },
};
function desenharPreviaConfig() {
  for (const [idioma, modelo, previa] of [['pt-BR', 'cfgModelo', 'cfgPrevia'], ['en', 'cfgModeloEn', 'cfgPreviaEn'], ['es', 'cfgModeloEs', 'cfgPreviaEs']])
    $(previa).textContent = t('Exemplo: {texto}', { texto: montarMensagem($(modelo).value, { distribuidora: $('cfgNome').value, municipio: 'Leopoldina',
      ...EXEMPLOS_MENSAGEM[idioma], comunidades_parciais: 'Tomé Nogueira', telefone_atendimento: $('cfgTelefone').value, codigo: 'FRL-0000-0000-0000' }) });
}

function desenharRegistro() {
  const linhas = estado.registro.map(r => no('tr', {}, no('th', { scope: 'row' }, quandoCurto(r.quando)),
    no('td', {}, r.usuario ? quem(r.usuario, r.perfil && t(r.perfil)) : '—'),
    no('td', { classe: 'curto', texto: r.empresa || '—' }), no('td', { texto: r.acao }), no('td', { classe: 'detalhe', texto: r.detalhe }),
    no('td', { classe: 'codigo', texto: r.codigo || '' })));
  $('listaRegistro').replaceChildren(no('h2', { classe: 'subtitulo', texto: t('Últimas ações (sem filtro)') }),
    no('div', { classe: 'rolagem', tabindex: '0', role: 'region', 'aria-label': t('Últimas ações (sem filtro)') }, no('table', { classe: 'tabela' },
    no('caption', { classe: 'visualmente-oculto', texto: t('Últimas ações (sem filtro)') }),
    no('thead', {}, no('tr', {}, ['Quando', 'Quem', 'Empresa', 'O quê', 'Detalhe', 'Código'].map(c => no('th', { scope: 'col', texto: t(c) })))),
    no('tbody', {}, linhas))));
}

function mostrarSenhaTemporaria(texto, senha) {
  $('caixaTexto').textContent = texto;
  $('caixaSenhaValor').textContent = senha;
  $('caixaSenha').hidden = false;
  $('caixaFechar').focus();
}

// ---- Mapa ----
const escuro = () => temaAtual() === 'escuro';
const COR = { ambar: '#F5B83D', ambarForte: '#B07800', cinza: '#93A1AF', info: '#1663C7', erro: '#B42318', verde: '#D99A16', corrigida: '#7A4FD1' };
let mapa, camadaConcessao, camadaComunidades, camadaUcs, telaUcs, camadaBase, camadaNomes, camadaCidades, caixasNomes = [], camadaRede, telaRede, atribuicao;
// a partir deste zoom, o contorno das comunidades dos municípios na tela; a partir do outro, os nomes escritos
const ZOOM_COMUNIDADES = 11, ZOOM_NOMES = 13, ZOOM_TRAFOS = 14, ZOOM_NOMES_AFETADAS = 10;
const ZOOM_CIDADES = [6, 12];   // faixa de zoom em que o nome de cada cidade da concessão aparece
const CREDITO_REDE = 'Rede fictícia sobre as vias do © OpenStreetMap';
const CORES_ALIMENTADOR = ['#1663C7', '#7A4FD1', '#0F8F86', '#C2410C', '#9D174D', '#4D7C0F', '#0E7490', '#A16207'];
const buscando = new Set();   // municípios cujas comunidades estão sendo buscadas

let fundoDoMapa;
function trocarFundoDoMapa() {
  if (!mapa) return;
  fundoDoMapa?.remove();
  fundoDoMapa = L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${escuro() ? 'Dark' : 'Light'}_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    { attribution: 'Fundo &copy; Esri', maxZoom: 16, noWrap: true }).addTo(mapa);
  fundoDoMapa.bringToBack();
}

function iniciarMapa() {
  if (mapa) return;
  mapa = L.map('mapa', { zoomControl: true, attributionControl: false, minZoom: 5, maxZoom: 16,
    zoomAnimation: !menosMovimento(), fadeAnimation: !menosMovimento(), markerZoomAnimation: !menosMovimento() });
  atribuicao = L.control.attribution({ prefix: t('Concessão e comunidades: IBGE · Leaflet') }).addTo(mapa);
  trocarFundoDoMapa();
  mapa.setView([-21.0, -42.6], 8);
  mapa.on('moveend', aoMoverMapa);
  mapa.on('click', e => {
    if (estado.evidencia) { estado.evidencia = null; aplicarEvidencia(); }
    cliqueNoMapa(e);   // desenhar a área da escolha (passo 3)
  });
}

// comunidade em evidência (clique): borda branca grossa e as demais mais apagadas
const chaveComunidade = f => `${f.properties.m?.nome ?? f.properties.municipio}|${f.properties.nome}|${f.properties.distrito}`;
function comEvidencia(estilo, f) {
  if (!estado.evidencia) return estilo;
  if (estado.evidencia.chave === chaveComunidade(f))
    return { ...estilo, color: escuro() ? '#FFFFFF' : '#0E1620', weight: 3.5, opacity: 1, dashArray: null, fillColor: estilo.fillColor || COR.ambar, fillOpacity: Math.max(estilo.fillOpacity || 0, .3) };
  return { ...estilo, opacity: (estilo.opacity ?? 1) * .5, fillOpacity: (estilo.fillOpacity || 0) * .5 };
}

const estiloBase = f => comEvidencia({ color: COR.cinza, weight: .8, ...estiloCalor(f.properties) }, f);
const estiloAviso = f => comEvidencia(!f.properties.c ? { color: COR.cinza, weight: .8, ...estiloCalor(f.properties) } : ({
  inteira: { color: COR.ambarForte, weight: 2, fillColor: COR.ambar, fillOpacity: .4 },
  parte: { color: COR.ambarForte, weight: 2, dashArray: '5 4', fillColor: COR.ambar, fillOpacity: .15 },
  vizinha: { color: COR.cinza, weight: 1, opacity: .7, fillColor: COR.cinza, fillOpacity: .2 },
})[situacao(f.properties.c)], f);

function aplicarEvidencia() {
  camadaBase?.setStyle(estiloBase);
  camadaComunidades?.setStyle(estiloAviso);
  for (const camada of [camadaBase, camadaComunidades])
    camada?.eachLayer(l => { if (estado.evidencia?.chave === chaveComunidade(l.feature)) l.bringToFront(); });
  desenharNomes();
}

// o clique numa comunidade: destaca (borda grossa, nome em evidência) e abre a ficha; no passo de escolher quem será
// desligado o clique é da escolha (cliqueNoMapa), então sobe para o mapa sem destacar
function cliqueNaComunidade(e, l, municipio, nome, distrito) {
  if (emEscolha()) return;
  evidenciar(e, l);
  abrirFicha(e.latlng || l.getBounds().getCenter(), municipio, nome, distrito);
}

// clique numa comunidade: põe em evidência (e aproxima); clicar de novo tira
function evidenciar(e, l) {
  L.DomEvent.stopPropagation(e);
  const chave = chaveComunidade(l.feature);
  estado.evidencia = estado.evidencia?.chave === chave ? null : { chave };
  aplicarEvidencia();
  if (estado.evidencia) mapa.fitBounds(l.getBounds(), { padding: [60, 60], maxZoom: 14 });
}

// municípios da concessão que aparecem na tela (pelo retângulo do contorno)
const municipiosNaTela = () => !camadaConcessao ? [] : camadaConcessao.getLayers()
  .filter(l => mapa.getBounds().intersects(l.getBounds())).map(l => l.feature.properties);
const distritoDe = (distrito, municipio) => distrito === municipio ? t('Sede') : distrito;

// comunidades dos municípios na tela, fora os do aviso (esses a desenharComunidades destaca)
function desenharBase() {
  camadaBase?.remove();
  camadaBase = null;
  if (!mapa || mapa.getZoom() < ZOOM_COMUNIDADES) return;
  const doAviso = new Set([...(estado.resultado?.municipios || []), ...(emEscolha() ? estado.leitura.base.municipios : [])].map(m => m.codigo_ibge));
  const feicoes = municipiosNaTela().filter(m => !doAviso.has(m.codigo_ibge) && estado.territorios[m.codigo_ibge])
    .flatMap(m => estado.territorios[m.codigo_ibge].features.map(f => ({ ...f, properties: { ...f.properties, municipio: m.nome,
      codigo_ibge: m.codigo_ibge } })));
  if (!feicoes.length) return;
  camadaBase = L.geoJSON({ type: 'FeatureCollection', features: feicoes }, {
    style: estiloBase,
    onEachFeature: (f, l) => {
      l.bindTooltip(() => no('span', {
        texto: `${semSufixo(f.properties.nome)} (${distritoDe(f.properties.distrito, f.properties.municipio)}) · ${f.properties.municipio}`
          + (estado.calor ? t(' · {n} desligamento(s) em 12 meses', { n: fmt(desligamentosDe(f.properties)) }) : '') }), { sticky: true });
      l.on('click', e => cliqueNaComunidade(e, l, f.properties.codigo_ibge, f.properties.nome, f.properties.distrito));
    },
  }).addTo(mapa);
  camadaBase.bringToBack();
  camadaConcessao?.bringToBack();
}

// nome escrito de cada comunidade na tela (só de perto), num ponto sempre dentro dela; o nome entra como texto.
// As maiores (mais endereços) primeiro; um nome que encostaria em outro já escrito fica para um zoom maior.
function desenharNomes() {
  camadaNomes?.remove();
  camadaNomes = null;
  caixasNomes = [];
  if (!mapa) return;
  // com um aviso na tela, as comunidades afetadas levam o nome desde o zoom ZOOM_NOMES_AFETADAS (em destaque,
  // e primeiro na disputa por espaço); os nomes das demais só de perto
  const afetadas = new Set();
  for (const m of estado.resultado?.municipios || []) for (const c of m.comunidades) afetadas.add(`${m.codigo_ibge}|${c.nome}`);
  const zoom = mapa.getZoom(), evidencia = estado.evidencia?.chave;
  if (zoom < (afetadas.size || evidencia ? ZOOM_NOMES_AFETADAS : ZOOM_NOMES)) return;
  const tela = mapa.getBounds().pad(.2), marcas = [], ocupado = [];
  const candidatas = municipiosNaTela().flatMap(m => (estado.territorios[m.codigo_ibge]?.features || [])
    .map(f => ({ f, afetada: afetadas.has(`${m.codigo_ibge}|${f.properties.nome}`), destaque: evidencia === chaveComunidade({ properties: { ...f.properties, municipio: m.nome } }) })))
    .filter(({ f, afetada, destaque }) => f.properties.rotulo && tela.contains(f.properties.rotulo) && (destaque || afetada || zoom >= ZOOM_NOMES))
    .sort((a, b) => b.destaque - a.destaque || b.afetada - a.afetada || b.f.properties.enderecos - a.f.properties.enderecos);
  for (const { f, afetada, destaque } of candidatas) {
    const nome = semSufixo(f.properties.nome), c = mapa.latLngToContainerPoint(f.properties.rotulo);
    const caixa = { x0: c.x - nome.length * 3.4 - 4, x1: c.x + nome.length * 3.4 + 4, y0: c.y - 9, y1: c.y + 9 };  // ~6,8 px por letra
    if (!destaque && ocupado.some(o => caixa.x0 < o.x1 && o.x0 < caixa.x1 && caixa.y0 < o.y1 && o.y0 < caixa.y1)) continue;
    ocupado.push(caixa);
    marcas.push(L.marker(f.properties.rotulo, { interactive: false, keyboard: false,
      icon: L.divIcon({ className: destaque ? 'rotulo afetada destaque' : afetada ? 'rotulo afetada' : 'rotulo', html: no('span', { texto: nome }), iconSize: null }) }));
  }
  caixasNomes = ocupado;
  if (marcas.length) camadaNomes = L.layerGroup(marcas).addTo(mapa);
}

// nome de cada cidade da concessão (no centro do retângulo do contorno), da mais extensa para a menos; um nome que
// encostaria em outro já escrito (de cidade ou de comunidade) fica para um zoom maior. O nome entra como texto.
function desenharCidades() {
  camadaCidades?.remove();
  camadaCidades = null;
  const zoom = mapa?.getZoom();
  if (!mapa || !camadaConcessao || zoom < ZOOM_CIDADES[0] || zoom > ZOOM_CIDADES[1]) return;
  const tela = mapa.getBounds().pad(.1), marcas = [], ocupado = [...caixasNomes];
  const area = b => (b.getNorth() - b.getSouth()) * (b.getEast() - b.getWest());
  const cidades = camadaConcessao.getLayers().map(l => ({ p: l.feature.properties, b: l.getBounds() }))
    .filter(({ b }) => tela.contains(b.getCenter())).sort((a, c) => area(c.b) - area(a.b));
  for (const { p, b } of cidades) {
    const nome = p.nome, c = mapa.latLngToContainerPoint(b.getCenter()), meia = nome.length * 4.2 + 6;  // ~8,4 px por letra
    const caixa = { x0: c.x - meia, x1: c.x + meia, y0: c.y - 11, y1: c.y + 11 };
    if (ocupado.some(o => caixa.x0 < o.x1 && o.x0 < caixa.x1 && caixa.y0 < o.y1 && o.y0 < caixa.y1)) continue;
    ocupado.push(caixa);
    marcas.push(L.marker(b.getCenter(), { interactive: false, keyboard: false,
      icon: L.divIcon({ className: 'rotulo cidade', html: no('span', { texto: nome }), iconSize: null }) }));
  }
  if (marcas.length) camadaCidades = L.layerGroup(marcas).addTo(mapa);
}

// ---- Mapa de calor e ficha da comunidade (só contagens; quem vê o histórico) ----
const chaveCalor = p => `${p.codigo_ibge}|${semSufixo(p.nome)}|${p.distrito || ''}`;
const desligamentosDe = p => estado.calor?.comunidades[chaveCalor(p)] || 0;
const ESCALA_CALOR = ['#FFF3C4', '#F5B83D', '#D9480F', '#8B1A1A'];
function estiloCalor(p) {
  const n = estado.calor ? desligamentosDe(p) : 0;
  if (!n) return { fillOpacity: 0 };
  const fr = n / Math.max(1, estado.calor.maximo);
  return { fillColor: ESCALA_CALOR[Math.min(3, Math.floor(fr * 4 - 1e-9))], fillOpacity: .6 };
}

async function alternarCalor() {
  try {
    estado.calor = estado.calor ? null : await api('/api/comunidades/calor');
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
  $('botaoCalor').setAttribute('aria-pressed', String(!!estado.calor));
  $('botaoCalor').textContent = estado.calor ? t('Esconder mapa de calor') : t('Mapa de calor (12 meses)');
  $('legendaCalor').hidden = !estado.calor;
  $('calorMax').textContent = estado.calor ? fmt(estado.calor.maximo) : '';
  desenharBase(); desenharComunidades();
  if (estado.calor && mapa.getZoom() < ZOOM_COMUNIDADES) avisar(t('O mapa de calor aparece de perto: aproxime num município (ou clique nele).'));
}

// a ficha abre num balão do mapa: contagens, rádios que alcançam e os botões do relatório da comunidade
async function abrirFicha(latlng, municipio, nome, distrito) {
  if (!pode('ver_historico') || !municipio) return;
  const filtros = { municipio, nome: semSufixo(nome), ...(distrito ? { distrito } : {}) };
  const caixa = no('div', { classe: 'ficha', role: 'dialog', 'aria-label': t('Ficha de {nome}', { nome: semSufixo(nome) }) }, no('p', { texto: t('Carregando a ficha…') }));
  L.popup({ maxWidth: 300 }).setLatLng(latlng).setContent(caixa).openOn(mapa);
  try {
    const f = estado.ficha = await api(`/api/comunidades/ficha?${consulta(filtros)}`);
    const linha = (rotulo, valor) => [no('dt', { texto: t(rotulo) }), no('dd', { texto: valor })];
    caixa.replaceChildren(
      no('h3', { texto: `${f.nome}${f.distrito ? ` (${f.distrito})` : ''}` }),
      no('p', { classe: 'ajuda', texto: t('{municipio} · últimos 12 meses · dados de demonstração (fictícios)', { municipio: f.municipio || '' }) }),
      no('dl', {}, ...linha('Desligamentos', fmt(f.desligamentos)), ...linha('Horas sem luz', t('{n} h', { n: fmt(f.horas) })),
        ...linha('UCs afetadas (soma)', fmt(f.ucs_afetadas)), ...linha('Endereços (IBGE)', f.enderecos == null ? '—' : fmt(f.enderecos)),
        ...linha('No prazo', f.pct_no_prazo == null ? '—' : `${f.pct_no_prazo.toLocaleString(IDIOMA)}%`),
        ...linha('Este mês', `${fmt(f.mes_atual)}${f.comparacao ? t(' ({comparacao} vs mês anterior)', { comparacao: f.comparacao }) : ''}`),
        ...linha('Último', f.ultimo ? dataLonga(f.ultimo.dia) : '—'), ...linha('Próximo', f.proximo ? dataLonga(f.proximo.dia) : '—')),
      no('p', { texto: f.radios.length ? t('Rádios que alcançam: {lista}', { lista: f.radios.join(', ') }) : t('Nenhuma rádio cadastrada alcança esta comunidade.') }),
      no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-ficha': 'pdf', texto: t('Relatório desta comunidade (PDF)') })),
      pode('enviar_relatorio') ? no('label', {}, no('span', { texto: t('Enviar por e-mail (domínio da empresa)') }), ' ',
        no('input', { 'data-ficha-destinos': '', maxlength: '400', autocomplete: 'email', inputmode: 'email' })) : null,
      pode('enviar_relatorio') ? no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-ficha': 'enviar', texto: t('Enviar') })) : null);
    caixa.addEventListener('click', async evento => {
      const b = evento.target.closest('button[data-ficha]');
      if (!b) return;
      b.disabled = true;
      try {
        if (b.dataset.ficha === 'pdf') {
          await baixarDaApi(`/api/relatorios/comunidade.pdf?${consulta(filtros)}`, { method: 'GET' }, 'farol-comunidade.pdf');
          avisar(t('Relatório de {nome} baixado, com o seu nome e o código de verificação (registrado na auditoria).', { nome: f.nome }));
        } else {
          const destinos = destinatarios(caixa.querySelector('[data-ficha-destinos]').value);
          if (!destinos.length) return avisar(t('Escreva o e-mail de quem vai receber (até 5, do domínio da empresa).'), true);
          if (!confirm(t('Enviar o relatório de {nome} (PDF) para {destinos}?', { nome: f.nome, destinos: destinos.join(', ') }))) return;
          const r = await api('/api/relatorios/comunidade/enviar', { method: 'POST', json: { filtros, destinatarios: destinos } });
          avisar(t('Relatório de {nome} enviado para {destinos} (código {codigo}).', { nome: f.nome, destinos: r.destinatarios.join(', '), codigo: r.codigo }));
        }
      } catch (e) {
        if (e.status !== 401) avisar(e.message, true);
      } finally {
        b.disabled = false;
      }
    });
  } catch (e) {
    caixa.replaceChildren(no('p', { texto: e.status === 401 ? t('A sessão acabou.') : e.message }));
  }
}

// rede elétrica FICTÍCIA dos municípios na tela (de perto): média tensão por alimentador, subestação,
// chaves e, mais de perto, os trafos. Só demonstração; nada de cliente.
// o rótulo do botão da rede (também ao trocar o idioma, antes de a rede carregar)
function desenharBotaoRede() {
  const botao = $('botaoRede');
  botao.textContent = estado.verRede ? t('Esconder rede fictícia') : t('Mostrar rede fictícia');
  botao.setAttribute('aria-pressed', String(estado.verRede));
}

function desenharRede() {
  camadaRede?.remove();
  camadaRede = null;
  desenharBotaoRede();
  $('legendaRede').hidden = !estado.verRede;
  atribuicao?.removeAttribution(CREDITO_REDE);
  atribuicao?.removeAttribution(t(CREDITO_REDE));
  if (!mapa || !estado.verRede || mapa.getZoom() < ZOOM_COMUNIDADES) return;
  telaRede ||= L.canvas({ padding: .3 });
  const partes = [];
  for (const m of municipiosNaTela()) {
    const r = estado.redes[m.codigo_ibge];
    if (!r) continue;
    const cor = a => CORES_ALIMENTADOR[(parseInt(a.split('-').pop(), 10) - 1) % CORES_ALIMENTADOR.length] || COR.info;
    partes.push(L.geoJSON(r.alimentadores, {
      style: f => ({ color: cor(f.properties.alimentador), weight: 2.2, opacity: .9 }),
      onEachFeature: (f, l) => l.bindTooltip(() => no('span', { texto: t('Alimentador {alimentador} (fictício) · {municipio}', { alimentador: f.properties.alimentador, municipio: m.nome }) }), { sticky: true }),
    }));
    if (mapa.getZoom() >= ZOOM_TRAFOS)
      for (const [lat, lon] of r.trafos)
        partes.push(L.circleMarker([lat, lon], { renderer: telaRede, radius: 2.5, weight: 0, fillColor: COR.cinza, fillOpacity: .9, interactive: false }));
    for (const [lat, lon, codigo, alim, jusante] of r.chaves)
      partes.push(L.circleMarker([lat, lon], { radius: 4.5, weight: 1.5, color: '#FFFFFF', fillColor: cor(alim), fillOpacity: 1 })
        .bindTooltip(() => no('span', { texto: t('Chave {codigo} (fictícia) · alimentador {alimentador} · {n} unidades a jusante', { codigo, alimentador: alim, n: fmt(jusante) }) })));
    const se = r.subestacao;
    partes.push(L.marker(se.ponto, { keyboard: false, icon: L.divIcon({ className: 'subestacao', html: no('span'), iconSize: [16, 16] }) })
      .bindTooltip(() => no('span', { texto: se.nome })));
  }
  if (!partes.length) return;
  camadaRede = L.layerGroup(partes).addTo(mapa);
  atribuicao.addAttribution(t(CREDITO_REDE));
}

function desenharLegenda() {
  const min = estado.legendaMinimizada;
  $('legenda').classList.toggle('minimizada', min);
  $('botaoLegenda').setAttribute('aria-expanded', String(!min));
  $('botaoLegendaTexto').textContent = min ? t('Legenda') : t('Minimizar legenda');
  $('botaoLegenda').querySelector('.seta').textContent = min ? '▸' : '▾';
}

function alternarLegenda() {
  estado.legendaMinimizada = !estado.legendaMinimizada;
  try { localStorage.setItem('farol.legenda', estado.legendaMinimizada ? 'minimizada' : 'aberta'); } catch (e) { /* sem armazenamento: só nesta visita */ }
  desenharLegenda();
}

// busca (uma vez) o que falta dos municípios na tela: comunidades e, com a rede ligada, a rede fictícia
async function buscarNaTela() {
  const tarefas = [];
  for (const m of municipiosNaTela()) {
    const c = m.codigo_ibge;
    if (!estado.territorios[c] && !buscando.has(c))
      tarefas.push([c, async () => { estado.territorios[c] = await api(`/api/municipios/${c}/comunidades`); }]);
    if (estado.verRede && !(c in estado.redes) && !buscando.has(`rede ${c}`))
      tarefas.push([`rede ${c}`, async () => {
        try { estado.redes[c] = (await api(`/api/municipios/${c}/rede`)) || null; } catch (e) { if (e.status === 404) estado.redes[c] = null; else throw e; }
      }]);
  }
  await Promise.all(tarefas.map(async ([chave, fazer]) => {
    buscando.add(chave);
    try { await fazer(); } catch (e) { /* tenta de novo no próximo movimento */ }
    buscando.delete(chave);
  }));
}

async function aoMoverMapa() {
  if (mapa.getZoom() >= ZOOM_COMUNIDADES && estado.tela === 'app' && !ehFarol()) await buscarNaTela();
  desenharBase(); desenharNomes(); desenharCidades(); desenharRede();
  document.documentElement.dataset.mapa = `z${mapa.getZoom()}`;
}

async function alternarRede() {
  estado.verRede = !estado.verRede;
  desenharRede();
  if (estado.verRede && mapa.getZoom() >= ZOOM_COMUNIDADES) { await buscarNaTela(); desenharRede(); }
  else if (estado.verRede) avisar(t('A rede fictícia aparece de perto: aproxime num município (ou clique nele).'));
}

// "Ir para": o estado e o município da concessão (a lista sai do contorno da concessão)
function desenharIrPara() {
  const feicoes = estado.concessao?.features || [];
  $('irPara').hidden = !feicoes.length;
  if (!feicoes.length) return;
  const ufs = [...new Set(feicoes.map(f => f.properties.uf))].sort();
  const uf = $('filtroUf').value || '';
  if (!$('filtroUf').options.length) $('filtroUf').replaceChildren(no('option', { value: '', texto: t('Todos') }), ...ufs.map(u => no('option', { value: u, texto: u })));
  else $('filtroUf').options[0].textContent = t('Todos');
  $('filtroMunicipio').replaceChildren(no('option', { value: '', texto: t('Escolha') }), ...feicoes.filter(f => !uf || f.properties.uf === uf)
    .map(f => [f.properties.codigo_ibge, f.properties.nome]).sort((a, b) => a[1].localeCompare(b[1], IDIOMA))
    .map(([c, n]) => no('option', { value: c, texto: n })));
}

function irParaNoMapa(evento) {
  if (!camadaConcessao) return;
  const camadas = camadaConcessao.getLayers();
  if (evento.target.id === 'filtroUf') {
    desenharIrPara();
    const uf = $('filtroUf').value, alvo = camadas.filter(l => !uf || l.feature.properties.uf === uf);
    if (alvo.length) mapa.fitBounds(L.featureGroup(alvo).getBounds(), { padding: [20, 20] });
  } else {
    const l = camadas.find(x => x.feature.properties.codigo_ibge === $('filtroMunicipio').value);
    if (l) mapa.fitBounds(l.getBounds(), { padding: [20, 20] });
  }
}

function desenharConcessao() {
  if (!estado.concessao) return;
  const afetados = new Set((estado.resultado?.municipios || []).map(m => m.codigo_ibge));
  const contagem = estado.vista === 'painel' && estado.painel ? estado.painel.por_municipio : null;
  const maxAvisos = contagem ? Math.max(1, ...Object.values(contagem)) : 1;
  $('mapa').closest('.mapa-area').querySelector('.legenda-painel').hidden = !contagem;
  camadaConcessao?.remove();
  camadaConcessao = L.geoJSON(estado.concessao, {
    style: f => contagem
      ? { color: contagem[f.properties.codigo_ibge] ? COR.verde : COR.cinza, weight: contagem[f.properties.codigo_ibge] ? 1.5 : .8,
          fillColor: COR.verde, fillOpacity: contagem[f.properties.codigo_ibge] ? .15 + .55 * contagem[f.properties.codigo_ibge] / maxAvisos : .03 }
      : afetados.has(f.properties.codigo_ibge)
        ? { color: COR.info, weight: 3, fillOpacity: 0 }
        : { color: COR.cinza, weight: .8, opacity: .6, fillColor: COR.cinza, fillOpacity: .04 },
    onEachFeature: (f, l) => {
      l.bindTooltip(() => no('span', { texto: `${f.properties.nome}/${f.properties.uf}`
        + (contagem ? t(' · {n} aviso(s)', { n: fmt(contagem[f.properties.codigo_ibge] || 0) }) : '') }), { sticky: true });
      // de longe, clicar no município aproxima nele (e aparecem as comunidades)
      l.on('click', () => { if (mapa.getZoom() < ZOOM_COMUNIDADES) mapa.fitBounds(l.getBounds(), { padding: [20, 20] }); });
    },
  }).addTo(mapa);
  camadaConcessao.bringToBack();
  desenharCidades();
}

function desenharComunidades() {
  camadaComunidades?.remove();
  camadaComunidades = null;
  const r = estado.resultado;
  if (!r || naEscolha()) return;   // no passo 3, o mapa é o da escolha (desenharMapaEscolha)
  // as afetadas preenchidas; as outras comunidades dos mesmos municípios só com o contorno, por baixo
  const feicoes = [], outras = [];
  for (const m of r.municipios) {
    const terr = estado.territorios[m.codigo_ibge];
    if (!terr) continue;
    const porNome = new Map(m.comunidades.map(c => [c.nome, c]));
    for (const f of terr.features) {
      const c = porNome.get(f.properties.nome);
      if (c) feicoes.push({ ...f, properties: { ...f.properties, m, c } });
      else outras.push({ ...f, properties: { ...f.properties, municipio: m.nome, codigo_ibge: m.codigo_ibge } });
    }
  }
  if (!feicoes.length) return;
  camadaComunidades = L.geoJSON({ type: 'FeatureCollection', features: [...outras, ...feicoes] }, {
    style: estiloAviso,
    onEachFeature: (f, l) => {
      const { c, m } = f.properties;
      l.on('click', e => cliqueNaComunidade(e, l, m?.codigo_ibge || f.properties.codigo_ibge, c?.nome || f.properties.nome, c ? c.distrito : f.properties.distrito));
      if (!c) return l.bindTooltip(() => no('span', { texto: t('{nome} · fora do aviso', { nome: semSufixo(f.properties.nome) }) }), { sticky: true });
      l.bindTooltip(() => no('span', {}, no('strong', { texto: nomeComDistrito(c, m) }), ` · ${t(ROTULO[situacao(c)])}`, no('br'),
        t('{ucs} UCs afetadas · {total} endereços na comunidade', { ucs: fmt(c.afetadas), total: fmt(c.total) })), { sticky: true });
    },
  }).addTo(mapa);
  // o zoom enquadra só as comunidades afetadas (não o município inteiro) e deixa de lado municípios com
  // menos de 10% das UCs (um ponto isolado longe do resto não pode afastar o mapa)
  const total = r.municipios.reduce((s, m) => s + m.ucs, 0);
  const principais = new Set(r.municipios.filter(m => m.ucs >= total * .1).map(m => m.codigo_ibge));
  const foco = feicoes.filter(f => principais.has(f.properties.m.codigo_ibge));
  mapa.fitBounds(L.geoJSON({ type: 'FeatureCollection', features: foco.length ? foco : feicoes }).getBounds(), { padding: [30, 30], maxZoom: 13 });
}

// pontos das UCs da planilha: só os do envio atual, desenhados num canvas (nada no HTML) e sem o
// número da UC; a dica mostra só a comunidade
const temPontos = () => !!estado.resultado && (estado.resultado.municipios.some(m => m.pontos?.length) || !!estado.resultado.pontos_fora?.length
  || !!estado.resultado.pontos_corrigidos?.length);

function desenharUcs() {
  camadaUcs?.remove();
  camadaUcs = null;
  const r = estado.resultado, botao = $('botaoUcs');
  botao.closest('li').hidden = !temPontos() || naEscolha();
  botao.textContent = estado.verUcs ? t('Esconder UCs') : t('Mostrar UCs');
  botao.setAttribute('aria-pressed', String(estado.verUcs));
  if (!temPontos() || !estado.verUcs || naEscolha()) return;
  telaUcs ||= L.canvas({ padding: .3 });
  const ponto = (lat, lon, cor, dica) => L.circleMarker([lat, lon], { renderer: telaUcs, radius: 3.5, weight: 1, color: '#FFFFFF', fillColor: cor, fillOpacity: .95 })
    .bindTooltip(() => no('span', { texto: dica }));   // nó de texto: o Leaflet poria uma string como HTML
  const marcas = [];
  for (const m of r.municipios) {
    for (const [lat, lon, i] of m.pontos || []) {
      const c = m.comunidades[i];
      marcas.push(ponto(lat, lon, c && situacao(c) !== 'vizinha' ? COR.ambarForte : COR.cinza,
        t('UC da planilha · {nome}', { nome: c ? nomeComDistrito(c, m) : m.nome })));
    }
  }
  for (const [lat, lon] of r.pontos_fora || []) marcas.push(ponto(lat, lon, COR.erro, t('UC fora da concessão')));
  // as corrigidas por último (por cima), com a cor própria
  for (const [lat, lon] of r.pontos_corrigidos || []) marcas.push(ponto(lat, lon, COR.corrigida, t('UC com coordenada corrigida (confira)')));
  camadaUcs = L.layerGroup(marcas).addTo(mapa);
  if (!camadaComunidades && marcas.length) mapa.fitBounds(L.featureGroup(marcas).getBounds(), { padding: [30, 30], maxZoom: 13 });
}

// ---- Mapa da escolha (passo 3): as comunidades dos municípios da planilha (clique: incluir ou tirar), as UCs da base num
// canvas sem clique (as escolhidas em âmbar, as inativas fora vazadas) e as áreas desenhadas. Nada disso vai para o HTML ----
let camadaEscolhaComunidades, camadaEscolhaPontos, camadaEscolhaAreas, telaEscolha, marcasEscolha = [], estilosEscolha = [];
const naEscolha = () => estado.passo === 3 && (estado.origem === 'novo' || !estado.resultado);
const emEscolha = () => estado.vista === 'aviso' && estado.passo === 3 && !!estado.leitura && !!estado.selecao;
function apagarMapaEscolha() {
  for (const c of [camadaEscolhaComunidades, camadaEscolhaPontos, camadaEscolhaAreas]) c?.remove();
  camadaEscolhaComunidades = camadaEscolhaPontos = camadaEscolhaAreas = null;
  marcasEscolha = []; estilosEscolha = [];
  if (mapa) { mapa.getContainer().classList.remove('desenhando'); mapa.doubleClickZoom.enable(); }
}
const ESTILO_PONTO = [   // 0 fora da escolha, 1 escolhida, 2 inativa (fora)
  { radius: 2.5, weight: 1, color: COR.cinza, fillColor: COR.cinza, fillOpacity: .35, opacity: .8 },
  { radius: 3.5, weight: 1, color: '#FFFFFF', fillColor: COR.ambarForte, fillOpacity: .95, opacity: 1 },
  { radius: 2.5, weight: 1, color: COR.cinza, fillColor: COR.cinza, fillOpacity: 0, opacity: .7 },
];
function estiloComunidadeEscolha(f) {
  const i = f.properties.indice;
  if (i < 0) return { color: COR.cinza, weight: .8, dashArray: null, fillColor: COR.cinza, fillOpacity: .02 };
  return estado.selecao.comunidades.has(i) ? { color: COR.ambarForte, weight: 2, dashArray: null, fillColor: COR.ambar, fillOpacity: .45 }
    : { color: COR.ambarForte, weight: 1, dashArray: '4 4', fillColor: COR.ambar, fillOpacity: .06 };
}
function desenharMapaEscolha(enquadrar = false) {
  if (!mapa) return;
  if (!emEscolha()) return apagarMapaEscolha();
  const b = estado.leitura.base, s = estado.selecao, sel = estado.sel, ln = b.linhas;
  if (!mapa.getPane('escolhaPontos')) {   // por cima das comunidades e sem pegar o clique (o clique vai para a comunidade ou o mapa)
    for (const [nome, z] of [['escolhaPontos', 450], ['escolhaDesenho', 460]]) {
      const pane = mapa.createPane(nome);
      pane.style.zIndex = z; pane.style.pointerEvents = 'none';
    }
  }
  if (!camadaEscolhaComunidades && b.municipios.every(m => estado.territorios[m.codigo_ibge])) {
    const indice = new Map(b.comunidades.map((c, i) => [`${b.municipios[c.municipio].codigo_ibge}|${c.nome}`, i]));
    const ucs = itensDaLista(b, s, 'comunidade');
    const feicoes = b.municipios.flatMap(m => estado.territorios[m.codigo_ibge].features.map(f => ({ ...f, properties: { ...f.properties,
      municipio: m.nome, indice: indice.get(`${m.codigo_ibge}|${f.properties.nome}`) ?? -1 } })));
    camadaEscolhaComunidades = L.geoJSON({ type: 'FeatureCollection', features: feicoes }, {
      style: estiloComunidadeEscolha,
      onEachFeature: (f, l) => {
        const p = f.properties;
        l.bindTooltip(() => no('span', { texto: `${semSufixo(p.nome)} (${distritoDe(p.distrito, p.municipio)}) · `
          + (p.indice >= 0 ? t('{n} UC(s) da planilha · clique para incluir ou tirar', { n: fmt(ucs[p.indice][2]) }) : t('nenhuma UC da planilha')) }), { sticky: true });
      },   // o clique é tratado no mapa (cliqueNoMapa): assim vale mesmo com a rede fictícia por cima
    }).addTo(mapa);
  } else camadaEscolhaComunidades?.setStyle(estiloComunidadeEscolha);
  if (!camadaEscolhaPontos) {
    telaEscolha ||= L.canvas({ padding: .3, pane: 'escolhaPontos' });
    marcasEscolha = ln.lat.map((lat, i) => lat === null ? null
      : L.circleMarker([lat, ln.lon[i]], { renderer: telaEscolha, pane: 'escolhaPontos', interactive: false, ...ESTILO_PONTO[0] }));
    estilosEscolha = marcasEscolha.map(() => 0);
    camadaEscolhaPontos = L.layerGroup(marcasEscolha.filter(Boolean)).addTo(mapa);
  }
  marcasEscolha.forEach((m, i) => {
    const e = sel[i] ? 1 : ln.inativa[i] && !s.incluirInativas ? 2 : 0;
    if (m && e !== estilosEscolha[i]) { m.setStyle(ESTILO_PONTO[e]); m.setRadius(ESTILO_PONTO[e].radius); estilosEscolha[i] = e; }
  });
  camadaEscolhaAreas?.remove();
  const areas = s.poligonos.map(p => L.polygon(p.map(anel => anel.map(([x, y]) => [y, x])), { pane: 'escolhaDesenho', interactive: false,
    color: COR.ambarForte, weight: 2.5, dashArray: '6 4', fillColor: COR.ambar, fillOpacity: .12 }));
  const d = s.desenho || [];
  if (d.length > 1) areas.push(L.polyline(d, { pane: 'escolhaDesenho', interactive: false, color: COR.ambarForte, weight: 3 }));
  if (d.length > 2) areas.push(L.polyline([d[d.length - 1], d[0]], { pane: 'escolhaDesenho', interactive: false, color: COR.ambarForte, weight: 2, dashArray: '4 6' }));
  for (const v of d) areas.push(L.circleMarker(v, { pane: 'escolhaDesenho', interactive: false, radius: 5, color: '#0E1620', weight: 2, fillColor: COR.ambar, fillOpacity: 1 }));
  camadaEscolhaAreas = L.layerGroup(areas).addTo(mapa);
  mapa.getContainer().classList.toggle('desenhando', !!s.desenho);
  if (s.desenho) mapa.doubleClickZoom.disable(); else mapa.doubleClickZoom.enable();
  const comPonto = marcasEscolha.filter(Boolean);
  if (enquadrar && comPonto.length) mapa.fitBounds(L.featureGroup(comPonto).getBounds(), { padding: [30, 30], maxZoom: 14 });
}

// ======================= Controller: eventos e chamadas à API (atualiza o estado e redesenha) =======================
class ErroApi extends Error {
  constructor(status, mensagem, dados = {}, campo = null) { super(mensagem); this.status = status; this.dados = dados; this.campo = campo; }
}
const SEM_CONEXAO = 'Sem conexão com o servidor: o pedido não foi concluído. Confira a internet e tente de novo.';
const ERRO_SERVIDOR = 'O servidor teve um problema e nada foi salvo. Tente de novo em instantes; se continuar, avise o suporte.';

// fetch com a falha de rede traduzida (o navegador diria só "Failed to fetch")
// o idioma da tela vai em todo pedido (X-Farol-Idioma): o servidor responde os erros e os relatórios nele
async function buscar(url, opcoes = {}) {
  try {
    return await fetch(url, { credentials: 'same-origin', ...opcoes, headers: { ...(opcoes.headers || {}), 'X-Farol-Idioma': IDIOMA } });
  } catch (e) { throw new ErroApi(0, t(SEM_CONEXAO)); }
}

// a resposta de erro vira uma mensagem clara: a do servidor (JSON) ou, se o corpo não for JSON (proxy fora do ar), a padrão
async function erroDaResposta(r, padrao = 'Não foi possível concluir. Confira os dados e tente de novo.') {
  const j = (r.headers.get('Content-Type') || '').includes('json') ? await r.json().catch(() => ({})) : {};
  if (r.status === 401 && estado.tela === 'app') { sessaoAcabou(); return new ErroApi(401, t('A sessão acabou. Entre de novo.')); }
  const texto = typeof j.detail === 'string' ? j.detail : r.status >= 500 ? t(ERRO_SERVIDOR) : t(padrao);
  return new ErroApi(r.status, texto, j, r.headers.get('X-Farol-Campo') || j.campo || null);
}

async function api(url, opcoes = {}) {
  const r = await buscar(url, { ...opcoes, headers: opcoes.json ? { 'Content-Type': 'application/json' } : undefined,
    body: opcoes.json ? JSON.stringify(opcoes.json) : opcoes.body });
  if (!r.ok) throw await erroDaResposta(r);
  return r.json().catch(() => ({}));
}

// enquanto salva: o botão fica desabilitado com "Salvando…" (ou outro texto) e um segundo clique não faz nada
async function ocupado(botao, texto, fazer) {
  if (!botao) return fazer();
  if (botao.dataset.ocupado) return;
  const antes = botao.textContent;
  texto = t(texto);
  Object.assign(botao.dataset, { ocupado: '1' });
  botao.disabled = true;
  botao.setAttribute('aria-busy', 'true');
  botao.textContent = texto;
  try {
    return await fazer();
  } finally {
    delete botao.dataset.ocupado;
    botao.disabled = false;
    botao.removeAttribute('aria-busy');
    if (botao.textContent === texto) botao.textContent = antes;
  }
}
const botaoDoEnvio = evento => evento.submitter || evento.target.querySelector('button[type=submit]');

// pedido que devolve um arquivo (CSV, JSON): baixa com o nome que o servidor sugere; nada fica na página
// rádios sugeridas e envios do aviso aberto (só depois de gerado; quem só consulta vê os envios)
async function carregarEnvios() {
  const r = estado.resultado;
  if (!r?.id) return;
  try {
    const [envs, sug, ped] = await Promise.all([pode('ver_historico') ? api(`/api/historico/${r.id}/envios`) : { envios: [] },
      pode('gerar_aviso') ? api(`/api/historico/${r.id}/radios`) : null, pode('pedir_radio') ? api('/api/radios/pedidos') : null]);
    estado.envios = envs.envios;
    if (ped) estado.meusPedidos = ped.pedidos;
    if (sug) { estado.radios = sug.radios; estado.sugestao = Object.fromEntries(sug.municipios.map(x => [x.codigo_ibge, x])); }
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
  for (const m of r.municipios) desenharEnvio(m);
}

function editarEnvio(evento) {
  const alvo = evento.target, sec = alvo.closest('section.envio-radio');
  if (!sec || !(alvo.dataset.envio || alvo.dataset.pedidoCampo)) return;
  const cod = sec.dataset.codigo, e = estado.escolha[cod];
  if (alvo.dataset.pedidoCampo) { e.pedido[alvo.dataset.pedidoCampo] = alvo.value; return; }
  e[alvo.dataset.envio] = alvo.value;
  if (alvo.dataset.envio === 'radioId' && evento.type === 'change') {   // outra rádio: o valor sugerido dela
    const radio = estado.radios.find(x => String(x.id) === alvo.value);
    Object.assign(e, escolhaPadrao(radio));
    return desenharEnvio(estado.resultado.municipios.find(x => x.codigo_ibge === cod));
  }
  desenharPrevia(cod);
}

async function acaoEnvio(evento) {
  const b = evento.target.closest('button[data-envio-acao], button[data-arquivo]');
  if (!b) return;
  if (b.dataset.arquivo) {
    return ocupado(b, 'Baixando…', async () => {
      try { await baixarDaApi(`/api/envios/${b.dataset.envioId}/arquivos/${b.dataset.arquivo}`, { method: 'GET' }, `farol-envio.${b.dataset.arquivo}`); }
      catch (e) { if (e.status !== 401) avisar(e.message, true); }
    });
  }
  if (b.dataset.envioAcao === 'ir-radios') return irPara('radios');
  const sec = b.closest('section.envio-radio'), cod = sec.dataset.codigo, m = estado.resultado.municipios.find(x => x.codigo_ibge === cod);
  if (b.dataset.envioAcao === 'pedir') {
    const p = estado.escolha[cod].pedido;
    p.aberto = !p.aberto;
    desenharEnvio(m);
    return p.aberto ? $(`pedido-nome-${cod}`)?.focus() : sec.querySelector('[data-envio-acao=pedir]')?.focus();
  }
  await ocupado(b, b.dataset.envioAcao === 'enviar-pedido' ? 'Enviando…' : b.dataset.envioAcao === 'copia' ? 'Copiando…' : 'Enviando…', async () => {
    try {
      if (b.dataset.envioAcao === 'enviar-pedido') await pedirRadio(m, sec);
      else await enviarParaRadio(m, b.dataset.envioAcao, sec);
    } catch (e) {
      if (e.status === 401) return;
      avisar(e.message, true);
      erroDoServidor(b.dataset.envioAcao === 'enviar-pedido' ? $(`pedido-${cod}`) : sec, e, b.dataset.envioAcao === 'enviar-pedido'
        ? Object.fromEntries(['nome', 'cidade', 'contato', 'observacao'].map(c => [c, `pedido-${c}-${cod}`]))
        : { valor: `valor-${cod}`, custo_antigo: `antigo-${cod}`, texto: `aviso-${cod}` });
    }
  });
}

async function pedirRadio(m, sec) {
  const cod = m.codigo_ibge, p = estado.escolha[cod].pedido, lugar = $(`pedido-${cod}`);
  const erros = [p.nome.trim().length < 2 && [`pedido-nome-${cod}`, t('Informe o nome da rádio (de 2 a 80 caracteres).')],
    p.cidade.trim().length < 2 && [`pedido-cidade-${cod}`, t('Informe a cidade da rádio.')]].filter(Boolean);
  if (erros.length) { mostrarErros(lugar, erros); return avisar(erros[0][1], true); }
  limparErros(lugar);
  const j = await api('/api/radios/pedidos', { method: 'POST', json: { nome: p.nome, cidade: p.cidade, contato: p.contato, observacao: p.observacao } });
  avisar(t('Pedido de cadastro da {nome} enviado ao Admin da empresa (registrado na auditoria).', { nome: j.pedido.nome }));
  Object.assign(p, { nome: '', contato: '', observacao: '' });
  estado.meusPedidos = (await api('/api/radios/pedidos')).pedidos;
  desenharEnvio(m);
  sec.querySelector('[data-envio-acao=pedir]')?.focus();
}

async function enviarParaRadio(m, canal, sec) {
  const cod = m.codigo_ibge, e = estado.escolha[cod], radio = estado.radios.find(x => String(x.id) === String(e.radioId));
  if (!radio) return avisar(t('Escolha a rádio.'), true);
  const valor = reaisNumero(e.valor), antigo = reaisNumero(e.antigo), texto = estado.avisos[cod];
  const erros = [(valor === null || Number.isNaN(valor)) && [`valor-${cod}`, t('Informe o valor deste envio em R$ (ex.: 150,00).')],
    Number.isNaN(antigo) && [`antigo-${cod}`, t('O custo antigo tem de ser um valor em R$ (ou vazio).')]].filter(Boolean);
  if (erros.length) { mostrarErros(sec, erros); return avisar(erros[0][1], true); }
  limparErros(sec);
  if (canal === 'email') {
    if (!radio.email) return avisar(t('{nome} não tem e-mail cadastrado.', { nome: radio.nome }), true);
    if (!confirm(t('Enviar para {nome} ({email})?', { nome: radio.nome, email: radio.email }))) return;
    avisar(t(temAudio() ? 'Gerando o PDF e o MP3 e enviando para {nome}…' : 'Gerando o PDF e enviando para {nome}…', { nome: radio.nome }));
  } else if (canal === 'whatsapp') {
    if (!radio.whatsapp) return avisar(t('{nome} não tem WhatsApp cadastrado.', { nome: radio.nome }), true);
    if (!confirm(t('Abrir o WhatsApp para {nome} ({numero}) com a mensagem?', { nome: radio.nome, numero: radio.whatsapp }))) return;
    const numero = radio.whatsapp.length > 11 ? radio.whatsapp : `55${radio.whatsapp}`;
    window.open(`https://wa.me/${numero}?text=${encodeURIComponent(texto)}`, '_blank', 'noopener');
  } else {
    if (!confirm(t('Copiar a mensagem para mandar para {nome}?', { nome: radio.nome }))) return;
    try { await navigator.clipboard.writeText(texto); } catch (x) { return avisar(t('Não foi possível copiar; selecione o texto e use Ctrl+C.'), true); }
  }
  const j = await api(`/api/historico/${estado.resultado.id}/envios`, { method: 'POST', json: { municipio: cod, radio_id: radio.id, canal, texto,
    valor: e.valor, cobranca: e.cobranca, custo_antigo: e.antigo || null } });
  avisar(j.erro || t({ email: 'E-mail entregue ao servidor para {nome} ({email}). A rádio confirma pelo link do e-mail.',
    whatsapp: 'WhatsApp aberto para {nome}; o envio ficou registrado.', copia: 'Mensagem copiada para {nome}; o envio ficou registrado.' }[canal],
    { nome: radio.nome, email: radio.email }), !!j.erro);
  estado.finais[cod] = texto;
  desenharFinal(cod);
  await carregarEnvios();
}

async function baixarDaApi(url, opcoes, nomePadrao) {
  const r = await buscar(url, { method: 'POST', ...opcoes });
  if (!r.ok) throw await erroDaResposta(r, 'Não foi possível baixar.');
  const nome = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '')?.[1] || nomePadrao;
  const href = URL.createObjectURL(await r.blob()), link = no('a', { href, download: nome });
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10000);
}

function sessaoAcabou() {
  limparTela();
  estado.tela = 'entrar';
  desenharTela(); desenharEstado();
  mensagemEm('estadoEntrar', t('A sessão acabou. Entre de novo.'), true);
}

function avisar(mensagem, erro = false) {
  estado.mensagem = mensagem; estado.erro = erro;
  desenharEstado();
}

async function abrirApp() {
  estado.tela = 'app';
  estado.vista = vistasDoPerfil()[0]?.[0] || 'historico';
  if (estado.vista === 'painel' && !pode('ver_historico')) estado.vista = 'historico';
  desenharTela(); desenharAbas();
  iniciarMapa();
  mapa.invalidateSize();
  [estado.config, estado.concessao] = await Promise.all([api('/api/config'),
    ehFarol() ? { type: 'FeatureCollection', features: [] } : api('/api/concessao')]);
  $('mapa').setAttribute('aria-label', ehFarol() ? t('Mapa das empresas: a área de atuação de cada uma') : t('Mapa dos municípios da concessão e das comunidades afetadas'));
  $('faixa').textContent = t(estado.config.aviso_ficticio);
  // o idioma do aviso: cada um no próprio nome (lang); o padrão é o da empresa
  $('idioma').replaceChildren(...Object.entries(estado.config.idiomas).map(([k, nome]) => no('option', { value: k, lang: k, texto: nome })));
  $('idioma').value = estado.config.idioma_padrao;
  estado.radio = { preco: estado.config.radio.preco_spot, veiculacoes: estado.config.radio.veiculacoes };
  $('precoSpot').value = String(estado.radio.preco).replace('.', ',');
  $('veiculacoes').value = String(estado.radio.veiculacoes);
  desenharCusto();
  desenharPergunta();
  desenharTipos();
  $('tipo').value = estado.config.tipo_padrao;
  desenharIdiomaAviso();
  $('tipoOutro').maxLength = estado.config.max_outro;
  desenharConcessao();
  desenharIrPara();
  $('botaoCalor').textContent = estado.calor ? t('Esconder mapa de calor') : t('Mapa de calor (12 meses)');
  atribuicao?.setPrefix(t('Concessão e comunidades: IBGE · Leaflet'));
  if (ehFarol()) {
    await carregarMapaEmpresas();
    if (camadaEmpresas?.getLayers().length) mapa.fitBounds(camadaEmpresas.getBounds(), { padding: [20, 20] });
  } else if (camadaConcessao.getLayers().length) mapa.fitBounds(camadaConcessao.getBounds(), { padding: [20, 20] });
  desenharLegendaEmpresas();
  await irPara(estado.vista);
}

async function aposEntrar(usuario) {
  estado.usuario = usuario;
  estado.painelAmplo = !!usuario.preferencias?.acessibilidade?.painel;
  carregarA11y(usuario.preferencias?.acessibilidade || {});
  desenharPainelAmplo();
  // o idioma guardado no perfil vale; sem ele, o escolhido na tela de entrar passa a ser o do perfil
  const preferido = usuario.preferencias?.idioma;
  if (preferido && preferido !== IDIOMA) await trocarIdioma(preferido, false);
  else if (!preferido && IDIOMA !== 'pt-BR') api('/api/eu/preferencias', { method: 'PUT', json: { idioma: IDIOMA } }).catch(() => {});
  if (usuario.trocar_senha) {
    estado.tela = 'senha';
    desenharTela();
    $('senhaAtual').focus();
  } else {
    await abrirApp();
  }
}

async function entrar(evento) {
  evento.preventDefault();
  const email = $('email').value.trim(), senha = $('senha').value;
  const erros = [!email && ['email', t('Informe o e-mail.')], !senha && ['senha', t('Informe a senha.')]].filter(Boolean);
  if (erros.length) { mostrarErros($('formEntrar'), erros); return mensagemEm('estadoEntrar', t('Informe o e-mail e a senha.'), true); }
  limparErros($('formEntrar'));
  await ocupado($('botaoEntrar'), 'Entrando…', async () => {
    try {
      const j = await api('/api/entrar', { method: 'POST', json: { email, senha } });
      $('senha').value = '';
      mensagemEm('estadoEntrar', '');
      await aposEntrar(j.usuario);
    } catch (e) {
      mensagemEm('estadoEntrar', e.message, true);
    }
  });
}

async function trocarSenha(evento) {
  evento.preventDefault();
  const atual = $('senhaAtual').value, nova = $('senhaNova').value;
  const erros = [!atual && ['senhaAtual', t('Informe a senha atual (a temporária).')], validarSenhaNova(nova, $('senhaNova2').value)].filter(Boolean);
  if (erros.length) { mostrarErros($('formSenha'), erros); return mensagemEm('estadoSenha', erros[0][1], true); }
  limparErros($('formSenha'));
  await ocupado($('botaoSenha'), 'Salvando…', async () => {
    try {
      const j = await api('/api/senha', { method: 'POST', json: { atual, nova } });
      for (const id of ['senhaAtual', 'senhaNova', 'senhaNova2']) $(id).value = '';
      mensagemEm('estadoSenha', '');
      await aposEntrar(j.usuario);
    } catch (e) {
      mensagemEm('estadoSenha', e.message, true);
      erroDoServidor($('formSenha'), e, { atual: 'senhaAtual', nova: 'senhaNova' });
    }
  });
}

// ao sair (ou quando a sessão acaba), nada do usuário anterior fica na página: num computador
// compartilhado, quem entra depois não vê resultados, listas nem o roteiro escondidos
function limparTela() {
  Object.assign(estado, { usuario: null, resultado: null, origem: null, avisos: {}, finais: {}, formulario: null, arquivo: null,
    conferi: false, justificativa: '', abas: [], aba: '',
    historico: [], usuarios: [], perfis: {}, empresas: [], registro: [], mensagem: '', erro: false,
    passo: 1, painel: null, pergunta: null, radio: null, evidencia: null, filtroHistorico: { busca: '', periodo: '' } });
  Object.assign(estado, { radios: [], sugestao: {}, envios: [], escolha: {}, relatorio: null, opcoesRelatorio: null, vias: [], ficha: null,
    calor: null, simulador: null });
  descartarLeitura();
  for (const id of ['abas', 'resumo', 'municipios', 'problemasCorpo', 'listaHistorico', 'listaUsuarios', 'listaEmpresas', 'listaRegistro',
    'painelDash', 'contagemHistorico', 'respostaPergunta', 'exemplosPergunta', 'conferencia', 'aba', 'solicitado', 'acoesAviso', 'estadoAuditoria', 'relatorio', 'relMes', 'audMes',
    'listaRadios', 'radComunidades', 'ajudaCorpo', 'subabas', 'docAuditoria', 'listaVias', 'relAno', 'linhaTempo', 'listaPedidos', 'simulador', 'simPeriodo'])
    $(id).replaceChildren();
  Object.assign(estado, { radiosAdmin: [], radioEditando: null, alcanceComunidades: [], configuracao: null, pedidos: [], meusPedidos: [],
    pedidoAtendendo: null, empresaEditando: null });
  Object.assign(estado, { mapaEmpresas: null, empresasOcultas: new Set(), fichaEmpresa: null, area: null, municipiosIbge: null, ufGeo: null });
  camadaEmpresas?.remove(); camadaEmpresas = null; camadaEditorArea?.remove(); camadaEditorArea = null;
  for (const id of ['listaLegendaEmpresas', 'fichaEmpresa', 'sobreposicaoEmpresas', 'areaLista', 'areaResumo']) $(id).replaceChildren();
  $('fichaEmpresa').hidden = $('editorArea').hidden = $('legendaEmpresas').hidden = true; $('legenda').hidden = false;
  mensagemEm('estadoArea', '');
  try { sessionStorage.removeItem('farol.a11y'); } catch (e) { /* sem armazenamento */ }
  if (estado.lendo) speechSynthesis.cancel();
  Object.assign(estado, { a11y: { ...A11Y_PADRAO }, painelA11y: false, lendo: false, painelAmplo: false });
  desenharA11y(); desenharPainelAmplo();
  for (const f of ['formEntrar', 'formSenha', 'formUsuario', 'formRadio', 'formConfig', 'formEmpresa', 'formSimulador', 'form']) limparErros($(f));
  $('formSimulador').hidden = true; mensagemEm('estadoSimulador', '');
  // as mensagens de status também (ex.: "Fulana: alterações salvas"): quem entra depois não vê nada do anterior
  for (const id of ['estadoUsuario', 'estadoRadio', 'estadoConfig', 'estadoEmpresa', 'estadoAuditoria', 'estadoSenha']) mensagemEm(id, '');
  $('caixaAjuda').hidden = true;
  $('relDestinos').value = $('audDestinos').value = '';
  $('linhaTempo').hidden = true; estado.linhaTempo = null;
  mapa?.closePopup();
  $('textoPergunta').value = ''; $('perguntaPainel').hidden = true;
  $('precoSpot').value = ''; $('veiculacoes').value = ''; $('custoRadio').hidden = true;
  $('legendaCalor').hidden = true; $('botaoCalor').setAttribute('aria-pressed', 'false'); $('botaoCalor').textContent = t('Mapa de calor (12 meses)');
  $('dica').hidden = true;
  $('arquivo').value = '';
  $('buscaHistorico').value = ''; $('periodoHistorico').value = '';
  $('resultado').hidden = true;
  camadaComunidades?.remove();
  camadaComunidades = null;
  camadaUcs?.remove();
  camadaUcs = null;
  $('botaoUcs').closest('li').hidden = true;
  for (const a of [...Object.values(estado.audios), ...Object.values(estado.audiosHoje)]) URL.revokeObjectURL(a.url);
  estado.audios = {}; estado.audiosHoje = {}; estado.ia = {};
  $('comparativo').replaceChildren(); $('comparativoTotal').replaceChildren();
  document.documentElement.dataset.farol = 'saiu';
}

async function sair() {
  try { await api('/api/sair', { method: 'POST' }); } catch (e) { /* a sessão já pode ter acabado */ }
  limparTela();
  estado.tela = 'entrar';
  desenharTela(); desenharEstado();
  $('email').focus();
}

async function irPara(vista) {
  estado.vista = vista;
  desenharAbas();
  try {
    if (vista === 'historico') { estado.historico = (await api('/api/historico')).avisos; desenharHistorico(); }
    if (vista === 'painel') { estado.painel = await api('/api/painel'); desenharPainel(); }
    if (vista === 'relatorios') { desenharFiltrosRelatorio(); await carregarRelatorio(); }
    if (vista === 'registro') prepararAuditoria();
    if (vista === 'radios') {
      const [r, p] = await Promise.all([api('/api/radios'), api('/api/radios/pedidos')]);
      estado.radiosAdmin = r.radios; estado.pedidos = p.pedidos;
      desenharRadios();
    }
    if (vista === 'empresas') desenharFormEmpresa();
    if (vista === 'configuracoes') { estado.configuracao = await api('/api/empresa/configuracao'); desenharConfig(); }
    if (vista === 'simulador') await carregarSimulador();
    if (vista === 'comparativo') { desenharComparativo(); estado.painel = await api('/api/painel'); desenharComparativo(); }
    if (vista === 'usuarios') { const j = await api('/api/usuarios'); estado.usuarios = j.usuarios; estado.perfis = j.perfis; desenharUsuarios(); }
    if (vista === 'empresas') {
      if (!estado.mapaEmpresas) await carregarMapaEmpresas();
      estado.empresas = (await api('/api/empresas')).empresas; desenharEmpresas(); desenharFichaEmpresa(); desenharEditorArea();
    }
    if (vista === 'registro') { estado.registro = (await api('/api/registro')).registro; desenharRegistro(); $('listaRegistro').hidden = !!$('docAuditoria').children.length; }
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
  if (estado.tela === 'app') desenharConcessao();   // no dashboard, o mapa pinta os municípios pelos avisos
  document.documentElement.dataset.farol = 'pronto';
}

// ---- Funil do novo aviso ----
// tabelas em cartões no celular: cada célula leva o nome da coluna (data-rotulo), que o CSS mostra ao lado do valor
// data curta na célula ("15/10 14:59"), com a completa no title e para o leitor de tela, no idioma da tela
function quandoCurto(quando) {
  const d = quando instanceof Date ? quando : new Date(quando);
  if (Number.isNaN(d.getTime())) return document.createTextNode(String(quando));
  const curta = d.toLocaleString(IDIOMA, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(',', '');
  const longa = d.toLocaleString(IDIOMA, { dateStyle: 'long', timeStyle: 'short' });
  return no('time', { datetime: d.toISOString(), title: longa, 'aria-label': longa, texto: curta });
}
// quem fez: o nome em cima e o perfil embaixo, menor
const quem = (nome, perfil) => no('span', { classe: 'quem' }, no('span', { texto: nome }), perfil ? no('small', { texto: perfil }) : null);
const DATA_BR = /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})(?::(\d{2}))?$/;
const CURTO = /^(FRL-[0-9A-F-]+|[A-Z0-9]{2,10}|[-+−↑↓]?\s?(R\$\s?)?[\d.,]+\s?%?( s)?|—|-)$/;
const DETALHE = new Set(['Detalhe', 'Detail', 'Detalle']);
function formatarCelula(c, coluna) {
  if (c.dataset.formatada) return;
  c.dataset.formatada = '1';
  const txt = c.textContent.trim(), m = c.children.length ? null : DATA_BR.exec(txt);
  if (m) c.replaceChildren(quandoCurto(new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5], +(m[6] || 0))));
  else if (!c.children.length && CURTO.test(txt)) c.classList.add('curto');
  if (DETALHE.has(coluna)) c.classList.add('detalhe');
}

function rotularTabelas(raiz) {
  for (const tabela of raiz.querySelectorAll?.('table.tabela') || []) {
    const cab = [...tabela.querySelectorAll('thead th')].map(th => th.textContent.trim());
    // os papéis explícitos mantêm a tabela para o leitor de tela quando o CSS a mostra em blocos
    tabela.setAttribute('role', 'table');
    for (const g of tabela.querySelectorAll('thead, tbody')) g.setAttribute('role', 'rowgroup');
    for (const tr of tabela.querySelectorAll('tr')) tr.setAttribute('role', 'row');
    for (const th of tabela.querySelectorAll('thead th')) th.setAttribute('role', 'columnheader');
    for (const tr of tabela.querySelectorAll('tbody tr'))
      [...tr.children].forEach((c, i) => {
        c.setAttribute('role', c.tagName === 'TH' ? 'rowheader' : 'cell');
        if (cab[i] && !c.dataset.rotulo) c.dataset.rotulo = cab[i];
        formatarCelula(c, cab[i]);
      });
  }
}

function desenharPainelAmplo() {
  $('telaApp').classList.toggle('amplo', estado.painelAmplo);
  $('botaoAmpliar').setAttribute('aria-pressed', String(estado.painelAmplo));
  $('botaoAmpliarTexto').textContent = estado.painelAmplo ? t('Reduzir painel') : t('Ampliar painel');
  mapa?.invalidateSize();
}
function ampliarPainel(amplo = !estado.painelAmplo) {
  estado.painelAmplo = amplo;
  desenharPainelAmplo();
  if (estado.usuario) api('/api/eu/preferencias', { method: 'PUT', json: { acessibilidade: { painel: amplo } } }).catch(() => {});
}

function alternarMenu(aberto = !estado.menuAberto) {
  estado.menuAberto = aberto;
  desenharAbas();
}

function irParaPasso(n) {
  if (n === 2 && passoMaximo() < 2) return avisar(validarArquivo(estado.arquivo), true);
  if (n > passoMaximo()) return;
  estado.passo = n;
  if (n < 3) avisar('');
  desenharAbas();
  desenharEscolha();
  desenharMapaDoPasso();
  if (n === 3) carregarTerritoriosEscolha();
  $('vista-aviso').scrollIntoView({ block: 'start' });
}

// as comunidades dos municípios da planilha lida (para clicar no mapa da escolha); só as que faltam
async function carregarTerritoriosEscolha(enquadrar = false) {
  const b = estado.leitura?.base;
  if (!b) return;
  try {
    await Promise.all(b.municipios.filter(m => !estado.territorios[m.codigo_ibge]).map(async m => {
      estado.territorios[m.codigo_ibge] = await api(`/api/municipios/${m.codigo_ibge}/comunidades`);
    }));
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
  desenharMapaEscolha(enquadrar);
}

// o mapa de cada passo: no 3, a escolha (a base inteira); no 4 e no 5, a conferência e o aviso (só as escolhidas)
function desenharMapaDoPasso() {
  desenharComunidades(); desenharUcs(); desenharMapaEscolha(); desenharBase(); desenharNomes();
}

// começa outro desligamento: tira o resultado do envio anterior da tela e do mapa (o histórico já o guardou)
function novoAviso() {
  descartarNovo();
  estado.arquivo = null;
  $('arquivo').value = '';
  estado.passo = 1;
  avisar('');
  desenharAbas();
}

// tira da tela e do mapa a conferência ou o aviso novo (a planilha escolhida fica)
function descartarNovo() {
  Object.assign(estado, { abas: [], aba: '' });
  $('aba').replaceChildren();
  descartarLeitura();
  if (estado.origem === 'novo') estado.formulario = null;
  descartarConferencia();
}

// a planilha lida (a base para escolher, com os pontos) sai da memória e do mapa
function descartarLeitura() {
  Object.assign(estado, { leitura: null, selecao: null, sel: null, arquivoLido: null, abaLida: null, formularioLido: null });
  $('escolhaCorpo').replaceChildren();
  apagarMapaEscolha();
  desenharContaEscolha();
}

// a conferência na tela não vale mais (a escolha mudou, ou começou outro desligamento); a planilha lida fica
function descartarConferencia() {
  Object.assign(estado, { conferi: false, justificativa: '', chaveConferida: null });
  if (estado.origem === 'novo') {
    Object.assign(estado, { resultado: null, origem: null, avisos: {}, finais: {}, evidencia: null });
    for (const a of [...Object.values(estado.audios), ...Object.values(estado.audiosHoje)]) URL.revokeObjectURL(a.url);
    estado.audios = {}; estado.audiosHoje = {}; estado.ia = {};
    for (const id of ['resumo', 'municipios', 'problemasCorpo']) $(id).replaceChildren();
    desenharComparativo();
    camadaComunidades?.remove(); camadaComunidades = null;
    desenharConferencia(); desenharUcs(); desenharConcessao(); desenharBase(); desenharNomes();
  }
}

// outra planilha escolhida: a conferência (e a leitura) da anterior não vale mais
function escolherPlanilha(arquivo) {
  if (temResultadoNovo() && !gerado() || estado.leitura && !gerado()) descartarNovo();
  else Object.assign(estado, { abas: [], aba: '' });
  estado.arquivo = arquivo || null;
  avisar('');
}

async function mostrarResultado(resultado, origem, formulario) {
  if (origem === 'historico' && estado.leitura) descartarLeitura();   // os pontos somem ao abrir um aviso do histórico
  estado.resultado = resultado; estado.origem = origem; estado.formulario = formulario; estado.evidencia = null;
  desenharEscolha(); desenharMapaEscolha();
  Object.assign(estado, { envios: [], sugestao: {}, escolha: {} });
  estado.avisos = Object.fromEntries(resultado.municipios.map(m => [m.codigo_ibge, textoAviso(m)]));
  estado.finais = Object.fromEntries(resultado.municipios.filter(m => m.texto_final).map(m => [m.codigo_ibge, m.texto_final]));
  estado.ia = {};
  desenharResultado(); desenharConcessao();
  await Promise.all(resultado.municipios.filter(m => !estado.territorios[m.codigo_ibge]).map(async m => {
    estado.territorios[m.codigo_ibge] = await api(`/api/municipios/${m.codigo_ibge}/comunidades`);
  }));
  desenharComunidades(); desenharUcs(); desenharBase(); desenharNomes();
  await carregarEnvios();
}

// 1º passo (Conferir a planilha): a planilha vai ao servidor, que devolve a base para escolher quem será desligado (sem a
// UC), a conferência da planilha inteira e os pacotes assinados (15 min). Nada vai para o histórico ainda.
async function enviar(evento) {
  evento.preventDefault();
  const form = { arquivo: estado.arquivo, data: $('data').value, inicio: $('inicio').value, fim: $('fim').value, idioma: $('idioma').value,
    tipo: $('tipo').value, tipoOutro: $('tipoOutro').value };
  if (validarArquivo(form.arquivo)) { estado.passo = 1; desenharAbas(); return avisar(validarArquivo(form.arquivo), true); }
  const erros = validarFormulario(form);
  if (erros.length) { mostrarErros($('form'), erros); return avisar(erros[0][1], true); }
  limparErros($('form'));
  const horario = `${horaTexto(form.inicio)} às ${horaTexto(form.fim)}`;
  const formulario = { data: dataTexto(form.data), dataLonga: dataLonga(form.data), horario, idioma: form.idioma,
    tipo: form.tipo, tipoOutro: form.tipo === 'outro' ? form.tipoOutro : null };
  // a mesma planilha já lida (e o pacote ainda vale): só a data, o horário ou o tipo mudaram; a escolha fica
  const l = estado.leitura;
  if (l && estado.arquivoLido === form.arquivo && estado.aba === estado.abaLida && !gerado()
      && Date.now() < new Date(l.pacote_vence).getTime() - 60_000) {
    if (JSON.stringify(formulario) !== estado.formularioLido) descartarConferencia();
    estado.formulario = formulario;
    estado.passo = 3;
    avisar(t('Planilha já lida: escolha quem será desligado e confira.'));
    return irParaPasso(3);
  }
  const selecaoAnterior = l && estado.arquivoLido === form.arquivo ? estado.selecao : null;   // a mesma planilha lida de novo
  if (temResultadoNovo() && !gerado() || l) { descartarLeitura(); descartarConferencia(); }   // a aba escolhida fica
  estado.enviando = true;
  avisar(t('Lendo a planilha, conferindo as linhas e localizando as comunidades…'));
  const dados = new FormData();
  dados.append('arquivo', form.arquivo);
  dados.append('data', dataTexto(form.data));
  dados.append('horario', horario);
  dados.append('idioma', form.idioma);
  dados.append('tipo', form.tipo);
  if (form.tipo === 'outro') dados.append('tipo_outro', form.tipoOutro);
  if (estado.aba) dados.append('aba', estado.aba);
  try {
    const j = await api('/api/planilha', { method: 'POST', body: dados });
    Object.assign(estado, { leitura: j, arquivoLido: form.arquivo, abaLida: estado.aba, formulario, formularioLido: JSON.stringify(formulario),
      chaveConferida: null });
    estado.selecao = selecaoAnterior || novaSelecao(j.base);
    estado.sel = selecionadas(j.base, estado.selecao);
    const inativas = j.escolha.conta.inativas_fora;
    avisar(t('Planilha lida: {lidas} linha(s). Escolha quem será desligado e confira.', { lidas: fmt(j.base.lidas) })
      + (inativas ? ` ${t('{n} UC(s) inativa(s) não entram no aviso.', { n: fmt(inativas) })}` : ''));
    // sem as colunas de uma base de clientes, a planilha já é a lista do desligamento (como antes): vai direto à
    // conferência da planilha inteira; o passo 3 fica aberto para escolher no mapa, se a pessoa quiser
    if (!ehBaseDeClientes(j.base)) {
      estado.enviando = false;
      return await conferirEscolha();
    }
    estado.passo = 3;
    irParaPasso(3);
    document.documentElement.dataset.farol = 'escolha';
    await carregarTerritoriosEscolha(true);
  } catch (e) {
    if (e.status === 409 && e.dados.abas) {   // mais de uma aba serve: a pessoa escolhe e confere de novo
      estado.abas = e.dados.abas;
      estado.aba = estado.abas[0];
      $('aba').replaceChildren(...estado.abas.map(a => no('option', { value: a, texto: a })));
      avisar(t('{erro} Escolha a aba e clique em "Conferir a planilha" de novo.', { erro: e.message }), true);
    } else if (e.status !== 401) {
      avisar(e.message, true);
      erroDoServidor($('form'), e, { data: 'data', horario: 'inicio', tipo: 'tipo', tipo_outro: 'tipoOutro', idioma: 'idioma' });
    }
  } finally {
    estado.enviando = false;
    desenharEstado();
  }
}

// ---- Passo 3: escolher quem será desligado. Cada mudança refaz o contador e o mapa (a regra de nucleo/selecao.py);
// a conferência anterior deixa de valer (a escolha conferida é a que gera o aviso) ----
function selecaoMudou(tudo = false) {
  if (temResultadoNovo() && !gerado()) descartarConferencia();
  estado.sel = selecionadas(estado.leitura.base, estado.selecao);
  if (tudo) desenharEscolha(); else desenharContaEscolha();
  desenharMapaEscolha();
  desenharFunil();
}
function alternarComunidade(i) {
  const c = estado.selecao.comunidades;
  if (c.has(i)) c.delete(i); else c.add(i);
  const caixa = $(`sel-comunidade-${i}`);
  if (caixa) caixa.checked = c.has(i);
  selecaoMudou();
}
const redesenharBlocoMapa = () => $('blocoMapa')?.replaceWith(blocoMapa(estado.leitura.base, estado.selecao));
// a comunidade da base (índice) que contém o ponto, pelo contorno do IBGE; -1 se nenhuma
function comunidadeNoPonto(lat, lon) {
  for (const l of camadaEscolhaComunidades?.getLayers() || []) {
    const p = l.feature.properties, g = l.feature.geometry;
    if (p.indice < 0 || !l.getBounds().contains([lat, lon])) continue;
    const polis = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
    if (polis.some(pp => naArea(lat, lon, pp))) return p.indice;
  }
  return -1;
}
// clique no mapa do passo 3: desenhando, é um canto da área; senão, inclui ou tira a comunidade clicada (pelo contorno,
// mesmo com a rede fictícia ou um nome por cima)
function cliqueNoMapa(e) {
  const s = estado.selecao;
  if (!emEscolha()) return;
  if (!s.desenho) {
    const i = s.modo === 'escolha' ? comunidadeNoPonto(e.latlng.lat, e.latlng.lng) : -1;
    if (i >= 0) alternarComunidade(i);
    return;
  }
  if (verticesArea(s.poligonos) + s.desenho.length + 1 > MAX_VERTICES_AREA) return avisar(t('A área passou do limite de {n} vértices.', { n: fmt(MAX_VERTICES_AREA) }), true);
  s.desenho.push([e.latlng.lat, e.latlng.lng]);
  redesenharBlocoMapa(); desenharContaEscolha(); desenharMapaEscolha();
}
const arred6 = v => +v.toFixed(6);   // como nucleo/area.CASAS
function acaoEscolha(evento) {
  const b = evento.target.closest('button[data-sel]');
  if (!b || !estado.selecao) return;
  const s = estado.selecao, acao = b.dataset.sel;
  if (acao === 'desenhar') { s.desenho = []; mapa?.closePopup(); redesenharBlocoMapa(); desenharContaEscolha(); desenharMapaEscolha(); $('passosDesenho')?.focus?.(); }
  else if (acao === 'desfazer') { s.desenho.pop(); redesenharBlocoMapa(); desenharContaEscolha(); desenharMapaEscolha(); }
  else if (acao === 'cancelar') { s.desenho = null; redesenharBlocoMapa(); desenharContaEscolha(); desenharMapaEscolha(); $('blocoMapa')?.querySelector('button')?.focus(); }
  else if (acao === 'concluir') {
    const anel = s.desenho.map(([lat, lon]) => [arred6(lon), arred6(lat)]);
    s.poligonos.push([[...anel, anel[0]]]);
    s.desenho = null;
    selecaoMudou(true);
    $('blocoMapa')?.querySelector('button')?.focus();
  } else if (acao === 'remover') { s.poligonos.splice(Number(b.dataset.area), 1); selecaoMudou(true); $('blocoMapa')?.querySelector('button')?.focus(); }
  else if (acao === 'marcar' || acao === 'desmarcar') {
    const tipo = b.dataset.tipo, marcados = marcadosDe(s, tipo);
    if (acao === 'marcar') for (const [i] of itensBuscados(estado.leitura.base, s, tipo)) marcados.add(i);
    else marcados.clear();
    desenharItens($(`itens-${tipo}`), estado.leitura.base, s, tipo);
    selecaoMudou();
  }
}
function editarEscolha(evento) {
  const alvo = evento.target, s = estado.selecao;
  if (!s) return;
  if (alvo.name === 'modoEscolha') {
    s.modo = alvo.value;
    if (s.modo === 'planilha') s.desenho = null;
    selecaoMudou(true);
    $(`modo-${s.modo}`)?.focus();
  } else if (alvo.id === 'incluirInativas') {
    s.incluirInativas = alvo.checked;
    selecaoMudou(true);
    $('incluirInativas')?.focus();
  } else if (alvo.dataset.selTipo) {
    const marcados = marcadosDe(s, alvo.dataset.selTipo), i = Number(alvo.value);
    if (alvo.checked) marcados.add(i); else marcados.delete(i);
    selecaoMudou();
  }
}
function buscarNaEscolha(evento) {
  const tipo = evento.target.dataset.busca;
  if (!tipo || !estado.selecao) return;
  estado.selecao.buscas[tipo] = evento.target.value;
  desenharItens($(`itens-${tipo}`), estado.leitura.base, estado.selecao, tipo);
}
function abrirListaEscolha(evento) {   // lembra quais listas ficaram abertas (o painel é redesenhado ao mudar o modo)
  const d = evento.target, tipo = d.dataset?.lista;
  if (!tipo || !estado.selecao) return;
  if (d.open) estado.selecao.abertos.add(tipo); else estado.selecao.abertos.delete(tipo);
}

// passo 3 -> 4: o servidor aplica o critério e confere só as escolhidas (o pacote "escolha" leva o critério assinado).
// A planilha inteira sem as inativas já veio conferida em /api/planilha (com a mesma data e horário).
async function conferirEscolha() {
  if (gerado()) return irParaPasso(4);
  const b = estado.leitura?.base, s = estado.selecao;
  if (!b) return;
  const problema = problemaDaSelecao(s, contaSelecao(b, s, estado.sel));
  if (problema) return avisar(problema, true);
  const chave = chaveSelecao(b, s);
  if (temResultadoNovo() && estado.chaveConferida === chave) return irParaPasso(4);
  const f = estado.formulario;
  estado.enviando = true;
  desenharContaEscolha();
  avisar(t('Conferindo a escolha: as travas e o aviso só para as UCs escolhidas…'));
  try {
    const mesmo = s.modo === 'planilha' && !s.incluirInativas && JSON.stringify(f) === estado.formularioLido;
    const j = mesmo ? estado.leitura : await api('/api/planilha/escolha', { method: 'POST', json: { pacote: estado.leitura.pacote_base,
      criterio: criterioDe(b, s), data: f.data, horario: f.horario, idioma: f.idioma, tipo: f.tipo, tipo_outro: f.tipoOutro } });
    const c = j.conferencia;
    avisar(c.vital_bloqueio.length ? t('Conferência pronta, com bloqueio: há equipamento vital com problema (veja em vermelho).')
      : t('Conferência pronta: {clientes} cliente(s), {comunidades} comunidade(s). Confira os números e o mapa para gerar o aviso.',
        { clientes: fmt(c.numeros.clientes), comunidades: fmt(c.numeros.comunidades) }),
      !!c.vital_bloqueio.length || !j.municipios.length);
    estado.chaveConferida = chave;
    estado.passo = 4;
    await mostrarResultado(j, 'novo', f);
    document.documentElement.dataset.farol = 'conferencia';
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    estado.enviando = false;
    desenharContaEscolha();
    desenharFunil();
  }
}

// 2º passo (Gerar aviso): o pacote da conferência, a caixa "Conferi" e a justificativa; o servidor confere tudo de novo
async function gerarAviso() {
  const problema = problemaParaGerar();
  if (problema) return avisar(problema, true);
  const f = estado.formulario;
  estado.enviando = true;
  desenharFunil();
  avisar(t('Gerando o aviso…'));
  try {
    const j = await api('/api/avisos', { method: 'POST', json: { pacote: estado.resultado.pacote, data: f.data, horario: f.horario, idioma: f.idioma,
      conferi: estado.conferi, justificativa: estado.justificativa.trim() || null, tipo: f.tipo, tipo_outro: f.tipoOutro } });
    const n = j.municipios.length;
    avisar(n ? t('Pronto: {n} município(s), {comunidades} comunidade(s). Guardado no histórico (aviso nº {id}).',
      { n, comunidades: fmt(j.municipios.reduce((s, m) => s + m.comunidades.length, 0)), id: j.id })
      : t('Nenhuma UC na área de concessão. Guardado no histórico (aviso nº {id}).', { id: j.id }), !n);
    estado.passo = 5;
    await mostrarResultado(j, 'novo', f);
    document.documentElement.dataset.farol = 'resultado';
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    estado.enviando = false;
    desenharFunil();
  }
}

// conferência: caixa "Conferi", justificativa e os downloads (relatório sem UC; JSON com as UCs, registrado na auditoria)
function editarConferencia(evento) {
  const alvo = evento.target;
  if (alvo.id === 'conferi') estado.conferi = alvo.checked;
  else if (alvo.id === 'justificativa') {
    estado.justificativa = alvo.value;
    $('contaJustificativa').textContent = t('{n} de {max} caracteres', { n: alvo.value.length, max: MAX_JUSTIFICATIVA });
  } else return;
  desenharFunil();
}

async function acaoConferencia(evento) {
  const b = evento.target.closest('button[data-conf]');
  if (!b) return;
  b.disabled = true;
  try {
    if (b.dataset.conf === 'relatorio') {
      await baixarDaApi('/api/planilha/relatorio', { headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pacote: estado.resultado.pacote }) }, 'farol-relatorio-planilha.csv');
      avisar(t('Relatório da planilha baixado (só linha, situação e motivo; sem UC).'));
    } else {
      if (!estado.arquivo) return avisar(t('Escolha a planilha de novo para baixar o JSON.'), true);
      if (!confirm(t('O JSON tem os números de UC (dado pessoal). O download fica registrado na auditoria com o seu nome. Baixar?'))) return;
      const dados = new FormData();
      dados.append('arquivo', estado.arquivo);
      if (estado.aba) dados.append('aba', estado.aba);
      await baixarDaApi('/api/planilha/json', { body: dados }, 'farol-planilha.json');
      avisar(t('JSON da planilha baixado (registrado na auditoria).'));
    }
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    b.disabled = false;
  }
}

// guarda no histórico o texto que vai para a rádio (ao baixar o PDF ou copiar)
async function guardarFinal(codigo) {
  if (!pode('gerar_aviso') || !estado.resultado.id || estado.finais[codigo] === estado.avisos[codigo]) return;
  try {
    await api(`/api/historico/${estado.resultado.id}/municipios/${codigo}/texto`, { method: 'PUT', json: { texto: estado.avisos[codigo] } });
    estado.finais[codigo] = estado.avisos[codigo];
    desenharFinal(codigo);
  } catch (e) {
    avisar(t('Não foi possível guardar o texto final: {erro}', { erro: e.message }), true);
  }
}

async function gerarAudio(codigo, m) {
  if (audioAtual(codigo)) return audioAtual(codigo);
  avisar(t('Gerando o áudio de {nome}…', { nome: m.nome }));
  const texto = estado.avisos[codigo];
  const r = await buscar('/api/audio', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto, idioma: estado.formulario.idioma, municipio: m.nome }) });
  if (!r.ok) throw await erroDaResposta(r, 'Não foi possível gerar o áudio.');
  if (estado.audios[codigo]) URL.revokeObjectURL(estado.audios[codigo].url);
  estado.audios[codigo] = { texto, url: URL.createObjectURL(await r.blob()), segundos: Number(r.headers.get('X-Duracao-Segundos')) || 0 };
  avisar(t('Áudio de {nome} pronto.', { nome: m.nome }));
  desenharTocador(codigo);
  return estado.audios[codigo];
}

// áudio do comparativo: o do Norte é o mesmo de "Avisos"; o de hoje pede o limite maior (é bem mais longo)
async function audioHoje(codigo, m) {
  if (estado.audiosHoje[codigo]) return estado.audiosHoje[codigo];
  avisar(t('Gerando o áudio do aviso de hoje de {nome} (é longo: pode levar um tempo)…', { nome: m.nome }));
  const r = await buscar('/api/audio', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto: m.hoje.texto, idioma: 'pt-BR', municipio: m.nome, comparativo: true }) });
  if (!r.ok) throw await erroDaResposta(r, 'Não foi possível gerar o áudio.');
  estado.audiosHoje[codigo] = { url: URL.createObjectURL(await r.blob()), segundos: Number(r.headers.get('X-Duracao-Segundos')) || 0 };
  avisar(t('Áudio do aviso de hoje de {nome} pronto.', { nome: m.nome }));
  return estado.audiosHoje[codigo];
}

async function acaoComparativo(evento) {
  const b = evento.target.closest('button[data-comp]');
  if (!b) return;
  const codigo = b.dataset.codigo, m = estado.resultado.municipios.find(x => x.codigo_ibge === codigo);
  b.disabled = true;
  try {
    const a = b.dataset.comp === 'hoje' ? await audioHoje(codigo, m) : await gerarAudio(codigo, m);
    const lugar = $(`tocador-${b.dataset.comp}-${codigo}`);
    lugar.replaceChildren(no('audio', { controls: true, src: a.url, preload: 'auto', 'aria-label': t(b.dataset.comp === 'hoje' ? 'Áudio do aviso de hoje' : 'Áudio do aviso do Norte') }),
      no('span', { classe: 'ajuda', texto: t('{tempo} de áudio (voz sintetizada)', { tempo: tempoNoAr(Math.round(a.segundos)) }) }));
    lugar.querySelector('audio').play().catch(() => {});
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    b.disabled = false;
  }
}

async function pedirAoCopiloto(codigo, pedido) {
  const livre = pedido === 'livre' ? $(`ia-livre-${codigo}`).value : '';
  estado.ia[codigo] = { pedindo: true };
  desenharCopiloto(codigo);
  try {
    const r = await api(`/api/historico/${estado.resultado.id}/municipios/${codigo}/reescrever`,
      { method: 'POST', json: { texto: estado.avisos[codigo], pedido, livre } });
    estado.ia[codigo] = { verificado: r.verificado, motivos: r.motivos, provedor: r.provedor };
    if (r.verificado) {
      estado.avisos[codigo] = r.texto;
      $(`aviso-${codigo}`).value = r.texto;
      desenharTempo(codigo);
    }
  } catch (e) {
    if (e.status === 401) return;
    estado.ia[codigo] = { verificado: false, motivos: [], erro: e.message };
  }
  desenharCopiloto(codigo);
}

async function perguntarAoPainel(texto) {
  texto = texto.trim();
  if (texto.length < 3) return;
  estado.pergunta = { pedindo: true };
  desenharPergunta();
  try {
    estado.pergunta = { resposta: await api('/api/painel/perguntar', { method: 'POST', json: { pergunta: texto } }) };
  } catch (e) {
    if (e.status === 401) return;
    estado.pergunta = { erro: e.message };
  }
  desenharPergunta();
}

async function acao(evento) {
  const b = evento.target.closest('button[data-acao]');
  if (!b) return;
  const codigo = b.dataset.codigo, m = estado.resultado.municipios.find(x => x.codigo_ibge === codigo);
  if (b.dataset.acao === 'copiar') {
    try { await navigator.clipboard.writeText(estado.avisos[codigo]); avisar(t('Aviso de {nome} copiado.', { nome: m.nome })); }
    catch (e) { avisar(t('Não foi possível copiar; selecione o texto e use Ctrl+C.'), true); }
    await guardarFinal(codigo);
  } else if (b.dataset.acao === 'ia') {
    await pedirAoCopiloto(codigo, b.dataset.pedido);
  } else if (b.dataset.acao === 'restaurar') {
    estado.avisos[codigo] = textoGerado(m);
    $(`aviso-${codigo}`).value = textoGerado(m);
    delete estado.ia[codigo];
    desenharTempo(codigo); desenharCopiloto(codigo);
  } else if (b.dataset.acao === 'ouvir' || b.dataset.acao === 'audio') {
    b.disabled = true;
    try {
      const a = await gerarAudio(codigo, m);
      if (b.dataset.acao === 'ouvir') {
        $(`tocador-${codigo}`).querySelector('audio')?.play().catch(() => {});
      } else {
        const link = no('a', { href: a.url, download: `farol-aviso-${m.nome}-${estado.formulario.data.replace('/', '-')}.mp3` });
        document.body.append(link); link.click(); link.remove();
        await guardarFinal(codigo);
      }
    } catch (e) {
      if (e.status !== 401) avisar(e.message, true);
    } finally {
      b.disabled = false;
    }
  } else if (b.dataset.acao === 'pdf') {   // o PDF é gerado no servidor, com o texto editado, e fica na auditoria
    b.disabled = true;
    try {
      await baixarDaApi(`/api/historico/${estado.resultado.id}/municipios/${codigo}/pdf`, { headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto: estado.avisos[codigo] }) }, `farol-aviso-${codigo}.pdf`);
      await guardarFinal(codigo);
      avisar(t('PDF de {nome} baixado (registrado na auditoria).', { nome: m.nome }));
    } catch (e) {
      if (e.status !== 401) avisar(e.message, true);
    } finally {
      b.disabled = false;
    }
  }
}

function editar(evento) {
  const a = evento.target;
  if (a.tagName !== 'TEXTAREA' || !a.dataset.codigo || a.readOnly) return;
  estado.avisos[a.dataset.codigo] = a.value;
  desenharTempo(a.dataset.codigo);
}

async function abrirHistorico(evento) {
  const b = evento.target.closest('button[data-historico]');
  if (!b) return;
  try {
    const a = await api(`/api/historico/${b.dataset.historico}`);
    await mostrarResultado(doHistorico(a), 'historico', { data: a.data, dataLonga: a.data, horario: a.horario, idioma: a.idioma });
    desenharHistorico();
    $('resultado').scrollIntoView({ block: 'start' });
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

// aviso do histórico: mudar a data ou cancelar; o servidor confere a permissão e registra o antes e o depois
async function acaoAviso(evento) {
  const b = evento.target.closest('button[data-aviso]');
  if (!b) return;
  const r = estado.resultado, lugar = $('acoesAviso'), data = b.dataset.aviso === 'data';
  let erros = [];
  if (data) {
    const d = $('novaData').value, i = $('novoInicio').value, f = $('novoFim').value;
    erros = [!d && ['novaData', t('Informe a nova data.')], !i && ['novoInicio', t('Informe o início.')], !f && ['novoFim', t('Informe o fim.')],
      i && f && f <= i && ['novoFim', t('O fim tem de ser depois do início.')]].filter(Boolean);
  } else if ($('motivoCancelar').value.trim().length < 3) erros = [['motivoCancelar', t('Escreva o motivo do cancelamento (de 3 a 200 caracteres).')]];
  if (erros.length) { mostrarErros(lugar, erros); return avisar(erros[0][1], true); }
  limparErros(lugar);
  if (!data && !confirm(t('Cancelar o desligamento do aviso nº {id}? O aviso fica no histórico, marcado como cancelado.', { id: r.id }))) return;
  await ocupado(b, 'Salvando…', async () => {
    try {
      let a, feito;
      if (data) {
        const d = $('novaData').value, i = $('novoInicio').value, f = $('novoFim').value;
        a = await api(`/api/historico/${r.id}/data`, { method: 'POST', json: { data: dataTexto(d), horario: `${horaTexto(i)} às ${horaTexto(f)}` } });
        feito = t('Data do aviso nº {id} mudada para {data}, {horario} (registrado na auditoria).', { id: r.id, data: a.data, horario: a.horario });
      } else {
        a = await api(`/api/historico/${r.id}/cancelar`, { method: 'POST', json: { motivo: $('motivoCancelar').value.trim() } });
        feito = t('Desligamento do aviso nº {id} cancelado (registrado na auditoria).', { id: r.id });
      }
      // a lista e o aviso aberto primeiro; a mensagem de pronto só depois de tudo redesenhado
      estado.historico = estado.historico.map(x => x.id === a.id ? a : x);
      desenharHistorico();
      await mostrarResultado(doHistorico(a), 'historico', { data: a.data, dataLonga: a.data, horario: a.horario, idioma: a.idioma });
      avisar(feito);
    } catch (e) {
      if (e.status === 401) return;
      avisar(e.message, true);
      erroDoServidor(lugar, e, { data: 'novaData', horario: 'novoInicio', motivo: 'motivoCancelar' });
    }
  });
}

async function carregarRelatorio(evento) {
  evento?.preventDefault();
  const tipo = $('relQual').value;
  try {
    const [r, v] = await Promise.all([api(`/api/relatorios/${tipo}?${consulta(filtrosRelatorio())}`), api('/api/relatorios/vias')]);
    estado.relatorio = r; estado.vias = v.vias;
    if (r.opcoes) estado.opcoesRelatorio = r.opcoes;
    desenharRelatorio();
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

// trocar o tipo de relatório: o período volta ao padrão dele (mês ou ano)
function trocarTipoRelatorio() {
  $('relModo').value = TIPOS_RELATORIO[$('relQual').value] || 'mes';
  desenharFiltrosRelatorio();
  carregarRelatorio();
}

// destinatários do "Enviar": separados por vírgula, ponto e vírgula ou espaço
const destinatarios = texto => [...new Set(texto.split(/[\s,;]+/).map(d => d.trim().toLowerCase()).filter(Boolean))];

async function exportarRelatorio(evento) {
  const b = evento.target.closest('button[data-rel]');
  if (!b) return;
  const tipo = $('relQual').value, enviar = b.dataset.rel === 'enviar', destinos = destinatarios($('relDestinos').value);
  if (enviar) {
    if (!destinos.length) { mostrarErros($('relEnviar'), [['relDestinos', t('Escreva o e-mail de quem vai receber (até 5, do domínio da empresa).')]]);
      return avisar(t('Escreva o e-mail de quem vai receber.'), true); }
    limparErros($('relEnviar'));
    if (!confirm(t('Enviar o relatório por e-mail (PDF) para {destinos}? O envio fica na auditoria com o seu nome.', { destinos: destinos.join(', ') }))) return;
  }
  await ocupado(b, enviar ? 'Enviando…' : 'Gerando…', async () => {
    try {
      if (enviar) {
        const r = await api(`/api/relatorios/${tipo}/enviar`, { method: 'POST', json: { filtros: filtrosRelatorio(), destinatarios: destinos } });
        avisar(t('Relatório enviado para {destinos} (código {codigo}; registrado na auditoria).', { destinos: r.destinatarios.join(', '), codigo: r.codigo }));
      } else {
        await baixarDaApi(`/api/relatorios/${tipo}.${b.dataset.rel}?${consulta(filtrosRelatorio())}`, { method: 'GET' }, `farol-${tipo}.${b.dataset.rel}`);
        avisar(t('Relatório baixado em {formato}, com o seu nome e o código de verificação (registrado na auditoria).', { formato: b.dataset.rel.toUpperCase() }));
      }
      estado.vias = (await api('/api/relatorios/vias')).vias;
      desenharVias();
    } catch (e) {
      if (e.status === 401) return;
      avisar(e.message, true);
      erroDoServidor($('relEnviar'), e, { destinatarios: 'relDestinos' });
    }
  });
}

// simulador: o período dos avisos (de onde saem a redução real e o já economizado)
const filtrosSimulador = () => { const [modo, v] = ($('simPeriodo').value || `ano:${new Date().getFullYear()}`).split(':'); return { [modo]: v }; };

async function carregarSimulador(evento) {
  evento?.preventDefault();
  desenharSimulador();
  try {
    estado.simulador = await api(`/api/relatorios/simulador?${consulta(filtrosSimulador())}`);
    desenharSimulador();
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

function errosSimulador() {
  const num = id => $(id).value.trim() === '' ? NaN : Number($(id).value);
  const erros = [];
  if (!(num('simGastoMin') >= 0)) erros.push(['simGastoMin', t('Gasto mensal: um valor em R$.')]);
  if ($('simGastoMax').value.trim() && !(num('simGastoMax') >= num('simGastoMin'))) erros.push(['simGastoMax', t('Gasto máximo: igual ou maior que o mínimo.')]);
  if (!(num('simPct') >= 0 && num('simPct') <= 100)) erros.push(['simPct', t('Parte cobrada por tempo: de 0 a 100%.')]);
  return erros;
}

async function salvarSimulador(evento) {
  evento.preventDefault();
  const form = $('formSimulador'), erros = errosSimulador();
  if (erros.length) { mostrarErros(form, erros); return mensagemEm('estadoSimulador', erros[0][1], true); }
  limparErros(form);
  await ocupado(botaoDoEnvio(evento), 'Salvando…', async () => {
    try {
      await api('/api/empresa/configuracao/simulador', { method: 'PUT', json: { gasto_min: $('simGastoMin').value,
        gasto_max: $('simGastoMax').value.trim() === '' ? null : $('simGastoMax').value, pct_tempo: $('simPct').value,
        nota: $('simNota').value.trim() || null } });
      estado.simulador = await api(`/api/relatorios/simulador?${consulta(filtrosSimulador())}`);
      desenharSimulador();
      mensagemEm('estadoSimulador', t('Valores do simulador salvos nas configurações (registrado na auditoria).'));
    } catch (e) {
      if (e.status === 401) return;
      mensagemEm('estadoSimulador', e.message, true);
      erroDoServidor(form, e, { gasto_min: 'simGastoMin', gasto_max: 'simGastoMax', pct_tempo: 'simPct', nota: 'simNota' });
    }
  });
}

async function exportarSimulador(evento) {
  const b = evento.target.closest('button[data-sim]');
  if (!b) return;
  await ocupado(b, 'Gerando…', async () => {
    try {
      await baixarDaApi(`/api/relatorios/simulador.${b.dataset.sim}?${consulta(filtrosSimulador())}`, { method: 'GET' }, `farol-simulador.${b.dataset.sim}`);
      avisar(t('Relatório baixado em {formato}, com o seu nome e o código de verificação (registrado na auditoria).', { formato: b.dataset.sim.toUpperCase() }));
    } catch (e) {
      if (e.status !== 401) avisar(e.message, true);
    }
  });
}

async function baixarVia(evento) {
  const b = evento.target.closest('button[data-via]');
  if (!b) return;
  b.disabled = true;
  try {
    await baixarDaApi(`/api/relatorios/vias/${b.dataset.via}.pdf`, { method: 'GET' }, 'farol-via.pdf');
    avisar(t('Segunda via baixada: o mesmo PDF (SHA-256 conferido no servidor; registrado na auditoria).'));
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    b.disabled = false;
  }
}

// auditoria: o relatório da empresa (Admin da empresa) ou o geral de acessos (Admin do Norte)
function prepararAuditoria() {
  const geral = pode('auditoria_geral');
  $('formAuditoria').hidden = !geral && !pode('relatorio_auditoria');
  $('tituloRelAuditoria').textContent = geral ? t('Auditoria geral de acessos (todas as empresas)') : t('Relatório de auditoria da empresa');
  $('audEmpresaRotulo').hidden = !geral;
  $('audAcessos').checked = geral;
  $('audEnviar').hidden = geral || !pode('relatorio_auditoria');
  if (!$('audMes').options.length) $('audMes').replaceChildren(...ultimosMeses().map(([v, rot]) => no('option', { value: v, texto: rot })));
}

async function exportarAuditoria(evento) {
  const b = evento.target.closest('button[data-aud]');
  if (!b) return;
  const f = { mes: $('audMes').value };
  if ($('audAcessos').checked) f.so_acessos = 'true';
  if ($('audPessoa').value.trim()) f.pessoa = $('audPessoa').value.trim();
  if ($('audCategoria').value) f.categoria = $('audCategoria').value;
  if (pode('auditoria_geral') && $('audEmpresa').value.trim()) f.empresa = $('audEmpresa').value.trim().toUpperCase();
  const tipo = pode('auditoria_geral') ? 'acessos' : 'auditoria', acao = b.dataset.aud, destinos = destinatarios($('audDestinos').value);
  if (acao === 'enviar') {
    if (!destinos.length) { mostrarErros($('audEnviar'), [['audDestinos', t('Escreva o e-mail de quem vai receber (até 5, do domínio da empresa).')]]);
      return mensagemEm('estadoAuditoria', t('Escreva o e-mail de quem vai receber.'), true); }
    limparErros($('audEnviar'));
    if (!confirm(t('Enviar o relatório de auditoria (PDF) para {destinos}? O envio fica na auditoria com o seu nome.', { destinos: destinos.join(', ') }))) return;
  }
  await ocupado(b, acao === 'enviar' ? 'Enviando…' : acao === 'tela' ? 'Carregando…' : 'Gerando…', async () => {
    try {
      if (acao === 'tela') {
        const r = await api(`/api/relatorios/${tipo}?${consulta(f)}`);
        $('docAuditoria').replaceChildren(...documentoNaTela(r.documento, r.subtitulo),
          no('button', { type: 'button', id: 'verUltimas', texto: t('Ver as últimas ações (sem filtro)') }));
        $('listaRegistro').hidden = true;   // o relatório filtrado e a lista sem filtro não aparecem juntos
        mensagemEm('estadoAuditoria', t('{n} linha(s) no período (a consulta fica na auditoria com o seu nome).', { n: fmt(r.total) }));
      } else if (acao === 'enviar') {
        const r = await api(`/api/relatorios/${tipo}/enviar`, { method: 'POST', json: { filtros: f, destinatarios: destinos } });
        mensagemEm('estadoAuditoria', t('Relatório enviado para {destinos} (código {codigo}).', { destinos: r.destinatarios.join(', '), codigo: r.codigo }));
      } else if (acao === 'json') {
        // as linhas filtradas, como a tela as recebe (a consulta fica na auditoria)
        await baixarDaApi(`/api/relatorios/${tipo}?${consulta(f)}`, { method: 'GET' }, `farol-${tipo}-${f.mes}.json`);
        mensagemEm('estadoAuditoria', t('Relatório baixado em JSON (registrado na auditoria com o seu nome).'));
      } else {
        await baixarDaApi(`/api/relatorios/${tipo}.${acao}?${consulta(f)}`, { method: 'GET' }, `farol-auditoria.${acao}`);
        mensagemEm('estadoAuditoria', t('Relatório baixado em {formato}, com o seu nome e o código de verificação.', { formato: acao.toUpperCase() }));
      }
    } catch (e) {
      if (e.status === 401) return;
      mensagemEm('estadoAuditoria', e.message, true);
      erroDoServidor($('audEnviar'), e, { destinatarios: 'audDestinos' });
    }
  });
}

// tudo o que aconteceu com o aviso, da auditoria: quando, quem (nome e perfil), o quê e o código da linha
async function verLinhaTempo() {
  try {
    estado.linhaTempo = await api(`/api/historico/${estado.resultado.id}/linha-do-tempo`);
    const lt = estado.linhaTempo.linhas;
    $('linhaTempo').replaceChildren(no('h3', { texto: t('Linha do tempo do aviso nº {id}', { id: estado.linhaTempo.aviso }) }),
      lt.length ? no('ol', { classe: 'linha-tempo' }, lt.map(x => no('li', {}, no('strong', { texto: dataHora(x.quando) }), ` · ${x.acao}`,
        no('span', { classe: 'quem', texto: ` · ${x.usuario || t('sem login (rádio)')}${x.perfil ? ` (${t(x.perfil)})` : ''} · ${x.codigo}` }))))
        : no('p', { classe: 'ajuda', texto: t('Nada registrado para este aviso.') }));
    $('linhaTempo').hidden = false;
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

async function baixarComprovante(evento) {
  if (evento.target.id === 'verLinhaTempo') return verLinhaTempo();
  if (evento.target.id !== 'baixarComprovante') return;
  try {
    await baixarDaApi(`/api/historico/${estado.resultado.id}/comprovante.pdf`, { method: 'GET' }, 'farol-comprovante.pdf');
    avisar(t('Comprovante do aviso nº {id} baixado (registrado na auditoria).', { id: estado.resultado.id }));
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

async function verificarAuditoria() {
  try {
    const v = await api('/api/auditoria/verificar');
    mensagemEm('estadoAuditoria', v.ok ? t('Auditoria íntegra{linhas}. Nenhuma linha foi alterada nem apagada.', { linhas: v.linhas ? t(': {n} linhas conferidas', { n: fmt(v.linhas) }) : '' })
      : t('A auditoria NÃO confere{onde}.', { onde: v.quebra_id ? t(' a partir da linha {id} ({motivo})', { id: v.quebra_id, motivo: v.motivo }) : `: ${v.motivo}` }), !v.ok);
    estado.registro = (await api('/api/registro')).registro;
    desenharRegistro();
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoAuditoria', e.message, true);
  }
}

const selecionados = sel => [...sel.selectedOptions].map(o => o.value);

const nomeValido = n => n.trim().replace(/\s+/g, ' ').length >= 2;

async function cadastrarUsuario(evento) {
  evento.preventDefault();
  const form = $('formUsuario'), nome = $('novoNome').value, email = $('novoEmail').value.trim();
  const erros = [!nomeValido(nome) && ['novoNome', t('Informe o nome (de 2 a 120 caracteres).')],
    !EMAIL.test(email) && ['novoEmail', email ? t('E-mail inválido.') : t('Informe o e-mail da empresa.')]].filter(Boolean);
  if (erros.length) { mostrarErros(form, erros); return mensagemEm('estadoUsuario', erros[0][1], true); }
  limparErros(form);
  await ocupado(botaoDoEnvio(evento), 'Salvando…', async () => {
    try {
      const j = await api('/api/usuarios', { method: 'POST', json: { nome, email, perfil: $('novoPerfil').value,
        municipios: selecionados($('novoMunicipios')) } });
      for (const o of $('novoMunicipios').options) o.selected = false;
      $('novoNome').value = ''; $('novoEmail').value = '';
      mensagemEm('estadoUsuario', t('{nome} cadastrado (registrado na auditoria).', { nome: j.usuario.nome }));
      mostrarSenhaTemporaria(t('Senha temporária de {nome} ({email}):', { nome: j.usuario.nome, email: j.usuario.email }), j.senha_temporaria);
      await irPara('usuarios');
    } catch (e) {
      if (e.status === 401) return;
      mensagemEm('estadoUsuario', e.message, true);
      erroDoServidor(form, e, { nome: 'novoNome', email: 'novoEmail', perfil: 'novoPerfil', municipios: 'novoMunicipios' });
    }
  });
}

async function acaoUsuario(evento) {
  const b = evento.target.closest('button[data-acao-usuario]');
  if (!b) return;
  const linha = b.closest('[data-usuario]'), id = linha.dataset.usuario, x = estado.usuarios.find(u => String(u.id) === id);
  const salvar = b.dataset.acaoUsuario === 'salvar';
  if (salvar && !nomeValido($(`usu-${id}-nome`).value)) {
    mostrarErros(linha, [[`usu-${id}-nome`, t('Informe o nome (de 2 a 120 caracteres).')]]);
    return mensagemEm('estadoUsuario', t('{nome}: informe o nome.', { nome: x.nome }), true);
  }
  limparErros(linha);
  await ocupado(b, salvar ? 'Salvando…' : 'Gerando…', async () => {
    try {
      if (salvar) {
        const campo = n => $(`usu-${id}-${n}`).value;
        await api(`/api/usuarios/${id}`, { method: 'PATCH', json: { nome: campo('nome'), perfil: campo('perfil'), status: campo('status'),
          municipios: selecionados($(`usu-${id}-municipios`)) } });
        mensagemEm('estadoUsuario', t('{nome}: alterações salvas (registrado na auditoria).', { nome: campo('nome').trim() }));
      } else {
        const j = await api(`/api/usuarios/${id}/senha-temporaria`, { method: 'POST' });
        mostrarSenhaTemporaria(t('Nova senha temporária de {nome} ({email}). As sessões abertas dele foram encerradas.', { nome: x.nome, email: x.email }), j.senha_temporaria);
      }
      await irPara('usuarios');
    } catch (e) {
      if (e.status === 401) return;
      mensagemEm('estadoUsuario', e.message, true);
      erroDoServidor(linha, e, Object.fromEntries(['nome', 'perfil', 'status', 'municipios'].map(c => [c, `usu-${id}-${c}`])));
    }
  });
}

const CAMPOS_EMPRESA = { nome: 'empNome', sigla: 'empSigla', dominio: 'empDominio', cnpj: 'empCnpj', admin_nome: 'empAdminNome', admin_email: 'empAdminEmail' };

async function cadastrarEmpresa(evento) {
  evento.preventDefault();
  const form = $('formEmpresa'), v = id => $(id).value.trim(), editando = estado.empresaEditando;
  const erros = [!nomeValido(v('empNome')) && ['empNome', t('Informe o nome da empresa (de 2 a 120 caracteres).')],
    !editando && !/^[A-Za-z0-9]{2,10}$/.test(v('empSigla')) && ['empSigla', t('Sigla: de 2 a 10 letras ou números.')],
    !EMAIL.test(`x@${v('empDominio')}`) && ['empDominio', t('Informe o domínio dos e-mails (ex.: empresa.com.br).')],
    !editando && !nomeValido(v('empAdminNome')) && ['empAdminNome', t('Informe o nome do primeiro admin.')],
    !editando && !EMAIL.test(v('empAdminEmail')) && ['empAdminEmail', t('Informe o e-mail do primeiro admin (do domínio da empresa).')]].filter(Boolean);
  if (erros.length) { mostrarErros(form, erros); return mensagemEm('estadoEmpresa', erros[0][1], true); }
  limparErros(form);
  await ocupado(botaoDoEnvio(evento), 'Salvando…', async () => {
    try {
      if (editando) {
        await api(`/api/empresas/${editando.id}`, { method: 'PATCH', json: { nome: v('empNome'), dominio: v('empDominio'), cnpj: v('empCnpj') } });
        limparFormEmpresa();
        await irPara('empresas');
        return mensagemEm('estadoEmpresa', t('{nome} alterada (registrado na auditoria).', { nome: v('empNome') || editando.nome }));
      }
      const j = await api('/api/empresas', { method: 'POST', json: { nome: v('empNome'), sigla: v('empSigla'), dominio: v('empDominio'),
        admin_nome: v('empAdminNome'), admin_email: v('empAdminEmail'), cnpj: v('empCnpj') || null } });
      limparFormEmpresa();
      mensagemEm('estadoEmpresa', t('{nome} cadastrada (registrado na auditoria).', { nome: j.empresa.nome }));
      mostrarSenhaTemporaria(t('Senha temporária do primeiro admin de {nome}:', { nome: j.empresa.nome }), j.senha_temporaria);
      await irPara('empresas');
      await abrirEditorArea(j.empresa.id, false);   // em seguida, a área de atuação (sem ela, a empresa não cria avisos)
    } catch (e) {
      if (e.status === 401) return;
      mensagemEm('estadoEmpresa', e.message, true);
      erroDoServidor(form, e, CAMPOS_EMPRESA);
    }
  });
}

function limparFormEmpresa() {
  estado.empresaEditando = null;
  for (const id of Object.values(CAMPOS_EMPRESA)) $(id).value = '';
  limparErros($('formEmpresa'));
  desenharFormEmpresa();
}

// o mesmo formulário cadastra ou edita (nome, CNPJ e domínio; a sigla e o primeiro admin não mudam)
function desenharFormEmpresa() {
  const e = estado.empresaEditando;
  $('formEmpresaTitulo').textContent = e ? t('Editar {nome}', { nome: e.nome }) : t('Cadastrar empresa');
  $('empSalvar').textContent = e ? t('Salvar alterações') : t('Cadastrar empresa');
  $('empCancelar').hidden = !e;
  for (const id of ['empSiglaRotulo', 'empAdminNomeRotulo', 'empAdminEmailRotulo']) $(id).hidden = !!e;
}

async function acaoEmpresa(evento) {
  const b = evento.target.closest('button[data-empresa-acao]');
  if (!b) return;
  const id = b.closest('[data-empresa]').dataset.empresa, e = estado.empresas.find(x => String(x.id) === id), acao = b.dataset.empresaAcao;
  if (acao === 'ficha') return abrirFichaEmpresa(Number(id));
  if (acao === 'area') return abrirEditorArea(id);
  if (acao === 'editar') abrirEditorArea(id, false);   // o Editar da empresa também mostra a área de atuação
  if (acao === 'editar') {
    estado.empresaEditando = e;
    limparErros($('formEmpresa'));
    $('empNome').value = e.nome; $('empDominio').value = e.dominio; $('empCnpj').value = e.cnpj || '';
    desenharFormEmpresa();
    $('formEmpresa').scrollIntoView({ block: 'start' });
    return $('empNome').focus();
  }
  if (acao === 'suspensa' && !confirm(t('Suspender {nome}? Ninguém da empresa entra até ela ser reativada.', { nome: e.nome }))) return;
  await ocupado(b, 'Salvando…', async () => {
    try {
      await api(`/api/empresas/${id}`, { method: 'PATCH', json: { status: acao } });
      await irPara('empresas');
      mensagemEm('estadoEmpresa', t(acao === 'suspensa' ? '{nome} suspensa (registrado na auditoria).' : '{nome} reativada (registrado na auditoria).', { nome: e.nome }));
    } catch (x) {
      if (x.status !== 401) mensagemEm('estadoEmpresa', x.message, true);
    }
  });
}

// ---- Rádios (Admin da empresa) ----
function limparFormRadio() {
  estado.radioEditando = null;
  estado.pedidoAtendendo = null;
  estado.alcanceComunidades = [];
  for (const id of ['radNome', 'radEmail', 'radWhats', 'radValor']) $(id).value = '';
  $('radCobranca').value = 'fechado';
  $('radAtiva').checked = true;
  for (const o of $('radMunicipios').options) o.selected = false;
  $('radMunCom').value = '';
  limparErros($('formRadio'));
}

const CAMPOS_RADIO = { nome: 'radNome', email: 'radEmail', whatsapp: 'radWhats', valor_padrao: 'radValor', alcance: 'radMunicipios' };

// o que o servidor também confere (api/radio._validar_radio), antecipado na tela com o erro no campo
function errosRadio() {
  const nome = $('radNome').value.trim(), email = $('radEmail').value.trim(), whats = $('radWhats').value.replace(/\D/g, ''), valor = reaisNumero($('radValor').value);
  return [!(nome.length >= 2 && nome.length <= 80) && ['radNome', t('Informe o nome da rádio (de 2 a 80 caracteres).')],
    !email && !whats && ['radEmail', t('Informe o e-mail ou o WhatsApp da rádio.')],
    email && !EMAIL.test(email) && ['radEmail', t('E-mail da rádio inválido.')],
    whats && (whats.length < 10 || whats.length > 13) && ['radWhats', t('WhatsApp: de 10 a 13 algarismos, com o DDD.')],
    Number.isNaN(valor) && ['radValor', t('Valor padrão: um valor em R$ (ex.: 150,00).')]].filter(Boolean);
}

async function salvarRadio(evento) {
  evento.preventDefault();
  const r = estado.radioEditando, pedido = estado.pedidoAtendendo, form = $('formRadio');
  const erros = errosRadio();
  if (erros.length) { mostrarErros(form, erros); return mensagemEm('estadoRadio', erros[0][1], true); }
  limparErros(form);
  const dados = { nome: $('radNome').value, email: $('radEmail').value || null, whatsapp: $('radWhats').value || null,
    valor_padrao: $('radValor').value || null, cobranca: $('radCobranca').value, ativa: $('radAtiva').checked,
    alcance: { municipios: selecionados($('radMunicipios')), comunidades: estado.alcanceComunidades },
    ...(pedido && !r ? { pedido_id: pedido.id } : {}) };
  await ocupado(botaoDoEnvio(evento), 'Salvando…', async () => {
    try {
      const j = await api(r ? `/api/radios/${r.id}` : '/api/radios', { method: r ? 'PATCH' : 'POST', json: dados });
      limparFormRadio();
      await irPara('radios');
      mensagemEm('estadoRadio', j.nada_mudou ? t('{nome}: nada mudou.', { nome: j.radio.nome })
        : t(r ? '{nome} alterada (registrado na auditoria).' : pedido ? '{nome} cadastrada (pedido de {por} atendido) (registrado na auditoria).'
          : '{nome} cadastrada (registrado na auditoria).', { nome: j.radio.nome, por: pedido?.por }));
    } catch (e) {
      if (e.status === 401) return;
      mensagemEm('estadoRadio', e.message, true);
      erroDoServidor(form, e, CAMPOS_RADIO);
    }
  });
}

// os dados de uma rádio da lista, como o servidor recebe (para desativar e reativar sem mudar o resto)
const dadosDaRadio = (x, ativa) => ({ nome: x.nome, email: x.email, whatsapp: x.whatsapp, valor_padrao: x.valor_padrao, cobranca: x.cobranca,
  ativa, alcance: x.alcance });

async function editarRadio(evento) {
  const b = evento.target.closest('button[data-radio-acao]');
  if (!b) return;
  const r = estado.radiosAdmin.find(x => String(x.id) === b.closest('[data-radio]').dataset.radio);
  if (b.dataset.radioAcao !== 'editar') {
    const ativa = b.dataset.radioAcao === 'reativar';
    if (!ativa && !confirm(t('Desativar {nome}? Ela some da lista do envio até ser reativada.', { nome: r.nome }))) return;
    return ocupado(b, 'Salvando…', async () => {
      try {
        await api(`/api/radios/${r.id}`, { method: 'PATCH', json: dadosDaRadio(r, ativa) });
        await irPara('radios');
        mensagemEm('estadoRadio', t(ativa ? '{nome} reativada (registrado na auditoria).' : '{nome} desativada (registrado na auditoria).', { nome: r.nome }));
      } catch (e) {
        if (e.status !== 401) mensagemEm('estadoRadio', e.message, true);
      }
    });
  }
  estado.pedidoAtendendo = null;
  limparErros($('formRadio'));
  estado.radioEditando = r;
  estado.alcanceComunidades = r.alcance.comunidades.map(c => ({ ...c }));
  $('radNome').value = r.nome; $('radEmail').value = r.email || ''; $('radWhats').value = r.whatsapp || '';
  $('radValor').value = r.valor_padrao ? Number(r.valor_padrao).toFixed(2).replace('.', ',') : '';
  $('radCobranca').value = r.cobranca; $('radAtiva').checked = r.ativa;
  for (const o of $('radMunicipios').options) o.selected = r.alcance.municipios.includes(o.value);
  desenharRadios();
  $('formRadio').scrollIntoView({ block: 'start' });
}

// pedido de rádio: atender abre o cadastro preenchido (o envio do cadastro fecha o pedido); recusar pede o motivo
async function acaoPedido(evento) {
  const b = evento.target.closest('button[data-pedido-acao]');
  if (!b) return;
  const item = b.closest('[data-pedido]'), p = estado.pedidos.find(x => String(x.id) === item.dataset.pedido);
  if (b.dataset.pedidoAcao === 'atender') {
    limparFormRadio();
    estado.pedidoAtendendo = p;
    $('radNome').value = p.nome;
    if (p.contato.includes('@')) $('radEmail').value = p.contato; else $('radWhats').value = p.contato;
    desenharRadios();
    mensagemEm('estadoRadio', t('Confira o cadastro da {nome}, escolha o que ela alcança e clique em "Cadastrar rádio".', { nome: p.nome }));
    $('formRadio').scrollIntoView({ block: 'start' });
    return $('radNome').focus();
  }
  const motivo = $(`pedido-motivo-${p.id}`);
  if (motivo.value.trim().length < 3) {
    mostrarErros(item, [[motivo.id, t('Escreva o motivo da recusa (de 3 a 300 caracteres).')]]);
    return mensagemEm('estadoRadio', t('Escreva o motivo da recusa.'), true);
  }
  limparErros(item);
  await ocupado(b, 'Salvando…', async () => {
    try {
      await api(`/api/radios/pedidos/${p.id}/recusar`, { method: 'POST', json: { motivo: motivo.value } });
      await irPara('radios');
      mensagemEm('estadoRadio', t('Pedido da {nome} recusado (o Operador vê o motivo; registrado na auditoria).', { nome: p.nome }));
    } catch (e) {
      if (e.status === 401) return;
      mensagemEm('estadoRadio', e.message, true);
      erroDoServidor(item, e, { motivo: motivo.id });
    }
  });
}

async function escolherMunicipioRadio() {
  const cod = $('radMunCom').value;
  if (cod && !estado.territorios[cod]) {
    try { estado.territorios[cod] = await api(`/api/municipios/${cod}/comunidades`); } catch (e) { if (e.status !== 401) mensagemEm('estadoRadio', e.message, true); }
  }
  desenharComunidadesRadio();
}

function marcarComunidade(evento) {
  const c = evento.target.dataset?.comunidade;
  if (!c) return;
  const [municipio, nome, distrito] = c.split('|');
  estado.alcanceComunidades = estado.alcanceComunidades.filter(x => `${x.municipio}|${x.nome}|${x.distrito}` !== c);
  if (evento.target.checked) estado.alcanceComunidades.push({ municipio, nome, distrito });
  $('radResumo').textContent = resumoComunidades();   // só o resumo: a lista fica (e o foco também)
}

// ---- Configurações da empresa ----
const CAMPOS_CONFIG = { modelo_mensagem: 'cfgModelo', nome_mensagem: 'cfgNome', telefone: 'cfgTelefone', limite_rejeicao: 'cfgLimite',
  epsg_utm: 'cfgFuso', antecedencia_dias: 'cfgAntecedencia', orcamento_radio: 'cfgOrcamento', alerta_preco: 'cfgAlertaPreco',
  repeticao_n: 'cfgRepN', repeticao_dias: 'cfgRepDias', modelo_mensagem_en: 'cfgModeloEn', modelo_mensagem_es: 'cfgModeloEs', idioma_padrao: 'cfgIdioma' };
// [id, mínimo, máximo, inteiro, texto]: as faixas que o servidor aceita (api/radio.Configuracao)
const FAIXAS_CONFIG = [['cfgLimite', 0, 50, false, 'Limite de rejeição: de 0 a 50%.'], ['cfgAntecedencia', 1, 90, true, 'Antecedência: de 1 a 90 dias.'],
  ['cfgAlertaPreco', 0, 500, false, 'Alerta de preço: de 0 a 500%.'], ['cfgRepN', 2, 50, true, 'Repetição: de 2 a 50 desligamentos.'],
  ['cfgRepDias', 7, 365, true, 'Repetição: de 7 a 365 dias.']];

function errosConfig() {
  const num = id => $(id).value.trim() === '' ? NaN : Number($(id).value);
  const erros = FAIXAS_CONFIG.filter(([id, min, max, inteiro]) => { const n = num(id); return !(n >= min && n <= max) || (inteiro && !Number.isInteger(n)); })
    .map(([id, , , , texto]) => [id, t(texto)]);
  const orc = $('cfgOrcamento').value.trim();
  if (orc && !(Number(orc) >= 0)) erros.push(['cfgOrcamento', t('Orçamento: um valor em R$ (ou vazio, sem orçamento).')]);
  for (const id of ['cfgModeloEs', 'cfgModeloEn', 'cfgModelo']) if (!$(id).value.trim()) erros.unshift([id, t('Escreva o modelo da mensagem.')]);
  if (!nomeValido($('cfgNome').value)) erros.unshift(['cfgNome', t('Nome da empresa na mensagem: de 2 a 120 caracteres.')]);
  return erros;
}

async function salvarConfig(evento) {
  evento.preventDefault();
  const form = $('formConfig'), erros = errosConfig();
  if (erros.length) { mostrarErros(form, erros); return mensagemEm('estadoConfig', erros[0][1], true); }
  limparErros(form);
  await ocupado(botaoDoEnvio(evento), 'Salvando…', async () => {
    try {
      estado.configuracao = await api('/api/empresa/configuracao', { method: 'PUT', json: { modelo_mensagem: $('cfgModelo').value, nome_mensagem: $('cfgNome').value,
        telefone: $('cfgTelefone').value, limite_rejeicao: Number($('cfgLimite').value) / 100, epsg_utm: Number($('cfgFuso').value),
        antecedencia_dias: Number($('cfgAntecedencia').value),
        orcamento_radio: $('cfgOrcamento').value.trim() === '' ? null : Number($('cfgOrcamento').value),
        alerta_preco: Number($('cfgAlertaPreco').value) / 100, repeticao_n: Number($('cfgRepN').value), repeticao_dias: Number($('cfgRepDias').value),
        modelo_mensagem_en: $('cfgModeloEn').value, modelo_mensagem_es: $('cfgModeloEs').value, idioma_padrao: $('cfgIdioma').value } });
      desenharConfig();
      if (estado.config) estado.config.idioma_padrao = estado.configuracao.idioma_padrao;   // o idioma do próximo aviso
      mensagemEm('estadoConfig', t('Configurações salvas (registrado na auditoria). Valem para os próximos avisos.'));
    } catch (e) {
      if (e.status === 401) return;
      mensagemEm('estadoConfig', e.message, true);
      erroDoServidor(form, e, CAMPOS_CONFIG);
    }
  });
}

// ---- Idioma da tela (Fase K) ----
// os textos fixos do index.html: data-t (o texto do elemento) e data-t-placeholder / data-t-aria-label (o atributo)
function aplicarTextos() {
  for (const e of document.querySelectorAll('[data-t]')) {
    if (!e.dataset.t) e.dataset.t = e.textContent.trim();
    e.textContent = t(e.dataset.t);
  }
  for (const [atributo, dado] of [['placeholder', 'tPlaceholder'], ['aria-label', 'tAriaLabel']])
    for (const e of document.querySelectorAll(`[data-t-${atributo}]`)) e.setAttribute(atributo, t(e.dataset[dado]));
  document.documentElement.lang = IDIOMA;
  document.title = t('Norte · Aviso de desligamento');
}

// os tipos de desligamento vêm do servidor no idioma da tela
function desenharTipos() {
  const atual = $('tipo').value;
  $('tipo').replaceChildren(...Object.entries(estado.config?.tipos || {}).map(([k, nome]) => no('option', { value: k, texto: nome })));
  if (atual) $('tipo').value = atual;
}

// idioma do aviso sem voz (espanhol): a tela avisa já no passo 2
function desenharIdiomaAviso() {
  const sem = audioLigado() && pode('gerar_aviso') && !vozDoIdioma($('idioma').value);
  $('idiomaAudio').hidden = !sem;
  $('idiomaAudio').textContent = sem ? t('Áudio indisponível em espanhol: nenhuma voz em espanhol com licença clara (veja ORIGEM.md). Use o texto e o PDF.') : '';
}

async function trocarIdioma(novo, salvar = true) {
  if (!IDIOMAS_TELA.includes(novo)) return;
  IDIOMA = novo;
  $('idiomaTela').value = novo;
  try { sessionStorage.setItem('farol.idioma', novo); } catch (e) { /* sem armazenamento */ }
  aplicarTextos();
  desenharTema(); desenharLegenda(); desenharTela(); desenharEstado(); desenharBotaoRede(); desenharPainelAmplo(); desenharA11y();
  if (salvar && estado.usuario) api('/api/eu/preferencias', { method: 'PUT', json: { idioma: novo } }).catch(() => {});
  if (estado.tela !== 'app' || !estado.config) return;
  try { estado.config = await api('/api/config'); } catch (e) { return; }   // os tipos no idioma novo
  $('faixa').textContent = t(estado.config.aviso_ficticio);
  desenharTipos(); desenharIdiomaAviso(); desenharRede(); desenharUcs(); desenharIrPara();
  $('botaoCalor').textContent = estado.calor ? t('Esconder mapa de calor') : t('Mapa de calor (12 meses)');
  atribuicao?.setPrefix(t('Concessão e comunidades: IBGE · Leaflet'));
  for (const id of ['relMes', 'audMes', 'simPeriodo']) $(id).replaceChildren();   // os meses no formato do idioma
  if (estado.resultado) desenharResultado();
  desenharEscolha();   // o passo 3 (escolher quem será desligado) no idioma novo
  if (ehFarol()) { desenharLegendaEmpresas(); desenharSobreposicao(); }
  await irPara(estado.vista);
}

// ---- Acessibilidade (tamanho do texto, contraste, fonte de leitura, espaçamento, movimento, voz) ----
const A11Y_PADRAO = { texto: 100, contraste: false, dislexia: false, espacamento: false, movimento: false, links: false, guia: false, simples: false };
const A11Y_CAIXAS = [['a11yContraste', 'contraste'], ['a11yDislexia', 'dislexia'], ['a11yEspacamento', 'espacamento'], ['a11yMovimento', 'movimento'],
  ['a11yLinks', 'links'], ['a11yGuia', 'guia'], ['a11ySimples', 'simples']];
const menosMovimento = () => estado.a11y.movimento || matchMedia('(prefers-reduced-motion: reduce)').matches;

// View: aplica as escolhas na página inteira (atributos no <html>, lidos pelo CSS) e desenha o painel
function desenharA11y() {
  const a = estado.a11y, raiz = document.documentElement;
  raiz.style.fontSize = a.texto === 100 ? '' : `${a.texto}%`;   // pelo CSSOM (a CSP não deixa atributo style)
  for (const [, k] of A11Y_CAIXAS) raiz.toggleAttribute(`data-${k}`, !!a[k]);
  $('guiaLeitura').hidden = !a.guia;
  for (const b of $('a11yTexto').querySelectorAll('button')) b.setAttribute('aria-pressed', String(Number(b.dataset.texto) === a.texto));
  for (const [id, k] of A11Y_CAIXAS) $(id).checked = !!a[k];
  $('painelAcessibilidade').hidden = !estado.painelA11y;
  $('botaoAcessibilidade').setAttribute('aria-expanded', String(estado.painelA11y));
  $('a11yLer').setAttribute('aria-pressed', String(estado.lendo));
  $('a11yLer').textContent = estado.lendo ? t('Parar a leitura') : t('Ler esta tela em voz alta');
  desenharVoz();
  if (mapa) Object.assign(mapa.options, { zoomAnimation: !menosMovimento(), fadeAnimation: !menosMovimento(), markerZoomAnimation: !menosMovimento() });
  $('caixaDeclaracao').querySelector('.cartao').classList.toggle('simples', !!a.simples);
  mapa?.invalidateSize();
}

// Controller: muda uma escolha, guarda (perfil ou sessão) e redesenha
function mudarA11y(mudanca, anuncio) {
  Object.assign(estado.a11y, mudanca);
  try { sessionStorage.setItem('farol.a11y', JSON.stringify(estado.a11y)); } catch (e) { /* sem armazenamento */ }
  if (estado.usuario) api('/api/eu/preferencias', { method: 'PUT', json: { acessibilidade: mudanca } }).catch(() => {});
  desenharA11y();
  if (anuncio) $('a11yEstado').textContent = anuncio;
}
function abrirA11y(aberto = !estado.painelA11y) {
  estado.painelA11y = aberto;
  desenharA11y();
  if (aberto) $('a11yTitulo').focus(); else $('botaoConta').focus();
}
// ler em voz alta o que está na tela (a vista aberta, ou a tela de entrar): só a voz do aparelho, nada vai ao servidor
// só voz instalada no aparelho (localService): uma voz on-line mandaria o texto da tela a um servidor de fora
const vozLocal = () => ('speechSynthesis' in window ? speechSynthesis.getVoices() : [])
  .find(v => v.localService === true && v.lang.toLowerCase().startsWith(IDIOMA.slice(0, 2).toLowerCase())) || null;
function desenharVoz() {
  const tem = !!vozLocal();
  $('a11yLer').disabled = !tem;
  $('a11yVoz').textContent = tem ? t('A leitura usa a voz do próprio aparelho: nada é enviado ao Norte.')
    : t('Nenhuma voz instalada neste aparelho. Windows: Configurações > Hora e idioma > Fala > Adicionar vozes. Android: Configurações > Acessibilidade > Saída de texto em voz (baixe os dados de voz). iPhone e iPad: Ajustes > Acessibilidade > Conteúdo Falado > Vozes.');
}
function lerEmVozAlta() {
  if (estado.lendo) { speechSynthesis.cancel(); estado.lendo = false; return desenharA11y(); }
  const voz = vozLocal();
  if (!voz) return desenharVoz();   // nunca uma voz on-line
  const alvo = estado.tela === 'app' ? document.querySelector('.vista:not([hidden])') : document.querySelector('.tela-acesso:not([hidden])');
  const texto = (alvo?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 4000);
  if (!texto) return;
  const fala = new SpeechSynthesisUtterance(texto);
  fala.lang = voz.lang;
  fala.voice = voz;
  fala.onend = fala.onerror = () => { estado.lendo = false; desenharA11y(); };
  estado.lendo = true;
  speechSynthesis.speak(fala);
  desenharA11y();
}
function abrirDeclaracao() {
  estado.painelA11y = false; desenharA11y();
  $('caixaDeclaracao').hidden = false;
  $('relatoEnviar').disabled = !estado.usuario;
  mensagemEm('estadoRelato', estado.usuario ? '' : t('Entre no Norte para enviar um relato.'));
  $('declTitulo').focus();
}
async function enviarRelato(evento) {
  evento.preventDefault();
  const texto = $('relatoTexto').value.trim();
  if (texto.length < 10) { mostrarErros($('formRelato'), [['relatoTexto', t('Descreva o problema (pelo menos 10 caracteres).')]]); return; }
  limparErros($('formRelato'));
  await ocupado($('relatoEnviar'), 'Enviando…', async () => {
    try {
      const r = await api('/api/acessibilidade/relato', { method: 'POST', json: { texto, tela: estado.tela === 'app' ? estado.vista : estado.tela } });
      $('relatoTexto').value = '';
      mensagemEm('estadoRelato', t('Relato enviado e registrado na auditoria (código {codigo}). Obrigado!', { codigo: r.codigo }));
    } catch (e) {
      mensagemEm('estadoRelato', e.message, true);
      erroDoServidor($('formRelato'), e, { texto: 'relatoTexto' });
    }
  });
}

function carregarA11y(doPerfil) {
  let sessao = {};
  try { sessao = JSON.parse(sessionStorage.getItem('farol.a11y') || '{}'); } catch (e) { /* sem armazenamento */ }
  const valido = (k, v) => k in A11Y_PADRAO && (k === 'texto' ? [90, 100, 125, 150, 200].includes(v) : typeof v === 'boolean');
  if (doPerfil !== undefined) estado.painelA11y = false;
  const limpar = o => Object.fromEntries(Object.entries(o || {}).filter(([k, v]) => valido(k, v)));
  estado.a11y = { ...A11Y_PADRAO, ...limpar(sessao), ...limpar(doPerfil) };
  // no primeiro login, o que foi escolhido na tela de entrar passa para o perfil
  if (doPerfil !== undefined && !Object.keys(limpar(doPerfil)).length && Object.keys(limpar(sessao)).length)
    api('/api/eu/preferencias', { method: 'PUT', json: { acessibilidade: limpar(sessao) } }).catch(() => {});
  desenharA11y();
}

// ---- Tema, ajuda e dicas ----
function alternarTema() {
  const novo = temaAtual() === 'escuro' ? 'claro' : 'escuro';
  document.documentElement.dataset.tema = novo;
  try { localStorage.setItem('farol.tema', novo); } catch (e) { /* sem armazenamento: só nesta visita */ }
  desenharTema();
  trocarFundoDoMapa();
}

function abrirAjuda() {
  desenharAjuda();
  $('caixaAjuda').hidden = false;
  $('ajudaFechar').focus();
}

function mostrarDica(evento) {
  const b = evento.target.closest('button[data-dica]'), caixa = $('dica');
  if (!b) return;
  if (!caixa.hidden && caixa.dataset.de === b.dataset.dica) { caixa.hidden = true; return; }
  caixa.textContent = t(DICAS[b.dataset.dica]);
  caixa.dataset.de = b.dataset.dica;
  caixa.hidden = false;
  const r = b.getBoundingClientRect(), largura = Math.min(320, innerWidth - 24);
  Object.assign(caixa.style, { width: `${largura}px`, left: `${Math.max(12, Math.min(r.left + scrollX - largura / 2, innerWidth - largura - 12))}px`,
    top: `${r.bottom + scrollY + 6}px` });
}

function arrastar() {
  const z = $('zona');
  for (const ev of ['dragenter', 'dragover']) z.addEventListener(ev, e => { e.preventDefault(); z.classList.add('arrastando'); });
  for (const ev of ['dragleave', 'drop']) z.addEventListener(ev, () => z.classList.remove('arrastando'));
  z.addEventListener('drop', e => { e.preventDefault(); escolherPlanilha(e.dataTransfer.files[0]); });
}

async function abrir() {
  try { const tema = localStorage.getItem('farol.tema'); if (tema === 'claro' || tema === 'escuro') document.documentElement.dataset.tema = tema; } catch (e) { /* sem armazenamento */ }
  // antes de entrar, o idioma escolhido fica só nesta sessão do navegador; depois, no perfil do usuário
  let idioma = 'pt-BR';
  try { idioma = sessionStorage.getItem('farol.idioma') || 'pt-BR'; } catch (e) { /* sem armazenamento */ }
  await trocarIdioma(IDIOMAS_TELA.includes(idioma) ? idioma : 'pt-BR', false);
  carregarA11y();
  desenharTema();
  // data padrão: daqui a 4 dias (acima das 72 h legais)
  const d = new Date(Date.now() + 4 * 864e5);
  $('data').value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  $('formEntrar').addEventListener('submit', entrar);
  $('formSenha').addEventListener('submit', trocarSenha);
  $('sair').addEventListener('click', sair);
  $('abas').addEventListener('click', e => { const b = e.target.closest('button[data-vista]'); if (b) { estado.menuAberto = false; irPara(b.dataset.vista); } });
  $('botaoMenu').addEventListener('click', () => alternarMenu());
  $('botaoAmpliar').addEventListener('click', () => ampliarPainel());
  $('botaoAcessibilidade').addEventListener('click', () => abrirA11y());
  $('a11yFechar').addEventListener('click', () => abrirA11y(false));
  $('a11yTexto').addEventListener('click', e => { const b = e.target.closest('[data-texto]');
    if (b) mudarA11y({ texto: Number(b.dataset.texto) }, t('Texto em {n}%', { n: b.dataset.texto })); });
  for (const [id, k] of A11Y_CAIXAS) $(id).addEventListener('change', e => mudarA11y({ [k]: e.target.checked }));
  // guia de leitura: a faixa acompanha o mouse (e o foco, para quem usa o teclado)
  const moverGuia = y => { if (estado.a11y.guia) $('guiaLeitura').style.top = `${Math.max(0, y - 14)}px`; };
  document.addEventListener('pointermove', e => moverGuia(e.clientY));
  document.addEventListener('focusin', e => moverGuia(e.target.getBoundingClientRect?.().top + 10 || 0));
  // "Pular para o conteúdo": o título da tela que está aberta
  $('pular').addEventListener('click', e => {
    e.preventDefault();
    const alvo = estado.tela === 'app' ? document.querySelector('.vista:not([hidden]) h1') : document.querySelector('.tela-acesso:not([hidden]) h1');
    if (alvo) { alvo.setAttribute('tabindex', '-1'); alvo.focus(); }
  });
  $('a11yDeclaracao').addEventListener('click', abrirDeclaracao);
  $('declFechar').addEventListener('click', () => { $('caixaDeclaracao').hidden = true; $('botaoConta').focus(); });
  $('formRelato').addEventListener('submit', enviarRelato);
  $('a11yLer').addEventListener('click', lerEmVozAlta);
  if ('speechSynthesis' in window) speechSynthesis.addEventListener('voiceschanged', desenharVoz);   // as vozes chegam depois
  $('a11yPadrao').addEventListener('click', () => mudarA11y({ ...A11Y_PADRAO }, t('Opções de acessibilidade no padrão')));
  new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) rotularTabelas(n.matches('table') ? n.parentElement : n); })
    .observe(document.body, { childList: true, subtree: true });
  $('arquivo').addEventListener('change', e => escolherPlanilha(e.target.files[0]));
  $('aba').addEventListener('change', e => { estado.aba = e.target.value; });
  $('tipo').addEventListener('change', e => { for (const id of ['tipoOutroRotulo', 'tipoOutroAjuda']) $(id).hidden = e.target.value !== 'outro'; });
  $('acoesAviso').addEventListener('click', acaoAviso);
  $('verificarAuditoria').addEventListener('click', verificarAuditoria);
  $('formRelatorio').addEventListener('submit', carregarRelatorio);
  $('formRelatorio').addEventListener('click', exportarRelatorio);
  $('relQual').addEventListener('change', trocarTipoRelatorio);
  $('relModo').addEventListener('change', desenharFiltrosRelatorio);
  $('listaVias').addEventListener('click', baixarVia);
  $('formAuditoria').addEventListener('click', exportarAuditoria);
  $('docAuditoria').addEventListener('click', e => {
    if (e.target.id !== 'verUltimas') return;
    $('docAuditoria').replaceChildren(); mensagemEm('estadoAuditoria', '');
    $('listaRegistro').hidden = false; $('listaRegistro').querySelector('h2')?.setAttribute('tabindex', '-1'); $('listaRegistro').querySelector('h2')?.focus();
  });
  $('solicitado').addEventListener('click', baixarComprovante);
  $('conferencia').addEventListener('change', editarConferencia);
  $('conferencia').addEventListener('input', editarConferencia);
  $('conferencia').addEventListener('click', acaoConferencia);
  $('form').addEventListener('submit', enviar);
  $('botaoUcs').addEventListener('click', () => { estado.verUcs = !estado.verUcs; desenharUcs(); });
  $('botaoRede').addEventListener('click', alternarRede);
  $('botaoCalor').addEventListener('click', alternarCalor);
  $('botaoLegenda').addEventListener('click', alternarLegenda);
  try { estado.legendaMinimizada = localStorage.getItem('farol.legenda') === 'minimizada'; } catch (e) { /* sem armazenamento */ }
  desenharLegenda();
  $('funil').addEventListener('click', e => { const b = e.target.closest('button[data-passo]'); if (b && !b.disabled) irParaPasso(Number(b.dataset.passo)); });
  $('avancar').addEventListener('click', () => irParaPasso(2));
  $('voltar').addEventListener('click', () => irParaPasso(1));
  $('voltarResultado').addEventListener('click', () => irParaPasso(estado.passo - 1));
  $('voltarEscolha').addEventListener('click', () => irParaPasso(2));
  $('conferirEscolha').addEventListener('click', conferirEscolha);
  $('escolha').addEventListener('change', editarEscolha);
  $('escolha').addEventListener('input', buscarNaEscolha);
  $('escolha').addEventListener('click', acaoEscolha);
  $('escolha').addEventListener('toggle', abrirListaEscolha, true);   // o toggle do <details> não sobe: na captura
  $('avancarResultado').addEventListener('click', () => gerado() ? irParaPasso(5) : gerarAviso());
  $('novoAviso').addEventListener('click', novoAviso);
  $('verComparativo').addEventListener('click', () => irPara('comparativo'));
  $('comparativo').addEventListener('click', acaoComparativo);
  // o preço e as veiculações são do operador: valor inválido volta ao que valia (a conta nunca usa lixo)
  for (const [id, campo, min, max, inteiro] of [['precoSpot', 'preco', 0, 100000, false], ['veiculacoes', 'veiculacoes', 1, 100, true]])
    $(id).addEventListener('change', e => {
      const n = numeroDigitado(e.target.value, min, max, inteiro);
      if (n === null) { avisar(`${campo === 'preco' ? 'Preço do spot' : 'Veiculações'}: informe um número de ${fmt(min)} a ${fmt(max)}${inteiro ? ' (inteiro)' : ''}.`, true); }
      else estado.radio[campo] = n;
      e.target.value = String(estado.radio[campo]).replace('.', ',');
      desenharComparativo();
    });
  $('formPergunta').addEventListener('submit', e => { e.preventDefault(); perguntarAoPainel($('textoPergunta').value); });
  $('exemplosPergunta').addEventListener('click', e => {
    const b = e.target.closest('button[data-pergunta]');
    if (b) { $('textoPergunta').value = b.dataset.pergunta; perguntarAoPainel(b.dataset.pergunta); }
  });
  $('buscaHistorico').addEventListener('input', e => { estado.filtroHistorico.busca = e.target.value; desenharHistorico(); });
  $('periodoHistorico').addEventListener('change', e => { estado.filtroHistorico.periodo = e.target.value; desenharHistorico(); });
  $('municipios').addEventListener('click', acao);
  $('municipios').addEventListener('click', acaoEnvio);
  $('municipios').addEventListener('input', editarEnvio);
  $('municipios').addEventListener('change', editarEnvio);
  $('municipios').addEventListener('input', editar);
  $('listaHistorico').addEventListener('click', abrirHistorico);
  $('formUsuario').addEventListener('submit', cadastrarUsuario);
  $('listaEmpresas').addEventListener('click', acaoEmpresa);
  $('legendaEmpresas').addEventListener('click', acaoMapaEmpresas);
  $('fichaEmpresa').addEventListener('click', acaoMapaEmpresas);
  $('botaoLegendaEmpresas').addEventListener('click', () => { estado.legendaEmpresasAberta = !estado.legendaEmpresasAberta; desenharLegendaEmpresas(); });
  $('areaUf').addEventListener('change', e => { estado.area.uf = e.target.value; estado.area.busca = $('areaBusca').value = ''; desenharEditorArea(); desenharMapaDaUf(); });
  $('areaBusca').addEventListener('input', e => { estado.area.busca = e.target.value; desenharEditorArea(); });
  $('areaLista').addEventListener('change', e => { const c = e.target.dataset.areaMunicipio; if (c) alternarMunicipioArea(c, e.target.checked); });
  $('areaTodos').addEventListener('click', () => marcarUf(true));
  $('areaNenhum').addEventListener('click', () => marcarUf(false));
  $('areaArquivo').addEventListener('change', e => importarArquivoArea(e.target.files[0]));
  $('areaVerResumo').addEventListener('click', () => salvarArea(false));
  $('areaConfirmar').addEventListener('click', () => salvarArea(true));
  $('areaCancelar').addEventListener('click', () => { fecharEditorArea(); mensagemEm('estadoArea', ''); });
  $('formRadio').addEventListener('submit', salvarRadio);
  $('radCancelar').addEventListener('click', () => { limparFormRadio(); desenharRadios(); });
  $('listaRadios').addEventListener('click', editarRadio);
  $('listaPedidos').addEventListener('click', acaoPedido);
  $('empCancelar').addEventListener('click', limparFormEmpresa);
  // erro no campo: some quando a pessoa corrige; o link do resumo leva ao campo
  document.addEventListener('input', e => { if (e.target.getAttribute?.('aria-invalid') === 'true') limparErroCampo(e.target); });
  document.addEventListener('change', e => { if (e.target.getAttribute?.('aria-invalid') === 'true') limparErroCampo(e.target); });
  document.addEventListener('click', e => {
    const a = e.target.closest('a[data-campo-erro]');
    if (a) { e.preventDefault(); $(a.dataset.campoErro)?.focus(); }
  });
  $('radMunCom').addEventListener('change', escolherMunicipioRadio);
  $('radComunidades').addEventListener('change', marcarComunidade);
  $('formConfig').addEventListener('submit', salvarConfig);
  $('formSimulador').addEventListener('submit', salvarSimulador);
  $('simConservador').addEventListener('click', () => { $('simPct').value = '50'; $('simPct').focus();
    mensagemEm('estadoSimulador', t('Cenário conservador: 50% do gasto cobrado por tempo. Salve para guardar.')); });
  $('formSimPeriodo').addEventListener('submit', carregarSimulador);
  $('simPeriodo').addEventListener('change', () => carregarSimulador());
  $('formSimPeriodo').addEventListener('click', exportarSimulador);
  $('formConfig').addEventListener('input', desenharPreviaConfig);
  $('cfgPadrao').addEventListener('click', () => {
    const p = estado.configuracao.modelos_padrao || {};
    $('cfgModelo').value = p['pt-BR'] || estado.configuracao.modelo_padrao; $('cfgModeloEn').value = p.en || ''; $('cfgModeloEs').value = p.es || '';
    desenharPreviaConfig();
  });
  $('idiomaTela').addEventListener('change', e => trocarIdioma(e.target.value));
  $('idioma').addEventListener('change', desenharIdiomaAviso);
  $('subabas').addEventListener('click', e => { const b = e.target.closest('button[data-vista]'); if (b) irPara(b.dataset.vista); });
  $('botaoTema').addEventListener('click', alternarTema);
  $('botaoConta').addEventListener('click', () => alternarMenuConta());
  $('menuConta').addEventListener('click', e => {   // quem abre outra janela fecha o menu; idioma e tema ficam abertos para ver o efeito
    const b = e.target.closest('button');
    if (b && ['botaoAcessibilidade', 'botaoAjuda', 'sair'].includes(b.id)) alternarMenuConta(false);
  });
  document.addEventListener('click', e => { if (!$('menuConta').hidden && !e.target.closest('#menuConta, #botaoConta')) alternarMenuConta(false); });
  document.addEventListener('keydown', tecladoDoMenuConta);
  $('irPara').addEventListener('change', irParaNoMapa);
  $('irPara').addEventListener('submit', e => e.preventDefault());
  $('botaoAjuda').addEventListener('click', abrirAjuda);
  $('ajudaFechar').addEventListener('click', () => { $('caixaAjuda').hidden = true; $('botaoConta').focus(); });
  document.addEventListener('click', mostrarDica);
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    $('dica').hidden = true;
    if (!$('menuConta').hidden) { alternarMenuConta(false); $('botaoConta').focus(); }
    else if (!$('caixaDeclaracao').hidden) { $('caixaDeclaracao').hidden = true; $('botaoConta').focus(); }
    else if (estado.painelA11y) abrirA11y(false);
    else if (!$('caixaAjuda').hidden) { $('caixaAjuda').hidden = true; $('botaoConta').focus(); }
    else if (estado.menuAberto) { alternarMenu(false); $('botaoMenu').focus(); }
    else if (estado.painelAmplo && estado.tela === 'app' && !e.target.closest?.('input, select, textarea')) { ampliarPainel(false); $('botaoAmpliar').focus(); }
  });
  $('listaUsuarios').addEventListener('click', acaoUsuario);
  $('formEmpresa').addEventListener('submit', cadastrarEmpresa);
  $('caixaFechar').addEventListener('click', () => { $('caixaSenha').hidden = true; $('caixaSenhaValor').textContent = ''; });
  $('caixaCopiar').addEventListener('click', () => navigator.clipboard.writeText($('caixaSenhaValor').textContent).catch(() => {}));
  arrastar();
  try {
    const j = await api('/api/eu');
    await aposEntrar(j.usuario);
  } catch (e) {
    estado.tela = 'entrar';
    desenharTela();
  }
  desenharEstado();
  if (estado.tela !== 'app') document.documentElement.dataset.farol = 'pronto';
}

document.addEventListener('DOMContentLoaded', abrir);
