// Escolher quem será desligado (passo 3 do Novo aviso), com a base de clientes no formato da Energisa
// (testes/planilha/exemplos/demo/6_base_clientes.xlsx, UCs fictícias), contra a API de teste:
// - a base para no passo 3 (não vai direto à conferência); o contador "X de Y UCs selecionadas · Z comunidades" começa em 0;
// - as inativas ficam fora, com a contagem por bairro e por circuito (sem a UC) e a opção de incluir;
// - filtro pelo teclado (Espaço na caixa do circuito): o contador da tela é o mesmo número que o servidor confere;
// - área desenhada com cliques de verdade no mapa (os pontos não pegam o clique) e comunidade clicada no mapa;
// - mudar a escolha depois de conferir descarta a conferência; a planilha inteira; o aviso gerado guarda o critério
//   (histórico: "Quem foi desligado");
// - nenhuma UC nem coordenada no HTML; nenhuma exceção nem violação da CSP; 3 idiomas; celular (44 px, sem rolagem lateral).
// Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_escolha.mjs
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
if (!SENHAS['admin@emg.example']) { console.error('Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_escolha.mjs'); process.exit(2); }
const BASE_CLIENTES = join(RAIZ, 'testes', 'planilha', 'exemplos', 'demo', '6_base_clientes.xlsx');
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
const J = JSON.stringify;
const ate = (p, expr, ms = 60000) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > ${ms}) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);

async function escolherArquivo(p, caminho) {
  const { root } = await p.send('DOM.getDocument', { depth: 1 });
  const { nodeId } = await p.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#arquivo' });
  await p.send('DOM.setFileInputFiles', { nodeId, files: [caminho] });
}
// um clique de verdade no mapa (mouse), no ponto [lat, lon]
async function clicarNoMapa(p, lat, lon) {
  const { x, y } = await p.avaliar(`(() => { const r = mapa.getContainer().getBoundingClientRect(), q = mapa.latLngToContainerPoint([${lat}, ${lon}]);
    return { x: r.left + q.x, y: r.top + q.y }; })()`);
  for (const type of ['mousePressed', 'mouseReleased']) await p.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
  await espera(350);   // dois cliques rápidos seriam um duplo clique
}
async function tecla(p, key, code, keyCode) {
  for (const type of ['keyDown', 'keyUp']) await p.send('Input.dispatchKeyEvent', { type, key, code, windowsVirtualKeyCode: keyCode });
}
const CONTA = `({ x: contaSelecao(estado.leitura.base, estado.selecao, estado.sel).x, texto: $('contaEscolha').textContent })`;
// o mesmo critério que a tela mandaria, conferido pelo servidor: quantas escolhidas
const DO_SERVIDOR = `fetch('/api/planilha/escolha', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
  pacote: estado.leitura.pacote_base, criterio: criterioDe(estado.leitura.base, estado.selecao), data: '20/11', horario: '8h às 14h' }) })
  .then(r => r.json()).then(j => j.escolha?.conta.escolhidas ?? j.detail)`;

const p = await abrir(`${BASE}/`, { largura: 1440, altura: 900 });
await p.avaliar(`($('email').value = 'admin@emg.example', $('senha').value = ${J(SENHAS['admin@emg.example'])}, $('formEntrar').requestSubmit(), 0)`);
await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto' && estado.concessao && estado.config`);
await p.avaliar(`irPara('aviso').then(() => 0)`);
await escolherArquivo(p, BASE_CLIENTES);
await p.avaliar(`($('avancar').click(), 0)`);
await p.avaliar(`($('data').value = '2026-11-20', $('inicio').value = '08:00', $('fim').value = '14:00', 0)`);
await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('gerar').click(), 0)`);
await ate(p, `document.documentElement.dataset.farol === 'escolha' || $('estado').classList.contains('erro')`);
await ate(p, `camadaEscolhaComunidades && camadaEscolhaPontos`);

// ---------- o passo 3 ----------
const b = await p.avaliar(`({ lidas: estado.leitura.base.lidas, inativas: estado.leitura.base.linhas.inativa.reduce((n, v) => n + v, 0),
  passo: estado.passo, visivel: !!$('escolha').offsetParent, conta: $('contaEscolha').textContent, travado: $('conferirEscolha').disabled,
  motivo: $('motivoEscolha').textContent, listas: [...document.querySelectorAll('#escolha [data-lista]')].map(d => d.dataset.lista),
  inativasTexto: document.querySelector('#escolha .inativas strong')?.textContent || '', pontos: camadaEscolhaPontos.getLayers().length })`);
conferir('a base de clientes para no passo 3 (Escolher), com o contador em 0', b.passo === 3 && b.visivel && b.conta === `0 de ${b.lidas} UCs selecionadas · 0 comunidade(s)`
  && b.travado && /Escolha pelo menos um filtro/.test(b.motivo), J(b));
conferir('listas: comunidades, circuito, conjunto, transformador e bairro', J(b.listas) === J(['comunidade', 'circuito', 'conjunto', 'transformador', 'bairro']), J(b.listas));
conferir(`inativas fora por padrão: "${b.inativas} UC(s) inativa(s) não entram no aviso"`, b.inativas > 0 && b.inativasTexto === `${b.inativas} UC(s) inativa(s) não entram no aviso`, b.inativasTexto);
conferir('os pontos da base no mapa, num canvas (sem clique)', b.pontos === b.lidas && await p.avaliar(`mapa.getPane('escolhaPontos').style.pointerEvents === 'none'`));
await p.avaliar(`(document.querySelector('#escolha .inativas details').open = true, 0)`);
const inat = await p.avaliar(`[...document.querySelectorAll('#escolha .tabelas-inativas tbody tr')].map(tr => tr.textContent)`);
conferir('ver quais inativas: contagem por bairro e por circuito', inat.length > 2 && inat.every(l => !/\d{7,}/.test(l)), J(inat.slice(0, 4)));

// ---------- filtro pelo teclado ----------
await p.avaliar(`(document.querySelector('#escolha [data-lista=circuito]').open = true, 0)`);
await p.avaliar(`($('sel-circuito-0').focus(), 0)`);
await tecla(p, ' ', 'Space', 32);
await espera(300);
let c = await p.avaliar(CONTA), s = await p.avaliar(DO_SERVIDOR);
conferir(`Espaço na caixa do circuito: ${c.x} UCs, o mesmo número que o servidor confere`, c.x > 0 && c.x === s && /^\d+ de \d+ UCs selecionadas · \d+ comunidade/.test(c.texto),
  `${J(c)} servidor ${s}`);
await p.avaliar(`($('busca-bairro').value = ${J('a')}, $('busca-bairro').dispatchEvent(new Event('input', { bubbles: true })), 0)`);
conferir('a busca filtra a lista (sem acento e sem maiúscula)', await p.avaliar(`[...document.querySelectorAll('#itens-bairro .item-marcar')].every(l => normalizar(l.textContent).includes('a'))`));

// ---------- conferir; mudar a escolha descarta a conferência ----------
await p.avaliar(`($('conferirEscolha').click(), 0)`);
await ate(p, `document.documentElement.dataset.farol === 'conferencia' || $('estado').classList.contains('erro')`);
const conf = await p.avaliar(`({ passo: estado.passo, quem: document.querySelector('#conferencia .conta-fechada')?.textContent || '',
  conta: estado.resultado?.escolha?.conta, estado: $('estado').textContent })`);
conferir('conferir a escolha: passo 4 com o critério e a conta fechada', conf.passo === 4 && /Quem será desligado: circuito\(s\)/.test(conf.quem)
  && /Conta fechada: \d+ lidas = \d+ inativas fora \+ \d+ não escolhidas \+ \d+ escolhidas/.test(conf.quem) && conf.conta?.escolhidas === c.x, J(conf));
await p.avaliar(`($('voltarResultado').click(), 0)`);
await p.avaliar(`($('sel-circuito-0').click(), 0)`);
conferir('mudar a escolha depois de conferir descarta a conferência (confere de novo)', await p.avaliar(`estado.passo === 3 && !estado.resultado
  && document.querySelector('#funil [data-passo="4"]').disabled`));

// ---------- área desenhada com cliques de verdade no mapa ----------
const caixa = await p.avaliar(`(() => { const ln = estado.leitura.base.linhas, pts = ln.lat.map((a, i) => [a, ln.lon[i]]).filter(([a], i) => a !== null && !ln.inativa[i]);
  const la = pts.map(x => x[0]).sort((a, b) => a - b), lo = pts.map(x => x[1]).sort((a, b) => a - b), q = v => v[Math.floor(v.length / 4)], t3 = v => v[Math.floor(3 * v.length / 4)];
  return [q(la), q(lo), t3(la), t3(lo)]; })()`);
await p.avaliar(`(mapa.fitBounds([[${caixa[0]}, ${caixa[1]}], [${caixa[2]}, ${caixa[3]}]], { animate: false }), 0)`);
await espera(400);
await p.avaliar(`(document.querySelector('#escolha [data-sel=desenhar]').click(), 0)`);
for (const [la, lo] of [[caixa[0], caixa[1]], [caixa[0], caixa[3]], [caixa[2], caixa[3]], [caixa[2], caixa[1]]]) await clicarNoMapa(p, la, lo);
const desenho = await p.avaliar(`({ n: estado.selecao.desenho?.length, cursor: mapa.getContainer().classList.contains('desenhando'), passos: $('passosDesenho')?.textContent })`);
conferir('desenhando: cada clique no mapa é um canto (4 cliques, 4 cantos), cursor em cruz', desenho.n === 4 && desenho.cursor, J(desenho));
await p.avaliar(`(document.querySelector('#escolha [data-sel=concluir]').click(), 0)`);
await espera(300);
c = await p.avaliar(CONTA); s = await p.avaliar(DO_SERVIDOR);
conferir(`área desenhada: ${c.x} UCs, o mesmo número que o servidor confere`, c.x > 0 && c.x === s && await p.avaliar(`estado.selecao.poligonos.length === 1
  && /Área 1 · 4 vértices/.test($('blocoMapa').textContent)`), `${J(c)} servidor ${s}`);

// ---------- comunidade clicada no mapa ----------
const alvo = await p.avaliar(`(() => { const b = estado.leitura.base, n = itensDaLista(b, estado.selecao, 'comunidade');
  const i = n.reduce((m, x) => x[2] > m[2] ? x : m)[0], c = b.comunidades[i], m = b.municipios[c.municipio];
  const f = estado.territorios[m.codigo_ibge].features.find(f => f.properties.nome === c.nome);
  return { i, rotulo: f.properties.rotulo }; })()`);
await p.avaliar(`(estado.selecao.poligonos = [], selecaoMudou(true), mapa.setView(${J(alvo.rotulo)}, 15, { animate: false }), 0)`);
await espera(500);
const rot = Array.isArray(alvo.rotulo) ? alvo.rotulo : [alvo.rotulo.lat, alvo.rotulo.lng];
await clicarNoMapa(p, rot[0], rot[1]);
c = await p.avaliar(CONTA); s = await p.avaliar(DO_SERVIDOR);
conferir('clique numa comunidade do mapa: ela entra (e a caixa dela na lista fica marcada)', await p.avaliar(`estado.selecao.comunidades.has(${alvo.i})
  && $('sel-comunidade-${alvo.i}')?.checked`) && c.x > 0 && c.x === s, `${J(c)} servidor ${s}`);
await clicarNoMapa(p, rot[0], rot[1]);
conferir('outro clique na mesma comunidade: ela sai', await p.avaliar(`!estado.selecao.comunidades.has(${alvo.i})`));

// ---------- inativas e a planilha inteira ----------
await p.avaliar(`($('modo-planilha').click(), 0)`);
c = await p.avaliar(CONTA);
conferir(`a planilha inteira: ${b.lidas - b.inativas} de ${b.lidas} (sem as inativas)`, c.x === b.lidas - b.inativas, J(c));
await p.avaliar(`($('incluirInativas').click(), 0)`);
c = await p.avaliar(CONTA);
conferir('incluir as inativas: todas as linhas', c.x === b.lidas && await p.avaliar(`/inativa\\(s\\) incluída/.test(document.querySelector('#escolha .inativas strong').textContent)`), J(c));
await p.avaliar(`($('incluirInativas').click(), $('modo-escolha').click(), 0)`);

// ---------- nada de UC nem coordenada no HTML ----------
const html = await p.avaliar(`document.documentElement.outerHTML`);
const coords = await p.avaliar(`estado.leitura.base.linhas.lat.filter(Boolean).slice(0, 40).map(String)`);
conferir('nenhuma UC (NUMCDC) nem coordenada no HTML da página', !/\b0009\d{6}\b/.test(html) && !coords.some(v => html.includes(v)));

// ---------- 3 idiomas e celular ----------
for (const [idioma, re] of [['en', /^\d+ of \d+ UCs selected · \d+ communit/], ['es', /^\d+ de \d+ UC seleccionadas · \d+ comunidad/]]) {
  await p.avaliar(`trocarIdioma('${idioma}', false).then(() => 0)`);
  await espera(300);
  const tx = await p.avaliar(`({ conta: $('contaEscolha').textContent, titulo: $('tituloEscolha').textContent, passo: document.querySelector('#funil [data-passo="3"]').textContent })`);
  conferir(`idioma ${idioma}: o passo 3 traduzido`, re.test(tx.conta) && !/Escolher quem/.test(tx.titulo) && !/Escolher/.test(tx.passo), J(tx));
}
await p.avaliar(`trocarIdioma('pt-BR', false).then(() => 0)`);
await p.send('Emulation.setDeviceMetricsOverride', { width: 360, height: 740, deviceScaleFactor: 2, mobile: true });
await espera(500);
await p.avaliar(`(document.querySelectorAll('#escolha details').forEach(d => d.open = true), 0)`);
const cel = await p.avaliar(`({ rolagem: document.documentElement.scrollWidth > innerWidth + 1,
  pequenos: [...document.querySelectorAll('#escolha button, #escolha summary, #escolha input[type=search], #escolha .item-marcar, #escolha .opcao, #escolha .confirmar, #navEscolha button')]
    .filter(e => e.offsetParent).map(e => [e.id || e.className || e.tagName, Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])
    .filter(([, w, h]) => w < 44 || h < 44) })`);
conferir('celular (360 px): sem rolagem lateral e alvos de 44 px no passo 3', !cel.rolagem && !cel.pequenos.length, J(cel));
await p.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await espera(400);

// ---------- gerar com a escolha: o histórico guarda o critério ----------
await p.avaliar(`(document.querySelector('#escolha [data-lista=circuito]').open = true, $('sel-circuito-0').click(), 0)`);
await p.avaliar(`($('conferirEscolha').click(), 0)`);
await ate(p, `document.documentElement.dataset.farol === 'conferencia' || $('estado').classList.contains('erro')`);
await p.avaliar(`($('conferi').click(), $('avancarResultado').click(), 0)`);
await ate(p, `document.documentElement.dataset.farol === 'resultado' || $('estado').classList.contains('erro')`);
const id = await p.avaliar(`estado.resultado?.id`);
conferir('gerar o aviso com a escolha (passo 5)', !!id && await p.avaliar(`estado.passo === 5`), await p.avaliar(`$('estado').textContent`));
await p.avaliar(`irPara('historico').then(() => 0)`);
await ate(p, `document.querySelector('#listaHistorico [data-historico="${id}"]')`);
await p.avaliar(`(document.querySelector('#listaHistorico [data-historico="${id}"]').click(), 0)`);
await ate(p, `estado.origem === 'historico' && /Quem foi desligado/.test($('resumo').textContent)`);
const hist = await p.avaliar(`({ resumo: $('resumo').textContent, leitura: !!estado.leitura, pontos: !!camadaEscolhaPontos })`);
conferir('histórico: "Quem foi desligado: circuito(s) …" e os pontos da base somem', /Quem foi desligado: circuito\(s\) \S+ · \d+ UC\(s\)/.test(hist.resumo)
  && !hist.leitura && !hist.pontos, J(hist));

conferir('nenhuma exceção no navegador', !p.excecoes.length, J(p.excecoes.slice(0, 3)));
conferir('nenhuma violação da CSP', await p.avaliar(`window.__csp.length === 0`), J(await p.avaliar(`window.__csp`)));
await p.fechar();

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
