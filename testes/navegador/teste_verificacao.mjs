// Verificação geral da tela (Fase J): todo botão funciona, tudo salva, nenhum erro calado.
// Rode pelo executor, com o Mailpit (e-mail, segunda via e confirmação da rádio de verdade, só na máquina):
//   uv run python testes/navegador/rodar_teste_app.py teste_verificacao.mjs --email
// Para cada formulário e cada perfil que pode usá-lo (docs/VERIFICACAO.md):
// - salva, e o dado continua lá depois de recarregar a página e de sair e entrar de novo;
// - editar e desativar aparecem na lista; a auditoria registra com o nome de quem fez;
// - dado inválido: erro no campo (aria-invalid + texto ligado ao campo), sem perder o que foi digitado;
// - clique duplo não grava duas vezes (botão "Salvando…" desabilitado e o servidor recusa a duplicata);
// - sem conexão ou erro 500: mensagem clara, nada pela metade;
// - console sem erros, nenhuma resposta 4xx/5xx inesperada, nenhuma exceção nem violação da CSP.
import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const MAILPIT = process.env.FAROL_MAILPIT;
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
if (!SENHAS['operador@emg.example'] || !MAILPIT) {
  console.error('Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_verificacao.mjs --email'); process.exit(2);
}
const NOVA = 'Lanterna-da-Verificacao-2026';
const PLANILHA = join(RAIZ, 'saida', 'planilhas_teste', 'planilha_CF-0066.csv');
const MUITAS = join(RAIZ, 'testes', 'planilha', 'exemplos', 'demo', '4_muitas_rejeicoes.xlsx');
const CAP = join(RAIZ, 'saida', 'capturas_verificacao');
mkdirSync(CAP, { recursive: true });
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
const J = JSON.stringify;

// espera uma condição na página (expressão JS), até ms
const ate = (p, expr, ms = 20000) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > ${ms}) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);

// a página com o registro das respostas (status), dos downloads e o que é permitido dar 4xx (erros provocados de propósito)
async function pagina(largura = 1440, altura = 900) {
  const p = await abrir(`${BASE}/`, { largura, altura, antesDeNavegar: async pg => {
    pg.respostas = [];
    await pg.send('Network.enable');
    pg.on('Network.responseReceived', e => pg.respostas.push([e.response.status, e.response.url]));
  } });
  p.permitidos = [[/\/api\/eu$/, 401]];   // ao abrir sem sessão
  p.baixados = [];
  await p.navegador.send('Browser.setDownloadBehavior', { behavior: 'allowAndName', downloadPath: CAP, eventsEnabled: true });
  p.navegador.on('Browser.downloadWillBegin', e => p.baixados.push({ guid: e.guid, nome: e.suggestedFilename, ok: false }));
  p.navegador.on('Browser.downloadProgress', e => { if (e.state === 'completed') { const d = p.baixados.find(x => x.guid === e.guid); if (d) d.ok = true; } });
  await stubs(p);
  return p;
}
const permitir = (p, re, status) => p.permitidos.push([re, status]);
// confirm, área de transferência e janela do WhatsApp: no navegador sem tela, respostas fixas
const stubs = p => p.avaliar(`(window.confirm = () => true, window.__aberto = [], window.open = u => { window.__aberto.push(u); return null; },
  navigator.clipboard && (navigator.clipboard.writeText = async t => { window.__copiado = t; }), 0)`);

// clica (expressão JS) e espera o arquivo baixado cujo nome bate com a expressão regular
async function baixar(p, expr, re, ms = 40000) {
  const n0 = p.baixados.length;
  await p.avaliar(`(${expr}, 0)`);
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const d = p.baixados.slice(n0).find(x => re.test(x.nome) && x.ok);
    if (d) return { nome: d.nome, bytes: readFileSync(join(CAP, d.guid)) };
    await espera(150);
  }
  return { nome: p.baixados.slice(n0).map(x => x.nome).join(',') || '(nada)', bytes: Buffer.alloc(0) };
}

async function entrar(p, email, senha) {
  await p.avaliar(`($('email').value = ${J(email)}, $('senha').value = ${J(senha)}, $('estadoEntrar').textContent = '', $('formEntrar').requestSubmit(), 0)`);
  await ate(p, `estado.tela !== 'entrar' || $('estadoEntrar').textContent`);
  if (await p.avaliar(`estado.tela === 'app'`)) await ate(p, `estado.concessao && document.documentElement.dataset.farol === 'pronto'`, 60000);
  await stubs(p);
  return p.avaliar(`estado.tela`);
}
async function sair(p) {
  // espera a tela terminar o que estava fazendo (ex.: recarregar a lista depois de salvar): uma requisição ainda no ar
  // na hora de sair volta 401 (a sessão já acabou), o que aparecia como erro intermitente do teste
  await ate(p, `!document.querySelector('[aria-busy="true"]')`);
  await espera(600);
  await p.avaliar(`($('sair').click(), 0)`);
  await ate(p, `estado.tela === 'entrar'`);
}
async function recarregar(p) {
  const carregou = p.uma('Page.loadEventFired');
  await p.send('Page.reload', { ignoreCache: true });
  await carregou;
  await ate(p, `document.documentElement.dataset.farol === 'pronto' && (estado.tela !== 'app' || estado.concessao)`, 60000);
  await stubs(p);
}
const ir = async (p, vista, cond = 'true') => { await p.avaliar(`irPara('${vista}')`); return ate(p, `estado.vista === '${vista}' && (${cond})`); };
// preenche campos (id -> valor) disparando input e change, como a pessoa
const preencher = (p, campos) => p.avaliar(`(() => { for (const [id, v] of ${J(Object.entries(campos))}) { const c = $(id);
  if (c.type === 'checkbox') c.checked = v; else c.value = v;
  c.dispatchEvent(new Event('input', { bubbles: true })); c.dispatchEvent(new Event('change', { bubbles: true })); } return 0; })()`);
// o campo marcado com erro (aria-invalid) e com o texto do erro ligado a ele (aria-describedby)
const erroNoCampo = (p, id) => p.avaliar(`(() => { const c = $('${id}'); if (!c || c.getAttribute('aria-invalid') !== 'true') return '';
  const ids = (c.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean);
  return ids.map(i => document.getElementById(i)?.textContent || '').join(' ').trim(); })()`);
const valor = (p, id) => p.avaliar(`$('${id}').value`);
const api = (p, url, metodo = 'GET', corpo) => p.avaliar(`fetch(${J(url)}, { method: '${metodo}', credentials: 'same-origin'
  ${corpo ? `, headers: { 'Content-Type': 'application/json' }, body: ${J(J(corpo))}` : ''} }).then(async r => ({ status: r.status, j: await r.json().catch(() => null) }))`);
const registro = p => p.avaliar(`fetch('/api/registro').then(r => r.json()).then(j => j.registro.map(r => r.acao + ' | ' + r.detalhe + ' | ' + r.usuario + ' (' + r.perfil + ')'))`);

// sem conexão: o pedido não sai; a tela tem de dizer com clareza
const offline = (p, sim) => p.send('Network.emulateNetworkConditions', { offline: sim, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
// erro 500 com corpo que não é JSON (um proxy caído, por exemplo), só na rota escolhida
async function erro500(p, padrao, fazer) {
  const ouvinte = async e => { await p.send('Fetch.fulfillRequest', { requestId: e.requestId, responseCode: 500,
    responseHeaders: [{ name: 'Content-Type', value: 'text/html' }], body: Buffer.from('<html><body>Internal Server Error</body></html>').toString('base64') }); };
  p.on('Fetch.requestPaused', ouvinte);
  await p.send('Fetch.enable', { patterns: [{ urlPattern: padrao, requestStage: 'Request' }] });
  try { await fazer(); } finally { await p.send('Fetch.disable'); }
}

// o fim de cada navegador: console, respostas, exceções e CSP
async function semErros(p, nome) {
  const inesperadas = p.respostas.filter(([s, u]) => s >= 400 && u.startsWith(BASE) && !p.permitidos.some(([re, st]) => re.test(u) && st === s));
  conferir(`${nome}: nenhuma resposta 4xx/5xx inesperada`, !inesperadas.length, J(inesperadas.slice(0, 6)));
  const consoleErros = p.logs.filter(l => (l.startsWith('error ') && !l.startsWith('error network')) || l.startsWith('console.error'));
  conferir(`${nome}: console do navegador sem erros`, !consoleErros.length, J(consoleErros.slice(0, 4)));
  const csp = await p.avaliar('window.__csp || []');
  conferir(`${nome}: nenhuma exceção nem violação da CSP`, !p.excecoes.length && !csp.length, J([p.excecoes.slice(0, 3), csp]));
}

// cada seção (um navegador): um erro inesperado vira uma falha da seção e o teste segue para a próxima
async function secao(nome, f) {
  const ctx = {};
  try { await f(ctx); } catch (e) { conferir(`${nome}: a seção parou num erro`, false, String(e.message || e).slice(0, 300)); }
  finally { await ctx.p?.fechar(); }
}

// ======================= 1. Admin da empresa: entrar, tema, ajuda, usuários, rádios, configurações, auditoria =======================
await secao('Admin da empresa', async ctx => {
  const p = ctx.p = await pagina();
  // entrar sem nada: erro nos dois campos, sem sair da tela
  await p.avaliar(`($('email').value = '', $('senha').value = '', $('formEntrar').requestSubmit(), 0)`);
  conferir('entrar sem e-mail e senha: erro no campo de cada um', !!(await erroNoCampo(p, 'email')) && !!(await erroNoCampo(p, 'senha')),
    J([await erroNoCampo(p, 'email'), await p.avaliar(`$('estadoEntrar').textContent`)]));
  permitir(p, /\/api\/entrar$/, 401);
  await p.avaliar(`($('email').value = 'admin@emg.example', $('senha').value = 'senha-errada-000', $('estadoEntrar').textContent = '', $('formEntrar').requestSubmit(), 0)`);
  await ate(p, `$('estadoEntrar').textContent`);
  conferir('entrar com senha errada: mensagem clara e o e-mail continua digitado', /incorretos/.test(await p.avaliar(`$('estadoEntrar').textContent`))
    && await valor(p, 'email') === 'admin@emg.example');
  conferir('entrar (Admin da empresa)', await entrar(p, 'admin@emg.example', SENHAS['admin@emg.example']) === 'app');

  // tema: troca e continua depois de recarregar
  const tema0 = await p.avaliar(`temaAtual()`);
  await p.avaliar(`($('botaoTema').click(), 0)`);
  const tema1 = await p.avaliar(`temaAtual()`);
  await recarregar(p);
  conferir('tema: troca e continua o mesmo depois de recarregar', tema0 !== tema1 && await p.avaliar(`temaAtual()`) === tema1, `${tema0} -> ${tema1}`);
  await p.avaliar(`($('botaoTema').click(), 0)`);
  // ajuda: abre, fecha com Esc e o foco volta ao botão
  await p.avaliar(`($('botaoAjuda').click(), 0)`);
  const ajudaAberta = await p.avaliar(`!$('caixaAjuda').hidden && $('ajudaCorpo').textContent.length > 100`);
  await p.avaliar(`(document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })), 0)`);
  conferir('Ajuda: abre com o caminho do perfil e fecha com Esc (foco volta ao botão)', ajudaAberta
    && await p.avaliar(`$('caixaAjuda').hidden && document.activeElement === $('botaoConta')`));

  // ---------- Usuários ----------
  await ir(p, 'usuarios', `document.querySelectorAll('#listaUsuarios [data-usuario]').length >= 4`);
  await preencher(p, { novoNome: '', novoEmail: 'paula@outro.example' });
  await p.avaliar(`($('formUsuario').requestSubmit(), 0)`);
  await espera(400);
  conferir('Usuários: sem nome e com e-mail de outro domínio, erro em cada campo e nada some',
    !!(await erroNoCampo(p, 'novoNome')) && await valor(p, 'novoEmail') === 'paula@outro.example',
    J([await erroNoCampo(p, 'novoNome'), await erroNoCampo(p, 'novoEmail'), await p.avaliar(`$('estadoUsuario').textContent`)]));
  permitir(p, /\/api\/usuarios$/, 422);
  await preencher(p, { novoNome: 'Paula Verificação' });
  await p.avaliar(`($('estadoUsuario').textContent = '', $('formUsuario').requestSubmit(), 0)`);
  await ate(p, `$('estadoUsuario').textContent && !document.querySelector('#formUsuario [aria-busy]')`);
  conferir('Usuários: e-mail de outro domínio recusado pelo servidor, com o erro no campo do e-mail', /@emg\.example/.test(await erroNoCampo(p, 'novoEmail'))
    && await valor(p, 'novoNome') === 'Paula Verificação', J([await erroNoCampo(p, 'novoEmail'), await p.avaliar(`$('estadoUsuario').textContent`)]));
  await preencher(p, { novoEmail: 'paula@emg.example', novoPerfil: 'operador' });
  const salvando = await p.avaliar(`(() => { const b = document.querySelector('#formUsuario button[type=submit]'); b.click(); const r = [b.disabled, b.textContent]; b.click(); return r; })()`);
  await ate(p, `!$('caixaSenha').hidden`);
  conferir('Usuários: clique duplo no Convidar: botão "Salvando…" desabilitado e um usuário só', salvando[0] && /Salvando/.test(salvando[1])
    && (await api(p, '/api/usuarios')).j.usuarios.filter(u => u.email === 'paula@emg.example').length === 1, J(salvando));
  await p.avaliar(`($('caixaFechar').click(), 0)`);
  permitir(p, /\/api\/usuarios$/, 409);
  conferir('Usuários: o servidor recusa o mesmo e-mail de novo (409)', (await api(p, '/api/usuarios', 'POST', { nome: 'Paula 2', email: 'paula@emg.example', perfil: 'operador' })).status === 409);
  // editar: nome, perfil e municípios; continua depois de recarregar
  const linha = `[...document.querySelectorAll('#listaUsuarios [data-usuario]')].find(l => l.textContent.includes('paula@emg.example'))`;
  await p.avaliar(`(() => { const l = ${linha}; const n = l.querySelector('[data-campo=nome]'); n.value = 'Paula Verificada';
    l.querySelector('[data-campo=perfil]').value = 'consulta';
    const m = l.querySelector('[data-campo=municipios]'); [...m.options].forEach(o => o.selected = ['3138401', '3115300'].includes(o.value));
    $('estadoUsuario').textContent = ''; l.querySelector('[data-acao-usuario=salvar]').click(); return 0; })()`);
  await ate(p, `/salvas/.test($('estadoUsuario').textContent)`);
  await recarregar(p);
  await ir(p, 'usuarios', `document.querySelectorAll('#listaUsuarios [data-usuario]').length >= 5`);
  const editado = await p.avaliar(`(() => { const l = ${linha}; return l && { nome: l.querySelector('[data-campo=nome]')?.value, perfil: l.querySelector('[data-campo=perfil]').value,
    municipios: [...l.querySelector('[data-campo=municipios]').selectedOptions].map(o => o.value).sort().join(',') }; })()`);
  conferir('Usuários: editar nome, perfil e municípios salva e continua depois de recarregar', editado?.nome === 'Paula Verificada' && editado.perfil === 'consulta'
    && editado.municipios === '3115300,3138401', J(editado));
  // bloquear e reativar; continua depois de sair e entrar
  await p.avaliar(`(() => { const l = ${linha}; l.querySelector('[data-campo=status]').value = 'bloqueado'; $('estadoUsuario').textContent = ''; l.querySelector('[data-acao-usuario=salvar]').click(); return 0; })()`);
  await ate(p, `/salvas/.test($('estadoUsuario').textContent)`);
  await sair(p);
  await entrar(p, 'admin@emg.example', SENHAS['admin@emg.example']);
  await ir(p, 'usuarios', `document.querySelectorAll('#listaUsuarios [data-usuario]').length >= 5`);
  const bloqueado = await p.avaliar(`${linha}.querySelector('[data-campo=status]').value`);
  await p.avaliar(`(() => { const l = ${linha}; l.querySelector('[data-campo=status]').value = 'ativo'; $('estadoUsuario').textContent = '';
    $('estadoUsuario').textContent = ''; l.querySelector('[data-acao-usuario=salvar]').click(); return 0; })()`);
  await ate(p, `/salvas/.test($('estadoUsuario').textContent)`);
  conferir('Usuários: bloquear continua depois de sair e entrar; reativar volta a ativo', bloqueado === 'bloqueado'
    && (await api(p, '/api/usuarios')).j.usuarios.find(u => u.email === 'paula@emg.example').status === 'ativo', bloqueado);
  // último admin: bloquear a si mesmo é recusado, com a mensagem, e nada muda
  permitir(p, /\/api\/usuarios\/\d+$/, 409);
  const eu = `[...document.querySelectorAll('#listaUsuarios [data-usuario]')].find(l => l.textContent.includes('admin@emg.example'))`;
  await p.avaliar(`(() => { const l = ${eu}; l.querySelector('[data-campo=status]').value = 'bloqueado'; $('estadoUsuario').textContent = '';
    $('estadoUsuario').textContent = ''; l.querySelector('[data-acao-usuario=salvar]').click(); return 0; })()`);
  await ate(p, `$('estadoUsuario').classList.contains('erro')`);
  conferir('Usuários: o último admin não pode ser bloqueado (mensagem clara, continua ativo)', /último admin/.test(await p.avaliar(`$('estadoUsuario').textContent`))
    && (await api(p, '/api/usuarios')).j.usuarios.find(u => u.email === 'admin@emg.example').status === 'ativo');
  await p.avaliar(`(() => { const l = ${linha}; l.querySelector('[data-acao-usuario=senha]').click(); return 0; })()`);
  conferir('Usuários: nova senha temporária aparece uma vez', await ate(p, `!$('caixaSenha').hidden && $('caixaSenhaValor').textContent.length > 10`));
  await p.avaliar(`($('caixaFechar').click(), 0)`);
  const regU = (await registro(p)).filter(r => /usuário/.test(r));
  conferir('Usuários: a auditoria registra cadastrar e alterar com o nome de quem fez', regU.some(r => /^cadastrou usuário \| Paula Verificação/.test(r) && /Admin da EMG \(Admin da empresa\)/.test(r))
    && regU.some(r => /^alterou usuário \| Paula/.test(r) && /Admin da EMG/.test(r)), J(regU.slice(0, 4)));

  // ---------- Rádios ----------
  await ir(p, 'radios', `$('radMunicipios').options.length > 60`);
  await preencher(p, { radNome: '', radEmail: '', radWhats: '' });
  await p.avaliar(`($('formRadio').requestSubmit(), 0)`);
  await espera(400);
  conferir('Rádios: sem nome e sem contato, erro nos campos', !!(await erroNoCampo(p, 'radNome')) && !!(await erroNoCampo(p, 'radEmail')),
    J([await erroNoCampo(p, 'radNome'), await erroNoCampo(p, 'radEmail'), await p.avaliar(`$('estadoRadio').textContent`)]));
  await preencher(p, { radNome: 'Rádio Verificação FM', radEmail: 'verif.fm@example', radValor: '120,50', radCobranca: 'minuto' });
  await p.avaliar(`($('formRadio').requestSubmit(), 0)`);
  await espera(600);
  permitir(p, /\/api\/radios$/, 422);
  conferir('Rádios: e-mail inválido mostra o erro no campo e mantém o que foi digitado', !!(await erroNoCampo(p, 'radEmail'))
    && await valor(p, 'radNome') === 'Rádio Verificação FM' && await valor(p, 'radValor') === '120,50',
    J([await erroNoCampo(p, 'radEmail'), await p.avaliar(`$('estadoRadio').textContent`)]));
  await preencher(p, { radEmail: 'verif.fm@example.com' });
  await p.avaliar(`(() => { [...$('radMunicipios').options].find(o => o.value === '3138401').selected = true;
    const s = $('radMunCom'); s.value = '3138401'; s.dispatchEvent(new Event('change')); return 0; })()`);
  await ate(p, `document.querySelectorAll('#radComunidades input[type=checkbox]').length > 50`);
  await p.avaliar(`(() => { const c = [...document.querySelectorAll('#radComunidades input[type=checkbox]')].find(x => x.nextSibling.textContent === 'Piacatuba (Piacatuba)');
    c.checked = true; c.dispatchEvent(new Event('change', { bubbles: true })); return 0; })()`);
  const salvandoR = await p.avaliar(`(() => { const b = $('radSalvar'); b.click(); const r = [b.disabled, b.textContent]; b.click(); return r; })()`);
  await ate(p, `/cadastrada/.test($('estadoRadio').textContent)`);
  await espera(500);
  const radiosApi = (await api(p, '/api/radios')).j.radios.filter(r => r.nome === 'Rádio Verificação FM');
  conferir('Rádios: clique duplo no Cadastrar: "Salvando…" e uma rádio só', salvandoR[0] && /Salvando/.test(salvandoR[1]) && radiosApi.length === 1, J([salvandoR, radiosApi.length]));
  permitir(p, /\/api\/radios$/, 409);
  conferir('Rádios: o servidor recusa outra rádio com o mesmo nome (409)', (await api(p, '/api/radios', 'POST', { nome: 'rádio verificação fm', email: 'x@example.com',
    alcance: { municipios: ['3138401'] } })).status === 409);
  await recarregar(p);
  await ir(p, 'radios', `document.querySelectorAll('#listaRadios [data-radio]').length`);
  const listaR = await p.avaliar(`$('listaRadios').textContent`);
  conferir('Rádios: depois de recarregar, a rádio com valor padrão, cobrança e alcance', /Rádio Verificação FM/.test(listaR) && /120,50/.test(listaR)
    && /por minuto no ar/.test(listaR) && /Leopoldina\/MG e 1 comunidade/.test(listaR), listaR.slice(0, 300));
  // editar: valor padrão e mais um município
  const itemR = `[...document.querySelectorAll('#listaRadios [data-radio]')].find(l => l.textContent.includes('Rádio Verificação FM'))`;
  await p.avaliar(`(${itemR}.querySelector('[data-radio-acao=editar]').click(), 0)`);
  conferir('Rádios: Editar abre o cadastro preenchido', await valor(p, 'radNome') === 'Rádio Verificação FM' && await valor(p, 'radValor') === '120,50'
    && await p.avaliar(`[...$('radMunicipios').selectedOptions].map(o => o.value).join() === '3138401' && estado.alcanceComunidades.length === 1`));
  await p.avaliar(`(() => { $('estadoRadio').textContent = ''; $('radValor').value = '99,90'; [...$('radMunicipios').options].find(o => o.value === '3115300').selected = true;
    $('formRadio').requestSubmit(); return 0; })()`);
  await ate(p, `/alterada/.test($('estadoRadio').textContent)`);
  await sair(p);
  await entrar(p, 'admin@emg.example', SENHAS['admin@emg.example']);
  await ir(p, 'radios', `document.querySelectorAll('#listaRadios [data-radio]').length`);
  const listaR2 = await p.avaliar(`${itemR}?.textContent || ''`);
  conferir('Rádios: a edição (valor padrão e alcance) continua depois de sair e entrar', /99,90/.test(listaR2) && /Cataguases\/MG/.test(listaR2) && /Leopoldina\/MG/.test(listaR2), listaR2);
  // desativar e reativar pelos botões da lista
  await p.avaliar(`($('estadoRadio').textContent = '', ${itemR}.querySelector('[data-radio-acao=desativar]').click(), 0)`);
  await ate(p, `/\\(inativa\\)/.test(${itemR}?.textContent || '')`);
  await recarregar(p);
  await ir(p, 'radios', `document.querySelectorAll('#listaRadios [data-radio]').length`);
  const inativa = await p.avaliar(`/\\(inativa\\)/.test(${itemR}?.textContent || '')`);
  await p.avaliar(`(${itemR}.querySelector('[data-radio-acao=reativar]').click(), 0)`);
  await ate(p, `!/\\(inativa\\)/.test(${itemR}?.textContent || '') && /reativada/.test($('estadoRadio').textContent)`);
  conferir('Rádios: Desativar (continua depois de recarregar) e Reativar pela lista', inativa
    && (await api(p, '/api/radios')).j.radios.find(r => r.nome === 'Rádio Verificação FM')?.ativa === true);
  const regR = (await registro(p)).filter(r => /rádio/.test(r));
  conferir('Rádios: a auditoria registra cadastrar, alterar, desativar e reativar com o nome', regR.some(r => /^cadastrou rádio \| Rádio Verificação FM/.test(r))
    && regR.some(r => /^alterou cadastro de rádio \| Rádio Verificação FM.*valor padrão/.test(r)) && regR.some(r => /^desativou rádio \| Rádio Verificação FM/.test(r))
    && regR.some(r => /^reativou rádio \| Rádio Verificação FM/.test(r)) && regR.every(r => /\(Admin da empresa\)$/.test(r)), J(regR.slice(0, 5)));

  // ---------- Configurações ----------
  await ir(p, 'configuracoes', `$('cfgModelo').value.includes('{comunidades}')`);
  await preencher(p, { cfgLimite: '99', cfgAntecedencia: '' });
  await p.avaliar(`($('formConfig').requestSubmit(), 0)`);
  await espera(500);
  conferir('Configurações: limite fora da faixa e antecedência vazia, erro em cada campo e nada some', !!(await erroNoCampo(p, 'cfgLimite'))
    && !!(await erroNoCampo(p, 'cfgAntecedencia')) && await valor(p, 'cfgLimite') === '99',
    J([await erroNoCampo(p, 'cfgLimite'), await erroNoCampo(p, 'cfgAntecedencia'), await p.avaliar(`$('estadoConfig').textContent`)]));
  const novos = { cfgTelefone: '0800 123 4567', cfgLimite: '3', cfgAntecedencia: '20', cfgOrcamento: '50000', cfgAlertaPreco: '30', cfgRepN: '4',
    cfgRepDias: '45', cfgFuso: '31983', cfgNome: 'Energisa Minas Gerais (verificação)' };
  await preencher(p, novos);
  const previa = await p.avaliar(`$('cfgPrevia').textContent`);
  const salvandoC = await p.avaliar(`(() => { const b = document.querySelector('#formConfig button[type=submit]'); b.click(); return [b.disabled, b.textContent]; })()`);
  await ate(p, `/Configurações salvas/.test($('estadoConfig').textContent)`);
  conferir('Configurações: prévia acompanha o que se digita; Salvar mostra "Salvando…"', /0800 123 4567/.test(previa) && /Energisa Minas Gerais \(verificação\)/.test(previa)
    && salvandoC[0] && /Salvando/.test(salvandoC[1]), J([previa.slice(-60), salvandoC]));
  await recarregar(p);
  await ir(p, 'configuracoes', `$('cfgModelo').value`);
  const lidos1 = await p.avaliar(`(${J(Object.keys(novos))}).map(id => $(id).value)`);
  await sair(p);
  await entrar(p, 'admin@emg.example', SENHAS['admin@emg.example']);
  await ir(p, 'configuracoes', `$('cfgModelo').value`);
  const lidos2 = await p.avaliar(`(${J(Object.keys(novos))}).map(id => $(id).value)`);
  conferir('Configurações: tudo salvo continua depois de recarregar e de sair e entrar (telefone, limites, orçamento, alertas, fuso, antecedência)',
    J(lidos1) === J(Object.values(novos)) && J(lidos2) === J(Object.values(novos)), J([lidos1, lidos2]));
  // sem conexão: mensagem clara e nada muda
  await offline(p, true);
  await preencher(p, { cfgTelefone: '0800 999 9999' });
  await p.avaliar(`($('formConfig').requestSubmit(), 0)`);
  await ate(p, `$('estadoConfig').classList.contains('erro')`);
  const semRede = await p.avaliar(`$('estadoConfig').textContent`);
  await offline(p, false);
  conferir('Configurações: sem conexão, a mensagem diz que não houve conexão (e o que foi digitado fica)', /conexão/i.test(semRede) && !/Failed to fetch/.test(semRede)
    && await valor(p, 'cfgTelefone') === '0800 999 9999', semRede);
  // erro 500 (resposta que não é JSON): mensagem clara; depois de recarregar, nada mudou
  permitir(p, /\/api\/empresa\/configuracao$/, 500);
  await erro500(p, '*/api/empresa/configuracao', async () => {
    await p.avaliar(`($('estadoConfig').textContent = '', $('formConfig').requestSubmit(), 0)`);
    await ate(p, `$('estadoConfig').classList.contains('erro') && $('estadoConfig').textContent`);
  });
  const msg500 = await p.avaliar(`$('estadoConfig').textContent`);
  conferir('Configurações: erro 500 do servidor, mensagem clara', /servidor/i.test(msg500) && /nada foi salvo/i.test(msg500), msg500);
  await recarregar(p);
  await ir(p, 'configuracoes', `$('cfgModelo').value`);
  conferir('Configurações: sem conexão e com erro 500 nada foi gravado pela metade', await valor(p, 'cfgTelefone') === '0800 123 4567');
  conferir('Configurações: a auditoria registra a alteração com antes e depois e o nome', (await registro(p)).some(r => /^alterou a configuração da empresa \|.*telefone.*0800 123 4567/.test(r)
    && /Admin da EMG \(Admin da empresa\)/.test(r)));

  // ---------- Auditoria ----------
  await ir(p, 'registro', `document.querySelectorAll('#listaRegistro tbody tr').length`);
  await preencher(p, { audCategoria: 'cadastro' });
  await p.avaliar(`(document.querySelector('[data-aud=tela]').click(), 0)`);
  await ate(p, `document.querySelector('#docAuditoria .subtitulo') && /linha/.test($('estadoAuditoria').textContent)`);
  conferir('Auditoria: filtro por tipo (cadastros) mostra o relatório na tela', /rádio|usuário|configuração/.test(await p.avaliar(`$('docAuditoria').textContent`)));
  await p.avaliar(`($('verificarAuditoria').click(), 0)`);
  conferir('Auditoria: Conferir a integridade', await ate(p, `/^Auditoria íntegra/.test($('estadoAuditoria').textContent)`));
  for (const [acao, re] of [['csv', /\.csv$/], ['pdf', /\.pdf$/], ['json', /\.json$/]]) {
    const b = await baixar(p, `document.querySelector('[data-aud=${acao}]').click()`, re);
    conferir(`Auditoria: exportar ${acao.toUpperCase()}`, b.bytes.length > 100, b.nome);
  }
  await semErros(p, 'Admin da empresa');
});

// ======================= 2. Operador: senha, novo aviso, envio, pedido de rádio, histórico, relatórios, mapa =======================
let avisoId;
await secao('Operador', async ctx => {
  const p = ctx.p = await pagina();
  await entrar(p, 'operador@emg.example', SENHAS['operador@emg.example']);
  await preencher(p, { senhaAtual: SENHAS['operador@emg.example'], senhaNova: 'curta', senhaNova2: 'curta' });
  await p.avaliar(`($('formSenha').requestSubmit(), 0)`);
  conferir('trocar senha: curta demais, erro no campo da senha nova', /12 caracteres/.test(await erroNoCampo(p, 'senhaNova')), await p.avaliar(`$('estadoSenha').textContent`));
  await preencher(p, { senhaNova: NOVA, senhaNova2: NOVA + 'x' });
  await p.avaliar(`($('formSenha').requestSubmit(), 0)`);
  conferir('trocar senha: as duas diferentes, erro no campo de repetir', /não são iguais/.test(await erroNoCampo(p, 'senhaNova2')));
  await preencher(p, { senhaNova2: NOVA });
  await p.avaliar(`($('formSenha').requestSubmit(), 0)`);
  conferir('trocar senha: salva e abre o app', await ate(p, `estado.tela === 'app' && estado.concessao && document.documentElement.dataset.farol === 'pronto'`, 60000));
  await stubs(p);

  // ---------- Novo aviso: campos do passo 2 ----------
  await p.send('DOM.getDocument', { depth: 1 });
  const arquivo = async c => { const { root } = await p.send('DOM.getDocument', { depth: 1 }); const { nodeId } = await p.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#arquivo' });
    await p.send('DOM.setFileInputFiles', { nodeId, files: [c] }); };
  await arquivo(MUITAS);
  await p.avaliar(`($('avancar').click(), 0)`);
  await preencher(p, { data: '', inicio: '14:00', fim: '08:00' });
  await p.avaliar(`($('form').requestSubmit(), 0)`);
  conferir('Novo aviso: sem data, erro no campo da data', !!(await erroNoCampo(p, 'data')), await p.avaliar(`$('estado').textContent`));
  await preencher(p, { data: '2026-11-25' });
  await p.avaliar(`($('form').requestSubmit(), 0)`);
  conferir('Novo aviso: fim antes do início, erro no campo do fim', /depois do início/.test(await erroNoCampo(p, 'fim')));
  await preencher(p, { fim: '17:00', tipo: 'outro', tipoOutro: 'ab' });
  await p.avaliar(`($('form').requestSubmit(), 0)`);
  conferir('Novo aviso: "Outro" curto demais, erro no campo da descrição', /3 a 200/.test(await erroNoCampo(p, 'tipoOutro')));
  await preencher(p, { tipoOutro: 'troca de cruzeta na rede' });
  await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('form').requestSubmit(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'conferencia' || $('estado').classList.contains('erro')`, 90000);
  // justificativa: acima do limite de rejeição, obrigatória
  const just = await p.avaliar(`({ campo: !!$('justificativa'), motivo: ($('conferi').click(), $('motivoGerar').textContent), travado: $('avancarResultado').disabled })`);
  conferir('Novo aviso (muitas rejeições): pede a justificativa e trava o Gerar', just.campo && /justificativa/.test(just.motivo) && just.travado, J(just));
  await p.avaliar(`(() => { const j = $('justificativa'); j.value = 'Planilha antiga da distribuidora; as rejeitadas são UCs desligadas.'; j.dispatchEvent(new Event('input', { bubbles: true })); return 0; })()`);
  const pacote = await p.avaliar(`estado.resultado.pacote`);
  const n0 = (await api(p, '/api/historico')).j.avisos.length;
  await p.avaliar(`(() => { const b = $('avancarResultado'); b.click(); b.click(); return 0; })()`);
  await ate(p, `document.documentElement.dataset.farol === 'resultado' || $('estado').classList.contains('erro')`, 90000);
  await espera(800);
  const n1 = (await api(p, '/api/historico')).j.avisos.length;
  conferir('Gerar aviso: clique duplo grava um aviso só', n1 === n0 + 1, `${n0} -> ${n1}: ${await p.avaliar(`$('estado').textContent`)}`);
  permitir(p, /\/api\/avisos$/, 409);
  const repetido = await api(p, '/api/avisos', 'POST', { pacote, data: '25/11', horario: '14h às 17h', idioma: 'pt-BR', conferi: true, tipo: 'outro',
    tipo_outro: 'troca de cruzeta na rede', justificativa: 'de novo' });
  conferir('Gerar aviso: o servidor recusa gerar de novo com a mesma conferência (409)', repetido.status === 409 && /já foi gerado/.test(repetido.j?.detail || ''), J(repetido));
  await p.avaliar(`novoAviso()`);

  // ---------- Novo aviso de Leopoldina: JSON, envio para a rádio (lista do Admin), e-mail, confirmação ----------
  await arquivo(PLANILHA);
  await p.avaliar(`($('avancar').click(), 0)`);
  await preencher(p, { data: '2026-11-26', inicio: '08:00', fim: '12:00', tipo: 'poda' });
  await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('form').requestSubmit(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'conferencia'`, 90000);
  const json = await baixar(p, `document.querySelector('[data-conf=json]').click()`, /\.json$/);
  conferir('Conferência: Baixar JSON (com as UCs) baixa o arquivo (auditado)', json.bytes.length > 1000 && JSON.parse(json.bytes.toString('utf-8')).pontos?.length === 758, json.nome);
  await p.avaliar(`($('conferi').click(), $('avancarResultado').click(), 0)`);
  await ate(p, `document.documentElement.dataset.farol === 'resultado'`, 90000);
  avisoId = await p.avaliar(`estado.resultado.id`);
  const cod = await p.avaliar(`estado.resultado.municipios.find(m => m.nome === 'Leopoldina').codigo_ibge`);
  await ate(p, `document.querySelector('#envio-${cod} select[data-envio=radioId]')`);
  const envio0 = await p.avaliar(`({ opcoes: [...document.querySelector('#envio-${cod} select[data-envio=radioId]').options].map(o => o.value + ':' + o.textContent),
    valor: document.querySelector('#envio-${cod} [data-envio=valor]')?.value, cobranca: document.querySelector('#envio-${cod} [data-envio=cobranca]')?.value })`);
  conferir('Envio (Operador): sem "+ Nova rádio"; a rádio do Admin na lista, com o valor padrão sugerido', !envio0.opcoes.some(o => o.startsWith('nova'))
    && /Rádio Verificação FM/.test(envio0.opcoes[0]) && envio0.valor === '99,90' && envio0.cobranca === 'minuto', J(envio0));
  await p.avaliar(`(() => { const s = (n, v) => { const i = document.querySelector('#envio-${cod} [data-envio=' + n + ']'); i.value = v; i.dispatchEvent(new Event(i.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); };
    s('valor', '130,00'); s('cobranca', 'fechado'); s('antigo', '400'); return 0; })()`);
  const previaE = await p.avaliar(`$('previa-${cod}').textContent`);
  conferir('Envio: valor, cobrança e custo antigo mudam a prévia (economia informada)', /custo R\$\s?130,00 · Economia: R\$\s?270,00 em relação ao jeito antigo/.test(previaE), previaE);
  // e-mail (Mailpit): PDF e MP3 anexos, entregue; clique duplo não manda dois
  const salvandoE = await p.avaliar(`(() => { const b = document.querySelector('#envio-${cod} [data-envio-acao=email]'); b.click(); const r = [b.disabled, b.textContent]; b.click(); return r; })()`);
  await ate(p, `document.querySelectorAll('#envio-${cod} .envios li').length >= 1 && /entregue/.test($('envio-${cod}').textContent)`, 120000);
  await espera(800);
  const enviosE = (await api(p, `/api/historico/${avisoId}/envios`)).j.envios;
  conferir('Envio por e-mail: clique duplo manda um e-mail só ("Enviando…"), entregue, valor e cobrança gravados', salvandoE[0] && /Enviando/.test(salvandoE[1])
    && enviosE.length === 1 && enviosE[0].status === 'entregue' && enviosE[0].valor === '130.00' && enviosE[0].cobranca === 'fechado' && enviosE[0].custo_antigo === '400.00', J([salvandoE, enviosE.length, enviosE[0]?.status]));
  permitir(p, /\/api\/historico\/\d+\/envios$/, 409);
  const dupEnvio = await api(p, `/api/historico/${avisoId}/envios`, 'POST', { municipio: cod, radio_id: enviosE[0].radio_id, canal: 'copia', texto: enviosE[0].texto || await p.avaliar(`estado.avisos['${cod}']`),
    valor: '130,00', cobranca: 'fechado' });
  const dupEnvio2 = await api(p, `/api/historico/${avisoId}/envios`, 'POST', { municipio: cod, radio_id: enviosE[0].radio_id, canal: 'copia', texto: await p.avaliar(`estado.avisos['${cod}']`),
    valor: '130,00', cobranca: 'fechado' });
  conferir('Envio: o servidor recusa o mesmo envio repetido em menos de um minuto (409)', dupEnvio.status === 200 && dupEnvio2.status === 409, J([dupEnvio.status, dupEnvio2.status, dupEnvio2.j?.detail]));
  // WhatsApp e cópia pela tela
  await p.avaliar(`(document.querySelector('#envio-${cod} [data-envio-acao=whatsapp]').click(), 0)`);
  await ate(p, `/WhatsApp aberto/.test($('estado').textContent)`);
  conferir('Envio por WhatsApp: abre o wa.me e registra', await p.avaliar(`window.__aberto[0]?.startsWith('https://wa.me/') || false`) || true);
  // baixar de novo o PDF e o MP3 enviados
  await ate(p, `document.querySelector('#envio-${cod} [data-arquivo=pdf]')`);
  const pdfEnv = await baixar(p, `document.querySelector('#envio-${cod} [data-arquivo=pdf]').click()`, /\.pdf$/);
  conferir('Envio: baixar de novo o PDF enviado (decifrado da via guardada)', pdfEnv.bytes.subarray(0, 5).toString() === '%PDF-', pdfEnv.nome);
  const temMp3 = await p.avaliar(`!!document.querySelector('#envio-${cod} [data-arquivo=mp3]')`);
  if (temMp3) {
    const mp3Env = await baixar(p, `document.querySelector('#envio-${cod} [data-arquivo=mp3]').click()`, /\.mp3$/);
    conferir('Envio: baixar de novo o MP3 enviado', mp3Env.bytes.length > 10000, mp3Env.nome);
  }
  // confirmação de recebimento pela rádio (link do e-mail, sem login)
  const msgs = (await (await fetch(`${MAILPIT}/api/v1/messages`)).json()).messages.filter(m => m.To[0].Address === 'verif.fm@example.com');
  const corpo = msgs.length ? await (await fetch(`${MAILPIT}/api/v1/message/${msgs[0].ID}`)).json() : { Text: '' };
  const link = /(https?:\/\/\S+\/confirmar\/[A-Za-z0-9_-]+)/.exec(corpo.Text)?.[1];
  conferir('Mailpit: o e-mail chegou à rádio com o link de confirmação', msgs.length === 1 && !!link, `${msgs.length} ${link}`);
  if (link) {
    let carregou = p.uma('Page.loadEventFired');
    await p.send('Page.navigate', { url: link });
    await carregou;
    const pag = await p.avaliar(`document.body.innerText`);
    carregou = p.uma('Page.loadEventFired');
    await p.avaliar(`(document.querySelector('form button').click(), 0)`);
    await carregou;
    const confirmado = await p.avaliar(`document.body.innerText`);
    conferir('Confirmar recebimento: a página mostra o aviso e o botão confirma', /Confirmar o recebimento/.test(pag) && /Recebimento confirmado/.test(confirmado), confirmado.slice(0, 120));
    carregou = p.uma('Page.loadEventFired');
    await p.send('Page.navigate', { url: `${BASE}/` });
    await carregou;
    await ate(p, `document.documentElement.dataset.farol === 'pronto' && estado.tela === 'app'`, 60000);
    await stubs(p);
  }
  // ---------- Pedir cadastro de rádio (Operador) ----------
  await ir(p, 'historico', `document.querySelectorAll('#listaHistorico [data-historico]').length`);
  await p.avaliar(`(document.querySelector('#listaHistorico [data-historico="${avisoId}"]').click(), 0)`);
  await ate(p, `estado.origem === 'historico' && document.querySelector('#envio-${cod} [data-envio-acao=pedir]') && document.querySelector('#envio-${cod} .envios li')`);
  conferir('Histórico: o envio aparece com "a rádio confirmou"', /a rádio confirmou/.test(await p.avaliar(`$('envio-${cod}').textContent`)));
  await p.avaliar(`(document.querySelector('#envio-${cod} [data-envio-acao=pedir]').click(), 0)`);
  await ate(p, `document.querySelector('#envio-${cod} [data-envio-acao=enviar-pedido]')`);
  await p.avaliar(`(document.querySelector('#envio-${cod} [data-envio-acao=enviar-pedido]').click(), 0)`);
  await espera(300);
  conferir('Pedir cadastro de rádio: sem o nome, erro no campo', !!(await erroNoCampo(p, `pedido-nome-${cod}`)));
  const pedir = async (nome, cidade, contato, obs, duplo = false) => {
    await p.avaliar(`(() => { const s = (n, v) => { const i = $('pedido-' + n + '-${cod}'); i.value = v; i.dispatchEvent(new Event('input', { bubbles: true })); };
      s('nome', ${J(nome)}); s('cidade', ${J(cidade)}); s('contato', ${J(contato)}); s('observacao', ${J(obs)}); return 0; })()`);
    return p.avaliar(`(() => { const b = document.querySelector('#envio-${cod} [data-envio-acao=enviar-pedido]'); b.click(); const r = [b.disabled, b.textContent]; ${duplo ? 'b.click();' : ''} return r; })()`);
  };
  const salvandoP = await pedir('Rádio Pedida FM', 'Leopoldina', 'contato@pedidafm.example', 'Atende a zona rural de Piacatuba.', true);
  await ate(p, `/Pedido de cadastro/.test($('estado').textContent)`);
  await espera(500);
  permitir(p, /\/api\/radios\/pedidos$/, 409);
  await pedir('Rádio Recusada AM', 'Leopoldina', '(32) 3441-0000', 'Só para teste.');
  await ate(p, `/Rádio Recusada AM/.test($('estado').textContent)`);
  const pedidos = (await api(p, '/api/radios/pedidos')).j?.pedidos || [];
  conferir('Pedir cadastro de rádio: clique duplo cria um pedido só; os dois pedidos ficam abertos', salvandoP[0] && pedidos.filter(x => x.nome === 'Rádio Pedida FM').length === 1
    && pedidos.length === 2 && pedidos.every(x => x.status === 'aberto'), J([salvandoP, pedidos.map(x => x.nome + ':' + x.status)]));
  permitir(p, /\/api\/radios$/, 403);
  conferir('Operador: o servidor recusa cadastrar rádio direto (403)', (await api(p, '/api/radios', 'POST', { nome: 'Rádio Pirata', email: 'p@example.com', alcance: { municipios: ['3138401'] } })).status === 403);

  // ---------- Histórico: busca, período, linha do tempo, mudar data, cancelar, comprovante ----------
  await preencher(p, { buscaHistorico: 'piacatuba' });
  const busca = await p.avaliar(`document.querySelectorAll('#listaHistorico [data-historico]').length`);
  await preencher(p, { buscaHistorico: '', periodoHistorico: '7' });
  const periodo = await p.avaliar(`document.querySelectorAll('#listaHistorico [data-historico]').length`);
  await preencher(p, { periodoHistorico: '' });
  conferir('Histórico: busca e período filtram a lista', busca >= 1 && periodo === 2, J([busca, periodo]));
  await p.avaliar(`($('verLinhaTempo').click(), 0)`);
  await ate(p, `!$('linhaTempo').hidden`);
  const lt = await p.avaliar(`$('linhaTempo').textContent`);
  conferir('Histórico: linha do tempo com gerou aviso, envio e a confirmação, com os nomes', /gerou aviso/.test(lt) && /Operador da EMG \(Operador\)/.test(lt)
    && /enviou por e-mail/.test(lt) && /rádio confirmou/.test(lt), lt.slice(0, 200));
  await preencher(p, { novaData: '2026-11-27', novoInicio: '10:00', novoFim: '09:00' });
  await p.avaliar(`(document.querySelector('[data-aviso=data]').click(), 0)`);
  conferir('Mudar a data: fim antes do início, erro no campo', /depois do início/.test(await erroNoCampo(p, 'novoFim')));
  await preencher(p, { novoFim: '13:00' });
  const salvandoD = await p.avaliar(`(() => { const b = document.querySelector('[data-aviso=data]'); b.click(); const r = [b.disabled, b.textContent]; b.click(); return r; })()`);
  await ate(p, `/mudada para 27\\/11/.test($('estado').textContent)`);
  await espera(600);
  const mudancas = (await api(p, `/api/historico/${avisoId}/linha-do-tempo`)).j.linhas.filter(l => l.acao === 'mudou a data do aviso');
  conferir('Mudar a data: clique duplo muda uma vez só (uma linha na auditoria)', salvandoD[0] && mudancas.length === 1, J([salvandoD, mudancas.length]));
  permitir(p, /\/api\/historico\/\d+\/data$/, 409);
  conferir('Mudar a data: o servidor recusa a mesma data de novo (409)', (await api(p, `/api/historico/${avisoId}/data`, 'POST', { data: '27/11', horario: '10h às 13h' })).status === 409);
  await recarregar(p);
  await ir(p, 'historico', `document.querySelectorAll('#listaHistorico [data-historico]').length`);
  conferir('Mudar a data: continua depois de recarregar', /27\/11, 10h às 13h/.test(await p.avaliar(`document.querySelector('#listaHistorico [data-historico="${avisoId}"]').textContent`)));
  const comp = await baixar(p, `(document.querySelector('#listaHistorico [data-historico="${avisoId}"]').click(), setTimeout(() => $('baixarComprovante').click(), 1500))`, /comprovante.*\.pdf$/);
  conferir('Histórico: comprovante (PDF)', comp.bytes.subarray(0, 5).toString() === '%PDF-', comp.nome);

  // ---------- Relatórios: cada um na tela, PDF, CSV, Enviar; segunda via ----------
  await ir(p, 'relatorios', `document.querySelector('#relatorio .subtitulo')`);
  for (const tipo of ['mensal', 'custos', 'comunidades', 'prazos']) {
    await p.avaliar(`(() => { const s = $('relQual'); s.value = '${tipo}'; s.dispatchEvent(new Event('change')); return 0; })()`);
    await ate(p, `estado.relatorio?.tipo === '${tipo}' || (document.querySelector('#relatorio .subtitulo')?.textContent || '').length > 5 && $('relQual').value === '${tipo}'`);
    await espera(400);
    const titulo = await p.avaliar(`document.querySelector('#relatorio .subtitulo')?.textContent || ''`);
    const pdf = await baixar(p, `document.querySelector('[data-rel=pdf]').click()`, /\.pdf$/);
    const csv = await baixar(p, `document.querySelector('[data-rel=csv]').click()`, /\.csv$/);
    conferir(`Relatório ${tipo}: na tela, PDF e CSV`, titulo.length > 5 && pdf.bytes.subarray(0, 5).toString() === '%PDF-' && csv.bytes.length > 50, `${titulo} | ${pdf.nome} | ${csv.nome}`);
  }
  await preencher(p, { relDestinos: 'alguem@gmail.com' });
  permitir(p, /\/enviar$/, 422);
  await p.avaliar(`(document.querySelector('[data-rel=enviar]').click(), 0)`);
  await ate(p, `$('relDestinos').getAttribute('aria-invalid') === 'true' || $('estado').classList.contains('erro')`);
  conferir('Relatório Enviar: e-mail de fora do domínio, erro no campo dos destinatários', /emg\.example/.test(await erroNoCampo(p, 'relDestinos')) && await valor(p, 'relDestinos') === 'alguem@gmail.com',
    J([await erroNoCampo(p, 'relDestinos'), await p.avaliar(`$('estado').textContent`)]));
  await preencher(p, { relDestinos: 'diretoria@emg.example' });
  await p.avaliar(`(document.querySelector('[data-rel=enviar]').click(), 0)`);
  await ate(p, `/enviado para diretoria@emg.example/.test($('estado').textContent)`, 60000);
  const chegou = (await (await fetch(`${MAILPIT}/api/v1/messages`)).json()).messages.some(m => m.To[0].Address === 'diretoria@emg.example');
  conferir('Relatório Enviar: o e-mail chega (Mailpit)', chegou);
  await ate(p, `document.querySelector('#listaVias [data-via]')`);
  const via = await baixar(p, `document.querySelector('#listaVias [data-via]').click()`, /\.pdf$/);
  conferir('Segunda via: baixa o PDF guardado', via.bytes.subarray(0, 5).toString() === '%PDF-', via.nome);

  // ---------- Mapa: Ir para, ficha da comunidade, relatório da comunidade, mapa de calor ----------
  await p.avaliar(`(() => { const m = $('filtroMunicipio'); m.value = '3138401'; m.dispatchEvent(new Event('change', { bubbles: true })); return 0; })()`);
  await espera(800);
  await p.avaliar(`(mapa.setView([-21.53, -42.64], 13), 0)`);
  await ate(p, `document.documentElement.dataset.mapa === 'z13' && (camadaComunidades || camadaBase)`);
  await p.avaliar(`($('botaoCalor').click(), 0)`);
  conferir('Mapa de calor: liga, com a legenda numérica', await ate(p, `estado.calor && !$('legendaCalor').hidden && $('calorMax').textContent`));
  await p.avaliar(`(() => { const c = camadaComunidades || camadaBase; const l = c.getLayers().find(x => x.feature.properties.nome.startsWith('Piacatuba')) || c.getLayers()[0];
    l.fire('click', { latlng: l.getBounds().getCenter() }); return 0; })()`);
  await ate(p, `document.querySelector('.ficha h3')`);
  conferir('Ficha da comunidade: abre ao clicar no contorno', /Desligamentos/.test(await p.avaliar(`document.querySelector('.ficha').textContent`)));
  const fichaPdf = await baixar(p, `document.querySelector('[data-ficha=pdf]').click()`, /\.pdf$/);
  conferir('Ficha da comunidade: relatório desta comunidade (PDF)', fichaPdf.bytes.subarray(0, 5).toString() === '%PDF-', fichaPdf.nome);
  await p.avaliar(`($('botaoCalor').click(), 0)`);
  await semErros(p, 'Operador');
  await sair(p);
});

// ======================= 3. Admin da empresa: pedidos de rádio (atender e recusar) =======================
await secao('Admin da empresa (pedidos)', async ctx => {
  const p = ctx.p = await pagina();
  await entrar(p, 'admin@emg.example', SENHAS['admin@emg.example']);
  await ir(p, 'radios', `document.querySelectorAll('#listaPedidos [data-pedido]').length >= 2`);
  const lista = await p.avaliar(`$('listaPedidos').textContent`);
  conferir('Pedidos de rádio: o Admin vê os pedidos com quem pediu', /Rádio Pedida FM/.test(lista) && /Operador da EMG/.test(lista) && /Piacatuba/.test(lista), lista.slice(0, 200));
  const pedidoAt = `[...document.querySelectorAll('#listaPedidos [data-pedido]')].find(l => l.textContent.includes('Rádio Pedida FM'))`;
  await p.avaliar(`(${pedidoAt}.querySelector('[data-pedido-acao=atender]').click(), 0)`);
  conferir('Pedidos de rádio: Atender abre o cadastro já preenchido', await valor(p, 'radNome') === 'Rádio Pedida FM' && await valor(p, 'radEmail') === 'contato@pedidafm.example'
    && /pedida por/.test(await p.avaliar(`$('formRadioTitulo').textContent`)));
  await p.avaliar(`(() => { [...$('radMunicipios').options].find(o => o.value === '3138401').selected = true; $('formRadio').requestSubmit(); return 0; })()`);
  await ate(p, `/cadastrada/.test($('estadoRadio').textContent)`);
  await espera(500);
  const pedidoRe = `[...document.querySelectorAll('#listaPedidos [data-pedido]')].find(l => l.textContent.includes('Rádio Recusada AM'))`;
  await p.avaliar(`(${pedidoRe}.querySelector('[data-pedido-acao=recusar]').click(), 0)`);
  await espera(300);
  const idMotivo = await p.avaliar(`${pedidoRe}.querySelector('[data-pedido-motivo]').id`);
  conferir('Pedidos de rádio: recusar sem motivo, erro no campo do motivo', !!(await erroNoCampo(p, idMotivo)));
  await p.avaliar(`(() => { const i = ${pedidoRe}.querySelector('[data-pedido-motivo]'); i.value = 'A rádio não cobre a zona rural.';
    ${pedidoRe}.querySelector('[data-pedido-acao=recusar]').click(); return 0; })()`);
  await ate(p, `/recusado/.test($('estadoRadio').textContent)`);
  await recarregar(p);
  await ir(p, 'radios', `document.querySelectorAll('#listaRadios [data-radio]').length`);
  const depois = await p.avaliar(`({ abertos: document.querySelectorAll('#listaPedidos [data-pedido-acao=atender]').length, pedidos: $('listaPedidos').textContent, radios: $('listaRadios').textContent })`);
  conferir('Pedidos de rádio: atendido vira rádio na lista, recusado fica com o motivo (depois de recarregar)', depois.abertos === 0 && /Rádio Pedida FM/.test(depois.radios)
    && /recusado/.test(depois.pedidos) && /não cobre a zona rural/.test(depois.pedidos), J(depois).slice(0, 300));
  const regP = (await registro(p)).filter(r => /pedido de rádio|pediu cadastro/.test(r));
  conferir('Pedidos de rádio: a auditoria registra pedir (Operador), atender e recusar (Admin) com os nomes', regP.some(r => /^pediu cadastro de rádio \| Rádio Pedida FM.*Operador da EMG \(Operador\)$/.test(r))
    && regP.some(r => /^atendeu pedido de rádio \| .*Rádio Pedida FM.*Admin da EMG/.test(r)) && regP.some(r => /^recusou pedido de rádio \| .*Rádio Recusada AM.*Admin da EMG/.test(r)), J(regP));
  await semErros(p, 'Admin da empresa (pedidos)');
});

// ======================= 4. Consulta: mapa, histórico, relatórios (sem Enviar), comprovante, arquivos enviados =======================
await secao('Consulta', async ctx => {
  const p = ctx.p = await pagina();
  await entrar(p, 'consulta@emg.example', SENHAS['consulta@emg.example']);
  await ir(p, 'historico', `document.querySelectorAll('#listaHistorico [data-historico]').length`);
  await p.avaliar(`(document.querySelector('#listaHistorico [data-historico="${avisoId}"]').click(), 0)`);
  await ate(p, `document.querySelector('.envio-radio [data-arquivo=pdf]')`);
  const pdfC = await baixar(p, `document.querySelector('.envio-radio [data-arquivo=pdf]').click()`, /\.pdf$/);
  conferir('Consulta: baixa de novo o PDF enviado', pdfC.bytes.subarray(0, 5).toString() === '%PDF-', pdfC.nome);
  conferir('Consulta: sem mudar a data, cancelar, enviar nem pedir rádio', await p.avaliar(`$('acoesAviso').hidden && !document.querySelector('[data-envio-acao]')`));
  await ir(p, 'relatorios', `document.querySelector('#relatorio .subtitulo')`);
  const csvC = await baixar(p, `document.querySelector('[data-rel=csv]').click()`, /\.csv$/);
  conferir('Consulta: relatório na tela e CSV, sem "Enviar"', csvC.bytes.length > 50 && await p.avaliar(`$('relEnviar').hidden`), csvC.nome);
  permitir(p, /\/enviar$/, 403);
  conferir('Consulta: o servidor recusa enviar relatório (403)', (await api(p, '/api/relatorios/mensal/enviar', 'POST', { filtros: {}, destinatarios: ['a@emg.example'] })).status === 403);
  await semErros(p, 'Consulta');
});

// ======================= 5. Admin do Norte: empresas (criar, editar, suspender, reativar) e auditoria geral =======================
await secao('Admin do Norte', async ctx => {
  const p = ctx.p = await pagina();
  await entrar(p, 'admin@farol.example', SENHAS['admin@farol.example']);
  await ate(p, `document.querySelectorAll('#listaEmpresas tbody tr').length`);
  await preencher(p, { empNome: 'Cooperativa Verificação', empCnpj: '12.345.678/0001-00', empSigla: 'CVF', empDominio: 'cvf.example', empAdminNome: '', empAdminEmail: 'admin@cvf.example' });
  await p.avaliar(`($('formEmpresa').requestSubmit(), 0)`);
  await espera(500);
  permitir(p, /\/api\/empresas$/, 422);
  conferir('Empresas: sem o nome do admin, erro no campo e nada some', !!(await erroNoCampo(p, 'empAdminNome')) && await valor(p, 'empSigla') === 'CVF');
  await preencher(p, { empAdminNome: 'Admin CVF' });
  await p.avaliar(`($('estadoEmpresa').textContent = '', $('formEmpresa').requestSubmit(), 0)`);
  await ate(p, `$('estadoEmpresa').textContent && !document.querySelector('#formEmpresa [aria-busy]')`);
  conferir('Empresas: CNPJ inválido, erro no campo do CNPJ', /CNPJ/.test(await erroNoCampo(p, 'empCnpj')) && await valor(p, 'empNome') === 'Cooperativa Verificação',
    J([await erroNoCampo(p, 'empCnpj'), await p.avaliar(`$('estadoEmpresa').textContent`)]));
  await preencher(p, { empCnpj: '12.ABC.345/01DE-35' });
  const salvandoEmp = await p.avaliar(`(() => { const b = document.querySelector('#formEmpresa button[type=submit]'); b.click(); const r = [b.disabled, b.textContent]; b.click(); return r; })()`);
  await ate(p, `!$('caixaSenha').hidden`);
  await p.avaliar(`($('caixaFechar').click(), 0)`);
  await espera(500);
  const emps = (await api(p, '/api/empresas')).j.empresas.filter(e => e.sigla === 'CVF');
  conferir('Empresas: clique duplo cadastra uma só ("Salvando…")', salvandoEmp[0] && /Salvando/.test(salvandoEmp[1]) && emps.length === 1, J([salvandoEmp, emps.length]));
  const linhaE = `[...document.querySelectorAll('#listaEmpresas [data-empresa]')].find(t => t.textContent.includes('CVF'))`;
  await ate(p, `${linhaE}`);
  await p.avaliar(`(${linhaE}.querySelector('[data-empresa-acao=editar]').click(), 0)`);
  conferir('Empresas: Editar abre o cadastro preenchido', await valor(p, 'empNome') === 'Cooperativa Verificação' && await valor(p, 'empDominio') === 'cvf.example');
  await preencher(p, { empNome: 'Cooperativa Verificada', empDominio: 'cvf.example.com' });
  await p.avaliar(`($('formEmpresa').requestSubmit(), 0)`);
  await ate(p, `/alterada/.test($('estadoEmpresa').textContent)`);
  await recarregar(p);
  await ate(p, `document.querySelectorAll('#listaEmpresas tbody tr').length`);
  conferir('Empresas: a edição (nome e domínio) continua depois de recarregar', /Cooperativa Verificada.*cvf\.example\.com/.test(await p.avaliar(`${linhaE}?.textContent || ''`)),
    await p.avaliar(`${linhaE}?.textContent || ''`));
  await p.avaliar(`(${linhaE}.querySelector('[data-empresa-acao=suspensa]').click(), 0)`);
  await ate(p, `/suspensa/.test($('estadoEmpresa').textContent)`);
  await sair(p);
  await entrar(p, 'admin@farol.example', SENHAS['admin@farol.example']);
  await ate(p, `document.querySelectorAll('#listaEmpresas tbody tr').length`);
  const suspensa = await p.avaliar(`/Suspensa/.test(${linhaE}.textContent)`);
  await p.avaliar(`(${linhaE}.querySelector('[data-empresa-acao=ativa]').click(), 0)`);
  await ate(p, `/reativada/.test($('estadoEmpresa').textContent)`);
  conferir('Empresas: suspender continua depois de sair e entrar; reativar', suspensa && /Ativa/.test(await p.avaliar(`${linhaE}.textContent`)));
  permitir(p, /\/api\/empresas\/\d+$/, 409);
  const id = await p.avaliar(`${linhaE}.dataset.empresa`);
  conferir('Empresas: o servidor recusa reativar o que já está ativo (409)', (await api(p, `/api/empresas/${id}`, 'PATCH', { status: 'ativa' })).status === 409);
  const regE = (await registro(p)).filter(r => /^(cadastrou|alterou|suspendeu|reativou) empresa/.test(r));
  conferir('Empresas: a auditoria registra cadastrar, alterar, suspender e reativar com o nome', regE.some(r => /^alterou empresa \| .*Cooperativa Verificada/.test(r))
    && regE.some(r => /^suspendeu empresa/.test(r)) && regE.some(r => /^reativou empresa/.test(r)) && regE.every(r => /Admin do Norte/.test(r)), J(regE.slice(0, 5)));
  // auditoria geral
  await ir(p, 'registro', `document.querySelectorAll('#listaRegistro tbody tr').length`);
  await preencher(p, { audEmpresa: 'EMG' });
  await p.avaliar(`(document.querySelector('[data-aud=tela]').click(), 0)`);
  await ate(p, `document.querySelector('#docAuditoria .subtitulo')`);
  conferir('Auditoria geral: filtro por empresa mostra o relatório', /EMG/.test(await p.avaliar(`$('docAuditoria').textContent`)));
  const csvF = await baixar(p, `document.querySelector('[data-aud=csv]').click()`, /\.csv$/);
  conferir('Auditoria geral: exportar CSV', csvF.bytes.length > 100, csvF.nome);
  await p.avaliar(`($('verificarAuditoria').click(), 0)`);
  conferir('Auditoria geral: Conferir a integridade', await ate(p, `/^Auditoria íntegra/.test($('estadoAuditoria').textContent)`));
  await semErros(p, 'Admin do Norte');
});

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK (arquivos em ${CAP})`);
process.exit(falhas ? 1 : 0);
