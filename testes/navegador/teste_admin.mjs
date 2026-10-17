// Teste da área administrativa (protótipo, saida/admin.html) num navegador de verdade.
// Confere: cada perfil vê só o que pode; tela proibida mostra "Sem acesso"; um nome com HTML
// aparece como texto (sentinela intacta); validação na hora; convite simulado; último admin;
// .toml e registro baixados; nenhuma requisição de rede; console vazio; nenhuma violação de CSP;
// nada em localStorage/sessionStorage; alvos de 44 px nos dois temas, no computador e no celular;
// faixa de protótipo sempre visível. Grava as capturas em saida/capturas_passo17/.
// Uso (na raiz do projeto): node testes/navegador/teste_admin.mjs
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SAIDA = join(RAIZ, 'saida');
const ARQ = join(SAIDA, 'admin.html');
const CAP = join(SAIDA, 'capturas_passo17');
mkdirSync(CAP, { recursive: true });
const html = readFileSync(ARQ, 'utf8');
const fontes = ['admin_template.html', 'admin_modelo.js'].map(f => readFileSync(join(RAIZ, 'src', 'comunidades', 'apresentacao', f), 'utf8')).join('\n');

let n = 0;
const falhas = [];
const ok = (cond, nome) => { n++; if (!cond) falhas.push(nome); else console.log('ok  ' + nome); };
const espera = ms => new Promise(r => setTimeout(r, ms));

// ---------- Conferências no arquivo ----------
const csp = html.match(/Content-Security-Policy" content="([^"]*)"/)[1];
ok(csp.includes("connect-src 'none'") && /script-src( 'sha256-[^']+')+;/.test(csp) && !csp.includes('unsafe-eval') && !csp.includes('http'),
  'CSP: connect-src none, scripts só por hash, nenhum servidor');
// (os comentários citam os nomes; o que não pode haver é o uso)
ok(!/\b(localStorage|sessionStorage)\s*[.[]/.test(fontes), 'código não usa localStorage nem sessionStorage');
ok(!/\.(innerHTML|outerHTML)\s*[+]?=|insertAdjacentHTML|document\.write/.test(fontes), 'código não usa innerHTML (só textContent e value)');

// Ajudas dentro da página (só para o teste)
const AJUDAS = `window.T = {
  ir: h => new Promise(r => { location.hash = h; setTimeout(r, 120); }),
  titulo: () => document.querySelector('#conteudo h1')?.textContent ?? '',
  menu: () => document.getElementById('menu').hidden ? [] : [...document.querySelectorAll('#menuLista a')].map(a => a.textContent),
  aviso: () => document.getElementById('aviso')?.textContent ?? '',
  erro: c => document.getElementById('erro-' + c)?.textContent ?? '',
  digitar: (nome, v, i) => { const el = document.querySelector(i == null ? '[name="' + nome + '"]' : '[name="' + nome + '"][data-i="' + i + '"]');
    if (el.type === 'checkbox') el.checked = v; else el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); },
  clicar: sel => new Promise(r => { document.querySelector(sel).click(); setTimeout(r, 120); }),
  linhas: () => [...document.querySelectorAll('#conteudo tbody tr')].map(tr => [...tr.cells].map(c => c.textContent)),
  async entrar(perfil, empresaId) {
    if (!document.getElementById('btnTrocar').hidden) await T.clicar('#btnTrocar');
    document.querySelector('input[name="perfil"][value="' + perfil + '"]').click();
    await new Promise(r => setTimeout(r, 60));
    if (empresaId && perfil !== 'admin_farol') T.digitar('empresaId', empresaId);
    await T.clicar('form[data-form="entrar"] button[type="submit"]');
  },
};
window.__sentinela = 'intacta'; 0`;

const MEDIR_44 = `(() => [...document.querySelectorAll('button, a[href], input, select, summary, textarea')].filter(el => {
  const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
  if (!r.width || !r.height || cs.visibility === 'hidden' || el.closest('[hidden]')) return false;
  return r.width < 43.5 || r.height < 43.5;
}).map(el => el.tagName.toLowerCase() + (el.name ? '[' + el.name + ']' : '') + ' "' + (el.textContent || el.value || '').trim().slice(0, 25) + '" '
  + Math.round(el.getBoundingClientRect().width) + '×' + Math.round(el.getBoundingClientRect().height)))()`;
const FAIXA_VISIVEL = `(() => { const f = document.getElementById('faixa'), r = f.getBoundingClientRect();
  return r.top >= 0 && r.top < 2 && r.height > 20 && getComputedStyle(f).visibility === 'visible' && f.textContent.includes('Protótipo de demonstração'); })()`;

async function abrirAdmin(largura, altura) {
  const rede = [];
  const p = await abrir(ARQ, { largura, altura, antesDeNavegar: async pg => {
    await pg.send('Network.enable');
    pg.on('Network.requestWillBeSent', e => { if (!/^(file|data|blob):/.test(e.request.url)) rede.push(e.request.url); });
  } });
  p.rede = rede;
  await p.avaliar(AJUDAS);
  return p;
}
async function capturar(p, nome) {
  await p.avaliar('window.scrollTo(0, 0), new Promise(r => setTimeout(r, 50))');  // a faixa fixa sai no topo da captura inteira
  const r = await p.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  writeFileSync(join(CAP, nome), Buffer.from(r.data, 'base64'));
}

// =====================================================================================
// 1. Fluxo completo no computador
// =====================================================================================
const TMP = mkdtempSync(join(tmpdir(), 'farol-admin-'));
const p = await abrirAdmin(1440, 900);
const av = e => p.avaliar(e);
await p.navegador.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: TMP, eventsEnabled: true });

ok(await av(FAIXA_VISIVEL), 'faixa de protótipo visível na entrada');
ok((await av('T.titulo()')) === 'Entrar (simulado)', 'abre na entrada simulada');
await capturar(p, '1_entrar.png');

// --- Admin do Norte ---
await av("T.entrar('admin_farol')");
ok(JSON.stringify(await av('T.menu()')) === JSON.stringify(['Empresas', 'Registro de atividades']), 'Admin do Norte: menu Empresas e Registro');
ok((await av('T.titulo()')) === 'Empresas' && (await av('T.linhas().length')) === 2, 'Admin do Norte: lista as 2 empresas');
await av("T.digitar('busca', 'cataguases')");
ok((await av('T.linhas().length')) === 1 && (await av('T.linhas()[0][0]')) === 'Cooperativa Rural Exemplo', 'busca por município');
await av("T.digitar('busca', '')");
await capturar(p, '2_empresas.png');

// Nova empresa: validação na hora e nome com HTML
await av("T.ir('#/empresa/nova')");
ok((await av('T.titulo()')) === 'Nova empresa', 'formulário de nova empresa');
ok((await av("T.erro('cnpj')")) === '', 'sem mensagem antes de digitar');
await av("T.digitar('cnpj', '11.222.333/0001-82')");
ok((await av("T.erro('cnpj')")).includes('CNPJ inválido'), 'CNPJ inválido avisado na hora');
await av("T.digitar('cnpj', '11.222.333/0001-81')");
ok((await av("T.erro('cnpj')")) === '', 'CNPJ válido limpa a mensagem');
const XSS = '<img src=x onerror="window.__sentinela=\'violada\'">';
const campos = { razaoSocial: 'Empresa Teste de Segurança Ltda.', nomeFantasia: XSS, emailInstitucional: 'contato@teste.example.com',
  telefone: '0800 000 0003', gestorNome: 'Gestor Teste', gestorEmail: 'gestor@teste.example.com', dpoNome: 'DPO Teste',
  dpoEmail: 'dpo@teste.example.com', contratoInicio: '2026-10-01', contratoFim: '2027-09-30', dominio: 'teste.example.com' };
for (const [c, v] of Object.entries(campos)) await av(`T.digitar(${JSON.stringify(c)}, ${JSON.stringify(v)})`);
await av("T.clicar('[data-acao=\"adicionar-municipio\"]')");
await av("T.digitar('municipio-codigo', '3138402', 0)");
await av("T.digitar('municipio-nome', 'Leopoldina', 0)");
ok((await av("T.erro('municipio0')")).includes('Código IBGE inválido'), 'código IBGE com DV errado avisado na hora');
await av("T.digitar('antecedenciaHoras', '48')");
ok((await av("T.erro('antecedenciaHoras')")).includes('72'), 'antecedência menor que 72 h avisada');
await av("T.digitar('antecedenciaHoras', '72')");
await av("T.clicar('form[data-form=\"empresa\"] button[type=\"submit\"]')");
ok((await av('T.aviso()')).includes('Corrija') && (await av("T.titulo()")) === 'Nova empresa', 'não salva com erro e diz o que corrigir');
await capturar(p, '3_empresa_com_erros.png');
await av("T.digitar('municipio-codigo', '3138401', 0)");
await av("T.clicar('form[data-form=\"empresa\"] button[type=\"submit\"]')");
ok((await av('T.titulo()')) === `Editar ${XSS}`, 'empresa cadastrada; nome com HTML aparece como texto no título');
ok((await av('T.aviso()')).includes('Empresa cadastrada'), 'aviso de empresa cadastrada');
ok((await av("document.querySelectorAll('#conteudo img, body img').length")) === 0, 'nenhuma imagem criada pelo nome');
ok((await av('window.__sentinela')) === 'intacta', 'sentinela intacta (o onerror não rodou)');
const idNova = await av("decodeURIComponent(location.hash.split('/')[2])");
await capturar(p, '4_empresa_cadastrada.png');

// .toml da empresa nova
await av("T.clicar('[data-acao=\"gerar-toml\"]')");
await espera(800);
const baixados = readdirSync(TMP).filter(f => f.endsWith('.toml'));
ok(baixados.length === 1, `.toml baixado (${baixados.join(', ')})`);
const toml = baixados.length ? readFileSync(join(TMP, baixados[0]), 'utf8') : '';
ok(toml.includes('codigo_ibge = "3138401"') && toml.includes('[perfis.agropecuaria]') && !toml.includes('@'), '.toml com o município, os perfis e sem e-mails');
if (baixados.length) writeFileSync(join(CAP, 'empresa_nova.toml'), toml);

// Convite de usuário na empresa nova
await av(`T.ir('#/usuarios/${idNova}')`);
ok((await av('T.linhas()[0][0]')) === 'Nenhum usuário encontrado.', 'empresa nova sem usuários');
await av(`T.ir('#/usuario/${idNova}/novo')`);
await av("T.digitar('nome', 'Pessoa Teste')");
await av("T.digitar('email', 'pessoa@outro.example.com')");
ok((await av("T.erro('email')")).includes('@teste.example.com'), 'e-mail fora do domínio avisado na hora');
await av("T.digitar('email', 'pessoa@teste.example.com')");
await av("T.digitar('perfil', 'admin_empresa')");
ok((await av("document.querySelector('[name=\"doisFatores\"]').checked && document.querySelector('[name=\"doisFatores\"]').disabled")), '2 etapas obrigatória: marcada e travada');
ok((await av("document.querySelectorAll('[name=\"cpf\"], [name=\"nascimento\"], [name=\"endereco\"], [name=\"telefonePessoal\"]').length")) === 0, 'formulário sem CPF, nascimento, endereço ou telefone pessoal');
await capturar(p, '5_convidar_usuario.png');
await av("T.clicar('form[data-form=\"usuario\"] button[type=\"submit\"]')");
ok((await av('T.aviso()')).includes('Convite simulado') && (await av('T.aviso()')).includes('Nenhuma senha foi criada'), 'convite simulado explicado');
ok((await av('T.linhas()[0][4]')) === 'Convidado', 'usuário aparece como convidado');
await av("T.clicar('[data-acao=\"alternar-bloqueio\"]')");
ok((await av('T.aviso()')).includes('último admin'), 'não bloqueia o último admin');
await capturar(p, '6_usuarios.png');

// Suspender empresa
await av("T.ir('#/empresas')");
await av("T.clicar('[data-acao=\"alternar-empresa\"][data-id=\"emp-2\"]')");
await av("T.ir('#/usuarios/emp-2')");
ok((await av('T.linhas().every(l => l[4] === "Bloqueado (empresa suspensa)")')), 'empresa suspensa: usuários bloqueados');
await av("T.ir('#/empresas')");
await av("T.clicar('[data-acao=\"alternar-empresa\"][data-id=\"emp-2\"]')");

// Registro
await av("T.ir('#/registro')");
const reg = await av("T.linhas().map(l => l[2])");
ok(['criou empresa', 'gerou arquivo de configuração', 'convidou usuário (simulado)', 'suspendeu empresa', 'reativou empresa'].every(a => reg.includes(a)), 'registro com as atividades');
await capturar(p, '7_registro.png');
await av("T.clicar('[data-acao=\"baixar-registro\"]')");
await espera(800);
const txt = readdirSync(TMP).find(f => f.endsWith('.txt'));
ok(!!txt && readFileSync(join(TMP, txt), 'utf8').includes('criou empresa'), 'registro baixado em .txt');

// --- Admin da empresa: só a própria empresa ---
await av("T.entrar('admin_empresa', 'emp-1')");
ok(JSON.stringify(await av('T.menu()')) === JSON.stringify(['Usuários', 'Configuração', 'Registro de atividades']), 'Admin da empresa: menu Usuários, Configuração e Registro');
ok((await av('T.titulo()')) === 'Usuários · Distribuidora Demonstração MG' && (await av('T.linhas().length')) === 3, 'Admin da empresa: só os 3 usuários da própria empresa');
for (const rota of ['#/empresas', '#/empresa/emp-1', '#/empresa/nova', '#/usuarios/emp-2', '#/usuario/emp-2/usu-4', '#/usuario/emp-1/usu-4', '#/configuracao/emp-2', `#/usuarios/${idNova}`]) {
  await av(`T.ir('${rota}')`);
  ok((await av('T.titulo()')) === 'Sem acesso', `Admin da empresa: ${rota} mostra "Sem acesso"`);
}
await capturar(p, '8_sem_acesso.png');
await av("T.ir('#/registro')");
const regEmp = await av("T.linhas().map(l => l.join(' | '))");
ok(regEmp.every(l => !l.includes('<img') && !l.includes('Cooperativa')), 'Admin da empresa: registro só da própria empresa');
await av("T.ir('#/configuracao/emp-1')");
await av("T.digitar('antecedenciaHoras', '70')");
ok((await av("T.erro('antecedenciaHoras')")).includes('72'), 'configuração: antecedência validada');
await av("T.digitar('antecedenciaHoras', '96')");
await av("T.clicar('form[data-form=\"configuracao\"] button[type=\"submit\"]')");
ok((await av('T.aviso()')).includes('Configuração salva'), 'configuração salva');
await capturar(p, '9_configuracao.png');

// --- Operador e Consulta ---
for (const perfil of ['operador', 'consulta']) {
  await av(`T.entrar('${perfil}', 'emp-1')`);
  ok((await av('T.titulo()')) === 'Sem acesso à administração' && (await av('T.menu().length')) === 0, `${perfil}: "Sem acesso à administração", sem menu`);
  ok((await av("document.querySelector('#conteudo a.botao').getAttribute('href')")) === 'index.html', `${perfil}: link para os mapas`);
  await av("T.ir('#/usuarios/emp-1')");
  ok((await av('T.titulo()')) === 'Sem acesso à administração', `${perfil}: rota de usuários bloqueada`);
}
await capturar(p, '10_operador.png');

// Recarregar volta à demonstração
await av('location.reload(), 0');
await espera(800);
await p.avaliar(AJUDAS);
await av("T.entrar('admin_farol')");
ok((await av('T.linhas().length')) === 2, 'recarregar volta aos dados de demonstração');
ok((await av('localStorage.length + sessionStorage.length')) === 0, 'nada gravado no navegador');
await av('window.scrollTo(0, 1e6), 0');
ok(await av(FAIXA_VISIVEL), 'faixa visível depois de rolar');

ok(p.rede.length === 0, `nenhuma requisição de rede ${JSON.stringify(p.rede)}`);
ok(p.excecoes.length === 0, `nenhuma exceção ${JSON.stringify(p.excecoes)}`);
ok(p.logs.length === 0, `console vazio ${JSON.stringify(p.logs)}`);
ok((await av('window.__csp.length')) === 0, `nenhuma violação de CSP ${JSON.stringify(await av('window.__csp'))}`);
await p.fechar();
rmSync(TMP, { recursive: true, force: true });

// =====================================================================================
// 2. Alvos de 44 px, faixa e rolagem horizontal: cada tela, dois temas, computador e celular
// =====================================================================================
const TELAS = [
  ['entrada', null, '#/entrar'], ['empresas', 'admin_farol', '#/empresas'], ['nova empresa', 'admin_farol', '#/empresa/nova'],
  ['editar empresa', 'admin_farol', '#/empresa/emp-1'], ['usuários', 'admin_farol', '#/usuarios/emp-1'],
  ['convidar', 'admin_farol', '#/usuario/emp-1/novo'], ['editar usuário', 'admin_farol', '#/usuario/emp-1/usu-2'],
  ['registro', 'admin_farol', '#/registro'], ['configuração', 'admin_empresa', '#/configuracao/emp-1'],
  ['sem acesso', 'admin_empresa', '#/empresas'], ['sem acesso (operador)', 'operador', '#/sem-acesso'],
];
for (const [largura, altura, disp] of [[1440, 900, 'computador'], [390, 844, 'celular']]) {
  const q = await abrirAdmin(largura, altura);
  const aq = e => q.avaliar(e);
  for (const tema of ['claro', 'escuro']) {
    while ((await aq("document.getElementById('btnTema').textContent")) !== `Tema: ${tema}`) await aq("T.clicar('#btnTema')");
    let perfilAtual = null;
    for (const [nome, perfil, rota] of TELAS) {
      if (perfil !== perfilAtual) {
        if (perfil) await aq(`T.entrar('${perfil}', 'emp-1')`); else if (!(await aq("document.getElementById('btnTrocar').hidden"))) await aq("T.clicar('#btnTrocar')");
        perfilAtual = perfil;
      }
      await aq(`T.ir('${rota}')`);
      const pequenos = await aq(MEDIR_44);
      ok(pequenos.length === 0, `${disp}, tema ${tema}, ${nome}: alvos ≥ 44 px ${pequenos.length ? JSON.stringify(pequenos) : ''}`);
      ok(await aq(FAIXA_VISIVEL), `${disp}, tema ${tema}, ${nome}: faixa visível`);
      if (disp === 'celular') ok((await aq('document.documentElement.scrollWidth')) <= largura, `${disp}, tema ${tema}, ${nome}: sem rolagem horizontal`);
      if (tema === 'escuro' || disp === 'celular') await capturar(q, `${disp}_${tema}_${nome.replace(/[^a-z0-9]+/gi, '_')}.png`);
    }
  }
  ok(q.rede.length === 0 && q.excecoes.length === 0 && q.logs.length === 0 && (await aq('window.__csp.length')) === 0, `${disp}: sem rede, exceção, console ou CSP`);
  await q.fechar();
}

console.log(`\n${n - falhas.length} de ${n} verificações OK`);
if (falhas.length) { console.log('Falhas:'); falhas.forEach(f => console.log(' - ' + f)); process.exit(1); }
