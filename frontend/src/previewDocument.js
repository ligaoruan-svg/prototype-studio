// Re-seed a remounted iframe with the latest scroll state, never a cached seed.
export function preparePreviewDocument(html, { stored = {}, route = '', scroll = null, probe = false } = {}) {
  const safe = value => JSON.stringify(value).replace(/</g, '\\u003c')
  const clean = html.replace(/<script data-pa-seed>[\s\S]*?<\/script>/g, '')
  const script = '<script data-pa-seed>window.__paStorageSeed=' + safe(stored) + ';window.__paRoute=' + safe(route) + ';window.__paScrollSeed=' + safe(scroll) + (probe ? ';window.__paProbe=true' : '') + ';</scr' + 'ipt>'
  return clean.replace(/<head\b[^>]*>/i, match => match + script)
}
