function defaultApiBase() {
  if (typeof window === 'undefined' || !window.location?.hostname) {
    return 'http://127.0.0.1:8010';
  }
  return window.location.origin;
}

export const apiBase = (import.meta.env.VITE_API_BASE || defaultApiBase()).replace(/\/$/, '');

export async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export function webSocketUrl(path) {
  const url = new URL(path, apiBase);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}
