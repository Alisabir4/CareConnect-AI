export function usableEvidence(evidence) {
  return Array.isArray(evidence)
    ? evidence.filter(item => typeof item === 'string' && item.trim().length > 0)
    : [];
}
