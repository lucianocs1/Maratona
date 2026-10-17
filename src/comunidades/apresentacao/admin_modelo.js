// =====================================================================================
// MODEL da área administrativa (PROTÓTIPO): estado e regras puras de empresas e usuários.
// Não toca no HTML: recebe valores e devolve valores. O mesmo arquivo vai embutido em
// saida/admin.html (admin.py) e é testado no Node (testes/admin/teste_modelo.mjs).
// Não é controle de acesso real: tudo roda na memória do navegador (ver SEGURANCA.md).
// =====================================================================================
const Modelo = (() => {
  'use strict';

  // ---------- Perfis e permissões ----------
  const PERFIS = {
    admin_farol: 'Admin do Norte',
    admin_empresa: 'Admin da empresa',
    operador: 'Operador',
    consulta: 'Consulta',
  };
  // Perfis que um usuário de empresa pode ter (o Admin do Norte não pertence a empresa)
  const PERFIS_USUARIO = ['admin_empresa', 'operador', 'consulta'];
  const TIPOS_EMPRESA = { distribuidora: 'Distribuidora', cooperativa: 'Cooperativa', permissionaria: 'Permissionária' };
  const IDIOMAS = { 'pt-BR': 'Português (Brasil)', en: 'English', es: 'Español' };
  const FUSOS = ['America/Sao_Paulo', 'America/Bahia', 'America/Fortaleza', 'America/Recife', 'America/Belem',
    'America/Araguaina', 'America/Maceio', 'America/Cuiaba', 'America/Campo_Grande', 'America/Manaus',
    'America/Porto_Velho', 'America/Boa_Vista', 'America/Rio_Branco', 'America/Noronha'];
  const PRAZO_LEGAL_MIN_HORAS = 72;  // REN ANEEL 1.000/2021, art. 436: a antecedência não pode ser menor

  // Código IBGE de cada UF (os 2 primeiros dígitos do código do município)
  const UFS = { RO: '11', AC: '12', AM: '13', RR: '14', PA: '15', AP: '16', TO: '17', MA: '21', PI: '22',
    CE: '23', RN: '24', PB: '25', PE: '26', AL: '27', SE: '28', BA: '29', MG: '31', ES: '32', RJ: '33',
    SP: '35', PR: '41', SC: '42', RS: '43', MS: '50', MT: '51', GO: '52', DF: '53' };

  // ---------- Validações ----------
  const so = (s, re) => String(s ?? '').toUpperCase().replace(re, '');
  const vazio = s => !String(s ?? '').trim();

  // CNPJ numérico e alfanumérico (Receita Federal, a partir de julho de 2026): 12 caracteres
  // [0-9A-Z] e 2 dígitos verificadores numéricos. Valor de cada caractere = código ASCII - 48.
  function normalizarCNPJ(s) { return so(s, /[.\/\-\s]/g); }
  function cnpjValido(s) {
    const c = normalizarCNPJ(s);
    if (!/^[0-9A-Z]{12}[0-9]{2}$/.test(c) || /^(.)\1{13}$/.test(c)) return false;
    const dv = (base, pesos) => {
      const soma = [...base].reduce((t, ch, i) => t + (ch.charCodeAt(0) - 48) * pesos[i], 0);
      const r = soma % 11;
      return r < 2 ? 0 : 11 - r;
    };
    const d1 = dv(c.slice(0, 12), [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
    const d2 = dv(c.slice(0, 12) + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
    return c.slice(12) === `${d1}${d2}`;
  }
  function formatarCNPJ(s) {
    const c = normalizarCNPJ(s);
    return c.length === 14 ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}` : String(s ?? '');
  }

  // Código IBGE de município: 7 dígitos, prefixo da UF e dígito verificador (pesos 1,2,1,2,1,2;
  // soma dos algarismos dos produtos). Alguns municípios têm DV fora da regra: lista do IBGE.
  const IBGE_FORA_DA_REGRA = new Set(['2201919', '2201988', '2202251', '2611533', '3117836', '3152131',
    '4305871', '5203939', '5203962']);
  function ibgeValido(codigo, uf) {
    const c = String(codigo ?? '').trim();
    if (!/^\d{7}$/.test(c)) return false;
    if (uf && UFS[uf] !== c.slice(0, 2)) return false;
    if (!Object.values(UFS).includes(c.slice(0, 2))) return false;
    if (IBGE_FORA_DA_REGRA.has(c)) return true;
    const soma = [...c.slice(0, 6)].reduce((t, d, i) => {
      const p = Number(d) * (i % 2 ? 2 : 1);
      return t + Math.floor(p / 10) + (p % 10);
    }, 0);
    return (10 - (soma % 10)) % 10 === Number(c[6]);
  }

  const RE_DOMINIO = /^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/;
  const RE_EMAIL = /^[a-z0-9._%+-]+@([a-z0-9-]+\.)+[a-z]{2,63}$/;
  const dominioValido = d => RE_DOMINIO.test(String(d ?? '').trim().toLowerCase());
  const emailValido = e => RE_EMAIL.test(String(e ?? '').trim().toLowerCase()) && String(e).length <= 254;
  const emailNoDominio = (e, d) => emailValido(e) && String(e).trim().toLowerCase().endsWith('@' + String(d).trim().toLowerCase());
  // Telefone de atendimento: 0800 (11 dígitos) ou fixo/celular com DDD (10 ou 11 dígitos)
  function telefoneValido(t) {
    const d = String(t ?? '').replace(/\D/g, '');
    return /^0800\d{7}$/.test(d) || /^[1-9][1-9]\d{8,9}$/.test(d);
  }
  const siteValido = s => vazio(s) || /^https:\/\/([a-z0-9-]+\.)+[a-z]{2,63}(\/[^\s]*)?$/i.test(String(s).trim());
  const dataValida = s => /^\d{4}-\d{2}-\d{2}$/.test(s ?? '') && !Number.isNaN(Date.parse(s + 'T00:00:00Z'));

  // ---------- Empresa ----------
  function empresaVazia() {
    return {
      id: '', razaoSocial: '', nomeFantasia: '', cnpj: '', tipo: 'distribuidora',
      emailInstitucional: '', telefone: '', site: '',
      gestorNome: '', gestorEmail: '', dpoNome: '', dpoEmail: '',
      pais: 'Brasil', uf: 'MG', municipios: [],
      idioma: 'pt-BR', fuso: 'America/Sao_Paulo', antecedenciaHoras: PRAZO_LEGAL_MIN_HORAS, motivoPadrao: '',
      status: 'ativa', contratoInicio: '', contratoFim: '', dominio: '', exige2Etapas: true,
      criadoPor: '', criadoEm: '', alteradoPor: '', alteradoEm: '',
    };
  }

  // Devolve { campo: mensagem } (vazio = válida). empresas: as demais, para conferir duplicidade.
  function validarEmpresa(e, empresas = []) {
    const erros = {};
    const outras = empresas.filter(o => o.id !== e.id);
    if (vazio(e.razaoSocial)) erros.razaoSocial = 'Informe a razão social.';
    if (vazio(e.nomeFantasia)) erros.nomeFantasia = 'Informe o nome fantasia (é o que aparece nas mensagens).';
    else if (e.nomeFantasia.trim().length > 80) erros.nomeFantasia = 'Use no máximo 80 caracteres.';
    if (vazio(e.cnpj)) erros.cnpj = 'Informe o CNPJ.';
    else if (!cnpjValido(e.cnpj)) erros.cnpj = 'CNPJ inválido: confira os dígitos verificadores.';
    else if (outras.some(o => normalizarCNPJ(o.cnpj) === normalizarCNPJ(e.cnpj))) erros.cnpj = 'Já existe uma empresa com este CNPJ.';
    if (!TIPOS_EMPRESA[e.tipo]) erros.tipo = 'Escolha o tipo.';
    if (vazio(e.emailInstitucional)) erros.emailInstitucional = 'Informe o e-mail institucional.';
    else if (!emailValido(e.emailInstitucional)) erros.emailInstitucional = 'E-mail inválido.';
    if (vazio(e.telefone)) erros.telefone = 'Informe o telefone de atendimento.';
    else if (!telefoneValido(e.telefone)) erros.telefone = 'Use um 0800 (0800 000 0000) ou um número com DDD.';
    if (!siteValido(e.site)) erros.site = 'O site deve começar com https://';
    if (vazio(e.gestorNome)) erros.gestorNome = 'Informe o gestor do contrato.';
    if (vazio(e.gestorEmail)) erros.gestorEmail = 'Informe o e-mail do gestor.';
    else if (!emailValido(e.gestorEmail)) erros.gestorEmail = 'E-mail inválido.';
    if (vazio(e.dpoNome)) erros.dpoNome = 'Informe o encarregado de dados (DPO), exigido pela LGPD.';
    if (vazio(e.dpoEmail)) erros.dpoEmail = 'Informe o e-mail do encarregado de dados.';
    else if (!emailValido(e.dpoEmail)) erros.dpoEmail = 'E-mail inválido.';
    if (!UFS[e.uf]) erros.uf = 'Escolha a UF.';
    if (!e.municipios.length) erros.municipios = 'Inclua pelo menos um município atendido.';
    const vistos = new Set();
    e.municipios.forEach((m, i) => {
      if (vazio(m.nome)) erros[`municipio${i}`] = 'Informe o nome do município.';
      else if (!ibgeValido(m.codigo, e.uf)) erros[`municipio${i}`] = `Código IBGE inválido para ${e.uf}: 7 dígitos, começando por ${UFS[e.uf] ?? '??'}, com dígito verificador correto.`;
      else if (vistos.has(m.codigo)) erros[`municipio${i}`] = 'Município repetido.';
      vistos.add(m.codigo);
    });
    if (!IDIOMAS[e.idioma]) erros.idioma = 'Escolha o idioma.';
    if (!FUSOS.includes(e.fuso)) erros.fuso = 'Escolha o fuso horário.';
    const h = Number(e.antecedenciaHoras);
    if (!Number.isInteger(h) || h < PRAZO_LEGAL_MIN_HORAS || h > 24 * 60)
      erros.antecedenciaHoras = `A antecedência mínima deve ser um número inteiro de horas, de ${PRAZO_LEGAL_MIN_HORAS} (prazo legal) a 1440.`;
    if (String(e.motivoPadrao ?? '').length > 120) erros.motivoPadrao = 'Use no máximo 120 caracteres.';
    if (!['ativa', 'suspensa'].includes(e.status)) erros.status = 'Escolha o status.';
    if (!dataValida(e.contratoInicio)) erros.contratoInicio = 'Informe o início do contrato.';
    if (!dataValida(e.contratoFim)) erros.contratoFim = 'Informe o fim do contrato.';
    else if (dataValida(e.contratoInicio) && e.contratoFim < e.contratoInicio) erros.contratoFim = 'O fim do contrato não pode ser antes do início.';
    if (vazio(e.dominio)) erros.dominio = 'Informe o domínio de e-mail permitido (ex.: example.com).';
    else if (!dominioValido(e.dominio)) erros.dominio = 'Domínio inválido (ex.: example.com, sem @).';
    else if (outras.some(o => o.dominio.toLowerCase() === e.dominio.trim().toLowerCase())) erros.dominio = 'Este domínio já pertence a outra empresa.';
    return erros;
  }

  // ---------- Usuário ----------
  function usuarioVazio(empresaId) {
    return { id: '', empresaId, nome: '', email: '', cargo: '', perfil: 'operador', municipios: [],
      status: 'convidado', doisFatores: false, ultimoAcesso: '', criadoPor: '', criadoEm: '', alteradoPor: '', alteradoEm: '' };
  }

  function validarUsuario(u, empresa, usuarios = []) {
    const erros = {};
    if (vazio(u.nome)) erros.nome = 'Informe o nome completo.';
    else if (u.nome.trim().length > 100) erros.nome = 'Use no máximo 100 caracteres.';
    if (vazio(u.email)) erros.email = 'Informe o e-mail corporativo.';
    else if (!emailValido(u.email)) erros.email = 'E-mail inválido.';
    else if (!emailNoDominio(u.email, empresa.dominio)) erros.email = `Só e-mails @${empresa.dominio} podem ser cadastrados nesta empresa.`;
    else if (usuarios.some(o => o.id !== u.id && o.email.toLowerCase() === u.email.trim().toLowerCase()))
      erros.email = 'Este e-mail já está cadastrado.';
    if (String(u.cargo ?? '').length > 80) erros.cargo = 'Use no máximo 80 caracteres.';
    if (!PERFIS_USUARIO.includes(u.perfil)) erros.perfil = 'Escolha o perfil.';
    const daEmpresa = new Set(empresa.municipios.map(m => m.codigo));
    if (!u.municipios.length) erros.municipios = 'Escolha pelo menos um município.';
    else if (u.municipios.some(c => !daEmpresa.has(c))) erros.municipios = 'Só é possível escolher municípios da empresa.';
    if (!['convidado', 'ativo', 'bloqueado'].includes(u.status)) erros.status = 'Escolha o status.';
    if (empresa.exige2Etapas && !u.doisFatores) erros.doisFatores = 'Esta empresa exige verificação em 2 etapas.';
    return erros;
  }

  // Situação mostrada na tela: empresa suspensa bloqueia todos os usuários dela
  function situacaoUsuario(u, empresa) {
    if (empresa.status === 'suspensa') return { codigo: 'bloqueado', texto: 'Bloqueado (empresa suspensa)' };
    return { convidado: { codigo: 'convidado', texto: 'Convidado' }, ativo: { codigo: 'ativo', texto: 'Ativo' },
      bloqueado: { codigo: 'bloqueado', texto: 'Bloqueado' } }[u.status];
  }

  const adminsAtivos = (usuarios, empresaId, excetoId) =>
    usuarios.filter(u => u.empresaId === empresaId && u.id !== excetoId && u.perfil === 'admin_empresa' && u.status !== 'bloqueado');

  // A mudança tira o último admin (não bloqueado) da empresa?
  function tiraUltimoAdmin(antes, depois, usuarios) {
    if (!antes || antes.perfil !== 'admin_empresa' || antes.status === 'bloqueado') return false;
    const continuaAdmin = depois && depois.perfil === 'admin_empresa' && depois.status !== 'bloqueado';
    return !continuaAdmin && adminsAtivos(usuarios, antes.empresaId, antes.id).length === 0;
  }

  // ---------- Sessão (simulada) e permissões ----------
  // sessao = { perfil, empresaId } (empresaId só para os perfis de empresa)
  function pode(sessao, acao, empresaId) {
    if (!sessao) return false;
    if (sessao.perfil === 'admin_farol') return true;
    if (sessao.perfil !== 'admin_empresa') return false;
    // Admin da empresa: só a própria empresa, e nunca a lista de empresas nem o cadastro delas
    if (['ver_empresas', 'criar_empresa', 'editar_empresa', 'suspender_empresa'].includes(acao)) return false;
    if (['ver_usuarios', 'editar_usuario', 'ver_configuracao', 'editar_configuracao', 'gerar_toml', 'ver_registro'].includes(acao))
      return acao === 'ver_registro' || empresaId === sessao.empresaId;
    return false;
  }

  // Telas do menu, na ordem
  function menu(sessao) {
    if (!sessao) return [];
    if (sessao.perfil === 'admin_farol') return [['empresas', 'Empresas'], ['registro', 'Registro de atividades']];
    if (sessao.perfil === 'admin_empresa') return [['usuarios', 'Usuários'], ['configuracao', 'Configuração'], ['registro', 'Registro de atividades']];
    return [];
  }

  function quem(sessao, estado) {
    if (sessao.perfil === 'admin_farol') return 'Admin do Norte';
    const e = estado.empresas.find(x => x.id === sessao.empresaId);
    return `${PERFIS[sessao.perfil]} · ${e ? e.nomeFantasia : '?'}`;
  }

  // ---------- Estado e operações (todas conferem a permissão e registram a atividade) ----------
  function criarEstado(demo) {
    const copia = JSON.parse(JSON.stringify(demo));
    return { empresas: copia.empresas, usuarios: copia.usuarios, registro: [], proximoId: 1, sessao: null };
  }
  const novoId = (estado, prefixo) => `${prefixo}-novo-${estado.proximoId++}`;
  const agoraIso = agora => (agora || new Date()).toISOString();

  function registrar(estado, acao, alvo, empresaId, agora) {
    estado.registro.push({ quando: agoraIso(agora), quem: quem(estado.sessao, estado), acao, alvo, empresaId: empresaId ?? null });
  }

  // Registro visível: o Admin do Norte vê tudo; o admin da empresa, só o da própria empresa
  function registroVisivel(estado) {
    const s = estado.sessao;
    if (!pode(s, 'ver_registro')) return [];
    return s.perfil === 'admin_farol' ? estado.registro.slice() : estado.registro.filter(r => r.empresaId === s.empresaId);
  }

  function entrar(estado, perfil, empresaId, agora) {
    if (!PERFIS[perfil]) return { ok: false, erro: 'Perfil desconhecido.' };
    if (perfil !== 'admin_farol' && !estado.empresas.some(e => e.id === empresaId)) return { ok: false, erro: 'Escolha a empresa.' };
    estado.sessao = { perfil, empresaId: perfil === 'admin_farol' ? null : empresaId };
    registrar(estado, 'entrou (simulado)', PERFIS[perfil], estado.sessao.empresaId, agora);
    return { ok: true };
  }

  function sair(estado) { estado.sessao = null; }

  const limparEmpresa = e => ({ ...e,
    razaoSocial: e.razaoSocial.trim(), nomeFantasia: e.nomeFantasia.trim(), cnpj: formatarCNPJ(e.cnpj),
    emailInstitucional: e.emailInstitucional.trim().toLowerCase(), telefone: e.telefone.trim(), site: e.site.trim(),
    gestorNome: e.gestorNome.trim(), gestorEmail: e.gestorEmail.trim().toLowerCase(),
    dpoNome: e.dpoNome.trim(), dpoEmail: e.dpoEmail.trim().toLowerCase(), dominio: e.dominio.trim().toLowerCase(),
    antecedenciaHoras: Number(e.antecedenciaHoras), motivoPadrao: String(e.motivoPadrao ?? '').trim(),
    municipios: e.municipios.map(m => ({ codigo: String(m.codigo).trim(), nome: m.nome.trim() })) });

  function salvarEmpresa(estado, dados, agora) {
    const nova = !dados.id;
    if (!pode(estado.sessao, nova ? 'criar_empresa' : 'editar_empresa', dados.id)) return { ok: false, erro: 'Sem permissão.' };
    const erros = validarEmpresa(dados, estado.empresas);
    if (Object.keys(erros).length) return { ok: false, erros };
    const quando = agoraIso(agora), autor = quem(estado.sessao, estado);
    const e = limparEmpresa(dados);
    if (nova) {
      Object.assign(e, { id: novoId(estado, 'emp'), criadoPor: autor, criadoEm: quando, alteradoPor: autor, alteradoEm: quando });
      estado.empresas.push(e);
    } else {
      const i = estado.empresas.findIndex(x => x.id === e.id);
      if (i < 0) return { ok: false, erro: 'Empresa não encontrada.' };
      Object.assign(e, { criadoPor: estado.empresas[i].criadoPor, criadoEm: estado.empresas[i].criadoEm, alteradoPor: autor, alteradoEm: quando });
      // Municípios que saíram da empresa saem também dos usuários
      const ficam = new Set(e.municipios.map(m => m.codigo));
      estado.usuarios.filter(u => u.empresaId === e.id).forEach(u => { u.municipios = u.municipios.filter(c => ficam.has(c)); });
      estado.empresas[i] = e;
    }
    registrar(estado, nova ? 'criou empresa' : 'alterou empresa', e.nomeFantasia, e.id, agora);
    return { ok: true, id: e.id };
  }

  function alternarEmpresa(estado, id, agora) {
    if (!pode(estado.sessao, 'suspender_empresa', id)) return { ok: false, erro: 'Sem permissão.' };
    const e = estado.empresas.find(x => x.id === id);
    if (!e) return { ok: false, erro: 'Empresa não encontrada.' };
    e.status = e.status === 'ativa' ? 'suspensa' : 'ativa';
    e.alteradoPor = quem(estado.sessao, estado); e.alteradoEm = agoraIso(agora);
    registrar(estado, e.status === 'suspensa' ? 'suspendeu empresa' : 'reativou empresa', e.nomeFantasia, e.id, agora);
    return { ok: true };
  }

  // Configuração (admin da empresa): só idioma, fuso, antecedência e motivo padrão
  const CAMPOS_CONFIGURACAO = ['idioma', 'fuso', 'antecedenciaHoras', 'motivoPadrao'];
  function salvarConfiguracao(estado, empresaId, dados, agora) {
    if (!pode(estado.sessao, 'editar_configuracao', empresaId)) return { ok: false, erro: 'Sem permissão.' };
    const atual = estado.empresas.find(x => x.id === empresaId);
    if (!atual) return { ok: false, erro: 'Empresa não encontrada.' };
    const candidata = { ...atual };
    CAMPOS_CONFIGURACAO.forEach(c => { candidata[c] = dados[c]; });
    const erros = Object.fromEntries(Object.entries(validarEmpresa(candidata, estado.empresas)).filter(([c]) => CAMPOS_CONFIGURACAO.includes(c)));
    if (Object.keys(erros).length) return { ok: false, erros };
    candidata.antecedenciaHoras = Number(candidata.antecedenciaHoras);
    candidata.motivoPadrao = String(candidata.motivoPadrao ?? '').trim();
    candidata.alteradoPor = quem(estado.sessao, estado); candidata.alteradoEm = agoraIso(agora);
    Object.assign(atual, candidata);
    registrar(estado, 'alterou configuração', atual.nomeFantasia, empresaId, agora);
    return { ok: true };
  }

  function salvarUsuario(estado, dados, agora) {
    const empresa = estado.empresas.find(x => x.id === dados.empresaId);
    if (!empresa) return { ok: false, erro: 'Empresa não encontrada.' };
    if (!pode(estado.sessao, 'editar_usuario', empresa.id)) return { ok: false, erro: 'Sem permissão.' };
    const antes = dados.id ? estado.usuarios.find(u => u.id === dados.id) : null;
    if (dados.id && (!antes || antes.empresaId !== empresa.id)) return { ok: false, erro: 'Usuário não encontrado nesta empresa.' };
    const erros = validarUsuario(dados, empresa, estado.usuarios);
    if (Object.keys(erros).length) return { ok: false, erros };
    if (tiraUltimoAdmin(antes, dados, estado.usuarios))
      return { ok: false, erros: { perfil: 'Este é o último admin da empresa: cadastre outro admin antes de mudar o perfil ou bloquear.' } };
    const quando = agoraIso(agora), autor = quem(estado.sessao, estado);
    const u = { ...dados, nome: dados.nome.trim(), email: dados.email.trim().toLowerCase(), cargo: String(dados.cargo ?? '').trim(),
      municipios: empresa.municipios.map(m => m.codigo).filter(c => dados.municipios.includes(c)) };
    if (!antes) {
      // "Convidar" não cria senha: na produção o usuário recebe um link e cria a própria senha
      Object.assign(u, { id: novoId(estado, 'usu'), status: 'convidado', ultimoAcesso: '', criadoPor: autor, criadoEm: quando, alteradoPor: autor, alteradoEm: quando });
      estado.usuarios.push(u);
      registrar(estado, 'convidou usuário (simulado)', `${u.nome} (${PERFIS[u.perfil]})`, empresa.id, agora);
    } else {
      Object.assign(u, { status: dados.status, ultimoAcesso: antes.ultimoAcesso, criadoPor: antes.criadoPor, criadoEm: antes.criadoEm, alteradoPor: autor, alteradoEm: quando });
      estado.usuarios[estado.usuarios.indexOf(antes)] = u;
      registrar(estado, 'alterou usuário', `${u.nome} (${PERFIS[u.perfil]})`, empresa.id, agora);
    }
    return { ok: true, id: u.id };
  }

  function alternarBloqueio(estado, id, agora) {
    const u = estado.usuarios.find(x => x.id === id);
    if (!u) return { ok: false, erro: 'Usuário não encontrado.' };
    if (!pode(estado.sessao, 'editar_usuario', u.empresaId)) return { ok: false, erro: 'Sem permissão.' };
    const depois = { ...u, status: u.status === 'bloqueado' ? 'ativo' : 'bloqueado' };
    if (tiraUltimoAdmin(u, depois, estado.usuarios))
      return { ok: false, erro: 'Este é o último admin da empresa: cadastre outro admin antes de bloquear.' };
    u.status = depois.status; u.alteradoPor = quem(estado.sessao, estado); u.alteradoEm = agoraIso(agora);
    registrar(estado, u.status === 'bloqueado' ? 'bloqueou usuário' : 'reativou usuário', u.nome, u.empresaId, agora);
    return { ok: true };
  }

  // ---------- Busca ----------
  const normalizar = s => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  const confere = (termo, ...campos) => !normalizar(termo) || campos.some(c => normalizar(c).includes(normalizar(termo)));

  // ---------- Arquivo de configuração (.toml), no formato de distribuidoras/*.toml ----------
  // padroes: os valores de demonstração (distribuidoras/demo-leopoldina.toml) para o que o cadastro
  // ainda não tem (expediente, limites do aviso, perfis). Nunca leva usuários.
  // String básica do TOML: os escapes do JSON são compatíveis (sem surrogates soltos, que o TOML recusa)
  const str = s => JSON.stringify(String(s).toWellFormed());
  function valorToml(v) {
    if (typeof v === 'string') return str(v);
    if (typeof v === 'number') return Number.isFinite(v) ? String(v) : '0';
    if (typeof v === 'boolean') return String(v);
    if (Array.isArray(v)) return `[${v.map(valorToml).join(', ')}]`;
    return `{ ${Object.entries(v).map(([k, x]) => `${k} = ${valorToml(x)}`).join(', ')} }`;
  }
  const secao = (nome, obj) => [`[${nome}]`, ...Object.entries(obj).map(([k, v]) => `${k} = ${valorToml(v)}`), ''];
  const slug = s => normalizar(s).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'empresa';

  function nomeArquivoToml(empresa, municipio) { return `${slug(empresa.nomeFantasia)}-${slug(municipio.nome)}.toml`; }

  function gerarToml(empresa, municipio, padroes, agora) {
    const linhas = [
      `# Configuração gerada pela área administrativa do Norte (PROTÓTIPO) em ${agoraIso(agora).slice(0, 10)}.`,
      `# Empresa: ${str(empresa.nomeFantasia)} · município: ${str(municipio.nome)}/${empresa.uf}.`,
      '# Expediente, limites do aviso e perfis de sensibilidade vêm da demonstração (a confirmar com a empresa).',
      '# Este arquivo não contém usuários nem dados pessoais.',
      '',
      ...secao('distribuidora', {
        nome: empresa.nomeFantasia,
        assinatura_aviso_atual: empresa.nomeFantasia,
        telefone: empresa.telefone,
        municipio: municipio.nome,
        uf: empresa.uf,
        codigo_ibge: municipio.codigo,
        idioma_padrao: empresa.idioma,
      }),
    ];
    // Ainda não usados pelo pipeline: ficam como comentário, para não mudar o formato do arquivo
    linhas.splice(linhas.length - 1, 0,
      `# fuso_horario = ${str(empresa.fuso)}            (ainda não usado pelo pipeline)`,
      `# motivo_padrao = ${str(empresa.motivoPadrao)}   (ainda não usado pelo pipeline)`);
    linhas.push(...secao('regulatorio', { ...padroes.regulatorio, prazo_legal_horas: Number(empresa.antecedenciaHoras) }));
    for (const s of ['expediente', 'aviso', 'obra', 'janela']) linhas.push(...secao(s, padroes[s]));
    for (const [nome, p] of Object.entries(padroes.perfis)) {
      linhas.push(`[perfis.${nome}]`, `singular = ${str(p.singular)}`, `plural = ${str(p.plural)}`, `padrao = ${valorToml(p.padrao)}`);
      linhas.push(p.periodos.length ? `periodos = [\n${p.periodos.map(q => `  ${valorToml(q)},`).join('\n')}\n]` : 'periodos = []', '');
    }
    return linhas.join('\n');
  }

  // Gera o arquivo de um município da empresa (confere a permissão e registra)
  function gerarConfiguracao(estado, empresaId, codigo, padroes, agora) {
    if (!pode(estado.sessao, 'gerar_toml', empresaId)) return { ok: false, erro: 'Sem permissão.' };
    const e = estado.empresas.find(x => x.id === empresaId);
    const m = e && e.municipios.find(x => x.codigo === codigo);
    if (!m) return { ok: false, erro: 'Município não encontrado nesta empresa.' };
    const nome = nomeArquivoToml(e, m);
    registrar(estado, 'gerou arquivo de configuração', `${e.nomeFantasia} · ${m.nome} (${nome})`, e.id, agora);
    return { ok: true, nome, texto: gerarToml(e, m, padroes, agora) };
  }

  // ---------- Registro em texto ----------
  function registroTexto(entradas) {
    const cab = ['Norte · Registro de atividades (PROTÓTIPO: dados fictícios, só na memória do navegador)', ''];
    return cab.concat(entradas.map(r => `${r.quando}\t${r.quem}\t${r.acao}\t${r.alvo}`)).join('\n') + '\n';
  }

  return {
    PERFIS, PERFIS_USUARIO, TIPOS_EMPRESA, IDIOMAS, FUSOS, UFS, PRAZO_LEGAL_MIN_HORAS, CAMPOS_CONFIGURACAO,
    cnpjValido, formatarCNPJ, normalizarCNPJ, ibgeValido, dominioValido, emailValido, emailNoDominio, telefoneValido,
    empresaVazia, validarEmpresa, usuarioVazio, validarUsuario, situacaoUsuario, tiraUltimoAdmin,
    pode, menu, quem, criarEstado, entrar, sair, registroVisivel,
    salvarEmpresa, alternarEmpresa, salvarConfiguracao, salvarUsuario, alternarBloqueio,
    confere, gerarToml, nomeArquivoToml, gerarConfiguracao, registroTexto,
  };
})();
