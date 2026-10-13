'use strict';
// Farol: tela do aviso de desligamento. Entrar, enviar a planilha, ver os municípios e as
// comunidades no mapa, gerar o roteiro (PDF) para a rádio, consultar o histórico e administrar
// usuários e empresas, conforme o perfil. Só fala com a própria API; quem decide o que cada perfil
// pode é o servidor (a tela só esconde o que não serve ao perfil).
// Organização: Model (estado e regras puras), View (desenha a partir do estado) e Controller (eventos).

// ======================= Model: estado da tela e regras puras (não toca no HTML) =======================
const estado = {
  usuario: null,           // /api/eu (perfil, empresa, ações permitidas)
  tela: 'carregando',      // carregando | entrar | senha | app
  vista: 'aviso',          // aviso | historico | painel | usuarios | empresas | registro
  passo: 1,                // funil do novo aviso: 1 planilha, 2 quando, 3 conferir, 4 avisos
  config: null, concessao: null,
  arquivo: null, enviando: false,
  mensagem: '', erro: false,
  resultado: null,         // resposta de /api/avisos ou um aviso do histórico (no mesmo formato)
  origem: null,            // 'novo' | 'historico'
  avisos: {},              // codigo_ibge -> texto do aviso (editável)
  finais: {},              // codigo_ibge -> texto final já guardado no histórico
  territorios: {},         // codigo_ibge -> GeoJSON das comunidades
  audios: {},              // codigo_ibge -> { texto, url (blob local), segundos }: o MP3 do texto atual
  audiosHoje: {},          // codigo_ibge -> { url, segundos }: o MP3 do aviso de hoje (comparativo)
  verUcs: true,            // camada dos pontos das UCs (só logo depois do envio; o histórico não tem pontos)
  verRede: true,           // rede elétrica FICTÍCIA (demonstração), de perto; o botão esconde
  evidencia: null,         // comunidade clicada no mapa: { chave } (borda branca e nome em destaque); clicar de novo ou no mapa tira
  legendaMinimizada: false, // lembrada neste navegador (só conveniência)
  redes: {},               // codigo_ibge -> rede fictícia do município (null: sem rede no banco)
  formulario: null,        // { data: '20/11', dataLonga: '20/11/2026', horario: '8h às 14h', idioma: 'pt-BR' }
  historico: [], usuarios: [], perfis: {}, empresas: [], registro: [],
  filtroHistorico: { busca: '', periodo: '' },
  painel: null,            // /api/painel: números do histórico da empresa
};

const VISTAS = [  // vista, rótulo, ação exigida
  ['aviso', 'Novo aviso', 'gerar_aviso'], ['historico', 'Histórico', 'ver_historico'], ['painel', 'Dashboard', 'ver_historico'],
  ['comparativo', 'Comparativo', 'ver_historico'],
  ['usuarios', 'Usuários', 'gerenciar_usuarios'], ['empresas', 'Empresas', 'gerenciar_empresas'],
  ['registro', 'Registro', 'ver_registro'],
];
const pode = acao => !!estado.usuario?.acoes.includes(acao);
const vistasDoPerfil = () => VISTAS.filter(([, , a]) => pode(a));

const fmt = n => Number(n).toLocaleString('pt-BR');
const dataHora = iso => new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

// "08:00" -> "8h", "08:30" -> "8h30" (como o aviso fala)
function horaTexto(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h}h${m ? String(m).padStart(2, '0') : ''}`;
}
// "2026-11-12" -> "12/11"
const dataTexto = iso => { const [, m, d] = iso.split('-'); return `${d}/${m}`; };
const dataLonga = iso => { const [a, m, d] = iso.split('-'); return `${d}/${m}/${a}`; };

function validarArquivo(arquivo) {
  if (!arquivo) return 'Escolha a planilha das UCs afetadas.';
  if (!/\.(csv|xlsx)$/i.test(arquivo.name)) return 'A planilha tem de ser .csv ou .xlsx.';
  if (estado.config && arquivo.size > estado.config.limites.bytes) return 'A planilha passa de 10 MB.';
  return null;
}

function validarFormulario({ arquivo, data, inicio, fim }) {
  const problema = validarArquivo(arquivo);
  if (problema) return problema;
  if (!data) return 'Informe a data do desligamento.';
  if (!inicio || !fim) return 'Informe o horário de início e de fim.';
  if (fim <= inicio) return 'O fim tem de ser depois do início.';
  return null;
}

function validarSenhaNova(nova, repetida) {
  if (nova.length < 12) return 'A senha nova precisa ter pelo menos 12 caracteres.';
  if (nova !== repetida) return 'As duas senhas novas não são iguais.';
  return null;
}

// o áudio vale enquanto o texto não muda; só em português por enquanto
const audioAtual = codigo => estado.audios[codigo]?.texto === estado.avisos[codigo] ? estado.audios[codigo] : null;
// o servidor pode estar sem a voz (FAROL_AUDIO=0, em produção no plano gratuito)
const audioLigado = () => estado.config?.audio !== false;
const temAudio = () => audioLigado() && estado.formulario?.idioma === 'pt-BR';

// 754 s -> "12 min 34 s"
const tempoNoAr = s => s < 60 ? `${fmt(s)} s` : `${fmt(Math.floor(s / 60))} min${s % 60 ? ` ${s % 60} s` : ''}`;

const palavras = texto => texto.trim().split(/\s+/).filter(Boolean).length;
const segundos = texto => Math.round(palavras(texto) / (estado.config?.palavras_por_segundo || 2.5));

// como a comunidade entra no aviso: inteira, parte ou localidade vizinha (fragmento)
const situacao = c => c.fragmento ? 'vizinha' : c.parcial ? 'parte' : 'inteira';
const ROTULO = { inteira: 'inteira', parte: 'parte', vizinha: 'localidade vizinha' };
// homônimos vêm como "Piacatuba (Tebas)"; na tela, o nome sem o sufixo e o distrito uma vez só
// (o distrito com o nome do município é a "Sede", como no aviso)
const semSufixo = nome => nome.replace(/ \(.*\)$/, '');
const distritoTexto = (c, m) => c.distrito === m.nome ? 'Sede' : c.distrito;
const nomeComDistrito = (c, m) => `${semSufixo(c.nome)} (${distritoTexto(c, m)})`;
const homonimo = c => / \(.*\)$/.test(c.nome);

// funil: até onde dá para ir (o 2 pede a planilha; o 3 e o 4, o resultado do envio)
const temResultadoNovo = () => !!estado.resultado && estado.origem === 'novo';
const passoMaximo = () => temResultadoNovo() ? 4 : estado.arquivo && !validarArquivo(estado.arquivo) ? 2 : 1;

// histórico: busca por município ou comunidade (sem acento) e período pela data em que foi gerado
const normalizar = t => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
function historicoFiltrado() {
  const { busca, periodo } = estado.filtroHistorico, termo = normalizar(busca.trim());
  const desde = periodo ? Date.now() - Number(periodo) * 86400000 : 0;
  return estado.historico.filter(a => new Date(a.criado_em).getTime() >= desde && (!termo || a.municipios.some(m =>
    normalizar(m.nome).includes(termo) || m.comunidades.some(c => normalizar(semSufixo(c.nome)).includes(termo)))));
}

const MES_CURTO = mes => { const [a, m] = mes.split('-').map(Number);
  return `${new Date(a, m - 1, 1).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')}/${String(a).slice(2)}`; };

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
    criado_em: a.criado_em, usuario: a.usuario,
  };
}

async function codigoVerificacao(texto) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(texto));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
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

function desenharTela() {
  $('telaEntrar').hidden = estado.tela !== 'entrar';
  $('telaSenha').hidden = estado.tela !== 'senha';
  $('telaApp').hidden = estado.tela !== 'app';
  $('conta').hidden = !estado.usuario;
  if (estado.usuario) {
    const u = estado.usuario;
    $('contaNome').textContent = `${u.nome} · ${u.perfil_nome}${u.empresa_sigla ? ' · ' + u.empresa_sigla : ''}`;
  }
}

function desenharAbas() {
  $('abas').replaceChildren(...vistasDoPerfil().map(([v, rotulo]) =>
    no('button', { type: 'button', 'data-vista': v, 'aria-current': estado.vista === v ? 'page' : null, texto: rotulo })));
  for (const [v] of VISTAS) $(`vista-${v}`).hidden = estado.vista !== v;
  // o resultado aparece só na vista de onde veio (um aviso novo em "Novo aviso", um antigo no "Histórico");
  // no funil, o passo 3 mostra a conferência e o 4, os avisos
  const vistaDoResultado = { novo: 'aviso', historico: 'historico' }[estado.origem];
  const r = $('resultado');
  if (vistaDoResultado && r.parentElement.id !== `lugar-${vistaDoResultado}`) $(`lugar-${vistaDoResultado}`).append(r);
  r.dataset.modo = estado.origem === 'novo' ? `passo${estado.passo}` : 'completo';
  r.hidden = !estado.resultado || estado.vista !== vistaDoResultado || (estado.origem === 'novo' && estado.passo < 3);
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
  $('navResultado').hidden = n < 3 || !temResultadoNovo();
  $('avancarResultado').hidden = n !== 3;
  $('novoAviso').hidden = n !== 4;
  $('verComparativo').hidden = n !== 4 || !pode('ver_historico');
  $('passo2Arquivo').textContent = estado.arquivo ? `Planilha: ${estado.arquivo.name}` : '';
  if (estado.resultado && estado.origem === 'novo') $('tituloResultado').textContent = tituloResultado();
}

function desenharEstado() {
  $('estado').textContent = estado.mensagem;
  $('estado').classList.toggle('erro', estado.erro);
  $('gerar').disabled = estado.enviando;
  $('gerar').textContent = estado.enviando ? 'Gerando…' : 'Gerar aviso';
  $('arquivoNome').textContent = estado.arquivo
    ? `${estado.arquivo.name} (${fmt(Math.ceil(estado.arquivo.size / 1024))} KB)`
    : 'Escolha ou arraste o arquivo (.csv ou .xlsx, até 10 MB)';
  $('zona').classList.toggle('escolhido', !!estado.arquivo);
  desenharFunil();
}

function mensagemEm(id, texto, erro) {
  $(id).textContent = texto;
  $(id).classList.toggle('erro', !!erro);
}

function desenharResumo() {
  const r = estado.resultado, p = r.planilha;
  const ucs = r.municipios.reduce((s, m) => s + m.ucs, 0);
  const dl = no('dl', { classe: 'numeros' },
    [['linhas lidas', p.linhas], ['UCs localizadas', ucs], ['com problema', p.total_problemas], ['fora da concessão', r.fora_da_concessao.ucs]]
      .map(([t, v]) => no('div', {}, no('dt', { texto: t }), no('dd', { texto: fmt(v) }))));
  const filhos = [dl, no('p', { classe: 'prazo', texto: `Antecedência mínima do aviso: ${r.prazo.antecedencia_minima} (${r.prazo.norma}).` })];
  if (!r.municipios.length) filhos.push(no('p', { classe: 'alerta', texto: 'Nenhuma UC da planilha caiu na área de concessão. Confira as coordenadas.' }));
  if (r.fora_da_concessao.ucs && r.fora_da_concessao.linhas.length) {
    const mais = r.fora_da_concessao.ucs > r.fora_da_concessao.linhas.length ? '…' : '';
    filhos.push(no('p', { classe: 'alerta', texto: `${fmt(r.fora_da_concessao.ucs)} UC(s) fora da área de concessão, sem aviso: linha(s) ${r.fora_da_concessao.linhas.join(', ')}${mais}.` }));
  }
  filhos.push(no('p', { classe: 'ajuda', texto: r.aviso_ficticio }));
  $('resumo').replaceChildren(...filhos);
}

const tempoTexto = texto => `${fmt(palavras(texto))} palavras · cerca de ${fmt(segundos(texto))} s no ar`;

function desenharMunicipios() {
  const editavel = pode('gerar_aviso');
  const cartoes = estado.resultado.municipios.map(m => {
    const g = grupos(m), cod = m.codigo_ibge, texto = estado.avisos[cod];
    const area = no('textarea', { id: `aviso-${cod}`, 'aria-label': `Aviso de ${m.nome}`, 'data-codigo': cod, readonly: !editavel });
    area.value = texto;
    const vital = m.equipamento_vital;
    const listas = no('div', { classe: 'listas' },
      ['inteira', 'parte', 'vizinha'].filter(s => g[s].length).map(s => no('p', {},
        no('span', { classe: `etiqueta ${s}`, texto: { inteira: 'Inteiras', parte: 'Em parte', vizinha: 'Vizinhas' }[s] }),
        g[s].map(c => `${homonimo(c) ? nomeComDistrito(c, m) : c.nome}: ${fmt(c.afetadas)}`).join(', '))),
      no('p', { classe: 'ajuda', texto: `Equipamento vital: ${fmt(vital.sim)} sim, ${fmt(vital.nao)} não` + (vital.a_confirmar ? `, ${fmt(vital.a_confirmar)} a confirmar` : '') + '. Depois do nome, UCs afetadas da comunidade.' }));
    return no('article', { classe: 'cartao municipio', 'data-codigo': cod },
      no('div', { classe: 'mun-cab' }, no('h3', { texto: `${m.nome}/${m.uf}` }),
        no('span', { classe: 'meta', texto: `${fmt(m.ucs)} UCs · ${fmt(m.comunidades.length)} comunidades` })),
      listas,
      no('div', { classe: 'bloco-aviso' },
      no('label', { for: area.id, texto: editavel ? 'Aviso para a rádio (pode editar)' : 'Aviso para a rádio' }), area,
      no('p', { classe: 'tempo', id: `tempo-${cod}`, texto: tempoTexto(texto) }),
      no('p', { id: `final-${cod}`, classe: 'ajuda' }),
      no('div', { classe: 'acoes' },
        no('button', { type: 'button', classe: 'prim', 'data-acao': 'pdf', 'data-codigo': cod, texto: 'Baixar PDF para a rádio' }),
        no('button', { type: 'button', 'data-acao': 'copiar', 'data-codigo': cod, texto: 'Copiar texto' }),
        temAudio() && no('button', { type: 'button', 'data-acao': 'ouvir', 'data-codigo': cod, texto: 'Ouvir' }),
        temAudio() && no('button', { type: 'button', 'data-acao': 'audio', 'data-codigo': cod, texto: 'Baixar áudio (MP3)' }),
        editavel && no('button', { type: 'button', 'data-acao': 'restaurar', 'data-codigo': cod, texto: 'Desfazer edição' })),
      no('div', { id: `tocador-${cod}`, classe: 'tocador' }),
      temAudio() ? null : no('p', { classe: 'ajuda', texto: audioLigado() ? 'Áudio só para avisos em português, por enquanto.'
        : 'O áudio do aviso está desligado neste servidor.' })));
  });
  $('municipios').replaceChildren(...cartoes);
  for (const m of estado.resultado.municipios) { desenharFinal(m.codigo_ibge); desenharTocador(m.codigo_ibge); }
}

function desenharFinal(codigo) {
  const f = estado.finais[codigo];
  $(`final-${codigo}`).replaceChildren(...(f ? [no('span', { classe: 'selo final', texto: 'Texto final guardado no histórico' }),
    f !== estado.avisos[codigo] ? ' (o texto mudou depois; baixe o PDF ou copie de novo para guardar)' : ''] : []));
}

function desenharTempo(codigo) {
  $(`tempo-${codigo}`).textContent = tempoTexto(estado.avisos[codigo]);
  desenharFinal(codigo);
  desenharTocador(codigo);
}

// o tocador aparece com o áudio do texto atual; se o texto mudou, some (o áudio antigo não vale mais)
function desenharTocador(codigo) {
  const a = audioAtual(codigo), lugar = $(`tocador-${codigo}`);
  if (!lugar) return;
  if (!a) return lugar.replaceChildren();
  if (lugar.querySelector('audio')?.src === a.url) return;
  lugar.replaceChildren(no('audio', { controls: true, src: a.url, preload: 'auto', 'aria-label': 'Áudio do aviso' }),
    no('span', { classe: 'ajuda', texto: `${fmt(Math.round(a.segundos))} s de áudio (voz sintetizada)` }));
}

function desenharProblemas() {
  const p = estado.resultado.planilha;
  $('problemas').hidden = !p.problemas.length;
  if (!p.problemas.length) return;
  $('problemasTitulo').textContent = `${fmt(p.total_problemas)} linha(s) com problema`;
  const motivos = no('ul', {}, Object.entries(p.problemas_por_motivo).map(([m, n]) => no('li', { texto: `${m}: ${fmt(n)}` })));
  const tabela = no('table', {}, no('thead', {}, no('tr', {}, no('th', { texto: 'Linha' }), no('th', { texto: 'Problema' }))),
    no('tbody', {}, p.problemas.map(x => no('tr', {}, no('td', { texto: String(x.linha) }), no('td', { texto: x.motivo })))));
  $('problemasCorpo').replaceChildren(motivos, tabela,
    p.total_problemas > p.problemas.length ? no('p', { classe: 'ajuda', texto: `Mostrando as primeiras ${fmt(p.problemas.length)}.` }) : '');
}

function desenharResultado() {
  desenharAbas();
  if (!estado.resultado) return;
  const r = estado.resultado, f = estado.formulario;
  $('tituloResultado').textContent = estado.origem === 'historico'
    ? `Aviso de ${f.data}, ${f.horario} · gerado em ${dataHora(r.criado_em)}${r.usuario ? ' por ' + r.usuario : ''}`
    : tituloResultado();
  desenharResumo(); desenharMunicipios(); desenharProblemas(); desenharComparativo();
}

function tituloResultado() {
  const f = estado.formulario;
  return `${estado.passo === 4 ? 'Avisos para a rádio' : 'Conferir o resultado'} · ${f.data}, ${f.horario}`;
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
          : no('span', { classe: 'chip vazio', texto: 'nenhum município' })),
        no('span', { classe: 'meta', texto: `${fmt(ucs)} UCs · ${fmt(com)} comunidades · cerca de ${fmt(seg)} s no ar` }),
        no('span', { classe: 'meta', texto: `Gerado em ${dataHora(a.criado_em)}${a.usuario ? ' por ' + a.usuario : ''} · aviso nº ${a.id}` }),
        a.municipios.some(m => m.texto_final) ? no('span', { classe: 'selo final', texto: 'Texto final guardado' }) : null));
  });
  const total = estado.historico.length;
  $('contagemHistorico').textContent = total ? (lista.length === total ? `${fmt(total)} aviso(s).` : `${fmt(lista.length)} de ${fmt(total)} aviso(s).`) : '';
  $('listaHistorico').replaceChildren(...(itens.length ? itens
    : [no('p', { classe: 'ajuda', texto: total ? 'Nenhum aviso com esse filtro.' : 'Nenhum aviso gerado ainda.' })]));
}

// ---- Comparativo: o aviso de hoje (fazenda a fazenda) x o aviso por comunidade ----
function desenharComparativo() {
  const c = estado.painel?.comparativo;
  $('comparativoTotal').replaceChildren(...(c && c.municipios ? [no('div', { classe: 'cartao comp-total' },
    no('h2', { texto: 'Em todo o histórico da empresa' }),
    no('p', { texto: `${fmt(c.municipios)} aviso(s) por município com o aviso de hoje: ${tempoNoAr(c.segundos_hoje)} no ar fazenda a fazenda `
      + `(${fmt(c.locais)} locais citados) contra ${tempoNoAr(c.segundos_farol)} por comunidade (${fmt(c.comunidades)} comunidades).` }),
    no('p', { classe: 'comp-economia', texto: `${fmt(Math.round(100 * (1 - c.segundos_farol / Math.max(1, c.segundos_hoje))))}% menos tempo no ar` }))] : []));
  const r = estado.resultado;
  if (!r) return $('comparativo').replaceChildren(no('p', { classe: 'ajuda cartao',
    texto: 'Gere um aviso em "Novo aviso" (com a coluna local na planilha) ou abra um aviso do Histórico para comparar.' }));
  $('comparativo').replaceChildren(...r.municipios.map(m => {
    const cod = m.codigo_ibge, hoje = m.hoje, texto = estado.avisos[cod], seg = segundos(texto);
    const lado = (classe, titulo, numeros, corpo, acao) => no('section', { classe: `comp-lado ${classe}` },
      no('h3', { texto: titulo }), no('p', { classe: 'comp-numeros', texto: numeros }), corpo,
      acao && temAudio() ? no('button', { type: 'button', 'data-comp': acao, 'data-codigo': cod, texto: 'Ouvir' }) : null,
      acao ? no('div', { id: `tocador-${acao}-${cod}`, classe: 'tocador' }) : null);
    const caixa = t => no('div', { classe: 'texto-longo', tabindex: '0', texto: t });
    const ladoHoje = hoje
      ? lado('hoje', 'Hoje: fazenda a fazenda', `${fmt(hoje.locais)} locais · ${fmt(hoje.palavras)} palavras · cerca de ${tempoNoAr(hoje.segundos)} no ar`,
        hoje.texto ? caixa(hoje.texto) : no('p', { classe: 'ajuda', texto: 'O histórico guarda só as contagens do aviso de hoje (o texto lista imóveis e ruas).' }),
        hoje.texto ? 'hoje' : null)
      : lado('hoje', 'Hoje: fazenda a fazenda', 'sem o aviso de hoje',
        no('p', { classe: 'ajuda', texto: 'A planilha não trouxe a coluna local (o que o aviso de hoje cita para cada UC: o imóvel no rural, a rua no urbano). Sem ela não dá para montar o aviso de hoje.' }), null);
    const ladoFarol = lado('farol', 'Farol: por comunidade', `${fmt(m.comunidades.length)} comunidades · ${fmt(palavras(texto))} palavras · cerca de ${tempoNoAr(seg)} no ar`,
      caixa(texto), 'farol');
    const barras = hoje ? no('div', { classe: 'comp-barras', role: 'img', 'aria-label': `Hoje ${tempoNoAr(hoje.segundos)}, Farol ${tempoNoAr(seg)}` },
      no('span', { classe: 'comp-rotulo', texto: 'Hoje' }), no('span', { classe: 'comp-barra hoje' }, no('span', { estilo: { width: '100%' } })),
      no('span', { classe: 'comp-tempo', texto: tempoNoAr(hoje.segundos) }),
      no('span', { classe: 'comp-rotulo', texto: 'Farol' }),
      no('span', { classe: 'comp-barra farol' }, no('span', { estilo: { width: `${Math.max(1, Math.round(100 * seg / Math.max(1, hoje.segundos)))}%` } })),
      no('span', { classe: 'comp-tempo', texto: tempoNoAr(seg) })) : null;
    return no('article', { classe: 'cartao comp', 'data-codigo': cod },
      no('div', { classe: 'mun-cab' }, no('h2', { texto: `${m.nome}/${m.uf}` }),
        hoje ? no('span', { classe: 'comp-economia', texto: `${fmt(Math.round(100 * (1 - seg / Math.max(1, hoje.segundos))))}% menos tempo no ar` }) : null),
      barras, no('div', { classe: 'comp-lados' }, ladoHoje, ladoFarol));
  }));
}

// ---- Dashboard: só números do histórico da empresa ----
function desenharPainel() {
  const d = estado.painel;
  if (!d) return $('painelDash').replaceChildren();
  const t = d.totais;
  const kpi = (rotulo, valor, extra) => no('div', { classe: 'kpi' }, no('span', { classe: 'kpi-rotulo', texto: rotulo }),
    no('strong', { classe: 'kpi-valor', texto: valor }), extra ? no('span', { classe: 'kpi-extra', texto: extra }) : null);
  const kpis = no('div', { classe: 'kpis' },
    kpi('Avisos gerados', fmt(t.avisos), `${fmt(t.ultimos_30_dias)} nos últimos 30 dias`),
    kpi('UCs avisadas', fmt(t.ucs)),
    kpi('Comunidades citadas', fmt(t.comunidades)),
    kpi('Municípios', fmt(t.municipios)),
    kpi('Com equipamento vital', fmt(t.com_equipamento_vital), 'avisos com prazo de 5 dias úteis'),
    kpi('Tempo médio no ar', `${fmt(t.segundos_medio)} s`, `${fmt(t.textos_finais)} de ${fmt(t.avisos_municipio)} textos finais guardados`));
  const maxMes = Math.max(1, ...d.por_mes.map(m => m.avisos));
  const meses = no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: 'Avisos por mês' }),
    no('div', { classe: 'barras', role: 'img', 'aria-label': d.por_mes.map(m => `${MES_CURTO(m.mes)}: ${m.avisos}`).join(', ') },
      d.por_mes.map(m => no('div', { classe: 'barra-mes', title: `${MES_CURTO(m.mes)}: ${fmt(m.avisos)} aviso(s), ${fmt(m.ucs)} UCs` },
        no('span', { classe: 'barra-valor', texto: m.avisos ? fmt(m.avisos) : '' }),
        no('span', { classe: 'barra', estilo: { height: `${Math.round(m.avisos / maxMes * 100)}%` } }),
        no('span', { classe: 'barra-mes-rotulo', texto: MES_CURTO(m.mes) })))));
  const ranking = (titulo, itens, rotulo, vazio) => {
    const max = Math.max(1, ...itens.map(i => i.avisos));
    return no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: titulo }),
      itens.length ? no('ol', { classe: 'ranking' }, itens.map(i => no('li', {},
        no('span', { classe: 'ranking-nome', texto: rotulo(i) }),
        no('span', { classe: 'ranking-barra' }, no('span', { estilo: { width: `${Math.round(i.avisos / max * 100)}%` } })),
        no('span', { classe: 'ranking-valor', texto: `${fmt(i.avisos)} · ${fmt(i.ucs)} UCs` }))))
        : no('p', { classe: 'ajuda', texto: vazio }));
  };
  const proximos = no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: 'Próximos desligamentos' }),
    d.proximos.length ? no('ul', { classe: 'proximos' }, d.proximos.map(x => no('li', {},
      no('span', { classe: 'chip', texto: dataLonga(x.data) }),
      no('span', { texto: `${x.horario} · ${x.municipios.join(', ') || 'nenhum município'} · ${fmt(x.ucs)} UCs` }))))
      : no('p', { classe: 'ajuda', texto: 'Nenhum desligamento com data a partir de hoje.' }));
  $('painelDash').replaceChildren(kpis, meses, proximos,
    ranking('Municípios com mais avisos', d.municipios, i => `${i.nome}/${i.uf}`, 'Nenhum aviso ainda.'),
    ranking('Comunidades mais citadas', d.comunidades, i => `${semSufixo(i.nome)} (${i.municipio})`, 'Nenhum aviso ainda.'));
}

function desenharUsuarios() {
  $('novoPerfil').replaceChildren(...Object.entries(estado.perfis).map(([k, n]) => no('option', { value: k, texto: n, selected: k === 'operador' })));
  $('listaUsuarios').replaceChildren(...estado.usuarios.map(x => no('div', { classe: 'item usuario-linha', 'data-usuario': x.id },
    no('div', {}, no('strong', { texto: x.nome }), no('br'),
      no('span', { classe: 'meta', texto: `${x.email} · ${x.ultimo_acesso ? 'último acesso ' + dataHora(x.ultimo_acesso) : 'nunca entrou'}`
        + (x.trocar_senha ? ' · senha temporária' : '') })),
    no('div', { classe: 'controles' },
      no('select', { 'aria-label': `Perfil de ${x.nome}`, 'data-campo': 'perfil' },
        Object.entries(estado.perfis).map(([k, n]) => no('option', { value: k, texto: n, selected: k === x.perfil }))),
      no('select', { 'aria-label': `Situação de ${x.nome}`, 'data-campo': 'status' },
        [['ativo', 'Ativo'], ['bloqueado', 'Bloqueado']].map(([k, n]) => no('option', { value: k, texto: n, selected: k === x.status }))),
      no('button', { type: 'button', 'data-acao-usuario': 'salvar', texto: 'Salvar' }),
      no('button', { type: 'button', 'data-acao-usuario': 'senha', texto: 'Nova senha temporária' })))));
}

function desenharEmpresas() {
  const linhas = estado.empresas.map(e => no('tr', {}, no('td', { texto: e.nome }), no('td', { texto: e.sigla }), no('td', { texto: e.dominio }),
    no('td', { texto: e.status }), no('td', { texto: fmt(e.usuarios) }), no('td', { texto: fmt(e.avisos) })));
  $('listaEmpresas').replaceChildren(no('table', { classe: 'tabela' },
    no('thead', {}, no('tr', {}, ['Empresa', 'Sigla', 'Domínio', 'Situação', 'Usuários', 'Avisos'].map(t => no('th', { texto: t })))),
    no('tbody', {}, linhas)));
}

function desenharRegistro() {
  const linhas = estado.registro.map(r => no('tr', {}, no('td', { texto: dataHora(r.quando) }), no('td', { texto: r.usuario || '—' }),
    no('td', { texto: r.empresa || '—' }), no('td', { texto: r.acao }), no('td', { texto: r.detalhe })));
  $('listaRegistro').replaceChildren(no('table', { classe: 'tabela' },
    no('thead', {}, no('tr', {}, ['Quando', 'Quem', 'Empresa', 'O quê', 'Detalhe'].map(t => no('th', { texto: t })))),
    no('tbody', {}, linhas)));
}

function mostrarSenhaTemporaria(texto, senha) {
  $('caixaTexto').textContent = texto;
  $('caixaSenhaValor').textContent = senha;
  $('caixaSenha').hidden = false;
  $('caixaFechar').focus();
}

// ---- Mapa ----
// o mapa é sempre escuro (fundo da Esri); as cores do contorno e dos nomes foram escolhidas para ele
const COR = { ambar: '#F5B83D', ambarForte: '#FFD27A', cinza: '#93A1AF', info: '#5AA9FF', erro: '#B42318', verde: '#1B8A8A' };
let mapa, camadaConcessao, camadaComunidades, camadaUcs, telaUcs, camadaBase, camadaNomes, camadaCidades, caixasNomes = [], camadaRede, telaRede, atribuicao;
// a partir deste zoom, o contorno das comunidades dos municípios na tela; a partir do outro, os nomes escritos
const ZOOM_COMUNIDADES = 11, ZOOM_NOMES = 13, ZOOM_TRAFOS = 14, ZOOM_NOMES_AFETADAS = 10;
const ZOOM_CIDADES = [6, 12];   // faixa de zoom em que o nome de cada cidade da concessão aparece
const CREDITO_REDE = 'Rede fictícia sobre as vias do © OpenStreetMap';
const CORES_ALIMENTADOR = ['#1663C7', '#7A4FD1', '#0F8F86', '#C2410C', '#9D174D', '#4D7C0F', '#0E7490', '#A16207'];
const buscando = new Set();   // municípios cujas comunidades estão sendo buscadas

function iniciarMapa() {
  if (mapa) return;
  mapa = L.map('mapa', { zoomControl: true, attributionControl: false, minZoom: 5, maxZoom: 16 });
  atribuicao = L.control.attribution({ prefix: 'Concessão e comunidades: IBGE · Leaflet' }).addTo(mapa);
  L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    { attribution: 'Fundo &copy; Esri', maxZoom: 16, noWrap: true }).addTo(mapa);
  mapa.setView([-21.0, -42.6], 8);
  mapa.on('moveend', aoMoverMapa);
  mapa.on('click', () => { if (estado.evidencia) { estado.evidencia = null; aplicarEvidencia(); } });
}

// comunidade em evidência (clique): borda branca grossa e as demais mais apagadas
const chaveComunidade = f => `${f.properties.m?.nome ?? f.properties.municipio}|${f.properties.nome}|${f.properties.distrito}`;
function comEvidencia(estilo, f) {
  if (!estado.evidencia) return estilo;
  if (estado.evidencia.chave === chaveComunidade(f))
    return { ...estilo, color: '#FFFFFF', weight: 3.5, opacity: 1, dashArray: null, fillColor: estilo.fillColor || COR.ambar, fillOpacity: Math.max(estilo.fillOpacity || 0, .3) };
  return { ...estilo, opacity: (estilo.opacity ?? 1) * .5, fillOpacity: (estilo.fillOpacity || 0) * .5 };
}

const estiloBase = f => comEvidencia({ color: COR.cinza, weight: .5, opacity: .3, fillOpacity: 0 }, f);
const estiloAviso = f => comEvidencia(!f.properties.c ? { color: COR.cinza, weight: .5, opacity: .3, fillOpacity: 0 } : ({
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
const distritoDe = (distrito, municipio) => distrito === municipio ? 'Sede' : distrito;

// comunidades dos municípios na tela, fora os do aviso (esses a desenharComunidades destaca)
function desenharBase() {
  camadaBase?.remove();
  camadaBase = null;
  if (!mapa || mapa.getZoom() < ZOOM_COMUNIDADES) return;
  const doAviso = new Set((estado.resultado?.municipios || []).map(m => m.codigo_ibge));
  const feicoes = municipiosNaTela().filter(m => !doAviso.has(m.codigo_ibge) && estado.territorios[m.codigo_ibge])
    .flatMap(m => estado.territorios[m.codigo_ibge].features.map(f => ({ ...f, properties: { ...f.properties, municipio: m.nome } })));
  if (!feicoes.length) return;
  camadaBase = L.geoJSON({ type: 'FeatureCollection', features: feicoes }, {
    style: estiloBase,
    onEachFeature: (f, l) => {
      l.bindTooltip(() => no('span', {
        texto: `${semSufixo(f.properties.nome)} (${distritoDe(f.properties.distrito, f.properties.municipio)}) · ${f.properties.municipio}` }), { sticky: true });
      l.on('click', e => evidenciar(e, l));
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

// rede elétrica FICTÍCIA dos municípios na tela (de perto): média tensão por alimentador, subestação,
// chaves e, mais de perto, os trafos. Só demonstração; nada de cliente.
function desenharRede() {
  camadaRede?.remove();
  camadaRede = null;
  const botao = $('botaoRede');
  botao.textContent = estado.verRede ? 'Esconder rede fictícia' : 'Mostrar rede fictícia';
  botao.setAttribute('aria-pressed', String(estado.verRede));
  $('legendaRede').hidden = !estado.verRede;
  atribuicao?.removeAttribution(CREDITO_REDE);
  if (!mapa || !estado.verRede || mapa.getZoom() < ZOOM_COMUNIDADES) return;
  telaRede ||= L.canvas({ padding: .3 });
  const partes = [];
  for (const m of municipiosNaTela()) {
    const r = estado.redes[m.codigo_ibge];
    if (!r) continue;
    const cor = a => CORES_ALIMENTADOR[(parseInt(a.split('-').pop(), 10) - 1) % CORES_ALIMENTADOR.length] || COR.info;
    partes.push(L.geoJSON(r.alimentadores, {
      style: f => ({ color: cor(f.properties.alimentador), weight: 2.2, opacity: .9 }),
      onEachFeature: (f, l) => l.bindTooltip(() => no('span', { texto: `Alimentador ${f.properties.alimentador} (fictício) · ${m.nome}` }), { sticky: true }),
    }));
    if (mapa.getZoom() >= ZOOM_TRAFOS)
      for (const [lat, lon] of r.trafos)
        partes.push(L.circleMarker([lat, lon], { renderer: telaRede, radius: 2.5, weight: 0, fillColor: COR.cinza, fillOpacity: .9, interactive: false }));
    for (const [lat, lon, codigo, alim, jusante] of r.chaves)
      partes.push(L.circleMarker([lat, lon], { radius: 4.5, weight: 1.5, color: '#FFFFFF', fillColor: cor(alim), fillOpacity: 1 })
        .bindTooltip(() => no('span', { texto: `Chave ${codigo} (fictícia) · alimentador ${alim} · ${fmt(jusante)} unidades a jusante` })));
    const se = r.subestacao;
    partes.push(L.marker(se.ponto, { keyboard: false, icon: L.divIcon({ className: 'subestacao', html: no('span'), iconSize: [16, 16] }) })
      .bindTooltip(() => no('span', { texto: se.nome })));
  }
  if (!partes.length) return;
  camadaRede = L.layerGroup(partes).addTo(mapa);
  atribuicao.addAttribution(CREDITO_REDE);
}

function desenharLegenda() {
  const min = estado.legendaMinimizada;
  $('legenda').classList.toggle('minimizada', min);
  $('botaoLegenda').setAttribute('aria-expanded', String(!min));
  $('botaoLegendaTexto').textContent = min ? 'Legenda' : 'Minimizar legenda';
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
        try { estado.redes[c] = await api(`/api/municipios/${c}/rede`); } catch (e) { if (e.status === 404) estado.redes[c] = null; else throw e; }
      }]);
  }
  await Promise.all(tarefas.map(async ([chave, fazer]) => {
    buscando.add(chave);
    try { await fazer(); } catch (e) { /* tenta de novo no próximo movimento */ }
    buscando.delete(chave);
  }));
}

async function aoMoverMapa() {
  if (mapa.getZoom() >= ZOOM_COMUNIDADES && estado.tela === 'app') await buscarNaTela();
  desenharBase(); desenharNomes(); desenharCidades(); desenharRede();
  document.documentElement.dataset.mapa = `z${mapa.getZoom()}`;
}

async function alternarRede() {
  estado.verRede = !estado.verRede;
  desenharRede();
  if (estado.verRede && mapa.getZoom() >= ZOOM_COMUNIDADES) { await buscarNaTela(); desenharRede(); }
  else if (estado.verRede) avisar('A rede fictícia aparece de perto: aproxime num município (ou clique nele).');
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
        + (contagem ? ` · ${fmt(contagem[f.properties.codigo_ibge] || 0)} aviso(s)` : '') }), { sticky: true });
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
  if (!r) return;
  // as afetadas preenchidas; as outras comunidades dos mesmos municípios só com o contorno, por baixo
  const feicoes = [], outras = [];
  for (const m of r.municipios) {
    const terr = estado.territorios[m.codigo_ibge];
    if (!terr) continue;
    const porNome = new Map(m.comunidades.map(c => [c.nome, c]));
    for (const f of terr.features) {
      const c = porNome.get(f.properties.nome);
      if (c) feicoes.push({ ...f, properties: { ...f.properties, m, c } });
      else outras.push({ ...f, properties: { ...f.properties, municipio: m.nome } });
    }
  }
  if (!feicoes.length) return;
  camadaComunidades = L.geoJSON({ type: 'FeatureCollection', features: [...outras, ...feicoes] }, {
    style: estiloAviso,
    onEachFeature: (f, l) => {
      const { c, m } = f.properties;
      l.on('click', e => evidenciar(e, l));
      if (!c) return l.bindTooltip(() => no('span', { texto: `${semSufixo(f.properties.nome)} · fora do aviso` }), { sticky: true });
      l.bindTooltip(() => no('span', {}, no('strong', { texto: nomeComDistrito(c, m) }), ` · ${ROTULO[situacao(c)]}`, no('br'),
        `${fmt(c.afetadas)} UCs afetadas · ${fmt(c.total)} endereços na comunidade`), { sticky: true });
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
const temPontos = () => !!estado.resultado && (estado.resultado.municipios.some(m => m.pontos?.length) || !!estado.resultado.pontos_fora?.length);

function desenharUcs() {
  camadaUcs?.remove();
  camadaUcs = null;
  const r = estado.resultado, botao = $('botaoUcs');
  botao.closest('li').hidden = !temPontos();
  botao.textContent = estado.verUcs ? 'Esconder UCs' : 'Mostrar UCs';
  botao.setAttribute('aria-pressed', String(estado.verUcs));
  if (!temPontos() || !estado.verUcs) return;
  telaUcs ||= L.canvas({ padding: .3 });
  const ponto = (lat, lon, cor, dica) => L.circleMarker([lat, lon], { renderer: telaUcs, radius: 3.5, weight: 1, color: '#FFFFFF', fillColor: cor, fillOpacity: .95 })
    .bindTooltip(dica);
  const marcas = [];
  for (const m of r.municipios) {
    for (const [lat, lon, i] of m.pontos || []) {
      const c = m.comunidades[i];
      marcas.push(ponto(lat, lon, c && situacao(c) !== 'vizinha' ? COR.ambarForte : COR.cinza,
        c ? `UC da planilha · ${nomeComDistrito(c, m)}` : `UC da planilha · ${m.nome}`));
    }
  }
  for (const [lat, lon] of r.pontos_fora || []) marcas.push(ponto(lat, lon, COR.erro, 'UC fora da concessão'));
  camadaUcs = L.layerGroup(marcas).addTo(mapa);
  if (!camadaComunidades && marcas.length) mapa.fitBounds(L.featureGroup(marcas).getBounds(), { padding: [30, 30], maxZoom: 13 });
}

// ---- Roteiro (PDF) de um município ----
async function desenharRoteiro(codigo) {
  const m = estado.resultado.municipios.find(x => x.codigo_ibge === codigo);
  const f = estado.formulario, texto = estado.avisos[codigo], g = grupos(m);
  const codigoV = (await codigoVerificacao(texto)).slice(0, 16);
  const lista = (titulo, cs) => cs.length ? [no('h2', { texto: titulo }), no('ul', {}, cs.map(c => no('li', { texto: nomeComDistrito(c, m) })))] : [];
  const agora = new Date();
  $('roteiro').replaceChildren(
    no('div', { classe: 'rt-marca' }, no('img', { src: '/assets/marca/farol.svg', alt: '' }),
      no('div', {}, no('p', { classe: 'rt-nome', texto: 'Farol' }), no('p', { classe: 'rt-slogan', texto: 'Cada comunidade avisada pelo nome' }))),
    no('h1', { texto: 'Roteiro para a rádio' }),
    no('p', { classe: 'rt-meta', texto: `${m.nome}/${m.uf} · desligamento programado em ${f.dataLonga}, das ${f.horario} · ${estado.usuario.empresa || estado.config.distribuidora}` }),
    no('h2', { texto: 'Texto para leitura' }),
    no('p', { classe: 'rt-aviso', texto }),
    no('p', { classe: 'rt-tempo', texto: tempoTexto(texto) }),
    lista('Comunidades inteiras', g.inteira), lista('Parte da comunidade', g.parte),
    g.vizinha.length ? [no('h2', { texto: 'Localidades vizinhas (citadas em conjunto)' }), no('p', { texto: g.vizinha.map(c => nomeComDistrito(c, m)).join(', ') })] : [],
    no('h2', { texto: 'Prazo' }),
    no('p', { texto: `Antecedência mínima: ${estado.resultado.prazo.antecedencia_minima} (${estado.resultado.prazo.norma}).` }),
    no('p', { texto: `Unidades com equipamento vital: ${fmt(m.equipamento_vital.sim)}` + (m.equipamento_vital.a_confirmar ? ` (${fmt(m.equipamento_vital.a_confirmar)} a confirmar)` : '') + '.' }),
    no('div', { classe: 'rt-rodape' },
      no('p', { texto: `Gerado em ${agora.toLocaleDateString('pt-BR')} às ${agora.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`
        + `${estado.resultado.id ? ` · aviso nº ${estado.resultado.id}` : ''} · ${estado.usuario.nome}. Código de verificação do texto (SHA-256): ` },
        no('span', { classe: 'rt-codigo', texto: codigoV })),
      no('p', { texto: estado.resultado.aviso_ficticio })));
}

// ======================= Controller: eventos e chamadas à API (atualiza o estado e redesenha) =======================
class ErroApi extends Error {
  constructor(status, mensagem) { super(mensagem); this.status = status; }
}

async function api(url, opcoes = {}) {
  const r = await fetch(url, { credentials: 'same-origin', ...opcoes,
    headers: opcoes.json ? { 'Content-Type': 'application/json' } : undefined,
    body: opcoes.json ? JSON.stringify(opcoes.json) : opcoes.body });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401 && estado.tela === 'app') { sessaoAcabou(); throw new ErroApi(401, 'A sessão acabou. Entre de novo.'); }
  if (!r.ok) throw new ErroApi(r.status, typeof j.detail === 'string' ? j.detail : 'Não foi possível concluir. Tente de novo.');
  return j;
}

function sessaoAcabou() {
  limparTela();
  estado.tela = 'entrar';
  desenharTela(); desenharEstado();
  mensagemEm('estadoEntrar', 'A sessão acabou. Entre de novo.', true);
}

function avisar(mensagem, erro = false) {
  estado.mensagem = mensagem; estado.erro = erro;
  desenharEstado();
}

async function abrirApp() {
  estado.tela = 'app';
  estado.vista = vistasDoPerfil()[0]?.[0] || 'historico';
  desenharTela(); desenharAbas();
  iniciarMapa();
  mapa.invalidateSize();
  [estado.config, estado.concessao] = await Promise.all([api('/api/config'), api('/api/concessao')]);
  $('faixa').textContent = estado.config.aviso_ficticio;
  $('idioma').replaceChildren(...Object.entries(estado.config.idiomas).map(([k, nome]) => no('option', { value: k, texto: nome })));
  $('idioma').value = estado.config.idioma_padrao;
  desenharConcessao();
  mapa.fitBounds(camadaConcessao.getBounds(), { padding: [20, 20] });
  await irPara(estado.vista);
}

async function aposEntrar(usuario) {
  estado.usuario = usuario;
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
  if (!email || !senha) return mensagemEm('estadoEntrar', 'Informe o e-mail e a senha.', true);
  $('botaoEntrar').disabled = true;
  try {
    const j = await api('/api/entrar', { method: 'POST', json: { email, senha } });
    $('senha').value = '';
    mensagemEm('estadoEntrar', '');
    await aposEntrar(j.usuario);
  } catch (e) {
    mensagemEm('estadoEntrar', e.message, true);
  } finally {
    $('botaoEntrar').disabled = false;
  }
}

async function trocarSenha(evento) {
  evento.preventDefault();
  const atual = $('senhaAtual').value, nova = $('senhaNova').value, problema = validarSenhaNova(nova, $('senhaNova2').value);
  if (problema) return mensagemEm('estadoSenha', problema, true);
  $('botaoSenha').disabled = true;
  try {
    const j = await api('/api/senha', { method: 'POST', json: { atual, nova } });
    for (const id of ['senhaAtual', 'senhaNova', 'senhaNova2']) $(id).value = '';
    mensagemEm('estadoSenha', '');
    await aposEntrar(j.usuario);
  } catch (e) {
    mensagemEm('estadoSenha', e.message, true);
  } finally {
    $('botaoSenha').disabled = false;
  }
}

// ao sair (ou quando a sessão acaba), nada do usuário anterior fica na página: num computador
// compartilhado, quem entra depois não vê resultados, listas nem o roteiro escondidos
function limparTela() {
  Object.assign(estado, { usuario: null, resultado: null, origem: null, avisos: {}, finais: {}, formulario: null, arquivo: null,
    historico: [], usuarios: [], perfis: {}, empresas: [], registro: [], mensagem: '', erro: false,
    passo: 1, painel: null, evidencia: null, filtroHistorico: { busca: '', periodo: '' } });
  for (const id of ['abas', 'resumo', 'municipios', 'problemasCorpo', 'listaHistorico', 'listaUsuarios', 'listaEmpresas', 'listaRegistro', 'roteiro',
    'painelDash', 'contagemHistorico'])
    $(id).replaceChildren();
  $('arquivo').value = '';
  $('buscaHistorico').value = ''; $('periodoHistorico').value = '';
  $('resultado').hidden = true;
  camadaComunidades?.remove();
  camadaComunidades = null;
  camadaUcs?.remove();
  camadaUcs = null;
  $('botaoUcs').closest('li').hidden = true;
  for (const a of [...Object.values(estado.audios), ...Object.values(estado.audiosHoje)]) URL.revokeObjectURL(a.url);
  estado.audios = {}; estado.audiosHoje = {};
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
    if (vista === 'comparativo') { desenharComparativo(); estado.painel = await api('/api/painel'); desenharComparativo(); }
    if (vista === 'usuarios') { const j = await api('/api/usuarios'); estado.usuarios = j.usuarios; estado.perfis = j.perfis; desenharUsuarios(); }
    if (vista === 'empresas') { estado.empresas = (await api('/api/empresas')).empresas; desenharEmpresas(); }
    if (vista === 'registro') { estado.registro = (await api('/api/registro')).registro; desenharRegistro(); }
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
  if (estado.tela === 'app') desenharConcessao();   // no dashboard, o mapa pinta os municípios pelos avisos
  document.documentElement.dataset.farol = 'pronto';
}

// ---- Funil do novo aviso ----
function irParaPasso(n) {
  if (n === 2 && passoMaximo() < 2) return avisar(validarArquivo(estado.arquivo), true);
  if (n > passoMaximo()) return;
  estado.passo = n;
  if (n < 3) avisar('');
  desenharAbas();
  $('vista-aviso').scrollIntoView({ block: 'start' });
}

// começa outro desligamento: tira o resultado do envio anterior da tela e do mapa (o histórico já o guardou)
function novoAviso() {
  if (estado.origem === 'novo') {
    Object.assign(estado, { resultado: null, origem: null, avisos: {}, finais: {}, formulario: null, evidencia: null });
    for (const a of [...Object.values(estado.audios), ...Object.values(estado.audiosHoje)]) URL.revokeObjectURL(a.url);
    estado.audios = {}; estado.audiosHoje = {};
    for (const id of ['resumo', 'municipios', 'problemasCorpo']) $(id).replaceChildren();
    desenharComparativo();
    camadaComunidades?.remove(); camadaComunidades = null;
    desenharUcs(); desenharConcessao(); desenharBase(); desenharNomes();
  }
  estado.arquivo = null;
  $('arquivo').value = '';
  estado.passo = 1;
  avisar('');
  desenharAbas();
}

async function mostrarResultado(resultado, origem, formulario) {
  estado.resultado = resultado; estado.origem = origem; estado.formulario = formulario; estado.evidencia = null;
  estado.avisos = Object.fromEntries(resultado.municipios.map(m => [m.codigo_ibge, m.texto_final || m.aviso]));
  estado.finais = Object.fromEntries(resultado.municipios.filter(m => m.texto_final).map(m => [m.codigo_ibge, m.texto_final]));
  desenharResultado(); desenharConcessao();
  await Promise.all(resultado.municipios.filter(m => !estado.territorios[m.codigo_ibge]).map(async m => {
    estado.territorios[m.codigo_ibge] = await api(`/api/municipios/${m.codigo_ibge}/comunidades`);
  }));
  desenharComunidades(); desenharUcs(); desenharBase(); desenharNomes();
}

async function enviar(evento) {
  evento.preventDefault();
  const form = { arquivo: estado.arquivo, data: $('data').value, inicio: $('inicio').value, fim: $('fim').value, idioma: $('idioma').value };
  const problema = validarFormulario(form);
  if (problema) {
    if (validarArquivo(form.arquivo)) { estado.passo = 1; desenharAbas(); }
    return avisar(problema, true);
  }
  estado.enviando = true;
  avisar('Lendo a planilha e localizando as comunidades…');
  const horario = `${horaTexto(form.inicio)} às ${horaTexto(form.fim)}`;
  const dados = new FormData();
  dados.append('arquivo', form.arquivo);
  dados.append('data', dataTexto(form.data));
  dados.append('horario', horario);
  dados.append('idioma', form.idioma);
  try {
    const j = await api('/api/avisos', { method: 'POST', body: dados });
    const n = j.municipios.length;
    avisar(n ? `Pronto: ${n} município(s), ${fmt(j.municipios.reduce((s, m) => s + m.comunidades.length, 0))} comunidade(s). Guardado no histórico (aviso nº ${j.id}).`
      : 'Nenhuma UC na área de concessão.', !n);
    estado.passo = 3;
    await mostrarResultado(j, 'novo', { data: dataTexto(form.data), dataLonga: dataLonga(form.data), horario, idioma: form.idioma });
    document.documentElement.dataset.farol = 'resultado';
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    estado.enviando = false;
    desenharEstado();
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
    avisar(`Não foi possível guardar o texto final: ${e.message}`, true);
  }
}

async function gerarAudio(codigo, m) {
  if (audioAtual(codigo)) return audioAtual(codigo);
  avisar(`Gerando o áudio de ${m.nome}…`);
  const texto = estado.avisos[codigo];
  const r = await fetch('/api/audio', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto, idioma: estado.formulario.idioma, municipio: m.nome }) });
  if (r.status === 401) { sessaoAcabou(); throw new ErroApi(401, 'A sessão acabou.'); }
  if (!r.ok) throw new ErroApi(r.status, (await r.json().catch(() => ({}))).detail || 'Não foi possível gerar o áudio.');
  if (estado.audios[codigo]) URL.revokeObjectURL(estado.audios[codigo].url);
  estado.audios[codigo] = { texto, url: URL.createObjectURL(await r.blob()), segundos: Number(r.headers.get('X-Duracao-Segundos')) || 0 };
  avisar(`Áudio de ${m.nome} pronto.`);
  desenharTocador(codigo);
  return estado.audios[codigo];
}

// áudio do comparativo: o do Farol é o mesmo de "Avisos"; o de hoje pede o limite maior (é bem mais longo)
async function audioHoje(codigo, m) {
  if (estado.audiosHoje[codigo]) return estado.audiosHoje[codigo];
  avisar(`Gerando o áudio do aviso de hoje de ${m.nome} (é longo: pode levar um tempo)…`);
  const r = await fetch('/api/audio', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto: m.hoje.texto, idioma: 'pt-BR', municipio: m.nome, comparativo: true }) });
  if (r.status === 401) { sessaoAcabou(); throw new ErroApi(401, 'A sessão acabou.'); }
  if (!r.ok) throw new ErroApi(r.status, (await r.json().catch(() => ({}))).detail || 'Não foi possível gerar o áudio.');
  estado.audiosHoje[codigo] = { url: URL.createObjectURL(await r.blob()), segundos: Number(r.headers.get('X-Duracao-Segundos')) || 0 };
  avisar(`Áudio do aviso de hoje de ${m.nome} pronto.`);
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
    lugar.replaceChildren(no('audio', { controls: true, src: a.url, preload: 'auto', 'aria-label': `Áudio do aviso ${b.dataset.comp === 'hoje' ? 'de hoje' : 'do Farol'}` }),
      no('span', { classe: 'ajuda', texto: `${tempoNoAr(Math.round(a.segundos))} de áudio (voz sintetizada)` }));
    lugar.querySelector('audio').play().catch(() => {});
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    b.disabled = false;
  }
}

async function acao(evento) {
  const b = evento.target.closest('button[data-acao]');
  if (!b) return;
  const codigo = b.dataset.codigo, m = estado.resultado.municipios.find(x => x.codigo_ibge === codigo);
  if (b.dataset.acao === 'copiar') {
    try { await navigator.clipboard.writeText(estado.avisos[codigo]); avisar(`Aviso de ${m.nome} copiado.`); }
    catch (e) { avisar('Não foi possível copiar; selecione o texto e use Ctrl+C.', true); }
    await guardarFinal(codigo);
  } else if (b.dataset.acao === 'restaurar') {
    estado.avisos[codigo] = m.aviso;
    $(`aviso-${codigo}`).value = m.aviso;
    desenharTempo(codigo);
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
  } else if (b.dataset.acao === 'pdf') {
    await desenharRoteiro(codigo);
    await guardarFinal(codigo);
    const titulo = document.title;
    document.title = `Farol - aviso ${m.nome} ${estado.formulario.data.replace('/', '-')}`;  // nome sugerido do PDF
    window.print();
    document.title = titulo;
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

async function cadastrarUsuario(evento) {
  evento.preventDefault();
  try {
    const j = await api('/api/usuarios', { method: 'POST', json: { nome: $('novoNome').value, email: $('novoEmail').value, perfil: $('novoPerfil').value } });
    $('novoNome').value = ''; $('novoEmail').value = '';
    mensagemEm('estadoUsuario', `${j.usuario.nome} cadastrado.`);
    mostrarSenhaTemporaria(`Senha temporária de ${j.usuario.nome} (${j.usuario.email}):`, j.senha_temporaria);
    await irPara('usuarios');
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoUsuario', e.message, true);
  }
}

async function acaoUsuario(evento) {
  const b = evento.target.closest('button[data-acao-usuario]');
  if (!b) return;
  const linha = b.closest('[data-usuario]'), id = linha.dataset.usuario, x = estado.usuarios.find(u => String(u.id) === id);
  try {
    if (b.dataset.acaoUsuario === 'salvar') {
      const campo = n => linha.querySelector(`[data-campo="${n}"]`).value;
      await api(`/api/usuarios/${id}`, { method: 'PATCH', json: { perfil: campo('perfil'), status: campo('status') } });
      mensagemEm('estadoUsuario', `${x.nome}: alterações salvas.`);
    } else {
      const j = await api(`/api/usuarios/${id}/senha-temporaria`, { method: 'POST' });
      mostrarSenhaTemporaria(`Nova senha temporária de ${x.nome} (${x.email}). As sessões abertas dele foram encerradas.`, j.senha_temporaria);
    }
    await irPara('usuarios');
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoUsuario', e.message, true);
  }
}

async function cadastrarEmpresa(evento) {
  evento.preventDefault();
  const v = id => $(id).value;
  try {
    const j = await api('/api/empresas', { method: 'POST', json: { nome: v('empNome'), sigla: v('empSigla'), dominio: v('empDominio'),
      admin_nome: v('empAdminNome'), admin_email: v('empAdminEmail') } });
    for (const id of ['empNome', 'empSigla', 'empDominio', 'empAdminNome', 'empAdminEmail']) $(id).value = '';
    mensagemEm('estadoEmpresa', `${j.empresa.nome} cadastrada.`);
    mostrarSenhaTemporaria(`Senha temporária do primeiro admin de ${j.empresa.nome}:`, j.senha_temporaria);
    await irPara('empresas');
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoEmpresa', e.message, true);
  }
}

function arrastar() {
  const z = $('zona');
  for (const ev of ['dragenter', 'dragover']) z.addEventListener(ev, e => { e.preventDefault(); z.classList.add('arrastando'); });
  for (const ev of ['dragleave', 'drop']) z.addEventListener(ev, () => z.classList.remove('arrastando'));
  z.addEventListener('drop', e => { e.preventDefault(); estado.arquivo = e.dataTransfer.files[0] || null; avisar(''); });
}

async function abrir() {
  // data padrão: daqui a 4 dias (acima das 72 h legais)
  const d = new Date(Date.now() + 4 * 864e5);
  $('data').value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  $('formEntrar').addEventListener('submit', entrar);
  $('formSenha').addEventListener('submit', trocarSenha);
  $('sair').addEventListener('click', sair);
  $('abas').addEventListener('click', e => { const b = e.target.closest('button[data-vista]'); if (b) irPara(b.dataset.vista); });
  $('arquivo').addEventListener('change', e => { estado.arquivo = e.target.files[0] || null; avisar(''); });
  $('form').addEventListener('submit', enviar);
  $('botaoUcs').addEventListener('click', () => { estado.verUcs = !estado.verUcs; desenharUcs(); });
  $('botaoRede').addEventListener('click', alternarRede);
  $('botaoLegenda').addEventListener('click', alternarLegenda);
  try { estado.legendaMinimizada = localStorage.getItem('farol.legenda') === 'minimizada'; } catch (e) { /* sem armazenamento */ }
  desenharLegenda();
  $('funil').addEventListener('click', e => { const b = e.target.closest('button[data-passo]'); if (b && !b.disabled) irParaPasso(Number(b.dataset.passo)); });
  $('avancar').addEventListener('click', () => irParaPasso(2));
  $('voltar').addEventListener('click', () => irParaPasso(1));
  $('voltarResultado').addEventListener('click', () => irParaPasso(estado.passo - 1));
  $('avancarResultado').addEventListener('click', () => irParaPasso(4));
  $('novoAviso').addEventListener('click', novoAviso);
  $('verComparativo').addEventListener('click', () => irPara('comparativo'));
  $('comparativo').addEventListener('click', acaoComparativo);
  $('buscaHistorico').addEventListener('input', e => { estado.filtroHistorico.busca = e.target.value; desenharHistorico(); });
  $('periodoHistorico').addEventListener('change', e => { estado.filtroHistorico.periodo = e.target.value; desenharHistorico(); });
  $('municipios').addEventListener('click', acao);
  $('municipios').addEventListener('input', editar);
  $('listaHistorico').addEventListener('click', abrirHistorico);
  $('formUsuario').addEventListener('submit', cadastrarUsuario);
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
