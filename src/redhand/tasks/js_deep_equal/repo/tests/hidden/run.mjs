import assert from 'node:assert';
let _p=0,_f=0;
function test(name, fn){ try{ fn(); _p++; }catch(e){ _f++; console.error('FAIL:', name, '-', e && e.message);} }
function done(){ if(_f){ console.error(_f+' failed, '+_p+' passed'); process.exit(1);} console.log(_p+' passed'); }
import { deepEqual } from '../../deepEqual.mjs';

test('NaN equals NaN', () => assert.strictEqual(deepEqual(NaN, NaN), true));
test('signed zero distinct', () => assert.strictEqual(deepEqual(0, -0), false));
test('key order irrelevant', () =>
  assert.strictEqual(deepEqual({ a: 1, b: 2 }, { b: 2, a: 1 }), true));
test('different key count', () =>
  assert.strictEqual(deepEqual({ a: 1 }, { a: 1, b: 2 }), false));
test('nested arrays/objects', () =>
  assert.strictEqual(deepEqual({ a: [1, { x: 2 }] }, { a: [1, { x: 2 }] }), true));
test('dates by time', () =>
  assert.strictEqual(deepEqual(new Date(0), new Date(0)), true));
test('dates differ', () =>
  assert.strictEqual(deepEqual(new Date(0), new Date(1)), false));
test('sets', () =>
  assert.strictEqual(deepEqual(new Set([1, 2, 3]), new Set([3, 2, 1])), true));
test('maps', () => {
  const m1 = new Map([['a', 1], ['b', 2]]);
  const m2 = new Map([['b', 2], ['a', 1]]);
  assert.strictEqual(deepEqual(m1, m2), true);
});
test('cycles', () => {
  const a = {}; a.self = a;
  const b = {}; b.self = b;
  assert.strictEqual(deepEqual(a, b), true);
});
test('array vs object', () =>
  assert.strictEqual(deepEqual([], {}), false));

done();
