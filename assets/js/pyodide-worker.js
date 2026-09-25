/* One lazy Python runtime per page. All tool logic lives in python/. */
const INDEX_URL = 'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/';
let engine;
let pillowReady = false;
let queue = Promise.resolve();
const status = (id, message) => postMessage({ id, status: message });

async function initialize(id) {
  if (!engine) {
    engine = (async () => {
      status(id, 'Loading Python engine… The first download may take a moment.');
      importScripts(`${INDEX_URL}pyodide.js`);
      const py = await loadPyodide({ indexURL: INDEX_URL });
      const modules = ['hash_tool', 'url_cleaner', 'base64_tool', 'json_tool', 'image_tool', 'privacy_tools', 'text_tools', 'data_tools', 'dispatch'];
      await Promise.all(modules.map(async name => {
        const response = await fetch(new URL(`../../python/${name}.py`, self.location.href));
        if (!response.ok) throw new Error(`Could not load Python module: ${name}`);
        py.FS.writeFile(`/home/pyodide/${name}.py`, await response.text());
      }));
      await py.runPythonAsync('import json\nfrom dispatch import execute_tool');
      return py;
    })().catch(error => { engine = null; throw error; });
  }
  return engine;
}

async function run({ id, version, tool: action, payload: options, buffer }) {
  let py;
  try {
    if (version !== 1) throw new Error('Unsupported worker protocol version.');
    py = await initialize(id);
    if (action.startsWith('image-') && !pillowReady) {
      status(id, 'Loading image tools…');
      await py.loadPackage('pillow');
      pillowReady = true;
    }
    status(id, 'Processing locally…');
    py.globals.set('_action', action);
    py.globals.set('_options', JSON.stringify(options));
    py.globals.set('_input_bytes', new Uint8Array(buffer || new ArrayBuffer(0)));
    const result = await py.runPythonAsync("execute_tool(_action, json.loads(_options), bytes(_input_bytes.to_py()))");
    postMessage({ id, version: 1, ...JSON.parse(result) });
  } catch (error) {
    const lines = String(error.message || error).trim().split('\n');
    postMessage({ id, version: 1, success: false, error: { code: 'ENGINE_ERROR', message: lines.at(-1).replace(/^(ValueError|Error):\s*/, '') } });
  } finally {
    if (py) for (const name of ['_action', '_options', '_input_bytes']) py.globals.delete(name);
  }
}

self.onmessage = event => {
  queue = queue.then(() => run(event.data)).catch(error => {
    postMessage({ id: event.data.id, success: false, error: {code: 'ENGINE_ERROR', message: String(error.message || error)} });
  });
};
