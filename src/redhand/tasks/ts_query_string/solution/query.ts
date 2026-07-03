export function parseQuery(qs: string): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {};
  let s = qs;
  if (s.startsWith('?')) s = s.slice(1);
  if (s === '') return out;
  for (const pair of s.split('&')) {
    if (pair === '') continue;
    const eq = pair.indexOf('=');
    const rawKey = eq === -1 ? pair : pair.slice(0, eq);
    const rawVal = eq === -1 ? '' : pair.slice(eq + 1);
    const key = decodeURIComponent(rawKey.replace(/\+/g, ' '));
    const val = decodeURIComponent(rawVal.replace(/\+/g, ' '));
    if (Object.prototype.hasOwnProperty.call(out, key)) {
      const cur = out[key];
      if (Array.isArray(cur)) cur.push(val);
      else out[key] = [cur, val];
    } else {
      out[key] = val;
    }
  }
  return out;
}

export function stringifyQuery(obj: Record<string, string | string[]>): string {
  const parts: string[] = [];
  for (const key of Object.keys(obj)) {
    const value = obj[key];
    const values = Array.isArray(value) ? value : [value];
    for (const v of values) {
      parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(v));
    }
  }
  return parts.join('&');
}
