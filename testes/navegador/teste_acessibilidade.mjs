// Painel Acessibilidade e Declaração (Bloco D, 15/10/2026): botão no topo (também em Entrar), tamanho do texto até 200%
// sem rolagem horizontal, alto contraste, fonte Atkinson Hyperlegible servida pelo Norte, espaçamento, reduzir movimento,
// destacar links e foco, guia de leitura, modo simples, voltar ao padrão; antes de entrar só na sessão, depois no perfil
// (e na auditoria); "Pular para o conteúdo"; Declaração com o relato que vai para a auditoria; em inglês.
// Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_acessibilidade.mjs
import { abrir } from './cdp.mjs';

const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
const J = JSON.stringify;
const ate = (p, expr, ms = 30000) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > ${ms}) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);
const tecla = async (p, key, code, vk, shift = false) => {
  for (const type of ['keyDown', 'keyUp']) await p.send('Input.dispatchKeyEvent', { type, key, code, windowsVirtualKeyCode: vk, modifiers: shift ? 8 : 0 });
};
const SEM_ROLAGEM = 'document.documentElement.scrollWidth <= innerWidth + 1';

const p = await abrir(`${BASE}/`, { largura: 1280, altura: 800 });
// ---------- antes de entrar ----------
await tecla(p, 'Tab', 'Tab', 9);
conferir('o primeiro Tab mostra "Pular para o conteúdo" (visível no foco)', await p.avaliar(`document.activeElement?.id === 'pular' && $('pular').getBoundingClientRect().top >= 0`));
await tecla(p, 'Enter', 'Enter', 13);
conferir('"Pular para o conteúdo" leva ao título da tela', await p.avaliar(`document.activeElement?.tagName === 'H1'`));
conferir('menu no topo da tela de entrar, com o botão Acessibilidade dentro', await p.avaliar(`!!$('botaoConta').offsetParent && ($('botaoConta').click(), !!$('botaoAcessibilidade').offsetParent && $('botaoAcessibilidade').textContent.includes('Acessibilidade'))`));
await p.avaliar(`($('botaoAcessibilidade').click(), 0)`);
conferir('abre o painel (aria-expanded) com o foco no título', await p.avaliar(`!$('painelAcessibilidade').hidden && $('botaoAcessibilidade').getAttribute('aria-expanded') === 'true' && document.activeElement?.id === 'a11yTitulo'`));
await tecla(p, 'Escape', 'Escape', 27);
conferir('Esc fecha e o foco volta ao botão do menu', await p.avaliar(`$('painelAcessibilidade').hidden && document.activeElement?.id === 'botaoConta'`));
await p.avaliar(`($('botaoAcessibilidade').click(), document.querySelector('[data-texto="200"]').click(), 0)`);
conferir('A++: texto a 200% (aria-pressed)', await p.avaliar(`parseFloat(getComputedStyle(document.body).fontSize) === 30 && document.querySelector('[data-texto="200"]').getAttribute('aria-pressed') === 'true'`),
  await p.avaliar(`getComputedStyle(document.body).fontSize`));
conferir('antes de entrar, fica só na sessão do navegador', await p.avaliar(`JSON.parse(sessionStorage.getItem('farol.a11y')).texto === 200`));
await p.avaliar(`($('a11yFechar').click(), 0)`);

// ---------- depois de entrar: as escolhas da tela de entrar vão para o perfil ----------
await p.avaliar(`($('email').value = 'consulta@emg.example', $('senha').value = ${J(SENHAS['consulta@emg.example'])}, $('formEntrar').requestSubmit(), 0)`);
await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto' && estado.concessao`, 60000);
await espera(1500);
conferir('depois de entrar, continua a 200% e foi para o perfil', await p.avaliar(`fetch('/api/eu').then(r => r.json()).then(j => j.usuario.preferencias.acessibilidade?.texto === 200)`));
const ruins = [];
for (const v of await p.avaliar(`vistasDoPerfil().map(([v]) => v)`)) {
  await p.avaliar(`irPara('${v}').then(() => 0)`); await espera(400);
  if (!(await p.avaliar(SEM_ROLAGEM))) ruins.push(v);
}
conferir('texto a 200%: nenhuma tela com rolagem horizontal', !ruins.length, ruins.join(', '));
await p.avaliar(`($('botaoAcessibilidade').click(), 0)`);
const marcar = id => p.avaliar(`(() => { const c = $('${id}'); c.checked = true; c.dispatchEvent(new Event('change')); return 0; })()`);
await marcar('a11yContraste');
conferir('alto contraste: texto preto puro no fundo branco', await p.avaliar(`document.documentElement.hasAttribute('data-contraste') && getComputedStyle(document.body).color === 'rgb(0, 0, 0)'`));
await marcar('a11yDislexia');
await p.avaliar(`document.fonts.ready.then(() => 0)`);
conferir('fonte de leitura facilitada: Atkinson Hyperlegible, servida pelo próprio Norte', await p.avaliar(`getComputedStyle(document.body).fontFamily.startsWith('"Atkinson Hyperlegible"')
  && document.fonts.check('16px "Atkinson Hyperlegible"') && performance.getEntriesByType('resource').some(r => r.name.startsWith(location.origin + '/assets/vendor/atkinson/'))`));
await marcar('a11yEspacamento');
conferir('espaçamento (WCAG 1.4.12): letras 0,12 em e linhas 1,5', await p.avaliar(`(() => { const e = document.querySelector('.vista:not([hidden]) h1'), cs = getComputedStyle(e);
  return Math.abs(parseFloat(cs.letterSpacing) - 0.12 * parseFloat(cs.fontSize)) < 0.6; })()`));
await marcar('a11yMovimento');
conferir('reduzir movimento: sem transição e o mapa sem animação', await p.avaliar(`getComputedStyle(document.querySelector('button')).transitionDuration.startsWith('1e-05s') || getComputedStyle(document.querySelector('button')).transitionDuration === '0.00001s' || parseFloat(getComputedStyle(document.querySelector('button')).transitionDuration) < 0.001`)
  && await p.avaliar(`mapa.options.zoomAnimation === false`));
await marcar('a11yLinks');
conferir('destacar links e foco', await p.avaliar(`document.documentElement.hasAttribute('data-links')`));
await marcar('a11yGuia');
await p.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 300, y: 400 });
conferir('guia de leitura acompanha o mouse', await p.avaliar(`!$('guiaLeitura').hidden && Math.abs(parseFloat($('guiaLeitura').style.top) - 386) < 3`), await p.avaliar(`$('guiaLeitura').style.top`));
await marcar('a11ySimples');
conferir('modo simples: sem o mapa e as dicas', await p.avaliar(`getComputedStyle(document.querySelector('.mapa-area')).display === 'none'`));
await espera(800);
const audit = await p.avaliar(`fetch('/api/eu').then(r => r.json()).then(j => j.usuario.preferencias.acessibilidade)`);
conferir('tudo guardado no perfil', audit.contraste && audit.dislexia && audit.espacamento && audit.movimento && audit.links && audit.guia && audit.simples, J(audit));
// recarregar: continua; Voltar ao padrão desfaz tudo
const carregou = p.uma('Page.loadEventFired');
await p.send('Page.reload'); await carregou;
await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto'`, 60000);
conferir('depois de recarregar, continua (vem do perfil)', await p.avaliar(`document.documentElement.hasAttribute('data-contraste') && document.documentElement.style.fontSize === '200%'`));
await p.avaliar(`($('botaoAcessibilidade').click(), $('a11yPadrao').click(), 0)`);
conferir('"Voltar ao padrão" desfaz tudo', await p.avaliar(`!document.documentElement.hasAttribute('data-contraste') && !document.documentElement.style.fontSize
  && !document.documentElement.hasAttribute('data-simples') && $('guiaLeitura').hidden`));
// Declaração e relato
await p.avaliar(`($('botaoAcessibilidade').click(), $('a11yDeclaracao').click(), 0)`);
conferir('Declaração de acessibilidade (WCAG 2.2 AA, NBR 17225, LBI art. 63, limitações)', await p.avaliar(`!$('caixaDeclaracao').hidden && /WCAG 2\\.2/.test($('caixaDeclaracao').textContent)
  && /17225/.test($('caixaDeclaracao').textContent) && /art\\. 63/.test($('caixaDeclaracao').textContent) && /Limitações conhecidas/.test($('caixaDeclaracao').textContent)`));
await p.avaliar(`($('relatoTexto').value = 'Meu fone 32 99999-8888', $('formRelato').requestSubmit(), 0)`);
await ate(p, `$('estadoRelato').textContent`);
conferir('relato com dado pessoal (telefone) é recusado', await p.avaliar(`$('estadoRelato').classList.contains('erro')`), await p.avaliar(`$('estadoRelato').textContent`));
await p.avaliar(`($('estadoRelato').textContent = '', $('relatoTexto').value = 'O botão do mapa de calor não é lido pelo NVDA.', $('formRelato').requestSubmit(), 0)`);
await ate(p, `/FRL-/.test($('estadoRelato').textContent)`);
conferir('relato enviado com o código da auditoria', await p.avaliar(`/FRL-/.test($('estadoRelato').textContent)`), await p.avaliar(`$('estadoRelato').textContent`));
await tecla(p, 'Escape', 'Escape', 27);
// voz: só voz instalada no aparelho; com só voz on-line, o botão fica desligado e o painel diz como instalar
const local = await p.avaliar(`!!vozLocal()`);
conferir(`leitura em voz alta: ${local ? 'voz local disponível, botão ligado' : 'sem voz local, botão desligado'}`,
  await p.avaliar(`$('a11yLer').disabled === !vozLocal()`));
await p.avaliar(`(speechSynthesis.getVoices = () => [{ localService: false, lang: 'pt-BR', name: 'voz on-line' }], desenharVoz(), 0)`);
conferir('só voz on-line no aparelho: botão desligado e "Nenhuma voz instalada" com como instalar', await p.avaliar(`$('a11yLer').disabled
  && /Nenhuma voz instalada neste aparelho/.test($('a11yVoz').textContent) && /Windows/.test($('a11yVoz').textContent) && /Android/.test($('a11yVoz').textContent)`));
conferir('a Declaração diz que só vozes instaladas no aparelho são usadas', await p.avaliar(`/nunca vozes on-line/.test($('caixaDeclaracao').textContent)`));
// inglês
await p.avaliar(`trocarIdioma('en', false).then(() => 0)`);
conferir('em inglês', await p.avaliar(`$('botaoAcessibilidade').textContent.includes('Accessibility') && $('pular').textContent === 'Skip to content'`));
conferir('nenhuma exceção nem violação da CSP', !p.excecoes.length && !(await p.avaliar('window.__csp')).length, J(p.excecoes.slice(0, 3)));
await p.fechar();

// auditoria: só "alterou as preferências de acessibilidade", nunca quais opções (dado sensível); o Admin da empresa vê a auditoria
{
  const a = await abrir(`${BASE}/`, { largura: 1280, altura: 800 });
  await a.avaliar(`($('email').value = 'admin@emg.example', $('senha').value = ${J(SENHAS['admin@emg.example'])}, $('formEntrar').requestSubmit(), 0)`);
  await ate(a, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto'`, 60000);
  const reg = await a.avaliar(`fetch('/api/registro').then(r => r.json()).then(j => j.registro)`);
  const pref = reg.filter(r => /prefer/.test(r.acao));
  const opcoes = /contraste|dislexia|espacamento|movimento|links|guia|simples|texto|painel/;
  conferir('auditoria: "alterou as preferências de acessibilidade", sem dizer quais opções', pref.some(r => r.acao === 'alterou as preferências de acessibilidade')
    && pref.every(r => !r.detalhe && !opcoes.test(r.acao)), J(pref.slice(0, 3)));
  conferir('nenhuma linha da auditoria cita as opções de acessibilidade de alguém', !reg.some(r => /prefer|idioma/.test(r.acao) && (r.detalhe || opcoes.test(r.acao))));
  await a.fechar();
}

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
