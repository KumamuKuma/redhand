import assert from 'node:assert';
let _p=0,_f=0;
function test(name, fn){ try{ fn(); _p++; }catch(e){ _f++; console.error('FAIL:', name, '-', e && e.message);} }
function done(){ if(_f){ console.error(_f+' failed, '+_p+' passed'); process.exit(1);} console.log(_p+' passed'); }
import { deepEqual } from '../../deepEqual.mjs';

test('primitives equal', () => assert.strictEqual(deepEqual(1, 1), true));
test('primitives unequal', () => assert.strictEqual(deepEqual(1, 2), false));
test('shallow object', () => assert.strictEqual(deepEqual({ a: 1 }, { a: 1 }), true));
test('array', () => assert.strictEqual(deepEqual([1, 2], [1, 2]), true));

done();
