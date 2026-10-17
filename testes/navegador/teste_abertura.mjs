// Teste da tela de abertura, da página de entrada e do botão "Trocar área" (passo 13), com capturas.
// - No mapa: a abertura aparece no primeiro quadro, mostra o progresso real ("Carregando o território…",
//   "Montando a rede…", "Pronto") e some sozinha quando o mapa termina de montar, sem tempo fixo.
//   O carregamento é feito com a CPU desacelerada, para cada etapa durar o bastante para ser vista.
// - Com movimento reduzido: sem animação do feixe e a abertura some na hora.
// - Na entrada: um cartão por município, links relativos que abrem, nenhum script e a abertura só com CSS.
// Uso (na raiz do projeto): node testes/navegador/teste_abertura.mjs
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SAIDA = join(RAIZ, 'saida'), CAP = join(SAIDA, 'capturas_passo13');
mkdirSync(CAP, { recursive: true });
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
async function captura(p, nome, clip) {
  const r = await p.send('Page.captureScreenshot', { format: 'png', ...(clip ? { clip: { ...clip, scale: 2 } } : {}) });
  writeFileSync(join(CAP, nome), Buffer.from(r.data, 'base64'));
}
async function clicar(p, sel) {
  const [x, y] = await p.avaliar(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.scrollIntoView({ block: 'center' }); const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; })()`);
  for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased'])
    await p.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: type === 'mouseMoved' ? 0 : 1 });
}
async function esperarPronto(p) {
  return p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => { const e = document.documentElement.dataset.farol;
    if (!e || e === 'pronto' || e === 'erro' || Date.now() - t0 > 60000) ok(e || 'sem estado'); else setTimeout(ver, 50); }; ver(); })`);
}
// Registro quadro a quadro: o que a abertura mostrava em cada quadro desenhado
const REGISTRO = `window.__quadros = [];
(function quadro() {
  const ab = document.getElementById('abertura'), pr = document.getElementById('aberturaProgresso');
  const s = !document.body || !document.body.firstElementChild ? 'antes do corpo | ' : (ab ? (ab.hidden ? 'oculta' : ab.classList.contains('saindo') ? 'saindo' : 'visível') : 'sem abertura') + ' | ' + (pr ? pr.textContent : '');
  const q = window.__quadros, u = q[q.length - 1];
  if (u && u[0] === s) u[1]++; else q.push([s, 1, Math.round(performance.now())]);
  requestAnimationFrame(quadro);
})();`;

// ---------- 1. Abertura do mapa, carregando com a CPU 4× mais lenta ----------
for (const [cidade, arq] of [['Leopoldina', 'mapa_comunidades.html'], ['Muriaé', 'muriae/mapa_comunidades.html']]) {
  let frames = 0;
  const p = await abrir(join(SAIDA, arq), { antesDeNavegar: async pg => {
    await pg.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    await pg.send('Page.addScriptToEvaluateOnNewDocument', { source: REGISTRO });
    // capturas durante o carregamento, em paralelo à navegação (só as que saem antes do mapa ficar pronto contam)
    setTimeout(async () => {
      for (let i = 0; i < 20 && !pg.pronto; i++) {
        try { const r = await pg.send('Page.captureScreenshot', { format: 'png' });
          if (!pg.pronto) { if (cidade === 'Leopoldina') writeFileSync(join(CAP, `0_abertura_carregando_${frames}.png`), Buffer.from(r.data, 'base64')); frames++; } } catch (e) { /* página trocando */ }
        await espera(100);
      }
    }, 60);
  } });
  p.pronto = true;
  await p.send('Emulation.setCPUThrottlingRate', { rate: 1 });
  // espera a abertura sumir (fim da transição), sem tempo fixo no código do mapa
  const sumiu = await p.avaliar(`new Promise(ok => { const t0 = performance.now(), ver = () => {
    if ($('abertura').hidden) ok(Math.round(performance.now() - t0)); else if (performance.now() - t0 > 5000) ok(-1); else requestAnimationFrame(ver); }; ver(); })`);
  const quadros = await p.avaliar('window.__quadros');
  const etapas = quadros.map(q => q[0]).filter(e => !e.startsWith('antes do corpo'));
  const primeiro = etapas[0] || '';
  const ordem = ['visível | Carregando o território…', 'visível | Montando a rede…', 'saindo | Pronto', 'oculta | Pronto'];
  conferir(`${cidade}: a abertura é a primeira coisa desenhada da página, antes dos dados`, primeiro === ordem[0], primeiro);
  conferir(`${cidade}: progresso real, na ordem (cada etapa em pelo menos 1 quadro)`, ordem.every(o => etapas.includes(o)) && ordem.map(o => etapas.indexOf(o)).every((v, i, a) => !i || v > a[i - 1]),
    quadros.map(q => `${q[0].split(' | ')[1]} (${q[0].split(' | ')[0]}, ${q[1]} quadros)`).join(' → '));
  conferir(`${cidade}: a abertura some sozinha quando o mapa fica pronto`, sumiu >= 0 && await p.avaliar(`document.documentElement.dataset.farol === 'pronto' && $('abertura').hidden`), `oculta ${sumiu} ms depois de conferir`);
  conferir(`${cidade}: feixe animado (sem pedido de movimento reduzido)`, await p.avaliar(`getComputedStyle(document.querySelector('.abertura .feixe')).animationName === 'feixe-gira'`));
  conferir(`${cidade}: capturas durante o carregamento`, frames > 0, `${frames} capturas`);
  if (cidade === 'Leopoldina') {
    await captura(p, '4_mapa_carregado.png');
    await captura(p, '5_botao_trocar_area.png', { x: 0, y: 0, width: 520, height: 64 });
  }
  await p.fechar();
}

// ---------- 2. Movimento reduzido: sem animação e sem transição ----------
{
  const p = await abrir(join(SAIDA, 'mapa_comunidades.html'), { antesDeNavegar: async pg => {
    await pg.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    await pg.send('Page.addScriptToEvaluateOnNewDocument', { source: REGISTRO });
  } });
  const r = await p.avaliar(`({ anim: getComputedStyle(document.querySelector('.abertura .feixe')).animationName, oculta: $('abertura').hidden,
    saindo: window.__quadros.some(q => q[0].startsWith('saindo')) })`);
  conferir('movimento reduzido: feixe parado e a abertura some na hora, sem transição', r.anim === 'none' && r.oculta && !r.saindo, JSON.stringify(r));
  await p.fechar();
}

// ---------- 3. Página de entrada: cartões, links, mapa do Brasil, abertura só com CSS ----------
// requisições da página: só o próprio arquivo, dados embutidos e os fundos de mapa da Esri
const registrarRede = lista => async pg => {
  await pg.send('Network.enable');
  pg.on('Network.requestWillBeSent', e => lista.push(e.request.url));
};
const externa = u => !/^(file:|data:|https:\/\/server\.arcgisonline\.com\/)/.test(u);
const textoPopup = `(() => { const e = document.querySelector('.leaflet-popup'), a = e?.querySelector('a.abrir');
  return { texto: e?.textContent.replace(/\\s+/g, ' ').trim(), link: a ? a.getAttribute('href') : null, zoom: mapa.getZoom() }; })()`;
for (const [largura, altura, nome] of [[1440, 900, 'computador'], [390, 844, 'celular']]) {
  const rede = [];
  const p = await abrir(join(SAIDA, 'index.html'), { largura, altura, antesDeNavegar: registrarRede(rede) });
  const info = await p.avaliar(`({
    csp: document.querySelector('meta[http-equiv="Content-Security-Policy"]').content,
    scripts: document.scripts.length, externos: [...document.scripts].filter(s => s.src).length,
    pergunta: document.querySelector('h1').textContent,
    cartoes: [...document.querySelectorAll('.cartao')].map(c => [c.querySelector('h2').textContent, c.querySelector('.uf').textContent,
      [...c.querySelectorAll('dd')].map(d => d.textContent).join(' / '), c.querySelector('a.abrir').getAttribute('href')]),
    nota: document.querySelector('footer').textContent.replace(/\\s+/g, ' ').trim(),
    fim: Math.max(...document.getAnimations().filter(a => a instanceof CSSAnimation).map(a => a.effect.getComputedTiming().endTime)),
    mapa: { visivel: getComputedStyle(document.querySelector('.painel-mapa')).display !== 'none', ufs: D.ufs.features.length,
      municipios: D.municipios.features.length, contagem: document.getElementById('n-municipios').textContent + ' / ' + document.getElementById('n-prontos').textContent,
      prontos: D.municipios.features.filter(f => f.properties.MAPA).map(f => f.properties.NM_MUN + '|' + f.properties.MAPA).join(', ') },
    rolagem: document.documentElement.scrollWidth > innerWidth })`);
  if (nome === 'computador') {
    conferir('entrada: um cartão por município processado, com links relativos', info.cartoes.length === 2 && info.cartoes.every(c => !/^(\/|[a-z]+:)/i.test(c[3])), JSON.stringify(info.cartoes));
    conferir('entrada: pergunta "Qual área você quer abrir?"', info.pergunta === 'Qual área você quer abrir?');
    conferir('entrada: só scripts embutidos, liberados pelo hash na CSP, e nenhuma conexão', info.scripts === 2 && !info.externos
      && /script-src 'sha256-[^']+' 'sha256-[^']+';/.test(info.csp) && info.csp.includes("connect-src 'none'"), info.csp.replace(/'sha256-[^']+'/g, "'sha256-…'"));
    conferir('entrada: nota de dados fictícios e de como gerar outro município', /fictícios/.test(info.nota) && info.nota.includes('Para outro município, gere o Norte pelo comando com --coordenada ou --distribuidora.'), info.nota);
    conferir('entrada: abertura só com CSS, terminando em cerca de 1,2 s', info.fim >= 1000 && info.fim <= 1500, `${Math.round(info.fim)} ms`);
    conferir('entrada: mapa do Brasil com as 27 UFs, a concessão e os 66 municípios', info.mapa.visivel && info.mapa.ufs === 27 && info.mapa.municipios === 66 && info.mapa.contagem === '66 / 2', JSON.stringify(info.mapa));
    conferir('entrada: Leopoldina e Muriaé marcados como prontos, com o link do mapa', info.mapa.prontos === 'Leopoldina|mapa_comunidades.html, Muriaé|muriae/mapa_comunidades.html', info.mapa.prontos);
    // capturas: congela a animação a 0,3 s (logo grande no centro) e no fim
    await p.avaliar('(document.getAnimations().forEach(a => { a.pause(); a.currentTime = 300; }), 0)');
    await captura(p, '2_entrada_abertura.png');
    await p.avaliar('(document.getAnimations().forEach(a => a.finish()), 0)'); await espera(1500);
    await captura(p, '3_escolha_da_cidade.png');
    // ponto de Muriaé na escala do país: aproxima e abre o popup com as contagens e o link do mapa
    await p.avaliar(`(() => { const c = camadas.municipios.getLayers().find(c => c.feature.properties.NM_MUN === 'Muriaé');
      camadas.pontos.getLayers().find(m => c.getBounds().contains(m.getLatLng())).fire('click'); return 0; })()`);
    await espera(1500);
    const pop = await p.avaliar(textoPopup);
    conferir('entrada: o ponto de Muriaé aproxima e abre o popup com as contagens e o link do mapa',
      pop.link === 'muriae/mapa_comunidades.html' && /Muriaé/.test(pop.texto) && /comunidades/.test(pop.texto) && pop.zoom >= 7, JSON.stringify(pop));
    await captura(p, '3c_entrada_popup_muriae.png');
    // município ainda não processado: só o nome e a situação, sem link
    await p.avaliar(`(() => { const c = camadas.municipios.getLayers().find(c => c.feature.properties.NM_MUN === 'Cataguases'); c.openPopup(c.getCenter()); return 0; })()`);
    await espera(800);
    const pend = await p.avaliar(textoPopup);
    conferir('entrada: município não processado mostra a situação, sem link', /Cataguases/.test(pend.texto) && /Ainda não processado/.test(pend.texto) && !pend.link, JSON.stringify(pend));
    await p.avaliar(`(irPara('concessao'), mapa.closePopup(), 0)`); await espera(1500);
    await captura(p, '3d_entrada_concessao.png');
    const csp = await p.avaliar('window.__csp');
    conferir('entrada: nenhuma exceção nem violação da CSP', !p.excecoes.length && !csp.length, JSON.stringify([p.excecoes, csp]));
    conferir('entrada: nenhuma requisição além dos fundos de mapa da Esri', rede.some(u => u.includes('arcgisonline')) && !rede.some(externa), JSON.stringify(rede.filter(externa)));
  } else {
    await p.avaliar('(document.getAnimations().forEach(a => a.finish()), 0)'); await espera(1500);
    await captura(p, '3b_escolha_da_cidade_celular.png');
  }
  conferir(`entrada (${nome}): sem rolagem horizontal`, !info.rolagem);
  await p.fechar();
}
{
  const p = await abrir(join(SAIDA, 'index.html'), { antesDeNavegar: pg => pg.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] }) });
  conferir('entrada com movimento reduzido: abre pronta, sem animação', await p.avaliar(`document.getAnimations().length === 0 && getComputedStyle(document.querySelector('.cartao')).opacity === '1'`));
  // Abrir Muriaé pelo cartão, voltar pelo "Trocar área", abrir Leopoldina e voltar de novo
  for (const cidade of ['Muriaé', 'Leopoldina']) {
    let carregou = p.uma('Page.loadEventFired');
    await clicar(p, `a.abrir[aria-label^="Abrir ${cidade}"]`); await carregou;
    const estadoMapa = await esperarPronto(p);
    const m = await p.avaliar(`({ municipio: DIST.municipio, link: $('btnTrocarArea').getAttribute('href'), abertura: $('abertura').hidden || $('abertura').classList.contains('saindo') })`);
    conferir(`entrada → "Abrir" ${cidade}: o mapa certo abre e fica pronto`, estadoMapa === 'pronto' && m.municipio === cidade && m.abertura, JSON.stringify(m));
    carregou = p.uma('Page.loadEventFired');
    await clicar(p, '#btnTrocarArea'); await carregou;
    conferir(`"Trocar área" no mapa de ${cidade} volta à página de entrada`, await p.avaliar(`location.pathname.endsWith('/saida/index.html') && !!document.querySelector('.cartao')`));
  }
  await p.fechar();
}

for (const r of resultados) console.log(r[0], r[1], r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
