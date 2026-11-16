// The Stage 1 dashboard is intentionally read-only.
// Interactive YouTube import, AI generation and audit logging follow later.
fetch('/api/health').then((r) => {
  if (!r.ok) throw new Error('Health check failed');
  return r.json();
}).then((data) => console.info('JG Marketing Agent:', data))
  .catch((error) => console.error('Local server health error:', error));
