// Nenhum null/undefined/NaN/True/False/None na tela (15/10/2026): todas as vistas dos 4 perfis, nos 3 idiomas, com um aviso
// aberto (o envio para a rádio aparece) e depois de clicar em cada botão que só mostra ou alterna (nunca os que salvam,
// enviam, apagam, suspendem ou saem). Também confere que o select da cobrança mostra o texto inteiro, até no celular.
// Rode pelo executor: uv run python testes/navegador/rodar_teste_app.py teste_sem_null.mjs
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8001';
const SENHAS = JSON.parse(process.env.FAROL_TESTE_SENHAS || '{}');
const PLANILHA = join(RAIZ, 'saida', 'planilhas_teste', 'planilha_CF-0066.csv');
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
const J = JSON.stringify;
const ate = (p, expr, ms = 30000) => p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
  let v; try { v = (${expr}); } catch (e) { v = false; }
  if (v || Date.now() - t0 > ${ms}) ok(!!v); else setTimeout(ver, 100); }; ver(); })`);
// o texto visível (nós de texto e o valor mostrado de selects/inputs), fora o fundo do mapa
const ACHAR = `(() => {
  const proibido = /\\b(null|undefined|NaN|True|False|None)\\b/;
  const achados = [];
  const andar = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = andar.nextNode())) {
    const e = n.parentElement;
    if (!e || !e.offsetParent || e.closest('script, style, .leaflet-tile-pane')) continue;
    const m = proibido.exec(n.textContent);
    if (m) achados.push(m[0] + ' em ' + (e.id || e.className || e.tagName) + ': ' + n.textContent.trim().slice(0, 60));
  }
  for (const c of document.querySelectorAll('input:not([type=hidden]), select, textarea')) {
    if (!c.offsetParent) continue;
    const v = c.tagName === 'SELECT' ? c.selectedOptions[0]?.textContent || '' : c.value || c.placeholder || '';
    if (proibido.test(v)) achados.push('campo ' + (c.id || c.name) + ': ' + v.slice(0, 60));
  }
  return [...new Set(achados)].slice(0, 5);
})()`;
// botões que só mostram ou alternam (nada salva, envia, apaga, suspende nem sai)
const SEGUROS = `[...document.querySelectorAll('#telaApp .painel button, #legendaEmpresas button, #legenda button')].filter(b => b.offsetParent && !b.disabled
  && b.type !== 'submit' && !b.classList.contains('prim') && !b.classList.contains('perigo')
  && !b.matches('[data-envio-acao], [data-empresa-acao="suspensa"], [data-empresa-acao="ativa"], [data-acao-usuario], [data-aud], [data-rel], [data-arquivo], #sair')
  && !/salvar|enviar|gerar|cancelar|excluir|suspend|bloque|recusar|convidar|cadastrar|confirmar|baixar|copiar|mudar a data|nova senha|pdf|mp3|áudio|ouvir/i.test(b.textContent))`;

async function entrar(p, email) {
  await p.avaliar(`($('email').value = ${J(email)}, $('senha').value = ${J(SENHAS[email])}, $('formEntrar').requestSubmit(), 0)`);
  await ate(p, `estado.tela === 'app' || estado.tela === 'senha'`);
  if (await p.avaliar(`estado.tela === 'senha'`))
    await p.avaliar(`($('senhaAtual').value = ${J(SENHAS[email])}, $('senhaNova').value = $('senhaNova2').value = 'Lanterna-do-Farol-2026', $('formSenha').requestSubmit(), 0)`);
  await ate(p, `estado.tela === 'app' && document.documentElement.dataset.farol === 'pronto' && estado.concessao`, 60000);
  await espera(500);
}
const vistas = p => p.avaliar(`vistasDoPerfil().map(([v]) => v).concat(pode('ver_historico') ? RELATORIOS.map(([v]) => v) : []).filter((v, i, a) => a.indexOf(v) === i)`);
async function ir(p, v) { await p.avaliar(`irPara('${v}').then(() => 0)`); await espera(400); }
// no histórico, abre o primeiro aviso (aparece o envio para a rádio)
async function abrirAviso(p) {
  await p.avaliar(`(document.querySelector('#listaHistorico .item')?.click(), 0)`);
  await ate(p, `estado.resultado && estado.origem === 'historico'`, 15000);
  await espera(1200);
}

// um aviso e uma rádio da EMG, para o histórico e o envio terem conteúdo
{
  const p = await abrir(`${BASE}/`, { largura: 1280, altura: 800 });
  await entrar(p, 'admin@emg.example');
  const csv = readFileSync(PLANILHA, 'utf8').split('\n').slice(0, 60).join('\n');
  const st = await p.avaliar(`(async () => {
    await fetch('/api/radios', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nome: 'Rádio Teste (demonstração)',
      email: 'radio@example.com', alcance: { municipios: ['3138401'] }, valor_padrao: '120' }) });
    const fd = new FormData(); fd.append('arquivo', new Blob([${J(csv)}], { type: 'text/csv' }), 'p.csv'); fd.append('data', '12/11'); fd.append('horario', '8h');
    const c = await (await fetch('/api/planilha', { method: 'POST', body: fd })).json();
    return (await fetch('/api/avisos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pacote: c.pacote, data: '12/11', horario: '8h', conferi: true }) })).status;
  })()`);
  conferir('preparação: uma rádio e um aviso da EMG', st === 200, String(st));
  // o envio para a rádio: sem "null" embaixo dos botões; o select da cobrança mostra o texto inteiro (computador e celular)
  await ir(p, 'historico'); await abrirAviso(p);
  conferir('envio para a rádio: aparece, sem "null" embaixo dos botões', await p.avaliar(`!!document.querySelector('.envio-radio [data-envio-acao="copia"]')
    && !/\\bnull\\b/.test(document.querySelector('.envio-radio').textContent)`), await p.avaliar(`document.querySelector('.envio-radio')?.textContent.slice(-120)`));
  for (const [w, h] of [[1280, 800], [360, 640]]) {
    await p.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 1024 });
    await espera(300);
    for (const idioma of ['pt-BR', 'en', 'es']) {
      await p.avaliar(`trocarIdioma('${idioma}', false).then(() => 0)`);
      await espera(300);
      const corte = await p.avaliar(`(() => { const s = document.querySelector('[data-envio="cobranca"]'); if (!s) return 'sem select';
        const c = document.createElement('canvas').getContext('2d'); const cs = getComputedStyle(s); c.font = cs.fontSize + ' ' + cs.fontFamily;
        const maior = Math.max(...[...s.options].map(o => c.measureText(o.textContent).width));
        const util = s.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 20;
        return maior <= util ? '' : Math.round(maior) + ' > ' + Math.round(util); })()`);
      conferir(`select "Cobrança" mostra o texto inteiro (${w}px, ${idioma})`, !corte, corte);
    }
    await p.avaliar(`trocarIdioma('pt-BR', false).then(() => 0)`);
  }
  const previa = await p.avaliar(`(() => { const a = document.querySelector('[data-envio="antigo"]'); a.value = ''; a.dispatchEvent(new Event('input', { bubbles: true }));
    return document.querySelector('[id^="previa-"]').textContent; })()`);
  conferir('economia sem o custo antigo: diz o que preencher', /preencha "Quanto custaria do jeito antigo" para calcular/.test(previa) && /no ar/.test(previa), previa);
  const comAntigo = await p.avaliar(`(() => { const a = document.querySelector('[data-envio="antigo"]'); a.value = '900,00'; a.dispatchEvent(new Event('input', { bubbles: true }));
    return document.querySelector('[id^="previa-"]').textContent; })()`);
  conferir('economia com o custo antigo: "Economia: R$ X em relação ao jeito antigo"', /Economia: R\$\s?[\d.,]+ em relação ao jeito antigo/.test(comAntigo), comAntigo);
  await p.fechar();
}

for (const email of ['admin@farol.example', 'admin@emg.example', 'operador@emg.example', 'consulta@emg.example']) {
  const p = await abrir(`${BASE}/`, { largura: 1280, altura: 800 });
  await entrar(p, email);
  const ruins = {};
  let cliques = 0;
  for (const idioma of ['pt-BR', 'en', 'es']) {
    await p.avaliar(`trocarIdioma('${idioma}', false).then(() => 0)`);
    for (const v of await vistas(p)) {
      await ir(p, v);
      if (v === 'historico') await abrirAviso(p);
      let r = await p.avaliar(ACHAR);
      if (r.length) ruins[`${idioma} ${v}`] = r;
      // clica em cada botão seguro (até 15 por vista) e procura de novo
      const n = await p.avaliar(`${SEGUROS}.length`);
      for (let i = 0; i < Math.min(n, 15); i++) {
        const rotulo = await p.avaliar(`(() => { const b = ${SEGUROS}[${i}]; if (!b) return null; const r = b.textContent.trim().slice(0, 30); b.click(); return r; })()`);
        if (rotulo === null) break;
        cliques++;
        await espera(250);
        if (await p.avaliar(`estado.vista !== '${v}'`)) await ir(p, v);
        r = await p.avaliar(ACHAR);
        if (r.length) ruins[`${idioma} ${v} depois de "${rotulo}"`] = r;
        await p.avaliar(`(document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })), $('caixaAjuda').hidden = true, $('caixaSenha').hidden = true, 0)`);
      }
    }
  }
  conferir(`${email.split('@')[0]}${email.includes('farol') ? ' (Norte)' : ''}: todas as vistas x 3 idiomas, ${cliques} cliques: nenhum null/undefined/NaN/True/False/None`,
    !Object.keys(ruins).length, J(Object.entries(ruins).slice(0, 4)));
  conferir(`${email.split('@')[0]}: nenhuma exceção`, !p.excecoes.length, J(p.excecoes.slice(0, 2)));
  await p.fechar();
}

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
