import assert from 'node:assert';
let _p=0,_f=0;
function test(name, fn){ try{ fn(); _p++; }catch(e){ _f++; console.error('FAIL:', name, '-', e && e.message);} }
function done(){ if(_f){ console.error(_f+' failed, '+_p+' passed'); process.exit(1);} console.log(_p+' passed'); }
import { parseCSV } from '../../csv.mjs';

test('two simple rows', () =>
  assert.deepStrictEqual(parseCSV('a,b\nc,d'), [['a', 'b'], ['c', 'd']]));
test('single row', () =>
  assert.deepStrictEqual(parseCSV('x,y,z'), [['x', 'y', 'z']]));

done();
