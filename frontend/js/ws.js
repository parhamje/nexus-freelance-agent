// WebSocket connection with auto-reconnect
import { getToken } from './api.js';

let ws = null;
let retry = 0;
const handlers = [];

export function onEvent(fn) { handlers.push(fn); }

export function setWsStatus(connected) {
  const dot = document.getElementById('ws-status');
  const txt = document.getElementById('ws-status-text');
  if (!dot) return;
  dot.className = `inline-block w-2 h-2 rounded-full me-1 ${connected ? 'bg-green-500' : 'bg-neutral-400'}`;
  txt.textContent = connected ? 'متصل' : 'در حال اتصال…';
}

export function connectWS() {
  const token = getToken();
  if (!token) return;
  try { ws && ws.close(); } catch { /* ignore */ }
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/api/v1/ws?token=${encodeURIComponent(token)}`);
  ws.onopen = () => { retry = 0; setWsStatus(true); };
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.type === 'pong') return;
      handlers.forEach(fn => { try { fn(data); } catch (e) { console.error(e); } });
    } catch { /* ignore */ }
  };
  ws.onclose = () => {
    setWsStatus(false);
    const delay = Math.min(15000, 1000 * Math.pow(2, retry++));
    setTimeout(() => { if (getToken()) connectWS(); }, delay);
  };
  ws.onerror = () => ws.close();
}
