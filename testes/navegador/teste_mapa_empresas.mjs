// Mapa das empresas (Admin do Norte, desde 15/10/2026): áreas com cor e hachura, sigla no meio, legenda que liga e desliga,
// empresa sem área com o botão de cadastrar, editor da área (lista do estado, busca, resumo e confirmação), sobreposição,
// ficha da empresa (só cadastro e contagens), nada operacional pedido ao servidor, celular e inglês; e os outros perfis
// continuam com o mapa operacional.
// Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_mapa_empresas.mjs
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

async function entrar(p, email) {
  await p.avaliar(`($('email').value = ${J(email)}, $('senha').value = ${J(SENHAS[email])}, $('formEntrar').requestSubmit(), 0)`);
  await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto' && estado.concessao && estado.config`, 60000);
  await espera(500);
}

// ---------- Admin do Norte ----------
{
  const pedidos = [];
  const p = await abrir(`${BASE}/`, { largura: 1280, altura: 800, antesDeNavegar: async pg => {
    await pg.send('Network.enable');
    pg.on('Network.responseReceived', e => pedidos.push([e.response.status, e.response.url]));
  } });
  await entrar(p, 'admin@farol.example');
  await ate(p, `estado.mapaEmpresas && document.querySelector('#listaLegendaEmpresas [data-empresa-mapa]')`);
  conferir('o mapa do Admin do Norte é o das empresas (legenda das empresas; a operacional escondida)',
    await p.avaliar(`!$('legendaEmpresas').hidden && $('legenda').hidden && $('mapa').getAttribute('aria-label').startsWith('Mapa das empresas')`));
  const emg = await p.avaliar(`(() => { const li = [...document.querySelectorAll('.legenda-empresa')].find(l => l.textContent.includes('EMG'));
    return li && li.textContent; })()`);
  conferir('legenda: sigla, nome, situação e número de municípios da EMG', /EMG/.test(emg) && /Ativa/.test(emg) && /\d+ município/.test(emg), emg);
  conferir('a área da EMG desenhada com hachura (padrão SVG) e contorno', await p.avaliar(`!!document.querySelector('#mapa svg defs.hachuras pattern')
    && [...document.querySelectorAll('#mapa path.leaflet-interactive')].some(x => /url\\(#hachura-/.test(x.getAttribute('fill') || ''))`));
  conferir('a sigla escrita no meio da área', await p.avaliar(`[...document.querySelectorAll('.rotulo-empresa span')].some(s => s.textContent === 'EMG')`));
  const hachurados = `[...document.querySelectorAll('#mapa path')].filter(x => /url\\(#hachura-/.test(x.getAttribute('fill') || '')).length`;
  const antes = await p.avaliar(hachurados);
  await p.avaliar(`(document.querySelector('[data-empresa-mapa]').click(), 0)`);
  conferir('clicar na legenda desliga a empresa no mapa (aria-pressed=false)', await p.avaliar(`document.querySelector('[data-empresa-mapa]').getAttribute('aria-pressed') === 'false'`)
    && await p.avaliar(hachurados) === 0, `${antes}`);
  await p.avaliar(`(document.querySelector('[data-empresa-mapa]').click(), 0)`);
  conferir('e liga de novo', await p.avaliar(hachurados) === antes);

  // uma empresa nova, sem área: aviso na legenda e o botão de cadastrar
  await p.avaliar(`fetch('/api/empresas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nome: 'Outra Distribuidora',
    sigla: 'OUT', dominio: 'out.example', admin_nome: 'Admin Outra', admin_email: 'admin@out.example' }) }).then(r => r.status)`);
  await p.avaliar(`carregarMapaEmpresas().then(() => irPara('empresas')).then(() => 0)`);
  const semArea = await p.avaliar(`(() => { const li = [...document.querySelectorAll('.legenda-empresa')].find(l => l.textContent.includes('OUT'));
    return li ? [li.textContent, !!li.querySelector('[data-empresa-area]')] : null; })()`);
  conferir('empresa sem área: "Área de atuação não cadastrada" e o botão para cadastrar', semArea && /Área de atuação não cadastrada/.test(semArea[0]) && semArea[1], J(semArea));
  // editor: estado, busca, marcar, resumo, confirmar
  await p.avaliar(`([...document.querySelectorAll('.legenda-empresa')].find(l => l.textContent.includes('OUT')).querySelector('[data-empresa-area]').click(), 0)`);
  await ate(p, `!$('editorArea').hidden && $('areaLista').children.length > 100`);
  conferir('editor da área: lista do estado com busca (IBGE)', await p.avaliar(`$('areaUf').options.length === 27 && $('areaUf').value === 'MG'`));
  await p.avaliar(`(() => { const b = $('areaBusca'); b.value = 'leopoldína'; b.dispatchEvent(new Event('input')); return 0; })()`);
  conferir('a busca filtra a lista (sem acento)', await p.avaliar(`$('areaLista').children.length === 1 && $('areaLista').textContent.includes('Leopoldina')`),
    await p.avaliar(`$('areaLista').children.length + ' ' + $('areaLista').textContent.slice(0, 80)`));
  await p.avaliar(`($('areaLista').querySelector('input').click(), 0)`);
  conferir('marcar conta na hora', await p.avaliar(`$('areaContagem').textContent.startsWith('1 ')`), await p.avaliar(`$('areaContagem').textContent`));
  conferir('o mapa do estado para clicar (municípios de MG)', await ate(p, `camadaEditorArea && camadaEditorArea.getLayers().length > 800`));
  await p.avaliar(`($('areaVerResumo').click(), 0)`);
  await ate(p, `estado.area?.resumo`);
  const resumo = await p.avaliar(`$('areaResumo').textContent`);
  conferir('resumo antes de salvar: X municípios, Y novos, Z removidos, W em sobreposição', /1 municípios, 1 novos, 0 removidos, 1 em sobreposição/.test(resumo), resumo);
  conferir('nada salvo antes de confirmar', await p.avaliar(`fetch('/api/empresas/mapa').then(r => r.json()).then(m => m.empresas.find(e => e.sigla === 'OUT').municipios.length === 0)`));
  await p.avaliar(`($('areaConfirmar').click(), 0)`);
  await ate(p, `$('editorArea').hidden && estado.mapaEmpresas.empresas.find(e => e.sigla === 'OUT').municipios.length === 1`);
  await ate(p, `!$('fichaEmpresa').hidden && document.activeElement?.id === 'fichaEmpresaTitulo'`);
  conferir('confirmado: área salva, legenda com o aviso de sobreposição e a tabela da sobreposição',
    await p.avaliar(`!!document.querySelector('.legenda-sobreposicao') && $('sobreposicaoEmpresas').textContent.includes('Leopoldina') && $('sobreposicaoEmpresas').textContent.includes('EMG, OUT')`));
  conferir('a ficha da empresa abre depois de salvar (cadastro e contagens, nada de aviso)', await p.avaliar(`!$('fichaEmpresa').hidden
    && $('fichaEmpresa').textContent.includes('Leopoldina') && $('fichaEmpresa').textContent.includes('Cadastrada por') && document.activeElement?.id === 'fichaEmpresaTitulo'`),
    await p.avaliar(`[$('fichaEmpresa').hidden, document.activeElement?.id, $('fichaEmpresa').textContent.slice(0, 160)].join(' | ')`));
  // pela tabela: o nome abre a ficha e dá zoom na área
  const zoomAntes = await p.avaliar(`mapa.getZoom()`);
  await p.avaliar(`(mapa.setZoom(5, { animate: false }), 0)`);
  await p.avaliar(`([...document.querySelectorAll('#listaEmpresas button[data-empresa-acao="ficha"]')].find(b => b.textContent.includes('EMG') || b.textContent.includes('Distribuidora EMG')).click(), 0)`);
  await ate(p, `$('fichaEmpresa').textContent.includes('EMG')`);
  await espera(800);
  conferir('clicar na empresa na tabela abre a ficha e dá zoom na área dela', await p.avaliar(`mapa.getZoom() > 5`), `${zoomAntes}`);
  const operacionais = pedidos.filter(([s, u]) => /\/api\/(municipios\/\d+\/(comunidades|rede)|historico|painel|comunidades|planilha|avisos)/.test(u));
  conferir('nada operacional pedido ao servidor (comunidades, rede, histórico, painel, planilha)', !operacionais.length, J(operacionais.slice(0, 4)));
  conferir('nenhuma resposta 403 nem 5xx', !pedidos.some(([s, u]) => u.startsWith(BASE) && (s === 403 || s >= 500)), J(pedidos.filter(([s]) => s === 403 || s >= 500).slice(0, 4)));

  // celular: legenda recolhível e sem rolagem horizontal
  await p.send('Emulation.setDeviceMetricsOverride', { width: 360, height: 640, deviceScaleFactor: 1, mobile: true });
  await espera(300);
  await p.avaliar(`($('botaoLegendaEmpresas').click(), 0)`);
  conferir('celular: a legenda recolhe (aria-expanded=false)', await p.avaliar(`$('botaoLegendaEmpresas').getAttribute('aria-expanded') === 'false' && $('listaLegendaEmpresas').hidden`));
  await p.avaliar(`($('botaoLegendaEmpresas').click(), 0)`);
  conferir('celular: sem rolagem horizontal', await p.avaliar(`document.documentElement.scrollWidth <= innerWidth`));
  await p.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  // inglês
  await p.avaliar(`trocarIdioma('en', false).then(() => 0)`);
  await espera(600);
  conferir('legenda em inglês', await p.avaliar(`$('listaLegendaEmpresas').textContent.includes('municipality') && $('botaoLegendaEmpresas').textContent.includes('Companies on the map')`),
    await p.avaliar(`$('listaLegendaEmpresas').textContent.slice(0, 200)`));
  await p.avaliar(`trocarIdioma('pt-BR', false).then(() => 0)`);
  conferir('nenhuma exceção nem violação da CSP', !p.excecoes.length && !(await p.avaliar('window.__csp')).length, J(p.excecoes.slice(0, 3)));
  await p.fechar();
}

// ---------- os outros perfis: o mapa operacional de sempre, só com a área da empresa ----------
{
  const p = await abrir(`${BASE}/`, { largura: 1280, altura: 800 });
  await entrar(p, 'consulta@emg.example');
  conferir('Consulta: mapa operacional (legenda de sempre, sem a das empresas)', await p.avaliar(`$('legendaEmpresas').hidden && !$('legenda').hidden && camadaConcessao?.getLayers().length > 0`),
    await p.avaliar(`JSON.stringify([typeof camadaConcessao, estado.concessao?.features?.length, estado.vista, estado.tela])`) + JSON.stringify(p.excecoes.slice(0, 2)));
  conferir('Consulta: o mapa mostra só os municípios da área da EMG', await p.avaliar(`fetch('/api/concessao').then(r => r.json()).then(g => g.features.length === camadaConcessao?.getLayers().length)`));
  await p.fechar();
}

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
