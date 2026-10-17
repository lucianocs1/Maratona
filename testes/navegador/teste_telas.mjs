// Qualquer tela (Fase I1): sem rolagem horizontal da página do celular pequeno (320 px, o mesmo que 400% de zoom em
// 1280 px) às telas grandes, em todas as vistas; botão "Menu" (aria-expanded) no celular e no tablet; tabelas em cartões
// no celular; janela em tela cheia com o Fechar à vista; alvos de 48 px no toque; impressão sem menus nem mapa;
// manifest do app instalável e nenhum service worker.
// Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_telas.mjs
import { abrir } from './cdp.mjs';

const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
const ate = (p, expr, ms = 30000) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > ${ms}) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);
const TAMANHOS = [[320, 640], [360, 640], [390, 844], [768, 1024], [1024, 768], [1280, 800], [1920, 1080]];
const SEM_ROLAGEM = 'document.documentElement.scrollWidth <= innerWidth';
const visivel = id => `(() => { const e = $('${id}'); return !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0; })()`;
const tamanho = (p, [w, h]) => p.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 1024 });

async function entrar(p, email) {
  await p.avaliar(`($('email').value = ${JSON.stringify(email)}, $('senha').value = ${JSON.stringify(SENHAS[email])}, $('formEntrar').requestSubmit(), 0)`);
  await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto'`, 60000);
}

// ---------- 1. Admin da empresa: todas as vistas em todos os tamanhos ----------
{
  const p = await abrir(`${BASE}/`, { largura: 320, altura: 640 });
  await tamanho(p, [320, 640]);
  conferir('320 px: tela de entrar sem rolagem horizontal', await p.avaliar(SEM_ROLAGEM));
  await entrar(p, 'admin@emg.example');
  const vistas = await p.avaliar(`vistasDoPerfil().map(([v]) => v).concat(RELATORIOS.map(([v]) => v)).filter((v, i, a) => a.indexOf(v) === i)`);
  for (const t of TAMANHOS) {
    await tamanho(p, t);
    const ruins = [];
    for (const v of vistas) {
      await p.avaliar(`irPara('${v}')`);
      await espera(400);
      if (!(await p.avaliar(SEM_ROLAGEM))) ruins.push(`${v} (${await p.avaliar('document.documentElement.scrollWidth')} px)`);
    }
    conferir(`${t[0]}×${t[1]}: ${vistas.length} vistas sem rolagem horizontal da página`, !ruins.length, ruins.join(', '));
  }

  // menu no celular e no tablet
  await tamanho(p, [360, 640]);
  await p.avaliar(`irPara('aviso')`);
  await espera(300);
  conferir('celular: o botão "Menu" aparece e as seções ficam atrás dele', await p.avaliar(`${visivel('botaoMenu')} && !${visivel('abas')}
    && $('botaoMenu').getAttribute('aria-expanded') === 'false' && $('botaoMenu').getAttribute('aria-controls') === 'abas'`));
  conferir('o botão diz em que seção se está', await p.avaliar(`$('menuAtual').textContent.includes('Novo aviso')`), await p.avaliar(`$('menuAtual').textContent`));
  await p.avaliar(`($('botaoMenu').click(), 0)`);
  conferir('Menu aberto: aria-expanded="true" e as seções à vista', await p.avaliar(`$('botaoMenu').getAttribute('aria-expanded') === 'true' && ${visivel('abas')}`));
  await p.avaliar(`([...$('abas').querySelectorAll('button')].find(b => b.dataset.vista === 'historico').click(), 0)`);
  await espera(400);
  conferir('escolher uma seção fecha o menu', await p.avaliar(`estado.vista === 'historico' && !${visivel('abas')} && $('botaoMenu').getAttribute('aria-expanded') === 'false'`));
  await p.avaliar(`($('botaoMenu').click(), 0)`);
  await p.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await p.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  conferir('Esc fecha o menu e o foco volta ao botão', await p.avaliar(`!estado.menuAberto && document.activeElement === $('botaoMenu')`));
  await tamanho(p, [1280, 800]);
  conferir('computador: sem o botão "Menu", as seções sempre à vista', await p.avaliar(`!${visivel('botaoMenu')} && ${visivel('abas')}`));

  // mapa proporcional à tela no celular
  await tamanho(p, [390, 844]);
  const alt = await p.avaliar(`Math.round($('mapa').getBoundingClientRect().height)`);
  conferir('celular: mapa com altura proporcional à tela (entre 280 px e 55% da altura)', alt >= 280 && alt <= Math.ceil(844 * 0.55) + 1, `${alt} px`);

  // janela em tela cheia no celular, com o Fechar à vista
  await tamanho(p, [360, 640]);
  await p.avaliar(`($('botaoAjuda').click(), 0)`);
  await ate(p, `!$('caixaAjuda').hidden`);
  conferir('celular: Ajuda em tela cheia', await p.avaliar(`(() => { const r = document.querySelector('#caixaAjuda .cartao').getBoundingClientRect();
    return r.left <= 0.5 && r.top <= 0.5 && r.width >= innerWidth - 1 && r.height >= innerHeight - 1; })()`));
  conferir('o Fechar fica à vista sem rolar', await p.avaliar(`(() => { const r = $('ajudaFechar').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()`));
  await p.avaliar(`($('ajudaFechar').click(), 0)`);

  // toque: alvos de 48 px
  await p.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
  await p.send('Emulation.setEmulatedMedia', { features: [{ name: 'pointer', value: 'coarse' }, { name: 'any-pointer', value: 'coarse' }] }).catch(() => {});
  const grosso = await p.avaliar(`matchMedia('(pointer: coarse)').matches`);
  if (grosso) {
    const peq = [];
    for (const v of ['aviso', 'historico', 'relatorios', 'usuarios', 'radios', 'configuracoes']) {
      await p.avaliar(`irPara('${v}')`);
      await espera(400);
      peq.push(...await p.avaliar(`[...document.querySelectorAll('button, input:not([type=file]):not([type=checkbox]):not([type=radio]), select, summary, .arquivo')]
        .filter(e => e.offsetParent && !e.closest('.leaflet-control-attribution, #mapa .leaflet-control-zoom') || e.closest('#mapa .leaflet-bar'))
        .filter(e => e.offsetParent).map(e => [e.id || e.className || e.tagName, Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])
        .filter(([, w, h]) => h < 48 || w < 44).map(x => '${v}:' + x.join(' '))`));
    }
    conferir('toque (pointer: coarse): alvos com pelo menos 48 px de altura', !peq.length, JSON.stringify(peq.slice(0, 8)));
  } else conferir('toque: o navegador emula pointer: coarse', false, 'sem emulação de pointer');
  await p.send('Emulation.setTouchEmulationEnabled', { enabled: false });
  await p.send('Emulation.setEmulatedMedia', { features: [] });

  // impressão
  await tamanho(p, [1280, 800]);
  await p.avaliar(`irPara('relatorios')`);
  await espera(800);
  await p.send('Emulation.setEmulatedMedia', { media: 'print' });
  conferir('impressão: sem topo, menu, mapa nem botões; o relatório à vista', await p.avaliar(`['topo', 'abas', 'mapa-area', 'botaoMenu'].every(x => {
      const e = document.querySelector('.' + x) || $(x); return !e || getComputedStyle(e).display === 'none'; })
    && [...document.querySelectorAll('button')].every(b => getComputedStyle(b).display === 'none')
    && $('vista-relatorios').getBoundingClientRect().height > 0`));
  await p.send('Emulation.setEmulatedMedia', { media: '' });

  // manifest e nenhum service worker
  const man = await p.avaliar(`fetch(document.querySelector('link[rel=manifest]').href).then(async r => ({ tipo: r.headers.get('content-type'), j: await r.json() }))`);
  conferir('manifest do app instalável (nome, ícone, start_url)', /manifest\+json/.test(man.tipo) && man.j.short_name === 'Norte' && man.j.icons?.length && man.j.start_url === '/', JSON.stringify(man));
  conferir('nenhum service worker (nada da API guardado no aparelho)', await p.avaliar(`navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(r => r.length === 0) : true`));
  conferir('viewport com viewport-fit=cover (áreas seguras do celular)', await p.avaliar(`document.querySelector('meta[name=viewport]').content.includes('viewport-fit=cover')`));
  conferir('nenhuma exceção nem violação da CSP', !p.excecoes.length && !(await p.avaliar('window.__csp')).length, JSON.stringify(p.excecoes.slice(0, 3)));
  await p.fechar();
}

// ---------- 2. Admin do Norte: a tabela de empresas vira cartões no celular e rola com a 1ª coluna fixa no tablet ----------
{
  const p = await abrir(`${BASE}/`, { largura: 360, altura: 640 });
  await tamanho(p, [360, 640]);
  await entrar(p, 'admin@farol.example');
  await p.avaliar(`irPara('empresas')`);
  await ate(p, `document.querySelector('#listaEmpresas table.tabela tbody tr')`);
  const c = await p.avaliar(`(() => { const td = document.querySelector('#listaEmpresas tbody td[data-rotulo]'), tr = td?.closest('tr');
    return { rotulo: td?.dataset.rotulo, antes: td && getComputedStyle(td, '::before').content, tr: tr && getComputedStyle(tr).display,
      thead: getComputedStyle(document.querySelector('#listaEmpresas thead')).position, papel: td?.getAttribute('role'),
      tabela: document.querySelector('#listaEmpresas table').getAttribute('role') }; })()`);
  conferir('celular: tabela em cartões (cada valor com o nome da coluna)', c.tr === 'block' && c.rotulo && c.antes.includes(c.rotulo) && c.thead === 'absolute', JSON.stringify(c));
  conferir('a tabela em cartões continua tabela para o leitor de tela (role)', c.tabela === 'table' && c.papel === 'cell', JSON.stringify(c));
  conferir('celular: sem rolagem horizontal com a tabela', await p.avaliar(SEM_ROLAGEM));
  await tamanho(p, [768, 1024]);
  await espera(200);
  conferir('tablet: tabela de verdade, com a primeira coluna fixa ao rolar', await p.avaliar(`(() => { const th = document.querySelector('#listaEmpresas tbody tr > :first-child');
    return getComputedStyle(th.closest('tr')).display === 'table-row' && getComputedStyle(th).position === 'sticky'; })()`));
  conferir('nenhuma exceção (Admin do Norte)', !p.excecoes.length, JSON.stringify(p.excecoes.slice(0, 3)));
  await p.fechar();
}

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
