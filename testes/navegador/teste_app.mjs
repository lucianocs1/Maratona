// Teste da tela do app, com login e os 4 perfis, contra a API de teste (capturas e o PDF gerado).
// Rode pelo executor, que cria os usuários de teste num esquema próprio e sobe a API:
//   uv run python testes/navegador/rodar_teste_app.py
// - Entrar: senha errada mostra o erro; a senha temporária leva à troca obrigatória; depois, o app.
// - Operador: o funil (planilha, quando, conferir e avisos), o aviso na tela é idêntico ao da API, o mapa desenha as comunidades,
//   a edição atualiza o tempo, o PDF sai com o texto editado e o texto final fica no histórico.
// - Consulta: só o histórico, aviso só para ler. Admin da empresa: cadastra usuário e vê a senha
//   temporária uma vez. Admin do Norte: só empresas e registro. Dashboard com os números do histórico e busca no histórico.
// - Os pontos das UCs aparecem no mapa logo depois do envio (num canvas, sem o número da UC) e somem no
//   histórico e ao sair. Nenhuma UC nem coordenada no HTML da página; só requisições ao próprio servidor e à Esri; nenhuma
//   exceção nem violação da CSP; alvos de 44 px; celular sem rolagem horizontal.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { constants as zlibConst, inflateSync } from 'node:zlib';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
if (!SENHAS['operador@emg.example']) { console.error('Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py'); process.exit(2); }
const NOVA = 'Lanterna-do-Farol-2026';
const PLANILHA = join(RAIZ, 'saida', 'planilhas_teste', 'planilha_CF-0066.csv');
const CAP = join(RAIZ, 'saida', 'capturas_app');
mkdirSync(CAP, { recursive: true });
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
async function captura(p, nome) {
  const r = await p.send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(CAP, nome), Buffer.from(r.data, 'base64'));
}
const registrarRede = lista => async pg => { await pg.send('Network.enable'); pg.on('Network.requestWillBeSent', e => lista.push(e.request.url)); };
// blob: do próprio site é o MP3 já baixado, tocado da memória (não sai pela rede)
const externa = u => !u.startsWith(BASE + '/') && !u.startsWith('https://server.arcgisonline.com/') && !u.startsWith('data:') && !u.startsWith('blob:' + BASE + '/');
// espera uma condição na página (expressão JS), até 60 s
// o texto de um PDF do fpdf2: os fluxos comprimidos (zlib) e os textos entre parênteses (Latin-1)
function textoDoPdf(buf) {
  const s = buf.toString('latin1'), partes = [];
  // até endstream, sem exigir o \r\n antes (um \r no fim dos dados comprimidos não corta o fluxo); o que sobra depois do zlib é ignorado
  for (const m of s.matchAll(/stream\r?\n([\s\S]*?)endstream/g)) {
    try { partes.push(inflateSync(Buffer.from(m[1], 'latin1'), { finishFlush: zlibConst.Z_SYNC_FLUSH }).toString('latin1')); } catch (e) { /* imagem ou fluxo sem zlib */ }
  }
  return partes.join('\n').split('\n').map(l => [...l.matchAll(/\(((?:\\.|[^\\)])*)\)/g)].map(x => x[1].replace(/\\(.)/g, '$1')).join('')).filter(Boolean).join(' ');
}
const ate = (p, expr) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > 60000) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);

async function escolherArquivo(p, caminho) {
  const { root } = await p.send('DOM.getDocument', { depth: 1 });
  const { nodeId } = await p.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#arquivo' });
  await p.send('DOM.setFileInputFiles', { nodeId, files: [caminho] });
}
async function entrarNaTela(p, email, senha) {
  await p.avaliar(`($('email').value = ${JSON.stringify(email)}, $('senha').value = ${JSON.stringify(senha)}, $('estadoEntrar').textContent = '', $('formEntrar').requestSubmit(), 0)`);
  await ate(p, `estado.tela !== 'entrar' || $('estadoEntrar').textContent`);
  if (await p.avaliar(`estado.tela === 'app'`)) await ate(p, `estado.concessao && document.documentElement.dataset.farol === 'pronto'`);
  return p.avaliar(`({ tela: estado.tela, mensagem: $('estadoEntrar').textContent, abas: [...document.querySelectorAll('#abas button')].map(b => b.textContent) })`);
}
// os dois passos pela tela: Conferir a planilha; marcar "Conferi os números e o mapa"; Gerar aviso
async function gerar(p) {
  await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('form').requestSubmit(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'conferencia' || $('estado').classList.contains('erro')`);
  if (await p.avaliar(`document.documentElement.dataset.farol !== 'conferencia'`)) return p.avaliar(`$('estado').textContent`);
  await p.avaliar(`($('conferi').click(), $('avancarResultado').click(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'resultado' || $('estado').classList.contains('erro')`);
  return p.avaliar(`$('estado').textContent`);
}
const PEQUENOS = `[...document.querySelectorAll('button, input:not([type=file]), select, textarea, summary, a, .arquivo')]
  .filter(e => e.offsetParent && !e.closest('p, .leaflet-control-attribution'))
  .map(e => [e.id || e.className || e.tagName, Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])
  .filter(([, w, h]) => w < 44 || h < 44)`;

// ---------- Resposta esperada: a API, direto, com a mesma planilha (sessão do Admin da empresa) ----------
const login = await fetch(`${BASE}/api/entrar`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'admin@emg.example', senha: SENHAS['admin@emg.example'] }) });
const cookie = login.headers.get('set-cookie').split(';')[0];
const fd = new FormData();
fd.append('arquivo', new Blob([readFileSync(PLANILHA)]), 'planilha_CF-0066.csv');
fd.append('data', '20/11'); fd.append('horario', '8h às 14h'); fd.append('idioma', 'pt-BR'); fd.append('tipo', 'poda');
const conf = await (await fetch(`${BASE}/api/planilha`, { method: 'POST', body: fd, headers: { cookie, origin: BASE } })).json();
const esperado = await (await fetch(`${BASE}/api/avisos`, { method: 'POST', headers: { cookie, origin: BASE, 'Content-Type': 'application/json' },
  body: JSON.stringify({ pacote: conf.pacote, data: '20/11', horario: '8h às 14h', idioma: 'pt-BR', conferi: true, tipo: 'poda' }) })).json();
const ucs = readFileSync(PLANILHA, 'utf-8').split(/\r?\n/).slice(1).filter(Boolean).map(l => l.split(';'));

// ---------- 1. Operador: entrar, trocar a senha, gerar o aviso, PDF e histórico ----------
{
  const rede = [];
  const p = await abrir(`${BASE}/`, { largura: 1440, altura: 900, antesDeNavegar: registrarRede(rede) });
  conferir('sem sessão: abre a tela de entrar', await ate(p, `estado.tela === 'entrar'`));
  await captura(p, '0_entrar.png');
  const errada = await entrarNaTela(p, 'operador@emg.example', 'senha-errada-123');
  conferir('senha errada: mensagem de erro, continua em entrar', errada.tela === 'entrar' && /incorretos/.test(errada.mensagem), JSON.stringify(errada));
  const temp = await entrarNaTela(p, 'operador@emg.example', SENHAS['operador@emg.example']);
  conferir('senha temporária: leva à troca obrigatória', temp.tela === 'senha', JSON.stringify(temp));
  await p.avaliar(`($('senhaAtual').value = ${JSON.stringify(SENHAS['operador@emg.example'])}, $('senhaNova').value = ${JSON.stringify(NOVA)}, $('senhaNova2').value = 'outra-coisa-qualquer', $('formSenha').requestSubmit(), 0)`);
  conferir('senhas novas diferentes: avisa na tela', /não são iguais/.test(await p.avaliar(`$('estadoSenha').textContent`)));
  await p.avaliar(`($('senhaNova2').value = ${JSON.stringify(NOVA)}, $('formSenha').requestSubmit(), 0)`);
  await ate(p, `estado.tela === 'app' && estado.concessao && document.documentElement.dataset.farol === 'pronto'`);
  const ini = await p.avaliar(`({ tela: estado.tela, abas: [...document.querySelectorAll('#abas button')].map(b => b.textContent).join(','),
    conta: $('contaNome').textContent, municipios: estado.concessao?.features.length, idiomas: [...$('idioma').options].map(o => o.value).join(',') })`);
  conferir('depois da troca: app do Operador (Novo aviso, Histórico e Relatórios), 66 municípios, 3 idiomas',
    ini.tela === 'app' && ini.abas === 'Novo aviso,Histórico,Relatórios' && /Operador/.test(ini.conta) && ini.municipios === 66 && ini.idiomas === 'pt-BR,en,es', JSON.stringify(ini));

  // mapa inicial: de perto, o contorno e o nome das comunidades (antes de gerar aviso); de longe, só os municípios
  await p.avaliar(`(mapa.setView([-21.53, -42.64], 13), 0)`);
  await ate(p, `document.documentElement.dataset.mapa === 'z13' && camadaNomes`);
  const perto = await p.avaliar(`({ contornos: camadaBase ? camadaBase.getLayers().length : 0,
    nomes: [...document.querySelectorAll('.rotulo span')].map(e => e.textContent), html: document.querySelector('.rotulo')?.innerHTML })`);
  conferir('mapa inicial de perto: contornos e nomes das comunidades, sem gerar aviso',
    perto.contornos >= 100 && perto.nomes.length >= 5 && perto.nomes.every(n => n && !/[<>]/.test(n)), JSON.stringify({ ...perto, nomes: perto.nomes.slice(0, 6) }));
  await captura(p, '1b_comunidades_perto.png');
  // rede elétrica fictícia: aparece por padrão (de perto); o botão esconde e mostra, com o crédito do OSM só enquanto aparece
  await ate(p, `camadaRede && estado.redes['3138401']`);
  await p.avaliar(`(mapa.setZoom(14), 0)`);
  await ate(p, `document.documentElement.dataset.mapa === 'z14' && camadaRede`);
  const vistaRede = await p.avaliar(`({ partes: camadaRede ? camadaRede.getLayers().length : 0, legenda: !$('legendaRede').hidden,
    botao: $('botaoRede').getAttribute('aria-checked'), credito: document.querySelector('.leaflet-control-attribution').textContent.includes('OpenStreetMap'),
    chaves: estado.redes['3138401'].chaves.length })`);
  conferir('rede fictícia: aparece por padrão, com legenda e crédito do OSM', vistaRede.partes > 50 && vistaRede.legenda && vistaRede.credito
    && vistaRede.botao === 'true' && vistaRede.chaves > 10, JSON.stringify(vistaRede));
  await captura(p, '1c_rede_ficticia.png');
  await p.avaliar(`($('botaoLegenda').click(), 0)`);
  const minimizada = await p.avaliar(`({ itens: [...document.querySelectorAll('#legenda > li')].filter(l => l.offsetParent).length,
    texto: $('botaoLegenda').textContent.trim(), expandida: $('botaoLegenda').getAttribute('aria-expanded'), altura: $('legenda').getBoundingClientRect().height })`);
  await captura(p, '1d_legenda_minimizada.png');
  await p.avaliar(`($('botaoLegenda').click(), 0)`);
  conferir('camadas: o painel minimiza (só o botão "Camadas") e abre de novo', minimizada.itens === 1 && /Camadas$/.test(minimizada.texto)
    && minimizada.expandida === 'false' && minimizada.altura < 70 && await p.avaliar(`$('botaoLegenda').getAttribute('aria-expanded') === 'true'
    && [...document.querySelectorAll('#legenda > li')].filter(l => l.offsetParent).length > 5`), JSON.stringify(minimizada));
  await p.avaliar(`($('botaoRede').click(), 0)`);
  conferir('rede fictícia: o interruptor esconde (e tira o crédito)', await p.avaliar(`!camadaRede && $('legendaRede').hidden
    && !document.querySelector('.leaflet-control-attribution').textContent.includes('OpenStreetMap')`));
  await p.avaliar(`($('botaoRede').click(), 0)`);
  conferir('rede fictícia: o interruptor mostra de novo', await ate(p, `camadaRede && $('botaoRede').getAttribute('aria-checked') === 'true'`));
  // painel de camadas: interruptores (role=switch), contagem, legenda que abre e fecha, e a camada de clientes fictícios
  const camadas = await p.avaliar(`({ interruptores: [...document.querySelectorAll('#legenda [role=switch]')].map(b => b.id),
    cliente: !$('camadaClientes').hidden, ligadoPadrao: $('botaoClientes').getAttribute('aria-checked'),
    alvos: [...document.querySelectorAll('#legenda .interruptor, #legenda .expandir')].filter(e => e.offsetParent).every(e => e.getBoundingClientRect().height >= 43.5) })`);
  conferir('camadas: interruptores de comunidades, nomes, rede, clientes, localidades, calor e UCs, com alvo de 44 px; clientes desligada por padrão',
    camadas.interruptores.join() === 'botaoComunidades,botaoNomes,botaoRede,botaoClientes,botaoLocalidades,botaoCalor,botaoUcs' && camadas.cliente && camadas.ligadoPadrao === 'false' && camadas.alvos, JSON.stringify(camadas));
  await ate(p, `estado.resumoClientes && !$('contagemClientes').hidden`);
  const resumo = await p.avaliar(`({ total: estado.resumoClientes.total, chip: $('contagemClientes').textContent, classes: Object.keys(estado.resumoClientes.classes).join() })`);
  conferir('clientes fictícios: a contagem aparece ao lado do interruptor (só números)', resumo.total > 500000 && resumo.chip.replace(/\D/g, '') === String(resumo.total) && /Residencial/.test(resumo.classes), JSON.stringify(resumo));
  await p.avaliar(`(mapa.setZoom(14), $('botaoClientes').click(), 0)`);
  await ate(p, `camadaClientes && estado.clientesVista?.modo === 'densidade' && camadaClientes.getLayers().length > 20`);
  conferir('clientes fictícios: de longe, quadradinhos de densidade', await p.avaliar(`estado.clientesVista.celulas.length > 20 && $('botaoClientes').getAttribute('aria-checked') === 'true'
    && JSON.parse(localStorage.getItem('norte.camadas')).verClientes === true`));
  await p.avaliar(`(mapa.setZoom(16), 0)`);
  await ate(p, `estado.clientesVista?.modo === 'pontos' && camadaClientes && camadaClientes.getLayers().length > 10`);
  const pontos = await p.avaliar(`({ n: estado.clientesVista.pontos.length, formato: estado.clientesVista.pontos.slice(0, 50).every(q => q.length === 5 && q.every(v => typeof v === 'number' || typeof v === 'boolean')),
    texto: JSON.stringify(estado.clientesVista).match(/\d{9,}/g) })`);
  conferir('clientes fictícios: de perto, um ponto por cliente (só latitude, longitude, classe, vital e ativa; nenhum número de UC)', pontos.n > 10 && pontos.formato && !pontos.texto, JSON.stringify(pontos));
  await espera(700);   // o canvas do Leaflet redesenha no próximo quadro
  const pixels = await p.avaliar(`[...document.querySelectorAll('#mapa canvas')].map(c => { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i]) n++; return [c.width, Math.round(c.getBoundingClientRect().width), n]; })`);
  conferir('clientes fictícios: os pontos estão pintados e visíveis no canvas do mapa (largura na tela = largura do desenho)',
    pixels.some(([w, tela, n]) => n > 500 && tela >= w / 2 - 2), JSON.stringify(pixels));
  await captura(p, '1e_clientes_ficticios.png');
  await p.avaliar(`($('botaoNomes').click(), 0)`);
  conferir('camadas: o interruptor dos nomes tira os nomes do mapa', await p.avaliar(`!camadaNomes && $('botaoNomes').getAttribute('aria-checked') === 'false'`));
  await p.avaliar(`($('botaoNomes').click(), 0)`);
  await p.avaliar(`(document.querySelector('[data-expandir=legendaClientes]').click(), 0)`);
  conferir('camadas: a legenda de uma camada abre e fecha (aria-expanded)', await p.avaliar(`document.querySelector('[data-expandir=legendaClientes]').getAttribute('aria-expanded') === 'true'
    && !!document.querySelector('#legendaClientes .cli-vital')?.offsetParent`));
  await captura(p, '1f_camadas_clientes.png');
  await p.avaliar(`($('botaoClientes').click(), 0)`);
  conferir('clientes fictícios: o interruptor desliga e tira a camada', await p.avaliar(`!camadaClientes && $('botaoClientes').getAttribute('aria-checked') === 'false'`));
  // localidades oficiais do IBGE: interruptor, um ponto por localidade com nome, categoria e município, e a contagem
  await ate(p, `estado.localidades && !$('contagemLocalidades').hidden`);
  conferir('localidades oficiais: 470 buscadas, com a contagem ao lado do interruptor, e a camada desligada por padrão',
    await p.avaliar(`estado.localidades.length === 470 && $('contagemLocalidades').textContent.replace(/\D/g, '') === '470'
      && $('botaoLocalidades').getAttribute('aria-checked') === 'false' && !camadaLocalidades`));
  await p.avaliar(`($('botaoLocalidades').click(), 0)`);
  await ate(p, `camadaLocalidades`);
  const loc = await p.avaliar(`({ n: camadaLocalidades.getLayers().length, salvo: JSON.parse(localStorage.getItem('norte.camadas')).verLocalidades,
    dica: (() => { const l = camadaLocalidades.getLayers()[0], c = l.getTooltip().getContent(); return (typeof c === 'function' ? c(l) : c).textContent; })() })`);
  conferir('localidades oficiais: um ponto por localidade, com nome, categoria e município na dica, e o interruptor lembrado',
    loc.n === 470 && /localidade oficial do IBGE/.test(loc.dica) && loc.salvo === true, JSON.stringify(loc));
  await p.avaliar(`(mapa.setZoom(11), $('botaoClientes').getAttribute('aria-checked') === 'true' && $('botaoClientes').click(), 0)`);
  await espera(700);
  await captura(p, '1g_localidades_oficiais.png');
  await p.avaliar(`(mapa.setZoom(16), 0)`);
  await p.avaliar(`($('botaoLocalidades').click(), 0)`);
  conferir('localidades oficiais: o interruptor desliga e tira os pontos', await p.avaliar(`!camadaLocalidades && $('botaoLocalidades').getAttribute('aria-checked') === 'false'`));
  await p.avaliar(`(mapa.setZoom(13), 0)`);
  await ate(p, `document.documentElement.dataset.mapa === 'z13'`);
  await p.avaliar(`(mapa.setZoom(10), 0)`);
  await ate(p, `document.documentElement.dataset.mapa === 'z10'`);
  conferir('de longe: sem nomes nem contornos das comunidades', await p.avaliar(`!camadaNomes && !camadaBase`));
  // "Ir para": estado e município da concessão
  await p.avaliar(`(() => { const u = $('filtroUf'); u.value = 'MG'; u.dispatchEvent(new Event('change', { bubbles: true }));
    const m = $('filtroMunicipio'); m.value = '3138401'; m.dispatchEvent(new Event('change', { bubbles: true })); return 0; })()`);
  await espera(800);
  const irPara = await p.avaliar(`({ ufs: [...$('filtroUf').options].map(o => o.value).join(','), n: $('filtroMunicipio').options.length,
    dentro: camadaConcessao.getLayers().find(l => l.feature.properties.codigo_ibge === '3138401').getBounds().contains(mapa.getCenter()) })`);
  conferir('mapa: "Ir para" por estado e município aproxima no município escolhido', irPara.ufs.startsWith(',MG') && irPara.n > 10 && irPara.dentro,
    JSON.stringify(irPara));

  const visivel = id => `!!$('${id}').offsetParent`;
  await p.avaliar(`($('avancar').click(), 0)`);
  conferir('funil: sem planilha, o passo 1 não avança (e diz por quê)', await p.avaliar(`estado.passo === 1 && ${visivel('passo-1')}
    && $('estado').classList.contains('erro') && document.querySelector('#funil [data-passo="3"]').disabled`));
  await escolherArquivo(p, PLANILHA);
  await p.avaliar(`($('avancar').click(), 0)`);
  conferir('funil: com a planilha, passo 2 (data e horário)', await p.avaliar(`estado.passo === 2 && ${visivel('passo-2')} && !${visivel('passo-1')}
    && ${visivel('gerar')} && $('passo2Arquivo').textContent.includes('planilha_CF-0066.csv')`));
  await p.avaliar(`($('data').value = '2026-11-20', $('inicio').value = '08:00', $('fim').value = '14:00', 0)`);
  await p.avaliar(`(() => { const t = $('tipo'); t.value = 'outro'; t.dispatchEvent(new Event('change')); return 0; })()`);
  conferir('tipo "Outro": aparece o campo com o aviso de não escrever nome de cliente', await p.avaliar(`!$('tipoOutroRotulo').hidden
    && /Não escreva nome de cliente/.test($('tipoOutroAjuda').textContent) && [...$('tipo').options].length === 6`));
  await p.avaliar(`(() => { const t = $('tipo'); t.value = 'poda'; t.dispatchEvent(new Event('change')); return 0; })()`);
  await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('gerar').click(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'conferencia' || $('estado').classList.contains('erro')`);
  const msgConf = await p.avaliar(`$('estado').textContent`);
  conferir('conferir a planilha: conferência pronta, nada no histórico ainda', /^Conferência pronta: 758 cliente/.test(msgConf)
    && await p.avaliar(`fetch('/api/historico').then(r => r.json()).then(j => j.avisos.length === 1)`), msgConf);
  await espera(800);
  const conf3 = await p.avaliar(`({ visivel: ${visivel('conferencia')}, numeros: [...document.querySelectorAll('#conferencia dd')].map(d => d.textContent),
    amarelo: document.querySelector('#conferencia .alerta-amarelo')?.textContent || '', vermelho: !!document.querySelector('#conferencia .alerta-vermelho'),
    botao: $('avancarResultado').textContent, travado: $('avancarResultado').disabled, motivo: $('motivoGerar').textContent,
    json: !!document.querySelector('[data-conf=json]'), relatorio: !!document.querySelector('[data-conf=relatorio]') })`);
  conferir('conferência: números, suspeito amarelo (São João Nepomuceno), sem bloqueio vermelho, JSON e relatório',
    conf3.visivel && conf3.numeros[0] === '758' && conf3.numeros[1] === '2' && /São João Nepomuceno/.test(conf3.amarelo) && !conf3.vermelho
    && conf3.json && conf3.relatorio, JSON.stringify(conf3));
  conferir('conferência: "Gerar aviso" travado até marcar "Conferi os números e o mapa"', conf3.botao === 'Gerar aviso' && conf3.travado
    && /Conferi/.test(conf3.motivo), JSON.stringify(conf3));
  await captura(p, '2a_conferencia.png');
  await p.navegador.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: CAP, eventsEnabled: true });
  const nomesBaixados = [];
  p.navegador.on('Browser.downloadWillBegin', e => nomesBaixados.push(e.suggestedFilename));
  await p.avaliar(`(document.querySelector('[data-conf=relatorio]').click(), 0)`);
  await ate(p, `/Relatório da planilha baixado/.test($('estado').textContent)`);
  await espera(500);
  const rel = nomesBaixados.includes('farol-relatorio-planilha.csv') ? readFileSync(join(CAP, 'farol-relatorio-planilha.csv'), 'utf-8') : '';
  conferir('Baixar relatório (CSV): uma linha por linha, sem UC', rel.split(/\r?\n/).filter(Boolean).length === 2 + 758
    && !ucs.slice(0, 50).some(([uc]) => rel.includes(uc)), `${nomesBaixados} ${rel.slice(0, 80)}`);
  const conferencia = await p.avaliar(`({ passo: estado.passo, resumo: ${visivel('resumo')}, form: ${visivel('form')},
    texto: !!document.querySelector('#municipios textarea')?.offsetParent, listas: !!document.querySelector('#municipios .listas')?.offsetParent,
    titulo: $('tituloResultado').textContent })`);
  conferir('funil: passo 4 (conferir) mostra os números e as comunidades, sem o texto do aviso',
    conferencia.passo === 4 && conferencia.resumo && !conferencia.form && !conferencia.texto && conferencia.listas && /^Conferir/.test(conferencia.titulo),
    JSON.stringify(conferencia));
  const tela = await p.avaliar(`({ avisos: [...document.querySelectorAll('#municipios textarea')].map(t => t.value),
    titulos: [...document.querySelectorAll('.mun-cab h3')].map(h => h.textContent),
    comunidades: camadaComunidades ? camadaComunidades.getLayers().length : 0, resumo: $('resumo').textContent.replace(/\\s+/g, ' ') })`);
  conferir('a mensagem da rádio de cada município é idêntica à da API (modelo da empresa)',
    JSON.stringify(tela.avisos) === JSON.stringify(esperado.municipios.map(m => m.mensagem)) && esperado.municipios.every(m => /^Atenção, ouvintes\./.test(m.mensagem)),
    `\n  tela: ${JSON.stringify(tela.avisos)}\n  API:  ${JSON.stringify(esperado.municipios.map(m => m.mensagem))}`);
  conferir('municípios na ordem da API', JSON.stringify(tela.titulos) === JSON.stringify(esperado.municipios.map(m => `${m.nome}/${m.uf}`)), JSON.stringify(tela.titulos));
  conferir('mapa: comunidades afetadas desenhadas', tela.comunidades >= 8, String(tela.comunidades));
  const contornos = await p.avaliar(`camadaComunidades.getLayers().filter(l => !l.feature.properties.c).length`);
  conferir('mapa: contorno das outras comunidades dos municípios afetados', contornos > 20, String(contornos));
  const pts = await p.avaliar(`({ n: camadaUcs ? camadaUcs.getLayers().length : 0, botao: !$('botaoUcs').closest('li').hidden,
    canvas: !!document.querySelector('#mapa canvas'), dicas: camadaUcs.getLayers().slice(0, 50).map(l => {
      const c = l.getTooltip().getContent(); return typeof c === 'function' ? c(l).textContent : String(c); }) })`);
  const dicaComUc = pts.dicas.filter(d => /\d{6,}/.test(d));
  conferir('mapa: um ponto por UC válida (758), num canvas, dica sem número de UC', pts.n === 758 && pts.botao && pts.canvas && !dicaComUc.length,
    JSON.stringify({ ...pts, dicas: pts.dicas.slice(0, 2) }));
  await p.avaliar(`($('botaoUcs').click(), 0)`);
  const escondeu = await p.avaliar(`!camadaUcs && $('botaoUcs').getAttribute('aria-checked') === 'false'`);
  await p.avaliar(`($('botaoUcs').click(), 0)`);
  conferir('botão esconde e mostra as UCs', escondeu && await p.avaliar(`camadaUcs?.getLayers().length === 758`));
  // dica da UC com HTML no nome da comunidade: vira texto, nada é executado nem carregado
  const xss = await p.avaliar(`(() => {
    const m = estado.resultado.municipios.find(x => (x.pontos || []).some(pt => x.comunidades[pt[2]]));
    const c = m.comunidades[m.pontos.find(pt => m.comunidades[pt[2]])[2]], nome = c.nome;
    c.nome = '<img src=x onerror="window.__xss=1">Teste';
    desenharUcs();
    const l = camadaUcs.getLayers().find(x => { const d = x.getTooltip().getContent(); return (typeof d === 'function' ? d(x).textContent : String(d)).includes('<img'); });
    l?.openTooltip();
    const el = l?.getTooltip().getElement();
    const r = { achou: !!l, texto: el?.textContent || '', imgs: el ? el.querySelectorAll('img').length : -1 };
    l?.closeTooltip(); c.nome = nome; desenharUcs();
    return r; })()`);
  await new Promise(r => setTimeout(r, 300));
  conferir('dica da UC: HTML no nome vira texto (sem <img>, nada executado)', xss.achou && xss.imgs === 0
    && xss.texto.includes('<img src=x') && await p.avaliar(`window.__xss === undefined`), JSON.stringify(xss));
  conferir('resumo: 758 linhas e o prazo de 5 dias úteis', /758/.test(tela.resumo) && /5 dias úteis/.test(tela.resumo), tela.resumo);
  await captura(p, '2_resultado.png');
  await p.avaliar(`(camadaComunidades.getLayers().find(l => l.feature.properties.c).fire('click', { originalEvent: {} }), 0)`);
  await espera(600);
  const ev = await p.avaliar(`(() => { const ls = camadaComunidades.getLayers(), s = ls.find(l => estado.evidencia?.chave === chaveComunidade(l.feature));
    return { achou: !!s, borda: s?.options.color, peso: s?.options.weight, outras: ls.filter(l => l !== s && l.feature.properties.c).every(l => l.options.opacity <= .5 || l.options.fillOpacity < .3),
      nome: !!document.querySelector('#mapa .rotulo.destaque') }; })()`);
  conferir('mapa: clicar numa comunidade a põe em evidência (borda branca, nome em destaque, as outras apagadas)',
    ev.achou && ev.borda === '#FFFFFF' && ev.peso > 3 && ev.outras && ev.nome, JSON.stringify(ev));
  await captura(p, '2d_evidencia.png');
  await p.avaliar(`(camadaComunidades.getLayers().find(l => estado.evidencia && estado.evidencia.chave === chaveComunidade(l.feature)).fire('click', { originalEvent: {} }), 0)`);
  conferir('mapa: clicar de novo tira a evidência', await p.avaliar(`!estado.evidencia && !document.querySelector('#mapa .rotulo.destaque')`));
  await p.avaliar(`($('conferi').click(), 0)`);
  conferir('marcar "Conferi" libera o "Gerar aviso"', await p.avaliar(`!$('avancarResultado').disabled && estado.conferi`));
  await p.avaliar(`($('avancarResultado').click(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'resultado' || $('estado').classList.contains('erro')`);
  const msg = await p.avaliar(`$('estado').textContent`);
  conferir('gerar aviso: pronto e guardado no histórico', /^Pronto.*aviso nº \d+/.test(msg), msg);
  const sol = await p.avaliar(`$('solicitado').textContent`);
  conferir('aviso gerado: "Solicitado por" com o nome e o perfil do login, o código de verificação e o tipo',
    /^Solicitado por Operador da EMG \(Operador\) em \d{2}\/\d{2}\/\d{4} às \d{2}:\d{2} · código de verificação FRL-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}Tipo: Poda de árvores/.test(sol), sol);
  const avisos = await p.avaliar(`({ passo: estado.passo, resumo: ${visivel('resumo')}, texto: !!document.querySelector('#municipios textarea')?.offsetParent,
    novo: ${visivel('novoAviso')}, titulo: $('tituloResultado').textContent })`);
  conferir('funil: passo 5 (avisos) mostra o texto para a rádio e o "Novo desligamento"',
    avisos.passo === 5 && !avisos.resumo && avisos.texto && avisos.novo && /^Avisos para a rádio/.test(avisos.titulo), JSON.stringify(avisos));
  await captura(p, '2c_avisos.png');
  await p.avaliar(`($('verComparativo').click(), 0)`);
  await ate(p, `estado.vista === 'comparativo' && document.querySelector('#comparativo .comp')`);
  const comp = await p.avaliar(`({ textos: [...document.querySelectorAll('#comparativo .comp')].map(c => [...c.querySelectorAll('.texto-longo')].map(t => t.textContent)),
    economia: document.querySelector('#comparativo .comp .comp-economia')?.textContent, numeros: document.querySelector('#comparativo .comp-lado.hoje .comp-numeros')?.textContent })`);
  const m0 = esperado.municipios[0];
  conferir('comparativo: o aviso de hoje igual ao da API, ao lado do aviso por comunidade, com a economia de tempo',
    comp.textos[0]?.[0] === m0.hoje?.texto && comp.textos[0]?.[1] === m0.mensagem && /^\d+% menos tempo no ar$/.test(comp.economia || '')
    && comp.numeros?.startsWith(`${m0.hoje.locais} locais`), JSON.stringify({ economia: comp.economia, numeros: comp.numeros, hoje: comp.textos[0]?.[0]?.slice(0, 80) }));
  // custo no ar: a rádio cobra por spot de 30 s; o preço de referência vem da configuração e o operador pode mudar
  const brl = v => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
  const spH = Math.ceil(m0.hoje.segundos / 30), spF = Math.ceil(m0.segundos / 30);
  await ate(p, `document.querySelector('#comparativoTotal .comp-custo')`);
  const custo1 = await p.avaliar(`({ campo: !$('custoRadio').hidden, preco: $('precoSpot').value, ajuda: $('custoRadioAjuda').textContent,
    cartao: document.querySelector('#comparativo .comp .comp-custo')?.textContent.replace(/\\s/g, ' '),
    total: document.querySelector('#comparativoTotal .comp-custo')?.textContent.replace(/\\s/g, ' ') })`);
  const esperadoCartao = `Rádio (spots de 30 s): hoje ${spH} spot${spH === 1 ? '' : 's'} · ${brl(spH * 80)} · Farol ${spF} spot${spF === 1 ? '' : 's'} · ${brl(spF * 80)} · economia de ${brl((spH - spF) * 80)} por veiculação.`;
  conferir('custo: preço de referência de R$ 80 por spot de 30 s, spots inteiros, economia e aviso "a confirmar com a emissora"',
    custo1.campo && custo1.preco === '80' && /a confirmar com a emissora/.test(custo1.ajuda) && custo1.cartao === esperadoCartao, JSON.stringify({ custo1, esperadoCartao }));
  conferir('custo: o total da empresa também mostra spots e reais', /^Rádio \(spots de 30 s\): hoje \d+ spots? · R\$ [\d.,]+ · Farol \d+ spots? · R\$ [\d.,]+ · economia de R\$ [\d.,]+ por veiculação\.$/.test(custo1.total || ''), custo1.total);
  await p.avaliar(`($('precoSpot').value = '120,50', $('precoSpot').dispatchEvent(new Event('change', { bubbles: true })), 0)`);
  await p.avaliar(`($('veiculacoes').value = '3', $('veiculacoes').dispatchEvent(new Event('change', { bubbles: true })), 0)`);
  const custo2 = await p.avaliar(`document.querySelector('#comparativo .comp .comp-custo').textContent.replace(/\\s/g, ' ')`);
  conferir('custo: mudar o preço e as veiculações recalcula (R$ 120,50 x 3)', custo2.includes(brl(spH * 120.5 * 3)) && custo2.includes('em 3 veiculações'), custo2);
  await p.avaliar(`($('precoSpot').value = 'abc', $('precoSpot').dispatchEvent(new Event('change', { bubbles: true })), 0)`);
  conferir('custo: preço inválido volta ao valor anterior e avisa', await p.avaliar(`$('precoSpot').value === '120,5' && estado.erro && estado.radio.preco === 120.5`));
  await p.avaliar(`($('precoSpot').value = '80', $('precoSpot').dispatchEvent(new Event('change', { bubbles: true })), $('veiculacoes').value = '1', $('veiculacoes').dispatchEvent(new Event('change', { bubbles: true })), 0)`);
  await captura(p, '7_comparativo.png');
  await p.avaliar(`(document.querySelector('#comparativo [data-comp="hoje"]').click(), 0)`);
  conferir('comparativo: Ouvir o aviso de hoje (longo) toca o áudio', await ate(p, `document.querySelector('#comparativo [id^="tocador-hoje-"] audio')`));
  await p.avaliar(`irPara('aviso')`);

  const cod = esperado.municipios[0].codigo_ibge;

  // copiloto de IA (simulado nos testes): reescreve, o servidor confere, e "Desfazer edição" volta ao aviso da API
  const ia0 = await p.avaliar(`({ aviso: $('aviso-${cod}').value, botoes: document.querySelectorAll('[data-acao=ia][data-codigo="${cod}"]').length,
    rotulo: document.querySelector('#municipios .copiloto .ajuda')?.textContent })`);
  conferir('copiloto: botões dos pedidos e o aviso de que a IA é simulada', ia0.botoes === 5 && /simulado/.test(ia0.rotulo || ''), JSON.stringify(ia0));
  await p.avaliar(`(document.querySelector('[data-acao=ia][data-pedido=curto][data-codigo="${cod}"]').click(), 0)`);
  await ate(p, `/Verificado|Recusado/.test($('ia-status-${cod}').textContent)`);
  const ia1 = await p.avaliar(`({ texto: $('aviso-${cod}').value, status: $('ia-status-${cod}').textContent, estado: estado.avisos['${cod}'] })`);
  conferir('copiloto: "Mais curto" volta verificado, mais curto e com a mesma data e horário', /^Verificado/.test(ia1.status)
    && ia1.texto.length < ia0.aviso.length && ia1.texto === ia1.estado && ia1.texto.includes('20/11') && ia1.texto.includes('8h'),
    JSON.stringify({ status: ia1.status.slice(0, 200), tamanhos: [ia1.texto.length, ia0.aviso.length], igual: ia1.texto === ia1.estado }));
  await captura(p, '2f_copiloto.png');
  await p.avaliar(`(document.querySelector('[data-acao=ia][data-pedido=livre][data-codigo="${cod}"]').click(), 0)`);
  await ate(p, `/Recusado/.test($('ia-status-${cod}').textContent)`);
  const ia2 = await p.avaliar(`({ texto: $('aviso-${cod}').value, status: $('ia-status-${cod}').textContent })`);
  conferir('copiloto: pedido livre vazio é recusado na tela e o texto é mantido', ia2.texto === ia1.texto && /Recusado/.test(ia2.status), JSON.stringify(ia2));
  await p.avaliar(`(document.querySelector('[data-acao=restaurar][data-codigo="${cod}"]').click(), 0)`);
  conferir('copiloto: Desfazer edição volta ao aviso original e limpa o selo', await p.avaliar(`$('aviso-${cod}').value === ${JSON.stringify(ia0.aviso)}
    && !$('ia-status-${cod}').textContent`));
  const antes = await p.avaliar(`$('tempo-${cod}').textContent`);
  await p.avaliar(`(() => { const a = $('aviso-${cod}'); a.value = a.value + ' Mais informações pelo telefone da distribuidora.'; a.dispatchEvent(new Event('input', { bubbles: true })); return 0; })()`);
  const depois = await p.avaliar(`$('tempo-${cod}').textContent`);
  conferir('editar o aviso atualiza as palavras e o tempo no ar', antes !== depois && /palavras/.test(depois), `${antes} -> ${depois}`);

  // áudio: "Ouvir" gera o MP3 do texto atual e mostra o tocador; editar o texto tira o áudio antigo
  await p.avaliar(`(document.querySelector('[data-acao=ouvir][data-codigo="${cod}"]').click(), 0)`);
  const tocou = await ate(p, `(() => { const a = document.querySelector('#tocador-${cod} audio'); return a && a.readyState >= 1 && a.duration > 5; })()`);
  const dur = await p.avaliar(`document.querySelector('#tocador-${cod} audio')?.duration`);
  conferir('Ouvir: o tocador aparece com o áudio do texto atual', tocou, `${dur} s`);
  await captura(p, '2b_audio.png');
  await p.avaliar(`(() => { const a = $('aviso-${cod}'); a.value = a.value + ' '; a.dispatchEvent(new Event('input', { bubbles: true })); return 0; })()`);
  conferir('editar o texto tira o áudio antigo (não vale mais)', await p.avaliar(`!document.querySelector('#tocador-${cod} audio')`));
  // "Baixar áudio": o MP3 do texto editado vai para o disco
  await p.navegador.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: CAP, eventsEnabled: true });
  let nomeArq = '';
  p.navegador.on('Browser.downloadWillBegin', e => { nomeArq = e.suggestedFilename; });
  const baixou = new Promise(ok => p.navegador.on('Browser.downloadProgress', e => { if (e.state === 'completed') ok(true); }));
  await p.avaliar(`(document.querySelector('[data-acao=audio][data-codigo="${cod}"]').click(), 0)`);
  const ok = await Promise.race([baixou, espera(60000).then(() => false)]);
  const tamanho = ok && nomeArq ? readFileSync(join(CAP, nomeArq)).length : 0;
  conferir('Baixar áudio: o MP3 é salvo no disco', ok && /^farol-aviso-Leopoldina-20-11\.mp3$/.test(nomeArq) && tamanho > 100_000, `${nomeArq} ${Math.round(tamanho / 1024)} KB`);
  // servidor sem a voz (FAROL_AUDIO=0, produção no plano gratuito): sem Ouvir nem Baixar áudio, com o aviso na tela
  const semVoz = await p.avaliar(`(() => { estado.config.audio = false; desenharResultado(); desenharComparativo();
    const r = { botoes: document.querySelectorAll('[data-acao=ouvir], [data-acao=audio], [data-comp]').length,
      aviso: document.getElementById('municipios').textContent.includes('desligado neste servidor') };
    estado.config.audio = true; desenharResultado(); desenharComparativo(); return r; })()`);
  conferir('sem a voz no servidor: nenhum botão de áudio e o aviso na tela', !semVoz.botoes && semVoz.aviso, JSON.stringify(semVoz));

  // PDF: gerado no servidor com o texto editado (o arquivo é baixado; o texto final vai para o histórico)
  let nomePdf = '';
  p.navegador.on('Browser.downloadWillBegin', e => { if (e.suggestedFilename.endsWith('.pdf')) nomePdf = e.suggestedFilename; });
  await p.avaliar(`(document.querySelector('[data-acao=pdf][data-codigo="${cod}"]').click(), 0)`);
  await ate(p, `/PDF de .* baixado/.test($('estado').textContent)`);
  await espera(800);
  const bytesPdf = nomePdf ? readFileSync(join(CAP, nomePdf)) : Buffer.alloc(0);
  const roteiro = textoDoPdf(bytesPdf);
  writeFileSync(join(CAP, 'roteiro_leopoldina.txt'), roteiro);
  conferir('roteiro: "Solicitado por" com o código FRL e o tipo do desligamento', /Solicitado por Operador da EMG \(Operador\) em .* código de verificação FRL-/.test(roteiro)
    && roteiro.includes('poda de árvores'), roteiro.slice(-400));
  conferir('roteiro: texto editado, município, data, nº do aviso e código de verificação', roteiro.includes('Mais informações pelo telefone')
    && roteiro.includes('Leopoldina/MG') && roteiro.includes('em 20/11, das 8h às 14h') && /aviso nº \d+/.test(roteiro) && /SHA-256\): [0-9a-f]{16}/.test(roteiro), roteiro.slice(-300));
  const repetido = roteiro.match(/\(([^()]+)\) \(\1\)/);
  conferir('roteiro: homônimos com o distrito uma vez só', !repetido, repetido?.[0]);
  conferir('texto final guardado no histórico (selo na tela)', /guardado no histórico/.test(await p.avaliar(`$('final-${cod}').textContent`)));
  conferir('PDF do roteiro gerado no servidor e baixado', bytesPdf.subarray(0, 5).toString() === '%PDF-' && /^farol-aviso-leopoldina-20-11\.pdf$/.test(nomePdf),
    `${nomePdf} ${bytesPdf.length} bytes`);

  // envio para a rádio: sem rádio cadastrada, o alerta e o pedido ao Admin (o Operador não cadastra rádio, Fase J);
  // o Admin cadastra; valor e economia; WhatsApp e cópia (e-mail desligado aqui)
  const semRadio = await p.avaliar(`document.querySelector('#envio-${cod} .alerta-amarelo')?.textContent || ''`);
  conferir('envio: sem rádio cadastrada, o alerta lista as comunidades', /Sem rádio cadastrada para: .+\(.+\)/.test(semRadio), semRadio.slice(0, 120));
  conferir('envio (Operador): sem rádio, nada de "+ Nova rádio"; pede o cadastro ao Admin', await p.avaliar(`!document.querySelector('#envio-${cod} select[data-envio=radioId]')
    && /peça o cadastro ao Admin/.test($('envio-${cod}').textContent) && !!document.querySelector('#envio-${cod} [data-envio-acao=pedir]')`));
  await fetch(`${BASE}/api/radios`, { method: 'POST', headers: { cookie, origin: BASE, 'Content-Type': 'application/json' }, body: JSON.stringify({
    nome: 'Rádio Leopoldina FM (demonstração)', email: 'leopoldina.fm@example.com', whatsapp: '(32) 99999-0001', valor_padrao: '150,00', cobranca: 'minuto',
    alcance: { municipios: [cod] } }) });
  await p.avaliar(`carregarEnvios()`);
  await ate(p, `document.querySelector('#envio-${cod} [data-envio=valor]')`);
  conferir('envio: sem SMTP neste servidor, sem o botão de e-mail e com o aviso', await p.avaliar(`!document.querySelector('#envio-${cod} [data-envio-acao=email]')
    && /desligado neste servidor/.test($('envio-${cod}').textContent)`));
  const previa = await p.avaliar(`$('previa-${cod}').textContent`);
  conferir('rádio cadastrada pelo Admin: sugerida com o valor padrão; prévia com a economia calculada pelo tempo no ar',
    await p.avaliar(`document.querySelector('#envio-${cod} [data-envio=valor]').value === '150,00' && !document.querySelector('#envio-${cod} .alerta-amarelo')`)
    && /^custo R\$\s?[\d.,]+ · Economia: R\$\s?[\d.,]+ pelo tempo a menos no ar · .+ a menos no ar$/.test(previa), previa);
  await p.avaliar(`(() => { const i = document.querySelector('#envio-${cod} [data-envio=cobranca]'); i.value = 'fechado'; i.dispatchEvent(new Event('change', { bubbles: true })); return 0; })()`);
  const previaFechado = await p.avaliar(`$('previa-${cod}').textContent`);
  conferir('valor fechado sem o custo antigo: a prévia não inventa economia', /Economia: preencha "Quanto custaria do jeito antigo" para calcular/.test(previaFechado), previaFechado);
  await p.avaliar(`(() => { const i = document.querySelector('#envio-${cod} [data-envio=cobranca]'); i.value = 'minuto'; i.dispatchEvent(new Event('change', { bubbles: true })); return 0; })()`);
  await p.avaliar(`(window.__aberto = [], window.open = u => { window.__aberto.push(u); return null; }, window.confirm = () => true,
    navigator.clipboard.writeText = async () => {}, document.querySelector('#envio-${cod} [data-envio-acao=whatsapp]').click(), 0)`);
  await ate(p, `/WhatsApp aberto/.test($('estado').textContent) && document.querySelectorAll('#envio-${cod} .envios li').length === 1`);
  const wa = await p.avaliar(`window.__aberto[0] || ''`);
  conferir('WhatsApp: abre wa.me com o número da rádio e a mensagem; o envio fica na lista com valor e economia',
    wa.startsWith('https://wa.me/5532999990001?text=Aten%C3%A7%C3%A3o%2C%20ouvintes.') && /Economia: R\$\s?[\d.,]+ pelo tempo a menos no ar/.test(await p.avaliar(`$('envio-${cod}').textContent`)), wa.slice(0, 80));
  await p.avaliar(`(document.querySelector('#envio-${cod} [data-envio-acao=copia]').click(), 0)`);
  await ate(p, `document.querySelectorAll('#envio-${cod} .envios li').length === 2`);
  conferir('copiar a mensagem: o envio fica registrado', /cópia da mensagem/.test(await p.avaliar(`$('envio-${cod}').textContent`)));
  await captura(p, '2e_envio_radio.png');
  await p.avaliar(`($('novoAviso').click(), 0)`);
  conferir('Novo desligamento: volta ao passo 1, sem o resultado anterior na tela nem no mapa', await p.avaliar(`estado.passo === 1
    && !estado.resultado && $('resultado').hidden && !camadaUcs && !camadaComunidades && !$('municipios').children.length && !estado.arquivo`));

  // planilha de demonstração com equipamento vital rejeitado: alerta vermelho e nada é gerado
  await escolherArquivo(p, join(RAIZ, 'testes', 'planilha', 'exemplos', 'demo', '3_vital_rejeitado.xlsx'));
  await p.avaliar(`($('avancar').click(), 0)`);
  await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('gerar').click(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'conferencia' || $('estado').classList.contains('erro')`);
  await espera(500);
  const vit = await p.avaliar(`({ vermelho: document.querySelector('#conferencia .alerta-vermelho')?.textContent || '', caixa: $('conferi').disabled,
    botao: $('avancarResultado').disabled, erro: $('estado').classList.contains('erro'), roxo: estado.resultado.pontos_corrigidos.length })`);
  conferir('demo 3 (vital rejeitado): alerta vermelho com as 2 linhas, "Conferi" e "Gerar aviso" travados',
    /Bloqueado: 2 linha/.test(vit.vermelho) && /Linha \d+: rejeitada/.test(vit.vermelho) && vit.caixa && vit.botao && vit.erro, JSON.stringify(vit));
  const peqConf = await p.avaliar(PEQUENOS);
  conferir('conferência: alvos de toque de pelo menos 44 x 44 px', !peqConf.length, JSON.stringify(peqConf));
  await captura(p, '2d_vital_bloqueado.png');
  await p.avaliar(`(novoAviso(), 0)`);

  // histórico: o aviso aparece e abre com o texto final
  await p.avaliar(`irPara('historico')`);
  await ate(p, `document.querySelectorAll('#listaHistorico [data-historico]').length`);
  const n = await p.avaliar(`document.querySelectorAll('#listaHistorico [data-historico]').length`);
  conferir('histórico: os 2 avisos da empresa (o do teste e o do Operador)', n === 2, String(n));
  await captura(p, '4a_lista_historico.png');
  await p.avaliar(`(document.querySelector('#listaHistorico [data-historico]').click(), 0)`);
  await ate(p, `estado.origem === 'historico' && !$('resultado').hidden`);
  const doHist = await p.avaliar(`$('aviso-${cod}').value`);
  conferir('aviso do histórico abre com o texto final editado', doHist.includes('Mais informações pelo telefone'), doHist.slice(-80));
  await captura(p, '4_historico.png');
  conferir('aviso do histórico: sem pontos de UC no mapa', await p.avaliar(`!camadaUcs && $('botaoUcs').closest('li').hidden`));
  await p.avaliar(`(() => { const b = $('buscaHistorico'); b.value = 'piacatuba'; b.dispatchEvent(new Event('input')); return 0; })()`);
  const achou = await p.avaliar(`document.querySelectorAll('#listaHistorico [data-historico]').length`);
  await p.avaliar(`(() => { const b = $('buscaHistorico'); b.value = 'Cataguases'; b.dispatchEvent(new Event('input')); return 0; })()`);
  const nada = await p.avaliar(`({ n: document.querySelectorAll('#listaHistorico [data-historico]').length, msg: $('listaHistorico').textContent })`);
  await p.avaliar(`(() => { const b = $('buscaHistorico'); b.value = ''; b.dispatchEvent(new Event('input')); return 0; })()`);
  conferir('histórico: a busca acha a comunidade sem acento e filtra o que não tem', achou === 2 && nada.n === 0 && /Nenhum aviso com esse filtro/.test(nada.msg),
    JSON.stringify({ achou, nada }));
  // mudar a data e cancelar pelo histórico (o aviso aberto é o do Operador)
  conferir('histórico: quem gera aviso vê "Mudar a data" e "Cancelar"', await p.avaliar(`!$('acoesAviso').hidden && !!document.querySelector('[data-aviso=cancelar]')`));
  await p.avaliar(`($('novaData').value = '2026-11-21', $('novoInicio').value = '09:00', $('novoFim').value = '15:00', document.querySelector('[data-aviso=data]').click(), 0)`);
  await ate(p, `$('estado').textContent.includes('mudada para 21/11')`);
  const md = await p.avaliar(`({ n: estado.resultado.municipios.length, titulo: $('tituloResultado').textContent, lista: $('listaHistorico').textContent.slice(0, 300), estado: $('estado').textContent })`);
  conferir('mudar a data: o aviso e o cartão do histórico com a data nova', md.n > 0 && md.titulo.includes('21/11, 9h às 15h') && md.lista.includes('21/11, 9h às 15h'), JSON.stringify(md));
  await p.avaliar(`(window.confirm = () => true, $('motivoCancelar').value = 'chuva forte prevista', document.querySelector('[data-aviso=cancelar]').click(), 0)`);
  await ate(p, `/cancelado/.test($('estado').textContent)`);
  conferir('cancelar: marcado como cancelado, sem as ações, o chip no histórico', await p.avaliar(`estado.resultado.status === 'cancelado'
    && $('acoesAviso').hidden && /Desligamento cancelado/.test($('solicitado').textContent) && /Cancelado/.test($('listaHistorico').textContent)`));
  await captura(p, '4b_cancelado.png');

  await p.avaliar(`irPara('comparativo')`);
  await ate(p, `document.querySelector('#comparativo .comp') && document.querySelector('#comparativoTotal .comp-total')`);
  const compHist = await p.avaliar(`({ textos: document.querySelectorAll('#comparativo .comp-lado.hoje .texto-longo').length,
    aviso: document.querySelector('#comparativo .comp-lado.hoje .ajuda')?.textContent, total: $('comparativoTotal').textContent })`);
  conferir('comparativo do histórico: do aviso de hoje só as contagens, e o total da empresa', !compHist.textos
    && /só as contagens/.test(compHist.aviso || '') && /menos tempo no ar/.test(compHist.total), JSON.stringify(compHist));
  await p.avaliar(`irPara('painel')`);
  await ate(p, `document.querySelectorAll('#painelDash .kpi').length`);
  const dash = await p.avaliar(`({ kpis: [...document.querySelectorAll('#painelDash .kpi')].map(k => k.textContent),
    barras: document.querySelectorAll('#painelDash .barra-mes').length, legenda: !document.querySelector('.legenda-painel').hidden,
    leopoldina: camadaConcessao.getLayers().find(l => l.feature.properties.nome === 'Leopoldina').options.fillOpacity,
    top: document.querySelector('#painelDash .ranking-nome')?.textContent })`);
  conferir('dashboard: 2 avisos, 12 meses, Leopoldina no topo e pintada no mapa',
    dash.kpis.some(k => /^Avisos gerados2/.test(k)) && dash.barras === 12 && dash.legenda && dash.leopoldina > .3 && dash.top === 'Leopoldina/MG', JSON.stringify(dash));
  const mesDash = await p.avaliar(`document.querySelector('#painelDash .dash-bloco h2')?.textContent + ' | ' + document.querySelector('#painelDash .dash-bloco .kpis')?.textContent`);
  conferir('dashboard: o bloco do mês (gasto, economizado, desligamentos, no prazo)', /^Este mês/.test(mesDash) && /Gasto com rádio/.test(mesDash)
    && /Economizado/.test(mesDash) && /No prazo/.test(mesDash), mesDash.slice(0, 200));
  await captura(p, '6_dashboard.png');
  // "Pergunte ao painel" (IA simulada nos testes): a pergunta vira consulta e a tabela vem do histórico
  conferir('pergunte ao painel: cartão visível com a IA simulada e os exemplos', await p.avaliar(`!$('perguntaPainel').hidden
    && /simulada/.test($('perguntaAjuda').textContent) && document.querySelectorAll('#exemplosPergunta button').length === estado.config.ia.perguntas_exemplo.length`));
  await p.avaliar(`($('textoPergunta').value = 'Quais municípios tiveram mais avisos?', $('botaoPergunta').click(), 0)`);
  await ate(p, `document.querySelector('#respostaPergunta .tabela-pergunta')`);
  const perg = await p.avaliar(`({ texto: document.querySelector('#respostaPergunta .resposta-texto')?.textContent,
    linhas: [...document.querySelectorAll('#respostaPergunta tbody tr')].map(l => l.textContent), rodape: document.querySelector('#respostaPergunta .ajuda')?.textContent })`);
  conferir('pergunte ao painel: resposta com Leopoldina no topo, tabela e selo "Conferido"', /Leopoldina/.test(perg.texto || '') && /^Leopoldina\/MG/.test(perg.linhas[0] || '')
    && /^Conferido/.test(perg.rodape || '') && /Municípios com mais avisos/.test(perg.rodape), JSON.stringify(perg));
  await captura(p, '6b_pergunta_painel.png');
  await p.avaliar(`($('textoPergunta').value = 'qual a capital da França?', $('botaoPergunta').click(), 0)`);
  await ate(p, `/nenhuma consulta/.test($('respostaPergunta').textContent)`);
  conferir('pergunte ao painel: pergunta fora do assunto não inventa resposta e mostra exemplos', await p.avaliar(`!document.querySelector('#respostaPergunta table')
    && document.querySelectorAll('#respostaPergunta li').length === estado.config.ia.perguntas_exemplo.length`));
  // relatórios: o do mês, na tela e em PDF
  await p.avaliar(`irPara('relatorios')`);
  await ate(p, `document.querySelectorAll('#relatorio .kpi').length >= 7`);
  const relTela = await p.avaliar(`({ titulo: document.querySelector('#relatorio .subtitulo')?.textContent, kpi: document.querySelector('#relatorio .kpi-valor')?.textContent,
    blocos: [...document.querySelectorAll('#relatorio .dash-bloco h2')].map(h => h.textContent), radios: $('relRadio').options.length,
    texto: $('relatorio').textContent })`);
  conferir('relatórios: o mensal na tela (resumo com comparações, gráficos, por rádio, ocorrências, Como calculamos e o anexo)',
    relTela.kpi === '1' && /Relatório mensal/.test(relTela.titulo) && /cancel/i.test(relTela.texto) && relTela.blocos.includes('Resumo por rádio')
    && relTela.blocos.includes('Como calculamos') && relTela.blocos.some(b => /^Anexo/.test(b)) && relTela.blocos.some(b => /^Gasto mês a mês/.test(b))
    && relTela.radios === 2 && /Rádio Leopoldina FM/.test(relTela.texto) && !/\b3\d{9}\b/.test(relTela.texto),
    JSON.stringify({ radios: relTela.radios, leo: /Rádio Leopoldina FM/.test(relTela.texto), uc: /\b3\d{9}\b/.exec(relTela.texto)?.[0],
      fim: relTela.blocos.slice(-2) }));
  const largura = await p.avaliar(`(() => { const pn = document.querySelector('.painel');
    const largos = [...pn.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > pn.getBoundingClientRect().right + 1 && !e.closest('.rolagem'))
      .slice(0, 4).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().width));
    return { sobra: pn.scrollWidth - pn.clientWidth, largos }; })()`);
  conferir('relatórios: nada passa da largura do painel (sem rolagem lateral; tabelas rolam dentro do quadro)', largura.sobra <= 0, JSON.stringify(largura));
  let nomeRel = '';
  p.navegador.on('Browser.downloadWillBegin', e => { if (/farol-mensal/.test(e.suggestedFilename)) nomeRel = e.suggestedFilename; });
  await p.avaliar(`(document.querySelector('[data-rel=pdf]').click(), 0)`);
  await ate(p, `/Relatório baixado em PDF/.test($('estado').textContent)`);
  await espera(600);
  const relPdf = nomeRel ? textoDoPdf(readFileSync(join(CAP, nomeRel))) : '';
  conferir('relatório em PDF: gerado pelo Operador, com o código de verificação', /Gerado por Operador da EMG \(Operador\) em .* Código FRL-.* página 1 de \d+/.test(relPdf),
    `${nomeRel} ${relPdf.slice(0, 160)}`);
  await captura(p, '6b_relatorios.png');
  await p.avaliar(`irPara('historico')`);
  conferir('saindo do dashboard, o mapa volta ao normal', await p.avaliar(`document.querySelector('.legenda-painel').hidden`));

  const texto = await p.avaliar(`document.documentElement.outerHTML + document.body.innerText`);
  const vazou = ucs.filter(([uc, lat, lon]) => texto.includes(uc) || texto.includes(lat) || texto.includes(lon)).slice(0, 3);
  conferir('nenhuma UC nem coordenada da planilha na página', !vazou.length, JSON.stringify(vazou));
  const csp = await p.avaliar('window.__csp');
  conferir('nenhuma exceção nem violação da CSP', !p.excecoes.length && !csp.length, JSON.stringify([p.excecoes, csp]));
  conferir('só requisições ao próprio servidor e aos fundos da Esri', rede.length && !rede.some(externa), JSON.stringify(rede.filter(externa)));
  const peq = await p.avaliar(PEQUENOS);
  conferir('alvos de toque de pelo menos 44 x 44 px (computador)', !peq.length, JSON.stringify(peq));
  await p.avaliar(`($('sair').click(), 0)`);
  conferir('sair volta para a tela de entrar', await ate(p, `estado.tela === 'entrar'`));
  conferir('depois de sair, a API não aceita mais a sessão', await p.avaliar(`fetch('/api/eu').then(r => r.status === 401)`));
  conferir('depois de sair, nada do aviso anterior fica na página (computador compartilhado)',
    await p.avaliar(`!document.documentElement.outerHTML.includes('Mais informações pelo telefone') && !document.querySelectorAll('#abas button, #municipios *, #roteiro *').length && !camadaUcs`));
  await p.fechar();
}

// ---------- 2. Consulta, Admin da empresa e Admin do Norte ----------
{
  const p = await abrir(`${BASE}/`, { largura: 1440, altura: 900 });
  const c = await entrarNaTela(p, 'consulta@emg.example', SENHAS['consulta@emg.example']);
  await ate(p, `document.querySelectorAll('#painelDash .kpi').length > 0`);
  conferir('Consulta: Mapa, Histórico e Relatórios; abre no Mapa', c.tela === 'app' && c.abas.join(',') === 'Mapa,Histórico,Relatórios'
    && await p.avaliar(`estado.vista === 'painel' && !$('vista-painel').hidden`), JSON.stringify(c));
  await p.avaliar(`irPara('historico')`);
  await ate(p, `document.querySelectorAll('#listaHistorico [data-historico]').length`);
  await p.avaliar(`(document.querySelector('#listaHistorico [data-historico]').click(), 0)`);
  await ate(p, `!$('resultado').hidden && document.querySelector('#municipios textarea')`);
  const leitura = await p.avaliar(`({ readonly: [...document.querySelectorAll('#municipios textarea')].every(t => t.readOnly),
    desfazer: document.querySelectorAll('[data-acao=restaurar]').length, pdf: document.querySelectorAll('[data-acao=pdf]').length })`);
  conferir('Consulta: aviso só para ler (sem editar, desfazer nem PDF para a rádio)', leitura.readonly && !leitura.desfazer && leitura.pdf === 0, JSON.stringify(leitura));
  conferir('Consulta: vê quem pediu e o código, sem mudar a data nem cancelar', /^Solicitado por .+ código de verificação FRL-/.test(await p.avaliar(`$('solicitado').textContent`))
    && await p.avaliar(`$('acoesAviso').hidden`));
  await ate(p, `document.querySelectorAll('.envio-radio .envios li').length || document.querySelectorAll('[data-historico]').length > 1`);
  const envCon = await p.avaliar(`({ lista: document.querySelectorAll('.envio-radio .envios li').length, form: document.querySelectorAll('.envio-radio select, [data-envio-acao]').length })`);
  conferir('Consulta: vê os envios do aviso, sem o formulário de envio', envCon.form === 0, JSON.stringify(envCon));
  await p.navegador.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: CAP, eventsEnabled: true });
  let nomeComp = '';
  p.navegador.on('Browser.downloadWillBegin', e => { if (/comprovante/.test(e.suggestedFilename)) nomeComp = e.suggestedFilename; });
  await p.avaliar(`($('baixarComprovante').click(), 0)`);
  await ate(p, `/Comprovante do aviso nº \\d+ baixado/.test($('estado').textContent)`);
  await espera(600);
  const comp = nomeComp ? textoDoPdf(readFileSync(join(CAP, nomeComp))) : '';
  conferir('Consulta: baixa o comprovante do aviso (PDF com quem pediu, envios e o código)', /Comprovante do aviso nº \d+/.test(comp)
    && /Solicitado por/.test(comp) && /Envios às rádios/.test(comp) && /Gerado por Consulta da EMG \(Consulta\)/.test(comp), `${nomeComp} ${comp.slice(0, 160)}`);
  conferir('Consulta: nenhum ponto de UC no mapa', await p.avaliar(`!camadaUcs && $('botaoUcs').closest('li').hidden`));
  conferir('Consulta: a API recusa gerar aviso (403)', await p.avaliar(`fetch('/api/avisos', { method: 'POST' }).then(r => r.status === 403)`));
  const semAudio = await p.avaliar(`(() => { desenharComparativo();
    return document.querySelectorAll('[data-acao=ouvir], [data-acao=audio], [data-comp]').length; })()`);
  conferir('Consulta: sem Ouvir nem Baixar áudio (no aviso e no comparativo)', semAudio === 0, String(semAudio));
  conferir('Consulta: a API recusa gerar áudio (403)', await p.avaliar(`fetch('/api/audio', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ texto: 'teste' }) }).then(r => r.status === 403)`));
  await p.avaliar(`($('sair').click(), 0)`); await ate(p, `estado.tela === 'entrar'`);

  const a = await entrarNaTela(p, 'admin@emg.example', SENHAS['admin@emg.example']);
  conferir('Admin da empresa: Novo aviso, Histórico, Relatórios, Usuários, Rádios, Configurações e Auditoria',
    a.abas.join(',') === 'Novo aviso,Histórico,Relatórios,Usuários,Rádios,Configurações,Auditoria', JSON.stringify(a.abas));
  await p.avaliar(`irPara('usuarios')`);
  await ate(p, `document.querySelectorAll('#listaUsuarios [data-usuario]').length >= 3`);
  await p.avaliar(`($('novoNome').value = 'Maria Operadora', $('novoEmail').value = 'maria@emg.example', $('novoPerfil').value = 'operador', $('formUsuario').requestSubmit(), 0)`);
  await ate(p, `!$('caixaSenha').hidden`);
  const caixa = await p.avaliar(`({ senha: $('caixaSenhaValor').textContent, texto: $('caixaTexto').textContent, n: document.querySelectorAll('#listaUsuarios [data-usuario]').length })`);
  conferir('cadastrar usuário mostra a senha temporária uma vez', /^[A-Za-z2-9]{4}(-[A-Za-z2-9]{4}){3}$/.test(caixa.senha) && /Maria Operadora/.test(caixa.texto), JSON.stringify(caixa));
  await captura(p, '5_usuarios.png');
  await p.avaliar(`($('caixaFechar').click(), 0)`);
  conferir('fechar a caixa apaga a senha da página', await p.avaliar(`$('caixaSenha').hidden && !$('caixaSenhaValor').textContent && !document.body.innerText.includes(${JSON.stringify(caixa.senha)})`));
  await p.avaliar(`irPara('registro')`);
  await ate(p, `document.querySelectorAll('#listaRegistro tbody tr').length`);
  const reg = await p.avaliar(`[...document.querySelectorAll('#listaRegistro tbody tr')].map(t => t.textContent).join(' | ')`);
  conferir('registro da empresa: cadastro de usuário, aviso gerado e texto final', /cadastrou usuário/.test(reg) && /gerou aviso/.test(reg) && /guardou o texto final/.test(reg), reg.slice(0, 200));
  conferir('auditoria da empresa: PDF, rádio cadastrada, valor informado e envio por WhatsApp', /gerou PDF/.test(reg) && /cadastrou rádio/.test(reg)
    && /informou o valor do envio/.test(reg) && /enviou por WhatsApp/.test(reg), reg.slice(0, 300));
  conferir('auditoria da empresa: importou, conferiu, mudou a data e cancelou, com o nome e o perfil de quem fez',
    /importou planilha/.test(reg) && /conferiu os números e o mapa/.test(reg) && /Operador da EMG \(Operador\)/.test(reg)
    && /mudou a data do aviso/.test(reg) && /cancelou o aviso/.test(reg) && /FRL-[0-9A-F]{4}/.test(reg), reg.slice(0, 300));
  await p.avaliar(`($('verificarAuditoria').click(), 0)`);
  conferir('auditoria: "Conferir a integridade" diz que está íntegra', await ate(p, `/^Auditoria íntegra/.test($('estadoAuditoria').textContent)`));
  await captura(p, '5b_auditoria.png');
  let nomeAud = '';
  p.navegador.on('Browser.downloadWillBegin', e => { if (/auditoria/.test(e.suggestedFilename)) nomeAud = e.suggestedFilename; });
  await p.navegador.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: CAP, eventsEnabled: true });
  await p.avaliar(`(document.querySelector('[data-aud=csv]').click(), 0)`);
  await ate(p, `/Relatório baixado em CSV/.test($('estadoAuditoria').textContent)`);
  await espera(600);
  const audCsv = nomeAud ? readFileSync(join(CAP, nomeAud), 'utf-8') : '';
  conferir('relatório de auditoria em CSV (Admin da empresa): gerado por, código e as ações', /gerado_por;Admin da EMG \(Admin da empresa\)/.test(audCsv)
    && /codigo_verificacao;FRL-/.test(audCsv) && /;gerou aviso;/.test(audCsv), audCsv.slice(0, 200));

  // Rádios (Admin da empresa): cadastrar com um município inteiro e duas comunidades de outro, e editar
  await p.avaliar(`irPara('radios')`);
  await ate(p, `$('radMunicipios').options.length > 60`);
  await p.avaliar(`(() => { $('radNome').value = 'Rádio Cataguases AM (demonstração)'; $('radEmail').value = 'cataguases@example.com';
    $('radValor').value = '200,00'; $('radCobranca').value = 'fechado';
    [...$('radMunicipios').options].find(o => o.textContent.startsWith('Cataguases')).selected = true;
    const s = $('radMunCom'); s.value = '3138401'; s.dispatchEvent(new Event('change')); return 0; })()`);
  await ate(p, `document.querySelectorAll('#radComunidades input[type=checkbox]').length > 50`);
  await p.avaliar(`(() => { const cs = [...document.querySelectorAll('#radComunidades input[type=checkbox]')];
    for (const n of ['Piacatuba (Piacatuba)', 'Graminha (Piacatuba)']) { const c = cs.find(x => x.nextSibling.textContent === n); c.checked = true;
      c.dispatchEvent(new Event('change', { bubbles: true })); }
    $('formRadio').requestSubmit(); return 0; })()`);
  await ate(p, `/cadastrada/.test($('estadoRadio').textContent) && document.querySelectorAll('#listaRadios [data-radio]').length`);
  const radioTela = await p.avaliar(`$('listaRadios').textContent`);
  conferir('Rádios: cadastra com o município inteiro e as comunidades escolhidas (com o distrito)', /Rádio Cataguases AM/.test(radioTela)
    && /Cataguases\/MG e 2 comunidade\(s\)/.test(radioTela), radioTela.slice(0, 200) + ' | ' + await p.avaliar(`$('estadoRadio').textContent`));
  await p.avaliar(`(document.querySelector('#listaRadios [data-radio-acao=editar]').click(), 0)`);
  await p.avaliar(`($('radAtiva').checked = false, $('formRadio').requestSubmit(), 0)`);
  await ate(p, `/alterada/.test($('estadoRadio').textContent)`);
  conferir('Rádios: editar e desativar', /\(inativa\)/.test(await p.avaliar(`$('listaRadios').textContent`)));
  await captura(p, '5c_radios.png');
  // Configurações: o modelo da mensagem com a prévia, e salvar
  await p.avaliar(`irPara('configuracoes')`);
  await ate(p, `$('cfgModelo').value.includes('{comunidades}')`);
  await p.avaliar(`(() => { const t = $('cfgTelefone'); t.value = '0800 000 0000'; t.dispatchEvent(new Event('input', { bubbles: true })); return 0; })()`);
  const previa = await p.avaliar(`$('cfgPrevia').textContent`);
  conferir('Configurações: prévia da mensagem pelo modelo (com o telefone novo)', /^Exemplo: Atenção, ouvintes\./.test(previa) && /Dúvidas: 0800 000 0000\.$/.test(previa), previa);
  await p.avaliar(`($('formConfig').requestSubmit(), 0)`);
  await ate(p, `/Configurações salvas/.test($('estadoConfig').textContent)`);
  await p.avaliar(`(() => { $('cfgModelo').value = 'no dia {data} {cliente}'; $('formConfig').requestSubmit(); return 0; })()`);
  await ate(p, `$('estadoConfig').classList.contains('erro')`);
  conferir('Configurações: modelo com campo desconhecido é recusado na tela', /desconhecido/.test(await p.avaliar(`$('estadoConfig').textContent`)));
  await captura(p, '5d_configuracoes.png');
  // Ajuda e dicas
  await p.avaliar(`($('botaoAjuda').click(), 0)`);
  const ajuda = await p.avaliar(`({ aberta: !$('caixaAjuda').hidden, texto: $('ajudaCorpo').textContent })`);
  conferir('Ajuda: explica o caminho do perfil (Admin da empresa: aviso, rádios, usuários, auditoria)', ajuda.aberta && /Conferir/.test(ajuda.texto)
    && /Rádios e configurações/.test(ajuda.texto) && /Auditoria/.test(ajuda.texto), ajuda.texto.slice(0, 120));
  await p.avaliar(`(document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })), 0)`);
  conferir('Ajuda: fecha com Esc', await p.avaliar(`$('caixaAjuda').hidden`));
  // menu da conta no topo: iniciais, itens na ordem, Esc fecha e devolve o foco, clique fora fecha
  await p.avaliar(`($('botaoConta').click(), 0)`);
  const mc = await p.avaliar(`({ aberto: !$('menuConta').hidden, exp: $('botaoConta').getAttribute('aria-expanded'), itens: itensDoMenuConta().map(e => e.id),
    ini: $('contaAvatar').textContent, nome: $('contaNome').textContent.length > 3, topo: [...document.querySelectorAll('.topo-acoes > *')].length })`);
  conferir('menu da conta: abre com iniciais e os itens Acessibilidade, idioma, tema, Ajuda e Sair',
    mc.aberto && mc.exp === 'true' && mc.itens.join() === 'botaoAcessibilidade,idiomaTela,botaoTema,botaoAjuda,sair' && /^[A-ZÀ-Ý]{1,2}$/.test(mc.ini) && mc.nome && mc.topo === 2, JSON.stringify(mc));
  await captura(p, '5g_menu_conta.png');
  await p.avaliar(`(document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })), 0)`);
  conferir('menu da conta: Esc fecha e o foco volta ao botão', await p.avaliar(`$('menuConta').hidden && document.activeElement?.id === 'botaoConta' && $('botaoConta').getAttribute('aria-expanded') === 'false'`));
  await p.avaliar(`($('botaoConta').click(), document.body.click(), 0)`);
  conferir('menu da conta: clicar fora fecha', await p.avaliar(`$('menuConta').hidden`));
  await p.avaliar(`(document.querySelector('.legenda [data-dica=vizinha]').click(), 0)`);
  conferir('dica "?": explica o termo (localidade vizinha)', await p.avaliar(`!$('dica').hidden && /Localidade vizinha/.test($('dica').textContent)`));
  // tema escuro em todas as telas: cores do Norte, fundo do mapa escuro, alvos de 44 px
  await p.avaliar(`(document.documentElement.dataset.tema = 'claro', desenharTema(), trocarFundoDoMapa(), 0)`);   // o navegador de teste prefere o escuro
  const antes = await p.avaliar(`document.documentElement.dataset.tema + '/' + temaAtual()`);
  await p.avaliar(`($('botaoTema').click(), 0)`);
  const tema = await p.avaliar(`({ tema: document.documentElement.dataset.tema, fundo: getComputedStyle(document.body).backgroundColor,
    botao: $('botaoTema').textContent, mapa: [...document.querySelectorAll('.leaflet-tile')].some(t => t.src.includes('Dark_Gray')) })`);
  conferir('tema escuro: Noite no fundo, botão "Tema claro" e o fundo do mapa escuro', tema.tema === 'escuro' && tema.fundo === 'rgb(11, 27, 43)'
    && tema.botao === 'Tema claro' && tema.mapa, JSON.stringify({ antes, ...tema }));
  const pequenosTemas = [];
  for (const v of ['aviso', 'historico', 'relatorios', 'usuarios', 'radios', 'configuracoes', 'registro']) {
    await p.avaliar(`irPara('${v}')`);
    await espera(300);
    pequenosTemas.push(...(await p.avaliar(PEQUENOS)).map(x => `${v}:${x}`));
  }
  conferir('tema escuro: alvos de 44 px em todas as telas do Admin da empresa', !pequenosTemas.length, JSON.stringify(pequenosTemas.slice(0, 5)));
  await p.avaliar(`irPara('radios')`);
  await captura(p, '5e_tema_escuro.png');
  await p.avaliar(`($('botaoTema').click(), 0)`);
  await p.avaliar(`($('sair').click(), 0)`); await ate(p, `estado.tela === 'entrar'`);
  await captura(p, '0b_entrar_farol.png');

  const f = await entrarNaTela(p, 'admin@farol.example', SENHAS['admin@farol.example']);
  conferir('Admin do Norte: só Empresas e Auditoria geral', f.abas.join(',') === 'Empresas,Auditoria geral', JSON.stringify(f.abas));
  await ate(p, `document.querySelectorAll('#listaEmpresas tbody tr').length`);
  conferir('Admin do Norte: a empresa EMG na lista', /EMG/.test(await p.avaliar(`$('listaEmpresas').textContent`)));
  await p.avaliar(`($('empNome').value = 'Cooperativa Teste', $('empCnpj').value = '12.ABC.345/01DE-35', $('empSigla').value = 'CTT',
    $('empDominio').value = 'ctt.example', $('empAdminNome').value = 'Admin CTT', $('empAdminEmail').value = 'admin@ctt.example', $('formEmpresa').requestSubmit(), 0)`);
  await ate(p, `!$('caixaSenha').hidden`);
  await p.avaliar(`($('caixaFechar').click(), 0)`);
  await ate(p, `$('listaEmpresas').textContent.includes('12.ABC.345/01DE-35')`);
  await p.avaliar(`(window.confirm = () => true, [...document.querySelectorAll('#listaEmpresas [data-empresa]')].find(t => t.textContent.includes('CTT'))
    .querySelector('[data-empresa-acao=suspensa]').click(), 0)`);
  await ate(p, `/suspensa/.test($('estadoEmpresa').textContent)`);
  conferir('Empresas: cadastra com CNPJ alfanumérico e suspende (situação na lista)', await p.avaliar(`[...document.querySelectorAll('#listaEmpresas [data-empresa]')]
    .find(t => t.textContent.includes('CTT'))?.textContent.includes('Suspensa')`), await p.avaliar(`$('estadoEmpresa').textContent + ' | ' + $('listaEmpresas').textContent.slice(0, 300)`));
  await captura(p, '5f_empresas.png');
  conferir('nenhuma exceção nem violação da CSP (perfis)', !p.excecoes.length && !(await p.avaliar('window.__csp')).length, JSON.stringify(p.excecoes));
  await p.fechar();
}

// ---------- 3. Celular: entrar, gerar e planilha inválida ----------
{
  const p = await abrir(`${BASE}/`, { largura: 390, altura: 844 });
  conferir('celular: tela de entrar sem rolagem horizontal', await p.avaliar('document.documentElement.scrollWidth <= innerWidth'));
  await entrarNaTela(p, 'admin@emg.example', SENHAS['admin@emg.example']);
  await escolherArquivo(p, join(RAIZ, 'testes', 'navegador', 'exemplos', 'area_teste_sem_poligono.geojson'));
  const erroExt = await gerar(p);
  conferir('arquivo que não é .csv nem .xlsx: erro na tela, sem enviar', /\.csv ou \.xlsx/.test(erroExt), erroExt);
  await escolherArquivo(p, PLANILHA);
  const msg = await gerar(p);
  conferir('celular: gera o aviso', /^Pronto/.test(msg), msg);
  await espera(800);
  conferir('celular: sem rolagem horizontal', await p.avaliar('document.documentElement.scrollWidth <= innerWidth'));
  const peq = await p.avaliar(PEQUENOS);
  conferir('alvos de toque de pelo menos 44 x 44 px (celular)', !peq.length, JSON.stringify(peq));
  await captura(p, '3_celular.png');
  await p.fechar();
}

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK (capturas e PDF em ${CAP})`);
process.exit(falhas ? 1 : 0);
