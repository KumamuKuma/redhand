import assert from 'node:assert';
let _p=0,_f=0;
function test(name, fn){ try{ fn(); _p++; }catch(e){ _f++; console.error('FAIL:', name, '-', e && e.message);} }
function done(){ if(_f){ console.error(_f+' failed, '+_p+' passed'); process.exit(1);} console.log(_p+' passed'); }
import { parseCSV } from '../../csv.mjs';

test('quoted comma', () =>
  assert.deepStrictEqual(parseCSV('"a,b",c'), [['a,b', 'c']]));
test('escaped quotes', () =>
  assert.deepStrictEqual(parseCSV('"a""b",c'), [['a"b', 'c']]));
test('newline inside quotes', () =>
  assert.deepStrictEqual(parseCSV('"x\ny",z'), [['x\ny', 'z']]));
test('crlf line endings', () =>
  assert.deepStrictEqual(parseCSV('a,b\r\nc,d'), [['a', 'b'], ['c', 'd']]));
test('trailing newline no extra row', () =>
  assert.deepStrictEqual(parseCSV('a,b\n'), [['a', 'b']]));
test('empty fields preserved', () =>
  assert.deepStrictEqual(parseCSV('a,,c'), [['a', '', 'c']]));
test('quoted empty field', () =>
  assert.deepStrictEqual(parseCSV('"",x'), [['', 'x']]));

done();
