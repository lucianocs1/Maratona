// Telas em 3 idiomas (Fase K2): cada tela abre em inglês e em espanhol sem texto fixo em português sobrando,
// <html lang> acompanha, o idioma fica no perfil (continua depois de recarregar) e o aviso tem o lang do idioma dele.
// Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_idiomas_tela.mjs
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
const TEXTOS = new Function(readFileSync(join(RAIZ, 'src', 'comunidades', 'apresentacao', 'app', 'textos.js'), 'utf8') + '; return TEXTOS;')();
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const ate = (p, expr, ms = 30000) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > ${ms}) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);
// os textos visíveis (nós de texto inteiros) da página, fora o mapa (nomes de lugares) e o que vem da API (nomes)
const VISIVEIS = `[...document.querySelectorAll('body *')].filter(e => e.offsetParent && !e.closest('#mapa, .leaflet-container'))
  .flatMap(e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim())).filter(Boolean)`;

async function sobras(p, idioma) {
  const textos = new Set(await p.avaliar(VISIVEIS));
  // só os textos do dicionário que mudam no idioma (ex.: "Rádio" -> "Radio station"); nomes iguais nos dois não contam
  return [...textos].filter(x => x in TEXTOS[idioma] && TEXTOS[idioma][x] !== x);
}

const p = await abrir(`${BASE}/`, { largura: 1440, altura: 900 });
await p.avaliar(`(() => { const s = $('idiomaTela'); s.value = 'en'; s.dispatchEvent(new Event('change')); return 0; })()`);
await ate(p, `document.documentElement.lang === 'en'`);
conferir('tela de entrar em inglês (antes do login, só na sessão)', await p.avaliar(`document.querySelector('#telaEntrar h1').textContent === 'Sign in to Norte'
  && $('botaoEntrar').textContent === 'Sign in' && document.title.startsWith('Norte · Power')`), await p.avaliar(`document.querySelector('#telaEntrar h1').textContent`));
const sobraEntrar = await sobras(p, 'en');
conferir('tela de entrar: nenhum texto em português sobrando', !sobraEntrar.length, JSON.stringify(sobraEntrar));
await p.avaliar(`($('email').value = 'admin@emg.example', $('senha').value = ${JSON.stringify(SENHAS['admin@emg.example'])}, $('formEntrar').requestSubmit(), 0)`);
await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto'`, 60000);
conferir('depois de entrar, continua em inglês (e fica no perfil)', await p.avaliar(`IDIOMA === 'en' && $('abas').textContent.includes('New notice')`));
for (const idioma of ['en', 'es']) {
  if (idioma === 'es') {
    await p.avaliar(`(() => { const s = $('idiomaTela'); s.value = 'es'; s.dispatchEvent(new Event('change')); return 0; })()`);
    await ate(p, `document.documentElement.lang === 'es' && $('abas').textContent.includes('Nuevo aviso')`);
  }
  const ruins = {};
  for (const v of ['aviso', 'historico', 'relatorios', 'painel', 'comparativo', 'usuarios', 'radios', 'configuracoes', 'registro']) {
    await p.avaliar(`irPara('${v}')`);
    await new Promise(r => setTimeout(r, 700));
    if (v === 'aviso') await p.avaliar(`($('avancar').click(), 0)`);   // o passo 1 (sem planilha) mostra o aviso de erro
    const s = await sobras(p, idioma);
    if (s.length) ruins[v] = s.slice(0, 6);
  }
  conferir(`${idioma}: todas as telas do Admin da empresa sem texto em português sobrando`, !Object.keys(ruins).length, JSON.stringify(ruins));
}
const carregou = p.uma('Page.loadEventFired');
await p.send('Page.reload');
await carregou;
await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto'`, 60000);
conferir('o idioma fica no perfil: depois de recarregar, continua em espanhol', await p.avaliar(`IDIOMA === 'es' && document.documentElement.lang === 'es'`));
await p.avaliar(`(() => { const s = $('idiomaTela'); s.value = 'pt-BR'; s.dispatchEvent(new Event('change')); return 0; })()`);
await ate(p, `document.documentElement.lang === 'pt-BR' && $('abas').textContent.includes('Novo aviso')`);
conferir('volta ao português', await p.avaliar(`document.querySelector('#vista-aviso h1').textContent === 'Novo desligamento programado'`));
conferir('nenhuma exceção', !p.excecoes.length, JSON.stringify(p.excecoes.slice(0, 3)));
await p.fechar();

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
