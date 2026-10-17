// Dicionário da tela (Fase K2): todo texto em português usado na tela tem a tradução em inglês e em espanhol.
// Sem navegador: lê o app.js (as chaves passadas a t() e as listas de rótulos) e o index.html (data-t e data-t-*).
// Uso (na raiz): node testes/navegador/teste_textos.mjs
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const APP = join(RAIZ, 'src', 'comunidades', 'apresentacao', 'app');
const TEXTOS = new Function(readFileSync(join(APP, 'textos.js'), 'utf8') + '; return TEXTOS;')();
const js = readFileSync(join(APP, 'app.js'), 'utf8'), html = readFileSync(join(APP, 'index.html'), 'utf8');
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const desfaz = s => s.replace(/\\(.)/g, '$1');

const chaves = new Set();
// o primeiro argumento de uma chamada (até a vírgula ou o parêntese do mesmo nível, pulando textos entre aspas)
function primeiroArgumento(i) {
  let nivel = 0, aspas = null;
  for (let j = i; j < js.length; j++) {
    const c = js[j];
    if (aspas) { if (c === '\\') j++; else if (c === aspas) aspas = null; continue; }
    if (c === "'" || c === '`' || c === '"') aspas = c;
    else if ('([{'.includes(c)) nivel++;
    else if (')]}'.includes(c)) { if (!nivel) return js.slice(i, j); nivel--; }
    else if (c === ',' && !nivel) return js.slice(i, j);
  }
  return '';
}
// 1. t('…') e t(cond ? '…' : '…'): os textos do primeiro argumento (menos os comparados: x === 'ativa')
for (const m of js.matchAll(/\bt\(/g))
  for (const s of primeiroArgumento(m.index + 2).matchAll(/([=!]==?\s*)?'((?:[^'\\]|\\.)*)'/g)) if (!s[1]) chaves.add(desfaz(s[2]));
// 2. as listas de rótulos que a tela passa por t() (menus, ajuda, dicas, situações, cobrança, faixas)
for (const nome of ['MENUS', 'RELATORIOS', 'AJUDA', 'DICAS', 'COBRANCA', 'CANAL', 'SITUACAO_ENVIO', 'SITUACAO_PEDIDO', 'ROTULO', 'FAIXAS_CONFIG']) {
  const i = js.indexOf(`const ${nome} =`), fim = i + js.slice(i).search(/;[ \t]*(\/\/[^\n]*)?\r?\n/);
  const bloco = js.slice(i, fim) + (nome === 'AJUDA' ? js.slice(js.indexOf('AJUDA.admin_empresa'), js.indexOf('AJUDA.admin_empresa') + js.slice(js.indexOf('AJUDA.admin_empresa')).search(/;\r?\n/)) : '');
  for (const s of bloco.matchAll(/'((?:[^'\\]|\\.)*)'/g)) {
    const v = desfaz(s[1]);
    if (/\s|[À-ú]/.test(v) || /^[A-Z][a-z]+$/.test(v)) chaves.add(v);
  }
}
for (const c of ['SEM_CONEXAO', 'ERRO_SERVIDOR', 'CREDITO_REDE']) chaves.add(desfaz(new RegExp(`const ${c} = '((?:[^'\\\\]|\\\\.)*)'`).exec(js)[1]));
// 3. o index.html: o texto dos elementos com data-t e os atributos data-t-*
for (const m of html.matchAll(/<(\w+)[^>]*\sdata-t(?=[\s>])[^>]*>([^<]*)</g)) chaves.add(m[2].trim().replace(/\s+/g, ' '));
for (const m of html.matchAll(/data-t-(?:placeholder|aria-label)="([^"]*)"/g)) chaves.add(m[1]);
chaves.delete('');
for (const fixos of ['UC', 'Norte', 'WhatsApp', '{n} s', '{nome} ({kb} KB)']) chaves.add(fixos);

const faltando = { en: [], es: [] };
for (const k of chaves) for (const i of ['en', 'es']) if (!(k in TEXTOS[i])) faltando[i].push(k);
conferir(`${chaves.size} textos da tela: nenhum sem tradução em inglês`, !faltando.en.length, JSON.stringify(faltando.en.slice(0, 60)));
conferir('nenhum sem tradução em espanhol', !faltando.es.length, JSON.stringify(faltando.es.slice(0, 60)));
const chavesEn = Object.keys(TEXTOS.en), chavesEs = Object.keys(TEXTOS.es);
conferir('inglês e espanhol com as mesmas chaves', chavesEn.length === chavesEs.length && chavesEn.every(k => k in TEXTOS.es),
  JSON.stringify(chavesEn.filter(k => !(k in TEXTOS.es)).slice(0, 5)));
const marcas = [...chaves].filter(k => /\{\w+\}/.test(k));
const ruins = marcas.flatMap(k => ['en', 'es'].filter(i => TEXTOS[i][k] && [...k.matchAll(/\{(\w+)\}/g)].some(m => !TEXTOS[i][k].includes(`{${m[1]}}`))).map(i => `${i}: ${k}`));
conferir('as partes variáveis ({nome}…) estão nas traduções', !ruins.length, JSON.stringify(ruins.slice(0, 5)));

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
