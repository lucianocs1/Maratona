// Acessibilidade automática (Fase I5): axe-core (npm, versão fixada em testes/navegador/package.json, MPL-2.0, só nos
// testes) nas telas de entrar e de criar a senha e em todas as vistas dos 4 perfis, nos temas claro e escuro e nos
// 3 idiomas (1280×800), e em todas as vistas do Admin da empresa nos 7 tamanhos de tela; também no funil com o aviso
// gerado (passos 3 e 4). Regras WCAG 2.0/2.1/2.2 A e AA: nenhuma violação "serious" nem "critical".
// O relatório por tela fica em saida/capturas_app/axe.json.
// Antes: cd testes/navegador && npm ci --ignore-scripts. Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_axe.mjs
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const AQUI = dirname(fileURLToPath(import.meta.url)), RAIZ = resolve(AQUI, '..', '..');
const AXE = join(AQUI, 'node_modules', 'axe-core', 'axe.min.js');
if (!existsSync(AXE)) { console.error('axe-core não instalado: cd testes/navegador && npm ci --ignore-scripts'); process.exit(2); }
const FONTE_AXE = readFileSync(AXE, 'utf8');
const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
const PLANILHA = join(RAIZ, 'saida', 'planilhas_teste', 'planilha_CF-0066.csv');
const SAIDA = join(RAIZ, 'saida', 'capturas_app');
mkdirSync(SAIDA, { recursive: true });
// AXE_SO_FUNIL=1: só o funil do Operador (para depurar rápido)
const SO_FUNIL = process.env.AXE_SO_FUNIL === '1';
const PERFIS = SO_FUNIL ? ['operador@emg.example'] : ['admin@farol.example', 'admin@emg.example', 'operador@emg.example', 'consulta@emg.example'];
const TEMAS = ['claro', 'escuro'], IDIOMAS = SO_FUNIL ? ['pt-BR'] : ['pt-BR', 'en', 'es'];
const TAMANHOS = [[320, 640], [360, 640], [390, 844], [768, 1024], [1024, 768], [1280, 800], [1920, 1080]];
const espera = ms => new Promise(r => setTimeout(r, ms));
const ate = (p, expr, ms = 60000) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > ${ms}) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);
const tamanho = (p, [w, h]) => p.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 1024 });

const porTela = {};        // tela -> { execucoes, violacoes: { regra: { impacto, ajuda, alvos } } }
let execucoes = 0;
async function axe(p, tela, contexto) {
  if (!(await p.avaliar('!!window.axe'))) await p.avaliar(FONTE_AXE + '; 0');
  // o fundo do mapa (imagens da Esri) e os nomes desenhados sobre ele não têm cor de fundo conhecida: o axe os marca
  // como "incompleto", nunca como violação; o resto do mapa (controles, legenda) é conferido
  const r = await p.avaliar(`axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] },
      resultTypes: ['violations'] })
    .then(r => r.violations.map(v => ({ id: v.id, impacto: v.impact, ajuda: v.help, alvos: v.nodes.slice(0, 4).map(n => n.target.join(' ')) })))`);
  execucoes++;
  const t = porTela[tela] ||= { execucoes: 0, violacoes: {} };
  t.execucoes++;
  for (const v of r) {
    const x = t.violacoes[v.id] ||= { impacto: v.impacto, ajuda: v.ajuda, alvos: new Set(), contextos: new Set() };
    v.alvos.forEach(a => x.alvos.add(a));
    x.contextos.add(contexto);
  }
}

async function entrar(p, email) {
  await p.avaliar(`($('email').value = ${JSON.stringify(email)}, $('senha').value = ${JSON.stringify(SENHAS[email])}, $('formEntrar').requestSubmit(), 0)`);
  await ate(p, `estado.tela === 'app' || estado.tela === 'senha'`);
  if (await p.avaliar(`estado.tela === 'senha'`)) {   // senha temporária (o executor deixa o Operador assim): cria a senha
    const nova = 'Lanterna-do-Farol-2026';
    await p.avaliar(`($('senhaAtual').value = ${JSON.stringify(SENHAS[email])}, $('senhaNova').value = $('senhaNova2').value = '${nova}', $('formSenha').requestSubmit(), 0)`);
  }
  await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto' && estado.concessao`);
  await new Promise(r => setTimeout(r, 500));
}
const vistasDe = p => p.avaliar(`vistasDoPerfil().map(([v]) => v).concat(pode('ver_historico') ? RELATORIOS.map(([v]) => v) : []).filter((v, i, a) => a.indexOf(v) === i)`);
async function ir(p, v) {
  await p.avaliar(`irPara('${v}')`);
  await ate(p, `!document.querySelector('[aria-busy="true"]')`, 10000);
  await espera(500);
}
const tema = (p, x) => p.avaliar(`(document.documentElement.dataset.tema = '${x}', desenharTema(), 0)`);
const idioma = (p, x) => p.avaliar(`trocarIdioma('${x}', false).then(() => 0)`);

// ---------- telas de entrar e de criar a senha ----------
{
  const p = await abrir(`${BASE}/`, { largura: 1280, altura: 800 });
  for (const tm of TEMAS) for (const id of IDIOMAS) {
    await tema(p, tm); await idioma(p, id);
    await axe(p, 'entrar', `${tm} ${id} 1280`);
    await p.avaliar(`(estado.tela = 'senha', desenharTela(), 0)`);
    await axe(p, 'criar a senha', `${tm} ${id} 1280`);
    await p.avaliar(`(estado.tela = 'entrar', desenharTela(), 0)`);
  }
  await tema(p, 'claro'); await idioma(p, 'pt-BR');
  for (const tt of TAMANHOS) { await tamanho(p, tt); await axe(p, 'entrar', `claro pt-BR ${tt.join('×')}`); }
  // o painel Acessibilidade aberto e a Declaração, nos dois temas e com o alto contraste
  await tamanho(p, [1280, 800]);
  for (const tm of TEMAS) {
    await tema(p, tm);
    await p.avaliar(`(abrirA11y(true), 0)`); await axe(p, 'painel Acessibilidade', `${tm} pt-BR 1280`);
    await p.avaliar(`(mudarA11y({ contraste: true }), 0)`); await axe(p, 'painel Acessibilidade (alto contraste)', `${tm} pt-BR 1280`);
    await p.avaliar(`(mudarA11y({ contraste: false }), abrirDeclaracao(), 0)`); await axe(p, 'Declaração de acessibilidade', `${tm} pt-BR 1280`);
    await p.avaliar(`($('caixaDeclaracao').hidden = true, 0)`);
  }
  await tema(p, 'claro');
  await p.fechar();
}

// ---------- cada perfil: todas as vistas × temas × idiomas (1280×800) ----------
for (const email of PERFIS) {
  const perfil = email.split('@')[0] + (email.includes('farol') ? ' (Norte)' : '');
  const p = await abrir(`${BASE}/`, { largura: 1280, altura: 800 });
  await entrar(p, email);
  const vistas = await vistasDe(p);
  for (const tm of TEMAS) for (const id of IDIOMAS) {
    await tema(p, tm); await idioma(p, id);
    for (const v of vistas) { await ir(p, v); await axe(p, `${perfil}: ${v}`, `${tm} ${id} 1280`); }
  }
  await tema(p, 'claro'); await idioma(p, 'pt-BR');
  if (email === 'admin@emg.example') {
    // todas as vistas nos 7 tamanhos (no celular, também com o menu aberto)
    for (const tt of TAMANHOS) {
      await tamanho(p, tt);
      for (const v of vistas) { await ir(p, v); await axe(p, `${perfil}: ${v}`, `claro pt-BR ${tt.join('×')}`); }
      if (tt[0] < 1024) { await p.avaliar(`(alternarMenu(true), 0)`); await axe(p, `${perfil}: menu aberto`, `claro pt-BR ${tt.join('×')}`); await p.avaliar(`(alternarMenu(false), 0)`); }
    }
    await tamanho(p, [1280, 800]);
    // o simulador preenchido (cartões de estimativa): temas x idiomas e 3 tamanhos; depois, Operador e Consulta já o veem assim
    await p.avaliar(`fetch('/api/empresa/configuracao/simulador', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gasto_min: '160000', gasto_max: '300000', pct_tempo: '100' }) }).then(r => r.status)`);
    for (const tm of TEMAS) for (const id of IDIOMAS) {
      await tema(p, tm); await idioma(p, id); await ir(p, 'simulador');
      await axe(p, `${perfil}: simulador preenchido`, `${tm} ${id} 1280`);
    }
    await tema(p, 'claro'); await idioma(p, 'pt-BR');
    for (const tt of [[320, 640], [768, 1024], [1920, 1080]]) { await tamanho(p, tt); await ir(p, 'simulador'); await axe(p, `${perfil}: simulador preenchido`, `claro pt-BR ${tt.join('×')}`); }
    await tamanho(p, [1280, 800]);
  }
  if (email === 'operador@emg.example' && existsSync(PLANILHA)) {
    // o funil com a planilha: passo 3 (conferir) e passo 4 (avisos, com o envio à rádio), nos dois temas
    await ir(p, 'aviso');
    const { root } = await p.send('DOM.getDocument', { depth: 1 });
    const { nodeId } = await p.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#arquivo' });
    await p.send('DOM.setFileInputFiles', { nodeId, files: [PLANILHA] });
    await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('form').requestSubmit(), 0)`);
    if (!(await ate(p, `document.documentElement.dataset.farol === 'conferencia'`))) {
      porTela['funil (não chegou à conferência)'] = { execucoes: 0, violacoes: { 'teste': { impacto: 'serious', ajuda: 'o funil não chegou ao passo 3', alvos: new Set([await p.avaliar(`$('estado').textContent + ' | passo ' + estado.passo + ' | ' + estado.vista`)]), contextos: new Set() } } };
      await p.fechar(); continue;
    }
    for (const tm of TEMAS) { await tema(p, tm); await axe(p, `${perfil}: aviso passo 3 (conferir)`, `${tm} pt-BR 1280`); }
    await p.avaliar(`($('conferi').click(), $('avancarResultado').click(), 0)`);
    await ate(p, `document.documentElement.dataset.farol === 'resultado'`);
    await espera(800);
    for (const tm of TEMAS) for (const tt of [[1280, 800], [360, 640]]) {
      await tema(p, tm); await tamanho(p, tt);
      await axe(p, `${perfil}: aviso passo 4 (avisos)`, `${tm} pt-BR ${tt.join('×')}`);
    }
    await tamanho(p, [1280, 800]); await tema(p, 'claro');
    // o mesmo aviso aberto no histórico
    await ir(p, 'historico');
    await p.avaliar(`(document.querySelector('#listaHistorico button.item, #listaHistorico .item')?.click(), 0)`);
    await espera(1500);
    await axe(p, `${perfil}: aviso aberto no histórico`, 'claro pt-BR 1280');
  }
  await p.fechar();
}

// ---------- resultado ----------
const graves = [], resumo = {};
for (const [tela, t] of Object.entries(porTela)) {
  resumo[tela] = { execucoes: t.execucoes, violacoes: Object.fromEntries(Object.entries(t.violacoes).map(([id, v]) =>
    [id, { impacto: v.impacto, ajuda: v.ajuda, alvos: [...v.alvos].slice(0, 6), contextos: [...v.contextos].slice(0, 6) }])) };
  for (const [id, v] of Object.entries(t.violacoes)) if (v.impacto === 'serious' || v.impacto === 'critical') graves.push(`${tela} · ${id} (${v.impacto}) ${[...v.alvos].slice(0, 3).join(' | ')} [${[...v.contextos].slice(0, 2).join('; ')}]`);
}
writeFileSync(join(SAIDA, 'axe.json'), JSON.stringify({ axe: JSON.parse(readFileSync(join(AQUI, 'node_modules', 'axe-core', 'package.json'), 'utf8')).version, execucoes, telas: resumo }, null, 1));
for (const [tela, t] of Object.entries(resumo)) {
  const n = Object.values(t.violacoes);
  console.log(`${n.some(v => v.impacto === 'serious' || v.impacto === 'critical') ? 'FALHA' : 'OK  '} ${tela}: ${t.execucoes} execução(ões), ` +
    (n.length ? Object.entries(t.violacoes).map(([id, v]) => `${id} (${v.impacto})`).join(', ') : 'nenhuma violação'));
}
for (const g of graves) console.log('  → ' + g);
console.log(`\n${execucoes} execuções do axe em ${Object.keys(resumo).length} telas; ${graves.length} violação(ões) serious/critical`);
process.exit(graves.length ? 1 : 0);
