let worker;
let nextId = 0;
const pending = new Map();

export function resetEngine(message = 'Processing cancelled. You can try again.') {
  worker?.terminate();
  worker = undefined;
  for (const request of pending.values()) {
    clearTimeout(request.timeout);
    request.reject(new Error(message));
  }
  pending.clear();
}

export function runPython(action, options, buffer, onStatus) {
  if (!worker) {
    worker = new Worker(new URL('./pyodide-worker.js', import.meta.url));
    worker.onmessage = ({ data }) => {
      const request = pending.get(data.id);
      if (!request) return;
      if (data.status) { request.onStatus?.(data.status); return; }
      pending.delete(data.id);
      clearTimeout(request.timeout);
      if (data.error) request.reject(Object.assign(new Error(data.error.message || data.error), { code: data.error.code }));
      else request.resolve(data.result);
    };
    worker.onerror = () => resetEngine('Python could not start. Check your connection, then try again.');
    worker.onmessageerror = () => resetEngine('Could not read the Python response. Please try again.');
  }
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const timeout = setTimeout(() => resetEngine('Processing timed out. Try a smaller file or check your connection.'), 180_000);
    pending.set(id, { resolve, reject, onStatus, timeout });
    worker.postMessage({ id, version: 1, tool: action, payload: options, buffer }, buffer ? [buffer] : []);
  });
}
