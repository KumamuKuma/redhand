import assert from 'node:assert';
let _p=0,_f=0;
function test(name, fn){ try{ fn(); _p++; }catch(e){ _f++; console.error('FAIL:', name, '-', e && e.message);} }
function done(){ if(_f){ console.error(_f+' failed, '+_p+' passed'); process.exit(1);} console.log(_p+' passed'); }
import { parseQuery, stringifyQuery } from '../../query.ts';

test('leading question mark', () =>
  assert.deepStrictEqual(parseQuery('?a=1&b=2'), { a: '1', b: '2' }));
test('repeated key becomes array', () =>
  assert.deepStrictEqual(parseQuery('a=1&a=2&a=3'), { a: ['1', '2', '3'] }));
test('percent decoding', () =>
  assert.deepStrictEqual(parseQuery('a=%20x'), { a: ' x' }));
test('plus is space', () =>
  assert.deepStrictEqual(parseQuery('a=b+c'), { a: 'b c' }));
test('key without value', () =>
  assert.deepStrictEqual(parseQuery('flag'), { flag: '' }));
test('empty string', () =>
  assert.deepStrictEqual(parseQuery(''), {}));
test('stringify array', () =>
  assert.strictEqual(stringifyQuery({ a: ['1', '2'] }), 'a=1&a=2'));
test('stringify encodes space', () =>
  assert.strictEqual(stringifyQuery({ a: 'b c' }), 'a=b%20c'));
test('round trips special chars', () => {
  const obj = { 'k y': 'v&z', tag: ['x', 'y'] };
  assert.deepStrictEqual(parseQuery(stringifyQuery(obj)), obj);
});

done();
