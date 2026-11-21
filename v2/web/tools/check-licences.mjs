// ADR decision 1: a production dependency of the v2 web app carries an MIT, Apache-2.0, BSD, ISC or 0BSD
// licence, and nothing else ships to a browser. This is the check that makes the rule true; it runs in the
// `web` job of .github/workflows/tests.yml. It reads package-lock.json, so it needs no install.
//
// Production only, on purpose: dev tooling is not served, and its transitive tree carries dozens of SPDX
// expressions that would turn a licence rule into a maintenance chore. Dev licences are listed in
// THIRD-PARTY-NOTICES.md instead.
//
// Usage: node tools/check-licences.mjs   (exit 0 clean, exit 1 with the offenders named)
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = join(import.meta.dirname, '..');

const ALLOWED = new Set([
  '0BSD',
  'Apache-2.0',
  'BSD-2-Clause',
  'BSD-3-Clause',
  'ISC',
  'MIT',
  'MIT-0',
]);

// A fonts-only exception: SIL OFL-1.1 allows embedding, and Inter is served from the app (ADR decision 1).
const ALLOWED_FONT = 'OFL-1.1';

/** Every option of an SPDX expression, so "(MIT OR Apache-2.0)" passes and "(MIT AND GPL-3.0)" does not. */
function options(expression) {
  const text = expression.replaceAll('(', ' ').replaceAll(')', ' ').trim();
  if (/\bAND\b/i.test(text)) return text.split(/\s+AND\s+/i).map((s) => s.trim());
  return text.split(/\s+OR\s+/i).map((s) => s.trim());
}

function allowed(expression, name) {
  if (!expression) return false;
  const parts = options(expression);
  const ok = (p) => ALLOWED.has(p) || (p === ALLOWED_FONT && name.includes('font'));
  return /\bAND\b/i.test(expression) ? parts.every(ok) : parts.some(ok);
}

/** The licence npm recorded in the lockfile; the installed package.json is the fallback, when there is one. */
function licenceOf(path, entry) {
  if (typeof entry.license === 'string') return entry.license;
  if (Array.isArray(entry.license)) return entry.license.join(' OR ');
  let pkg;
  try {
    pkg = JSON.parse(readFileSync(join(ROOT, path, 'package.json'), 'utf8'));
  } catch {
    return '';
  }
  if (typeof pkg.license === 'string') return pkg.license;
  if (pkg.license?.type) return pkg.license.type;
  if (Array.isArray(pkg.licenses)) return pkg.licenses.map((l) => l.type ?? l).join(' OR ');
  return '';
}

const lock = JSON.parse(readFileSync(join(ROOT, 'package-lock.json'), 'utf8'));
if (lock.lockfileVersion < 3) {
  console.error(`package-lock.json is version ${lock.lockfileVersion}; this check needs 3 (npm 7+).`);
  process.exit(1);
}

const production = Object.entries(lock.packages ?? {}).filter(
  ([path, entry]) => path.startsWith('node_modules/') && !entry.dev && !entry.optional,
);
if (production.length === 0) {
  console.error('No production dependency found in package-lock.json: the check would pass on nothing.');
  process.exit(1);
}

const bad = [];
const rows = [];
for (const [path, entry] of production) {
  const name = path.slice(path.lastIndexOf('node_modules/') + 'node_modules/'.length);
  const licence = licenceOf(path, entry);
  rows.push(`${licence || '(none)'}\t${name}`);
  if (!allowed(licence, name)) bad.push(`${name}: ${licence || '(no licence field)'}`);
}

console.log(rows.sort().join('\n'));
if (bad.length > 0) {
  console.error(`\nLicence not allowed for the v2 web app (ADR v2/README.md, decision 1):\n  ${bad.join('\n  ')}`);
  process.exit(1);
}
console.log(`\n${production.length} production packages, every licence in the allowlist.`);
