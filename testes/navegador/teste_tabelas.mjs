// Tabelas do painel (Bloco A, 15/10/2026): em todas as telas com tabela (empresas, auditoria, relatórios), com o painel
// de 320, 400, 600 e 640 px (640 = 1280 px com zoom de 200%) e o painel lateral do computador (1280), em pt-BR, en e es:
// nenhum cabeçalho com mais de 2 linhas, nenhuma palavra quebrada no meio, tabela de até 3 colunas sem barra de rolagem,
// a página sem rolagem horizontal, nenhum True/False/None/null na tela; e o "Ampliar painel" (60%, Esc volta, fica no perfil).
// Também os cartões do simulador de economia (sem gasto e preenchido) em 320, 768, 1280 e 640 px (zoom de 200%).
// Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_tabelas.mjs
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
const PLANILHA = join(RAIZ, 'saida', 'planilhas_teste', 'planilha_CF-0066.csv');
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
const J = JSON.stringify;
const ate = (p, expr, ms = 30000) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > ${ms}) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);
const TAMANHOS = [[320, 640], [400, 800], [600, 900], [640, 800], [1280, 800]];
const tamanho = (p, [w, h]) => p.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 1024 });

// o que está errado nas tabelas visíveis (cabeçalho com 3+ linhas, palavra partida, rolagem desnecessária, True/False)
const PROBLEMAS = `(() => {
  const ruins = [];
  for (const tab of document.querySelectorAll('table.tabela')) {
    if (!tab.offsetParent) continue;
    const cartao = getComputedStyle(tab.tHead || tab).position === 'absolute';
    if (!cartao) for (const th of tab.querySelectorAll('thead th')) {
      const cs = getComputedStyle(th), lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.5;
      const h = th.getBoundingClientRect().height - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
      if (h > lh * 2.3) ruins.push('th em ' + Math.round(h / lh) + ' linhas: ' + th.textContent);
    }
    const andar = document.createTreeWalker(tab, NodeFilter.SHOW_TEXT);
    let n, vistos = 0;
    while ((n = andar.nextNode()) && vistos++ < 600) {
      for (const m of n.textContent.matchAll(/[^\\s-]{2,}/g)) {   // a quebra no hífen é permitida
        if (/[0-9a-f]{24,}/i.test(m[0])) continue;   // hash ou código comprido (não é palavra): pode quebrar
        const r = document.createRange(); r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
        const tops = new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top)));
        if (tops.size > 1) { ruins.push('palavra partida: ' + m[0]); break; }
      }
    }
    const rol = tab.closest('.rolagem'), cols = tab.querySelectorAll('thead th').length;
    if (rol && cols <= 3 && rol.scrollWidth > rol.clientWidth + 1) ruins.push('rolagem numa tabela de ' + cols + ' colunas');
  }
  if (document.documentElement.scrollWidth > innerWidth + 1) ruins.push('página com rolagem horizontal');
  const vis = [...document.querySelectorAll('#telaApp .painel *')].filter(e => e.offsetParent && !e.children.length).map(e => e.textContent).join(' ');
  const b = /\\b(True|False|None|null|undefined|NaN)\\b/.exec(vis);
  if (b) ruins.push('na tela: ' + b[0]);
  return [...new Set(ruins)].slice(0, 6);
})()`;

// o que está errado nos cartões do simulador de economia (número em 2 linhas ou maior que o cartão, cartão com mais que o
// dobro da altura de outro, linha da grade com espaço vazio, palavra partida, rolagem horizontal, True/False na tela)
const SIM_PROBLEMAS = `(() => {
  const ruins = [], cs = [...document.querySelectorAll('#simulador .sim-cartao')].filter(c => c.offsetParent);
  if (!cs.length) return ['nenhum cartão'];
  const hs = cs.map(c => c.getBoundingClientRect().height);
  if (Math.max(...hs) > 2 * Math.min(...hs)) ruins.push('cartão com mais que o dobro da altura de outro: ' + hs.map(Math.round).join(','));
  for (const c of cs) {
    const num = c.querySelector('.sim-numero'), vis = num.firstElementChild, st = getComputedStyle(num), sc = getComputedStyle(c);
    const lh = parseFloat(st.lineHeight) || parseFloat(st.fontSize) * 1.2;
    if (vis.getBoundingClientRect().height > lh * 1.5) ruins.push('número em 2+ linhas: ' + vis.textContent);
    if (vis.getBoundingClientRect().width > c.clientWidth - parseFloat(sc.paddingLeft) - parseFloat(sc.paddingRight) + 1) ruins.push('número não cabe: ' + vis.textContent);
    if (!num.title) ruins.push('número sem o valor completo no title');
  }
  for (const g of document.querySelectorAll('#simulador .sim-cartoes')) {
    const linhas = {};
    for (const x of g.children) { const t = Math.round(x.getBoundingClientRect().top); linhas[t] = (linhas[t] || 0) + 1; }
    const n = Object.keys(linhas).sort((a, b) => a - b).map(k => linhas[k]);
    if (n.length > 1 && n[n.length - 1] < n[0]) ruins.push('linha da grade com espaço vazio: ' + n.join(' + '));
  }
  for (const el of document.querySelectorAll('#simulador .sim-cartao, #simulador .sim-destaque, #simulador .sim-gasto')) {
    const andar = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let t;
    while ((t = andar.nextNode())) {
      if (t.parentElement.closest('.visualmente-oculto, input, select')) continue;
      for (const m of t.textContent.matchAll(/[^\\s\\-–]{2,}/g)) {
        const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length);
        if (new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top))).size > 1) { ruins.push('palavra partida: ' + m[0]); break; }
      }
    }
  }
  if (document.documentElement.scrollWidth > innerWidth + 1) ruins.push('página com rolagem horizontal');
  const vis = [...document.querySelectorAll('#vista-simulador *')].filter(e => e.offsetParent && !e.children.length).map(e => e.textContent).join(' ');
  const b = /\\b(True|False|None|null|undefined|NaN)\\b/.exec(vis);
  if (b) ruins.push('na tela: ' + b[0]);
  return [...new Set(ruins)].slice(0, 6);
})()`;
// 320, 768 e 1280 px, e 640 (1280 px com zoom de 200%)
const TAMANHOS_SIM = [[320, 640], [768, 1024], [1280, 800], [640, 800]];

async function entrar(p, email) {
  await p.avaliar(`($('email').value = ${J(email)}, $('senha').value = ${J(SENHAS[email])}, $('formEntrar').requestSubmit(), 0)`);
  await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto' && estado.concessao && estado.config`, 60000);
  await espera(400);
}
async function ir(p, vista) { await p.avaliar(`irPara('${vista}').then(() => 0)`); await espera(500); }
async function relatorioDaAuditoria(p) {
  await ir(p, 'registro');
  await p.avaliar(`(document.querySelector('#formAuditoria [data-aud="tela"]').click(), 0)`);
  await ate(p, `$('docAuditoria').children.length`);
}
// as telas com tabela de cada perfil: [nome, como abrir]
const TELAS = {
  'admin@farol.example': [['empresas', p => ir(p, 'empresas')], ['auditoria (lista)', p => ir(p, 'registro')], ['auditoria geral (relatório)', relatorioDaAuditoria]],
  'admin@emg.example': [['auditoria (lista)', p => ir(p, 'registro')], ['auditoria (relatório)', relatorioDaAuditoria],
    ...['mensal', 'custos', 'comunidades', 'prazos'].map(q => [`relatório ${q}`, async p => {
      await ir(p, 'relatorios');
      await p.avaliar(`($('relQual').value = '${q}', $('relQual').dispatchEvent(new Event('change', { bubbles: true })), $('formRelatorio').requestSubmit(), 0)`);
      await ate(p, `$('relatorio').children.length && !document.querySelector('#formRelatorio [aria-busy="true"]')`);
      await espera(300);
    }])],
};

for (const [email, telas] of Object.entries(TELAS)) {
  const p = await abrir(`${BASE}/`, { largura: 1280, altura: 800 });
  await entrar(p, email);
  if (email === 'admin@emg.example') {
    // um aviso, para os relatórios terem linhas
    const csv = readFileSync(PLANILHA, 'utf8').split('\n').slice(0, 60).join('\n');
    const g = await p.avaliar(`(async () => { const fd = new FormData(); fd.append('arquivo', new Blob([${J(csv)}], { type: 'text/csv' }), 'p.csv');
      fd.append('data', '12/11'); fd.append('horario', '8h');
      const c = await (await fetch('/api/planilha', { method: 'POST', body: fd })).json();
      const r = await fetch('/api/avisos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pacote: c.pacote, data: '12/11', horario: '8h', conferi: true }) });
      return r.status; })()`);
    conferir('um aviso gerado para os relatórios terem linhas', g === 200, String(g));
  }
  const ruins = {};
  for (const idioma of ['pt-BR', 'en', 'es']) {
    await p.avaliar(`trocarIdioma('${idioma}', false).then(() => 0)`);
    for (const t of TAMANHOS) {
      await tamanho(p, t);
      for (const [nome, abrirTela] of telas) {
        await abrirTela(p);
        const r = await p.avaliar(PROBLEMAS);
        if (r.length) ruins[`${idioma} ${t[0]}px ${nome}`] = r;
      }
    }
  }
  const n = Object.keys(ruins).length;
  conferir(`${email.split('@')[0]}: ${telas.length} telas x 5 larguras x 3 idiomas sem cabeçalho em 3+ linhas, palavra partida, rolagem desnecessária nem True/False`,
    !n, J(Object.entries(ruins).slice(0, 5)));
  if (email === 'admin@farol.example') {
    await p.avaliar(`trocarIdioma('pt-BR', false).then(() => 0)`);
    await tamanho(p, [1280, 800]);
    await ir(p, 'registro');
    conferir('painel lateral do computador: as tabelas viram cartões (rótulo: valor)', await p.avaliar(`(() => { const td = document.querySelector('#listaRegistro tbody td[data-rotulo]');
      return td && getComputedStyle(td).display === 'grid' && getComputedStyle(td, '::before').content.includes(td.dataset.rotulo); })()`));
    conferir('"Quem": o nome em cima e o perfil embaixo, menor (sem "Admin do Norte (Admin do Norte)")', await p.avaliar(`(() => {
      const qs = [...document.querySelectorAll('#listaRegistro .quem')];
      return qs.length > 0 && qs.every(q => !q.textContent.includes('(')) && qs.some(q => q.querySelector('small')); })()`),
      await p.avaliar(`[...document.querySelectorAll('#listaRegistro .quem')].slice(0, 3).map(q => q.outerHTML).join(' ')`));
    conferir('data curta ("15/10 14:59") com a completa no title e no aria-label', await p.avaliar(`(() => { const t = document.querySelector('#listaRegistro time');
      return t && /^\\d{2}\\/\\d{2} \\d{2}:\\d{2}$/.test(t.textContent) && t.title.length > t.textContent.length && t.getAttribute('aria-label') === t.title; })()`),
      await p.avaliar(`document.querySelector('#listaRegistro time')?.outerHTML`));
    await relatorioDaAuditoria(p);
    conferir('com o relatório filtrado na tela, a lista sem filtro fica escondida (e um botão a traz de volta)', await p.avaliar(`$('listaRegistro').hidden && !!$('verUltimas')`));
    await p.avaliar(`($('verUltimas').click(), 0)`);
    conferir('"Ver as últimas ações (sem filtro)" mostra a lista com esse título', await p.avaliar(`!$('listaRegistro').hidden && $('listaRegistro').querySelector('h2').textContent === 'Últimas ações (sem filtro)'`));
    // Ampliar painel: ~60% da tela, Esc volta, fica no perfil
    const largura = () => p.avaliar(`Math.round(document.querySelector('.painel').getBoundingClientRect().width)`);
    const antes = await largura();
    await p.avaliar(`($('botaoAmpliar').click(), 0)`);
    await espera(300);
    const amplo = await largura();
    conferir('"Ampliar painel": o painel com ~60% da tela (aria-pressed)', amplo >= 0.55 * 1280 && amplo <= 0.65 * 1280
      && await p.avaliar(`$('botaoAmpliar').getAttribute('aria-pressed') === 'true'`), `${antes} -> ${amplo}`);
    conferir('painel ampliado: as tabelas voltam a ser tabelas (largura suficiente)', await p.avaliar(`getComputedStyle(document.querySelector('#listaRegistro tbody tr')).display === 'table-row'`));
    conferir('painel ampliado: nada partido nem rolagem desnecessária', !(await p.avaliar(PROBLEMAS)).length, J(await p.avaliar(PROBLEMAS)));
    const carregou = p.uma('Page.loadEventFired');
    await p.send('Page.reload');
    await carregou;
    await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto'`, 60000);
    conferir('o painel ampliado fica no perfil (continua depois de recarregar)', await p.avaliar(`estado.painelAmplo && $('telaApp').classList.contains('amplo')`));
    await p.avaliar(`document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))`);
    await espera(300);
    conferir('Esc volta ao painel normal', !(await p.avaliar(`estado.painelAmplo`)) && await largura() <= antes + 2);
    conferir('só o painel rola: a página não rola e o cabeçalho fica no lugar', await p.avaliar(`(() => document.documentElement.scrollHeight <= innerHeight + 1 && getComputedStyle(document.body).overflow === 'hidden'
      && document.querySelector('.topo').getBoundingClientRect().top === 0)()`));
  }
  if (email === 'admin@emg.example') {
    // simulador de economia: sem o gasto (bloco de destaque com os campos e "Calcular") e depois de preenchido (cartões completos)
    const olhar = async nome => {
      const ruins = {};
      for (const idioma of ['pt-BR', 'en', 'es']) {
        await p.avaliar(`trocarIdioma('${idioma}', false).then(() => 0)`);
        for (const t of TAMANHOS_SIM) {
          await tamanho(p, t); await ir(p, 'simulador');
          const r = await p.avaliar(SIM_PROBLEMAS);
          if (r.length) ruins[`${idioma} ${t[0]}px`] = r;
        }
      }
      await p.avaliar(`trocarIdioma('pt-BR', false).then(() => 0)`); await tamanho(p, [1280, 800]); await ir(p, 'simulador');
      conferir(`simulador ${nome}: 4 larguras x 3 idiomas, número numa linha e cabendo, cartões de altura parecida, grade sem buraco, nada partido`,
        !Object.keys(ruins).length, J(Object.entries(ruins).slice(0, 4)));
    };
    await tamanho(p, [1280, 800]); await ir(p, 'simulador');
    conferir('simulador sem gasto: um bloco "Informe o gasto…" com os campos e o botão Calcular; nenhum cartão de economia', await p.avaliar(`!!$('simDestaque')
      && $('simDestaque').contains($('formSimulador')) && !$('formSimulador').hidden && $('simSalvar').textContent === 'Calcular'
      && document.querySelectorAll('#simulador .sim-cartao').length === 3 && !/—/.test($('simulador').textContent)`),
      await p.avaliar(`$('simulador').innerText.slice(0, 300)`));
    await olhar('sem gasto');
    await p.avaliar(`($('simGastoMin').value = '160000', $('simGastoMax').value = '300000', $('simPct').value = '100',
      $('simNota').value = 'valores de teste', $('formSimulador').requestSubmit(), 0)`);
    await ate(p, `estado.simulador?.documento.numeros.estimativa && !document.querySelector('#formSimulador [aria-busy="true"]')`);
    await espera(300);
    conferir('simulador preenchido: Estimativa (4 cartões) e Realizado (2), o formulário depois dos cartões com "Salvar"', await p.avaliar(`(() => {
      const g = [...document.querySelectorAll('#simulador .sim-grupo')];
      return g.length === 2 && g[0].querySelectorAll('.sim-cartao').length === 4 && g[1].querySelectorAll('.sim-cartao').length === 2
        && !$('simDestaque') && $('simSalvar').textContent === 'Salvar' && g[1].nextElementSibling === $('formSimulador'); })()`),
      await p.avaliar(`$('simulador').innerText.slice(0, 400)`));
    // os valores dependem da redução real (o aviso gerado acima): a faixa anual passa de 1 milhão ("mi") e a mensal fica em "mil"
    conferir('moeda curta no cartão ("R$ 0,82–1,54 mi", "R$ 69–129 mil") com o valor completo no title e para o leitor de tela', await p.avaliar(`(() => {
      const ns = [...document.querySelectorAll('#simulador .sim-numero')].filter(x => / a R\\$\\s/.test(x.title));   // o title vem do toLocaleString (espaço não separável depois do R$)
      return ns.length === 3 && ns.every(n => /^R\\$\\s[\\d,]+–[\\d,]+ (mi|mil)$/.test(n.firstElementChild.textContent)
        && n.firstElementChild.getAttribute('aria-hidden') === 'true' && n.querySelector('.visualmente-oculto').textContent === n.title)
        && ns.some(n => n.firstElementChild.textContent.endsWith(' mi')); })()`),
      await p.avaliar(`[...document.querySelectorAll('#simulador .sim-numero')].map(x => x.firstElementChild.textContent + ' | ' + x.title).join(' ; ')`));
    conferir('a legenda da redução diz de onde ela vem, em texto curto', await p.avaliar(`/^(média real de \\d+ avisos? da empresa|medição de validação \\(Leopoldina\\))$/.test(
      document.querySelector('#simulador .sim-cartao.destaque .sim-legenda').textContent)`), await p.avaliar(`document.querySelector('#simulador .sim-cartao.destaque')?.innerText`));
    await olhar('preenchido');
  }
  conferir(`${email.split('@')[0]}: nenhuma exceção`, !p.excecoes.length, J(p.excecoes.slice(0, 3)));
  await p.fechar();
}

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
