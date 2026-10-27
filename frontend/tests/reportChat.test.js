import test from 'node:test';
import assert from 'node:assert/strict';
import { usableEvidence } from '../src/reportChat.js';

test('empty or blank evidence is omitted from the report evidence section', () => {
  assert.deepEqual(usableEvidence([]), []);
  assert.deepEqual(usableEvidence(['', '  ', null]), []);
  assert.deepEqual(usableEvidence(['WBC 11.8 ×10⁹/L 4.0-11.0 H', '  ']), ['WBC 11.8 ×10⁹/L 4.0-11.0 H']);
  assert.deepEqual(usableEvidence(undefined), []);
});
