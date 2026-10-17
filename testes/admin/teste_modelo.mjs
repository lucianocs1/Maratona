// Teste do Model da área administrativa (admin_modelo.js), sem navegador: só o Node 22+.
// Usa o Model e os dados embutidos em saida/admin.html (o que o navegador recebe) e confere:
// CNPJ, domínio, código IBGE, permissões por perfil, isolamento entre empresas, último admin,
// registro e o arquivo .toml. Grava os .toml das empresas de demonstração em
// saida/admin_toml_teste/ e pede ao Python para carregá-los com distribuidora.py.
// Uso (na raiz do projeto): node testes/admin/teste_modelo.mjs
import { readFileSync, mkdirSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const ARQ_ADMIN = join(RAIZ, 'saida', 'admin.html');
const ARQ_MODELO = join(RAIZ, 'src', 'comunidades', 'apresentacao', 'admin_modelo.js');
if (!existsSync(ARQ_ADMIN)) { console.error('Falta saida/admin.html: rode py -m uv run python -m comunidades.apresentacao.admin'); process.exit(1); }

const html = readFileSync(ARQ_ADMIN, 'utf8');
const fonte = readFileSync(ARQ_MODELO, 'utf8');
const D = JSON.parse(html.match(/<script type="application\/json" id="dados">(.*?)<\/script>/s)[1]);
const M = vm.runInNewContext(fonte + '\nModelo');

let n = 0;
const falhas = [];
const ok = (cond, nome) => { n++; if (!cond) falhas.push(nome); };
const igual = (a, b, nome) => ok(JSON.stringify(a) === JSON.stringify(b), `${nome}: ${JSON.stringify(a)} ≠ ${JSON.stringify(b)}`);
const agora = new Date('2026-10-10T12:00:00Z');
const novo = () => M.criarEstado(D.demo);

// ---------- O Model embutido na página é o mesmo do arquivo-fonte ----------
// ignorando o fim de linha: no Windows o git entrega o .js com CRLF, e o gerador grava LF
const semCR = s => s.replace(/\r\n/g, '\n');
ok(semCR(html).includes(semCR(fonte)), 'admin.html embute exatamente o admin_modelo.js');

// ---------- CNPJ ----------
for (const c of ['11.222.333/0001-81', '11222333000181', '12.ABC.345/01DE-35', '12abc34501de35', 'FA.ROL.DEM/0001-19', 'CO.OPE.XEM/0001-27'])
  ok(M.cnpjValido(c), `CNPJ válido: ${c}`);
for (const c of ['11.222.333/0001-82', '12.ABC.345/01DE-36', '00.000.000/0000-00', 'AA.AAA.AAA/AAAA-00', '1122233300018', '112223330001811',
  '12.ABC.345/01DE-3A', '', '11.222.333/0001-8!'])
  ok(!M.cnpjValido(c), `CNPJ inválido: ${JSON.stringify(c)}`);
igual(M.formatarCNPJ('12abc34501de35'), '12.ABC.345/01DE-35', 'formatar CNPJ alfanumérico');

// ---------- Domínio e e-mail ----------
for (const d of ['example.com', 'distribuidora.example.com', 'empresa.com.br']) ok(M.dominioValido(d), `domínio válido: ${d}`);
for (const d of ['', 'example', '@example.com', 'exa mple.com', '-x.com', 'example..com', 'http://example.com']) ok(!M.dominioValido(d), `domínio inválido: ${d}`);
ok(M.emailNoDominio('Ana@Example.com', 'example.com'), 'e-mail no domínio (maiúsculas)');
ok(!M.emailNoDominio('ana@example.com.br', 'example.com'), 'e-mail de outro domínio parecido');
ok(!M.emailNoDominio('ana@sub.example.com', 'example.com'), 'subdomínio não é o domínio');
ok(!M.emailNoDominio('ana@outra.com', 'example.com'), 'e-mail fora do domínio');

// ---------- Código IBGE ----------
for (const [c, uf] of [['3138401', 'MG'], ['3143906', 'MG'], ['3115300', 'MG'], ['3550308', 'SP'], ['5300108', 'DF'], ['2201919', 'PI']])
  ok(M.ibgeValido(c, uf), `IBGE válido: ${c}/${uf}`);
for (const [c, uf] of [['3138402', 'MG'], ['3138401', 'SP'], ['313840', 'MG'], ['31384010', 'MG'], ['3a38401', 'MG'], ['9938401', null]])
  ok(!M.ibgeValido(c, uf), `IBGE inválido: ${c}/${uf}`);

// ---------- Dados de demonstração: válidos e fictícios ----------
for (const e of D.demo.empresas) {
  igual(M.validarEmpresa(e, D.demo.empresas), {}, `empresa de demonstração válida: ${e.nomeFantasia}`);
  ok(e.dominio.endsWith('example.com'), `domínio de exemplo: ${e.dominio}`);
}
for (const u of D.demo.usuarios) {
  const e = D.demo.empresas.find(x => x.id === u.empresaId);
  igual(M.validarUsuario(u, e, D.demo.usuarios), {}, `usuário de demonstração válido: ${u.nome}`);
  ok(u.email.endsWith('.example.com'), `e-mail de exemplo: ${u.email}`);
  for (const proibido of ['cpf', 'nascimento', 'endereco', 'telefone']) ok(!(proibido in u), `usuário sem ${proibido}`);
}

// ---------- Validação da empresa ----------
{
  const base = { ...D.demo.empresas[1], id: '' };
  const erro = (mudanca, campo) => ok(campo in M.validarEmpresa({ ...base, ...mudanca }, D.demo.empresas), `empresa: erro em ${campo} com ${JSON.stringify(mudanca)}`);
  erro({ cnpj: '11.222.333/0001-82' }, 'cnpj');
  erro({ cnpj: D.demo.empresas[0].cnpj }, 'cnpj');                    // CNPJ repetido
  erro({ dominio: D.demo.empresas[0].dominio }, 'dominio');            // domínio de outra empresa
  erro({ dominio: 'sem-ponto' }, 'dominio');
  erro({ razaoSocial: '  ' }, 'razaoSocial');
  erro({ dpoNome: '' }, 'dpoNome');
  erro({ dpoEmail: 'dpo@' }, 'dpoEmail');
  erro({ telefone: '123' }, 'telefone');
  erro({ site: 'http://inseguro.example.com' }, 'site');
  erro({ antecedenciaHoras: 48 }, 'antecedenciaHoras');               // menor que o prazo legal
  erro({ antecedenciaHoras: 72.5 }, 'antecedenciaHoras');
  erro({ contratoFim: '2026-01-01' }, 'contratoFim');                  // antes do início
  erro({ municipios: [] }, 'municipios');
  erro({ municipios: [{ codigo: '3138402', nome: 'X' }] }, 'municipio0');
  erro({ municipios: [{ codigo: '3550308', nome: 'São Paulo' }] }, 'municipio0'); // outra UF
  erro({ municipios: [{ codigo: '3115300', nome: 'A' }, { codigo: '3115300', nome: 'B' }] }, 'municipio1');
  igual(M.validarEmpresa({ ...base, cnpj: '11.222.333/0001-81', dominio: 'nova.example.com' }, D.demo.empresas), {}, 'empresa nova válida');
}

// ---------- Permissões por perfil ----------
{
  const [e1, e2] = D.demo.empresas.map(e => e.id);
  const farol = { perfil: 'admin_farol', empresaId: null }, adm1 = { perfil: 'admin_empresa', empresaId: e1 };
  for (const a of ['ver_empresas', 'criar_empresa', 'editar_empresa', 'suspender_empresa', 'ver_registro']) ok(M.pode(farol, a, e2), `Admin do Norte: ${a}`);
  for (const a of ['ver_usuarios', 'editar_usuario', 'ver_configuracao', 'editar_configuracao', 'gerar_toml']) {
    ok(M.pode(adm1, a, e1), `Admin da empresa: ${a} na própria`);
    ok(!M.pode(adm1, a, e2), `Admin da empresa: ${a} em outra empresa (negado)`);
  }
  for (const a of ['ver_empresas', 'criar_empresa', 'editar_empresa', 'suspender_empresa']) ok(!M.pode(adm1, a, e1), `Admin da empresa: ${a} (negado)`);
  for (const p of ['operador', 'consulta']) {
    for (const a of ['ver_empresas', 'ver_usuarios', 'editar_usuario', 'ver_configuracao', 'gerar_toml', 'ver_registro'])
      ok(!M.pode({ perfil: p, empresaId: e1 }, a, e1), `${p}: ${a} (negado)`);
    igual(M.menu({ perfil: p, empresaId: e1 }), [], `${p}: menu vazio`);
  }
  ok(!M.pode(null, 'ver_empresas'), 'sem sessão: nada');
}

// ---------- Isolamento entre empresas (operações) ----------
{
  const s = novo(), [e1, e2] = s.empresas.map(e => e.id);
  M.entrar(s, 'admin_empresa', e1, agora);
  const deOutra = s.usuarios.find(u => u.empresaId === e2);
  igual(M.alternarBloqueio(s, deOutra.id, agora).ok, false, 'admin da empresa 1 não bloqueia usuário da empresa 2');
  igual(M.salvarUsuario(s, { ...deOutra, nome: 'Trocado' }, agora).ok, false, 'admin da empresa 1 não edita usuário da empresa 2');
  igual(M.salvarUsuario(s, { ...deOutra, empresaId: e1 }, agora).ok, false, 'não move usuário de outra empresa para a sua');
  igual(M.salvarUsuario(s, { ...M.usuarioVazio(e2), nome: 'X', email: 'x@cooperativa.example.com', municipios: ['3115300'] }, agora).ok, false, 'não convida na outra empresa');
  igual(M.salvarConfiguracao(s, e2, { idioma: 'en', fuso: 'America/Manaus', antecedenciaHoras: 80, motivoPadrao: '' }, agora).ok, false, 'não altera configuração de outra empresa');
  igual(M.gerarConfiguracao(s, e2, '3115300', D.padroesToml, agora).ok, false, 'não gera .toml de outra empresa');
  igual(M.alternarEmpresa(s, e1, agora).ok, false, 'admin da empresa não suspende a própria empresa');
  igual(M.salvarEmpresa(s, { ...s.empresas[0], nomeFantasia: 'Nova' }, agora).ok, false, 'admin da empresa não altera o cadastro');
  igual(s.usuarios.find(u => u.id === deOutra.id).nome, deOutra.nome, 'usuário da outra empresa intacto');
  M.entrar(s, 'operador', e1, agora);
  igual(M.alternarBloqueio(s, s.usuarios[0].id, agora).ok, false, 'operador não bloqueia ninguém');
}

// ---------- Usuários: domínio, municípios, 2 etapas, último admin ----------
{
  const s = novo(), e1 = s.empresas[0];
  M.entrar(s, 'admin_empresa', e1.id, agora);
  const convite = { ...M.usuarioVazio(e1.id), nome: 'Fábio Exemplo', email: 'fabio@distribuidora.example.com', perfil: 'operador', municipios: ['3138401'], doisFatores: true };
  const erroU = (mudanca, campo) => ok(campo in (M.salvarUsuario(s, { ...convite, ...mudanca }, agora).erros || {}), `usuário: erro em ${campo} com ${JSON.stringify(mudanca)}`);
  erroU({ email: 'fabio@outra.example.com' }, 'email');
  erroU({ email: 'ana.exemplo@distribuidora.example.com' }, 'email');   // já cadastrado
  erroU({ municipios: ['3115300'] }, 'municipios');                     // município de outra empresa
  erroU({ municipios: [] }, 'municipios');
  erroU({ doisFatores: false }, 'doisFatores');                         // empresa exige 2 etapas
  erroU({ perfil: 'admin_farol' }, 'perfil');                           // perfil que não é de empresa
  const r = M.salvarUsuario(s, convite, agora);
  ok(r.ok, 'convite válido salvo');
  const criado = s.usuarios.find(u => u.id === r.id);
  igual([criado.status, 'senha' in criado], ['convidado', false], 'convite não cria senha e nasce como convidado');

  const ana = s.usuarios.find(u => u.nome === 'Ana Exemplo');            // único admin da empresa 1
  igual(M.alternarBloqueio(s, ana.id, agora).ok, false, 'não bloqueia o último admin');
  ok('perfil' in (M.salvarUsuario(s, { ...ana, perfil: 'operador' }, agora).erros || {}), 'não rebaixa o último admin');
  ok(M.salvarUsuario(s, { ...criado, perfil: 'admin_empresa', status: 'ativo' }, agora).ok, 'promove outro admin');
  ok(M.alternarBloqueio(s, ana.id, agora).ok, 'com outro admin, pode bloquear');
  igual(M.alternarBloqueio(s, criado.id, agora).ok, false, 'agora o novo admin é o último');

  M.entrar(s, 'admin_farol', null, agora);
  ok(M.alternarEmpresa(s, e1.id, agora).ok, 'Admin do Norte suspende empresa');
  ok(s.usuarios.filter(u => u.empresaId === e1.id).every(u => M.situacaoUsuario(u, e1).codigo === 'bloqueado'), 'empresa suspensa: todos bloqueados');
  ok(M.alternarEmpresa(s, e1.id, agora).ok, 'reativa empresa');
}

// ---------- Registro de atividades ----------
{
  const s = novo(), [e1, e2] = s.empresas.map(e => e.id);
  M.entrar(s, 'admin_farol', null, agora);
  M.salvarEmpresa(s, { ...M.empresaVazia(), ...D.demo.empresas[1], id: '', nomeFantasia: '<img src=x onerror=alert(1)>', cnpj: '11.222.333/0001-81', dominio: 'nova.example.com' }, agora);
  M.entrar(s, 'admin_empresa', e2, agora);
  M.salvarConfiguracao(s, e2, { idioma: 'es', fuso: 'America/Manaus', antecedenciaHoras: 100, motivoPadrao: 'teste' }, agora);
  M.entrar(s, 'admin_empresa', e1, agora);
  const visivel = M.registroVisivel(s);
  ok(visivel.every(r => r.empresaId === e1), 'admin da empresa só vê o registro da própria empresa');
  M.entrar(s, 'admin_farol', null, agora);
  ok(M.registroVisivel(s).some(r => r.acao === 'criou empresa' && r.alvo.includes('<img')), 'Admin do Norte vê tudo, com o alvo em texto');
  ok(M.registroTexto(M.registroVisivel(s)).includes('alterou configuração'), 'registro em texto');
}

// ---------- Arquivo .toml ----------
const PASTA = join(RAIZ, 'saida', 'admin_toml_teste');
rmSync(PASTA, { recursive: true, force: true });
mkdirSync(PASTA, { recursive: true });
{
  const s = novo();
  M.entrar(s, 'admin_farol', null, agora);
  for (const e of s.empresas) for (const m of e.municipios) {
    const r = M.gerarConfiguracao(s, e.id, m.codigo, D.padroesToml, agora);
    ok(r.ok && r.nome.endsWith('.toml'), `gera ${r.nome}`);
    for (const u of s.usuarios) ok(!r.texto.includes(u.email) && !r.texto.includes(u.nome), `${r.nome} sem o usuário ${u.nome}`);
    ok(r.texto.includes(`codigo_ibge = "${m.codigo}"`) && r.texto.includes(`municipio = ${JSON.stringify(m.nome)}`), `${r.nome}: município`);
    ok(r.texto.includes(`prazo_legal_horas = ${e.antecedenciaHoras}`), `${r.nome}: antecedência`);
    writeFileSync(join(PASTA, r.nome), r.texto, 'utf8');
  }
  // Nome com aspas, barra e quebra de linha: o TOML continua válido (o Python confere)
  const e = { ...s.empresas[1], nomeFantasia: 'Coop "Teste"\\ \nlinha 2 <b>' };
  writeFileSync(join(PASTA, 'caracteres-especiais.toml'), M.gerarToml(e, e.municipios[0], D.padroesToml, agora), 'utf8');
}

// ---------- O Python carrega cada .toml com distribuidora.py ----------
const tentativas = [['uv', ['run', 'python', '-m', 'comunidades.validacao.configuracao_admin', PASTA]],
  ['py', ['-m', 'uv', 'run', 'python', '-m', 'comunidades.validacao.configuracao_admin', PASTA]]];
let py = null;
for (const [cmd, args] of tentativas) {
  py = spawnSync(cmd, args, { cwd: RAIZ, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  if (!py.error) break;
}
process.stdout.write(py.stdout || '');
ok(py.status === 0, `distribuidora.py carregou todos os .toml (saída ${py.status}): ${py.stderr || py.error || ''}`);

console.log(`\n${n - falhas.length} de ${n} verificações OK`);
if (falhas.length) { console.log('Falhas:'); falhas.forEach(f => console.log(' - ' + f)); process.exit(1); }
