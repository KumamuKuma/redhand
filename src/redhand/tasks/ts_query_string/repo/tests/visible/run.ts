import assert from 'node:assert';
let _p=0,_f=0;
function test(name, fn){ try{ fn(); _p++; }catch(e){ _f++; console.error('FAIL:', name, '-', e && e.message);} }
function done(){ if(_f){ console.error(_f+' failed, '+_p+' passed'); process.exit(1);} console.log(_p+' passed'); }
import { parseQuery, stringifyQuery } from '../../query.ts';

test('parse basic', () =>
  assert.deepStrictEqual(parseQuery('a=1&b=2'), { a: '1', b: '2' }));
test('stringify basic', () =>
  assert.strictEqual(stringifyQuery({ a: '1' }), 'a=1'));

done();
