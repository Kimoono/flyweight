// Tiny auto-reconnecting WebSocket. Usage:
//   const sock = connect({ onOpen, onMessage, onClose });  sock.send(obj)
export function connect({ onOpen, onMessage, onClose } = {}) {
  const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
  let ws = null, tries = 0, closed = false;
  function open() {
    ws = new WebSocket(url);
    ws.onopen = () => { tries = 0; onOpen && onOpen(); };
    ws.onmessage = (e) => { let m; try { m = JSON.parse(e.data); } catch { return; } onMessage && onMessage(m); };
    ws.onclose = () => {
      onClose && onClose();
      if (closed) return;
      const wait = Math.min(5000, 300 * 2 ** Math.min(tries++, 4));   // 300 ms -> 5 s
      setTimeout(open, wait);
    };
    ws.onerror = () => ws.close();
  }
  open();
  return {
    send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); },
    get ready() { return !!ws && ws.readyState === 1; },
    close() { closed = true; ws && ws.close(); },
  };
}
