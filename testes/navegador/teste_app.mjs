// Teste da tela do app, com login e os 4 perfis, contra a API de teste (capturas e o PDF gerado).
// Rode pelo executor, que cria os usuários de teste num esquema próprio e sobe a API:
//   uv run python testes/navegador/rodar_teste_app.py
// - Entrar: senha errada mostra o erro; a senha temporária leva à troca obrigatória; depois, o app.
// - Operador: o funil (planilha, quando, conferir e avisos), o aviso na tela é idêntico ao da API, o mapa desenha as comunidades,
//   a edição atualiza o tempo, o PDF sai com o texto editado e o texto final fica no histórico.
// - Consulta: só o histórico, aviso só para ler. Admin da empresa: cadastra usuário e vê a senha
//   temporária uma vez. Admin do Farol: só empresas e registro. Dashboard com os números do histórico e busca no histórico.
// - Os pontos das UCs aparecem no mapa logo depois do envio (num canvas, sem o número da UC) e somem no
//   histórico e ao sair. Nenhuma UC nem coordenada no HTML da página; só requisições ao próprio servidor e à Esri; nenhuma
//   exceção nem violação da CSP; alvos de 44 px; celular sem rolagem horizontal.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
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
async function gerar(p) {
  await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('form').requestSubmit(), 0)`);
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
fd.append('data', '20/11'); fd.append('horario', '8h às 14h'); fd.append('idioma', 'pt-BR');
const esperado = await (await fetch(`${BASE}/api/avisos`, { method: 'POST', body: fd, headers: { cookie } })).json();
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
  conferir('depois da troca: app do Operador (Novo aviso, Histórico, Dashboard e Comparativo), 66 municípios, 3 idiomas',
    ini.tela === 'app' && ini.abas === 'Novo aviso,Histórico,Dashboard,Comparativo' && /Operador/.test(ini.conta) && ini.municipios === 66 && ini.idiomas === 'pt-BR,en,es', JSON.stringify(ini));

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
    botao: $('botaoRede').textContent, credito: document.querySelector('.leaflet-control-attribution').textContent.includes('OpenStreetMap'),
    chaves: estado.redes['3138401'].chaves.length })`);
  conferir('rede fictícia: aparece por padrão, com legenda e crédito do OSM', vistaRede.partes > 50 && vistaRede.legenda && vistaRede.credito
    && vistaRede.botao === 'Esconder rede fictícia' && vistaRede.chaves > 10, JSON.stringify(vistaRede));
  await captura(p, '1c_rede_ficticia.png');
  await p.avaliar(`($('botaoLegenda').click(), 0)`);
  const minimizada = await p.avaliar(`({ itens: [...document.querySelectorAll('#legenda > li')].filter(l => l.offsetParent).length,
    texto: $('botaoLegenda').textContent.trim(), expandida: $('botaoLegenda').getAttribute('aria-expanded'), altura: $('legenda').getBoundingClientRect().height })`);
  await captura(p, '1d_legenda_minimizada.png');
  await p.avaliar(`($('botaoLegenda').click(), 0)`);
  conferir('legenda: minimiza (só o botão "Legenda") e abre de novo', minimizada.itens === 1 && /Legenda$/.test(minimizada.texto)
    && minimizada.expandida === 'false' && minimizada.altura < 70 && await p.avaliar(`$('botaoLegenda').getAttribute('aria-expanded') === 'true'
    && [...document.querySelectorAll('#legenda > li')].filter(l => l.offsetParent).length > 5`), JSON.stringify(minimizada));
  await p.avaliar(`($('botaoRede').click(), 0)`);
  conferir('rede fictícia: o botão esconde (e tira o crédito)', await p.avaliar(`!camadaRede && $('legendaRede').hidden
    && !document.querySelector('.leaflet-control-attribution').textContent.includes('OpenStreetMap')`));
  await p.avaliar(`($('botaoRede').click(), 0)`);
  conferir('rede fictícia: o botão mostra de novo', await ate(p, `camadaRede && $('botaoRede').textContent === 'Esconder rede fictícia'`));
  await p.avaliar(`(mapa.setZoom(13), 0)`);
  await ate(p, `document.documentElement.dataset.mapa === 'z13'`);
  await p.avaliar(`(mapa.setZoom(10), 0)`);
  await ate(p, `document.documentElement.dataset.mapa === 'z10'`);
  conferir('de longe: sem nomes nem contornos das comunidades', await p.avaliar(`!camadaNomes && !camadaBase`));

  const visivel = id => `!!$('${id}').offsetParent`;
  await p.avaliar(`($('avancar').click(), 0)`);
  conferir('funil: sem planilha, o passo 1 não avança (e diz por quê)', await p.avaliar(`estado.passo === 1 && ${visivel('passo-1')}
    && $('estado').classList.contains('erro') && document.querySelector('#funil [data-passo="3"]').disabled`));
  await escolherArquivo(p, PLANILHA);
  await p.avaliar(`($('avancar').click(), 0)`);
  conferir('funil: com a planilha, passo 2 (data e horário)', await p.avaliar(`estado.passo === 2 && ${visivel('passo-2')} && !${visivel('passo-1')}
    && ${visivel('gerar')} && $('passo2Arquivo').textContent.includes('planilha_CF-0066.csv')`));
  await p.avaliar(`($('data').value = '2026-11-20', $('inicio').value = '08:00', $('fim').value = '14:00', 0)`);
  await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('gerar').click(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'resultado' || $('estado').classList.contains('erro')`);
  const msg = await p.avaliar(`$('estado').textContent`);
  conferir('gerar aviso: pronto e guardado no histórico', /^Pronto.*aviso nº \d+/.test(msg), msg);
  await espera(800);
  const conferencia = await p.avaliar(`({ passo: estado.passo, resumo: ${visivel('resumo')}, form: ${visivel('form')},
    texto: !!document.querySelector('#municipios textarea')?.offsetParent, listas: !!document.querySelector('#municipios .listas')?.offsetParent,
    titulo: $('tituloResultado').textContent })`);
  conferir('funil: passo 3 (conferir) mostra os números e as comunidades, sem o texto do aviso',
    conferencia.passo === 3 && conferencia.resumo && !conferencia.form && !conferencia.texto && conferencia.listas && /^Conferir/.test(conferencia.titulo),
    JSON.stringify(conferencia));
  const tela = await p.avaliar(`({ avisos: [...document.querySelectorAll('#municipios textarea')].map(t => t.value),
    titulos: [...document.querySelectorAll('.mun-cab h3')].map(h => h.textContent),
    comunidades: camadaComunidades ? camadaComunidades.getLayers().length : 0, resumo: $('resumo').textContent.replace(/\\s+/g, ' ') })`);
  conferir('o aviso de cada município é idêntico ao da API', JSON.stringify(tela.avisos) === JSON.stringify(esperado.municipios.map(m => m.aviso)),
    `\n  tela: ${JSON.stringify(tela.avisos)}\n  API:  ${JSON.stringify(esperado.municipios.map(m => m.aviso))}`);
  conferir('municípios na ordem da API', JSON.stringify(tela.titulos) === JSON.stringify(esperado.municipios.map(m => `${m.nome}/${m.uf}`)), JSON.stringify(tela.titulos));
  conferir('mapa: comunidades afetadas desenhadas', tela.comunidades >= 8, String(tela.comunidades));
  const contornos = await p.avaliar(`camadaComunidades.getLayers().filter(l => !l.feature.properties.c).length`);
  conferir('mapa: contorno das outras comunidades dos municípios afetados', contornos > 20, String(contornos));
  const pts = await p.avaliar(`({ n: camadaUcs ? camadaUcs.getLayers().length : 0, botao: !$('botaoUcs').closest('li').hidden,
    canvas: !!document.querySelector('#mapa canvas'), dicas: camadaUcs.getLayers().slice(0, 50).map(l => l.getTooltip().getContent()) })`);
  const dicaComUc = pts.dicas.filter(d => /\d{6,}/.test(d));
  conferir('mapa: um ponto por UC válida (758), num canvas, dica sem número de UC', pts.n === 758 && pts.botao && pts.canvas && !dicaComUc.length,
    JSON.stringify({ ...pts, dicas: pts.dicas.slice(0, 2) }));
  await p.avaliar(`($('botaoUcs').click(), 0)`);
  const escondeu = await p.avaliar(`!camadaUcs && $('botaoUcs').textContent === 'Mostrar UCs'`);
  await p.avaliar(`($('botaoUcs').click(), 0)`);
  conferir('botão esconde e mostra as UCs', escondeu && await p.avaliar(`camadaUcs?.getLayers().length === 758`));
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
  await p.avaliar(`($('avancarResultado').click(), 0)`);
  const avisos = await p.avaliar(`({ passo: estado.passo, resumo: ${visivel('resumo')}, texto: !!document.querySelector('#municipios textarea')?.offsetParent,
    novo: ${visivel('novoAviso')}, titulo: $('tituloResultado').textContent })`);
  conferir('funil: passo 4 (avisos) mostra o texto para a rádio e o "Novo desligamento"',
    avisos.passo === 4 && !avisos.resumo && avisos.texto && avisos.novo && /^Avisos para a rádio/.test(avisos.titulo), JSON.stringify(avisos));
  await captura(p, '2c_avisos.png');
  await p.avaliar(`($('verComparativo').click(), 0)`);
  await ate(p, `estado.vista === 'comparativo' && document.querySelector('#comparativo .comp')`);
  const comp = await p.avaliar(`({ textos: [...document.querySelectorAll('#comparativo .comp')].map(c => [...c.querySelectorAll('.texto-longo')].map(t => t.textContent)),
    economia: document.querySelector('#comparativo .comp .comp-economia')?.textContent, numeros: document.querySelector('#comparativo .comp-lado.hoje .comp-numeros')?.textContent })`);
  const m0 = esperado.municipios[0];
  conferir('comparativo: o aviso de hoje igual ao da API, ao lado do aviso por comunidade, com a economia de tempo',
    comp.textos[0]?.[0] === m0.hoje?.texto && comp.textos[0]?.[1] === m0.aviso && /^\d+% menos tempo no ar$/.test(comp.economia || '')
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
    && ia1.texto.length < ia0.aviso.length && ia1.texto === ia1.estado && ia1.texto.includes('20/11') && ia1.texto.includes('8h'), JSON.stringify(ia1).slice(0, 300));
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

  // PDF: o que o botão faz antes de abrir a impressão (roteiro + texto final no histórico)
  await p.avaliar(`desenharRoteiro('${cod}').then(() => guardarFinal('${cod}'))`);
  const roteiro = await p.avaliar(`$('roteiro').textContent`);
  conferir('roteiro: texto editado, município, data, nº do aviso e código de verificação', roteiro.includes('Mais informações pelo telefone')
    && roteiro.includes('Leopoldina/MG') && roteiro.includes('20/11/2026') && /aviso nº \d+/.test(roteiro) && /SHA-256\): [0-9a-f]{16}/.test(roteiro), roteiro.slice(0, 200));
  const repetido = roteiro.match(/\(([^()]+)\) \(\1\)/);
  conferir('roteiro: homônimos com o distrito uma vez só', !repetido, repetido?.[0]);
  conferir('texto final guardado no histórico (selo na tela)', /guardado no histórico/.test(await p.avaliar(`$('final-${cod}').textContent`)));
  await p.send('Emulation.setEmulatedMedia', { media: 'print' });
  const pdf = await p.send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true });
  await p.send('Emulation.setEmulatedMedia', { media: '' });
  writeFileSync(join(CAP, 'roteiro_leopoldina.pdf'), Buffer.from(pdf.data, 'base64'));
  conferir('PDF do roteiro gerado', pdf.data.length > 10_000, `${Math.round(pdf.data.length * .75 / 1024)} KB`);
  await p.avaliar(`($('novoAviso').click(), 0)`);
  conferir('Novo desligamento: volta ao passo 1, sem o resultado anterior na tela nem no mapa', await p.avaliar(`estado.passo === 1
    && !estado.resultado && $('resultado').hidden && !camadaUcs && !camadaComunidades && !$('municipios').children.length && !estado.arquivo`));

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
    /^Avisos gerados2/.test(dash.kpis[0]) && dash.barras === 12 && dash.legenda && dash.leopoldina > .3 && dash.top === 'Leopoldina/MG', JSON.stringify(dash));
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

// ---------- 2. Consulta, Admin da empresa e Admin do Farol ----------
{
  const p = await abrir(`${BASE}/`, { largura: 1440, altura: 900 });
  const c = await entrarNaTela(p, 'consulta@emg.example', SENHAS['consulta@emg.example']);
  conferir('Consulta: só Histórico, Dashboard e Comparativo', c.tela === 'app' && c.abas.join(',') === 'Histórico,Dashboard,Comparativo', JSON.stringify(c));
  await ate(p, `document.querySelectorAll('#listaHistorico [data-historico]').length`);
  await p.avaliar(`(document.querySelector('#listaHistorico [data-historico]').click(), 0)`);
  await ate(p, `!$('resultado').hidden && document.querySelector('#municipios textarea')`);
  const leitura = await p.avaliar(`({ readonly: [...document.querySelectorAll('#municipios textarea')].every(t => t.readOnly),
    desfazer: document.querySelectorAll('[data-acao=restaurar]').length, pdf: document.querySelectorAll('[data-acao=pdf]').length })`);
  conferir('Consulta: aviso só para ler (sem editar nem desfazer), com PDF', leitura.readonly && !leitura.desfazer && leitura.pdf > 0, JSON.stringify(leitura));
  conferir('Consulta: nenhum ponto de UC no mapa', await p.avaliar(`!camadaUcs && $('botaoUcs').closest('li').hidden`));
  conferir('Consulta: a API recusa gerar aviso (403)', await p.avaliar(`fetch('/api/avisos', { method: 'POST' }).then(r => r.status === 403)`));
  await p.avaliar(`($('sair').click(), 0)`); await ate(p, `estado.tela === 'entrar'`);

  const a = await entrarNaTela(p, 'admin@emg.example', SENHAS['admin@emg.example']);
  conferir('Admin da empresa: Novo aviso, Histórico, Dashboard, Comparativo, Usuários e Registro', a.abas.join(',') === 'Novo aviso,Histórico,Dashboard,Comparativo,Usuários,Registro', JSON.stringify(a.abas));
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
  await p.avaliar(`($('sair').click(), 0)`); await ate(p, `estado.tela === 'entrar'`);

  const f = await entrarNaTela(p, 'admin@farol.example', SENHAS['admin@farol.example']);
  conferir('Admin do Farol: só Empresas e Registro', f.abas.join(',') === 'Empresas,Registro', JSON.stringify(f.abas));
  await ate(p, `document.querySelectorAll('#listaEmpresas tbody tr').length`);
  conferir('Admin do Farol: a empresa EMG na lista', /EMG/.test(await p.avaliar(`$('listaEmpresas').textContent`)));
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
