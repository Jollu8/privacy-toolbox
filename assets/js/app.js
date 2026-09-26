import { localizeText } from './i18n.js';
import { runPython, resetEngine } from './python-bridge.js';
const $ = id => document.getElementById(id);
const bytesLabel = size => size < 1024 ? `${size} B` : size < 1024 ** 2 ? `${(size / 1024).toFixed(1)} KiB` : `${(size / 1024 ** 2).toFixed(2)} MiB`;

if ($('search')) {
  let category = new URLSearchParams(location.search).get('category') || 'all';
  const buttons = [...document.querySelectorAll('[data-filter]')];
  if (!buttons.some(b => b.dataset.filter === category)) category = 'all';
  const filter = () => {
    const query = $('search').value.trim().toLowerCase();
    let count = 0;
    for (const card of document.querySelectorAll('.tool-card')) {
      card.hidden = !(category === 'all' || card.dataset.category === category) || !(card.dataset.search + ' ' + card.textContent.toLowerCase()).includes(query);
      if (!card.hidden) count++;
    }
    for (const button of buttons) {
      button.classList.toggle('active', button.dataset.filter === category);
      button.setAttribute('aria-pressed', String(button.dataset.filter === category));
    }
    localizeText($('tool-count'), `${count} tool${count === 1 ? '' : 's'}`);
    $('no-tools').hidden = count !== 0;
  };
  document.addEventListener('languagechange', filter);
  $('search').addEventListener('input', filter);
  for (const button of buttons) button.addEventListener('click', () => { category = button.dataset.filter; filter(); });
  filter();
}

const action = document.body.dataset.tool;
if (action) {
  let selectedFile, imageInfo;
  let resizeAnchor = 'width';
  let urls = [];
  let busy = false, cancelled = false;
  const isImage = action.startsWith('image-');
  const say = (message, error = false) => {
    localizeText($('status'), message);
    $('status').classList.toggle('error', error);
  };
  const makeUrl = blob => { const url = URL.createObjectURL(blob); urls.push(url); return url; };
  const clearResult = () => {
    for (const url of urls) URL.revokeObjectURL(url);
    urls = [];
    for (const id of ['download', 'download-svg', 'preview', 'result-text', 'copy']) $(id).hidden = true;
    $('download').removeAttribute('href'); $('download-svg').removeAttribute('href'); $('preview').removeAttribute('src');
    $('result-text').value = '';
    $('result-details').replaceChildren();
    localizeText($('copy'), 'Copy result');
    $('result-empty').hidden = false;
  };
  const lock = value => {
    busy = value;
    $('controls').disabled = value;
    $('cancel').hidden = !value || action === 'qr-generator';
    $('result-panel').setAttribute('aria-busy', String(value));
    if (!value) $('progress').hidden = true;
  };
  const guard = () => { if (cancelled) throw new Error('Processing cancelled. You can try again.'); };
  const copyText = async (text, button) => {
    try { await navigator.clipboard.writeText(text); localizeText(button, 'Copied!'); }
    catch { $('result-text').focus(); $('result-text').select(); say('Clipboard access is unavailable. Select and copy the result manually.'); }
  };
  const detail = text => { const p = document.createElement('p'); localizeText(p, text); $('result-details').append(p); };
  const metadata = (target, values) => {
    const list = document.createElement('dl');
    for (const [key, value] of Object.entries(values)) {
      const term = document.createElement('dt'), description = document.createElement('dd');
      localizeText(term, key === 'Format' ? 'Image format' : key);
      if (typeof value === 'boolean' || value === 'Not found') localizeText(description, value === true ? 'Detected' : 'Not found');
      else description.textContent = String(value);
      list.append(term, description);
    }
    target.append(list);
  };
  const updateFields = () => {
    if (action === 'base64') {
      const fileMode = $('mode').value === 'encode-file';
      $('file-field').hidden = !fileMode; $('text-field').hidden = fileMode;
    }
    if ($('quality-field')) {
      const format = $('output').value === 'original' ? imageInfo?.format : $('output').value;
      $('quality-field').hidden = ['PNG', 'BMP'].includes(format);
      $('quality-value').value = $('quality').value;
    }
  };
  const inspect = async () => {
    if (!selectedFile || busy) return;
    cancelled = false; lock(true); say('Reading image metadata locally…');
    try {
      const buffer = await selectedFile.arrayBuffer(); guard();
      imageInfo = await runPython('image-inspect', {}, buffer, say); guard();
      $('image-info').replaceChildren();
      const p = document.createElement('p');
      localizeText(p, `Original: ${imageInfo.width} × ${imageInfo.height} pixels · ${imageInfo.format}`);
      $('image-info').append(p); metadata($('image-info'), imageInfo.metadata);
      if ($('width')) { $('width').value = imageInfo.width; $('height').value = imageInfo.height; resizeAnchor = 'width'; }
      updateFields(); say('Image inspected. Choose your settings, then process.');
    } catch (error) { say(error.message, true); }
    finally { lock(false); }
  };
  const chooseFile = file => {
    if (busy) return;
    clearResult(); selectedFile = undefined; imageInfo = undefined;
    $('image-info')?.replaceChildren();
    if (!file) { localizeText($('file-info'), 'No file selected'); return; }
    if (action !== 'hash' && file.size > 64 * 1024 ** 2) {
      localizeText($('file-info'), 'File exceeds the 64 MiB limit.'); $('file').value = '';
      say('Choose a file of 64 MiB or smaller.', true); return;
    }
    selectedFile = file;
    delete $('file-info').dataset.message;
    $('file-info').textContent = `${file.name} · ${bytesLabel(file.size)}`;
    say('File selected. Ready to process locally.');
    if (isImage) void inspect();
  };
  $('file')?.addEventListener('change', event => chooseFile(event.target.files[0]));
  if ($('dropzone')) {
    for (const name of ['dragenter','dragover','dragleave','drop']) $('dropzone').addEventListener(name, event => {
      event.preventDefault();
      $('dropzone').classList.toggle('dragging', !busy && ['dragenter','dragover'].includes(name));
      if (name === 'drop' && !busy) chooseFile(event.dataTransfer.files[0]);
    });
  }
  $('inspect')?.addEventListener('click', () => selectedFile ? void inspect() : say('Choose an image first.', true));
  $('tool-form').addEventListener('input', event => {
    if (imageInfo && $('keep_aspect')?.checked && ['width','height'].includes(event.target.id)) {
      resizeAnchor = event.target.id;
      if (resizeAnchor === 'width') $('height').value = Math.max(1, Math.round(Number($('width').value) * imageInfo.height / imageInfo.width));
      else $('width').value = Math.max(1, Math.round(Number($('height').value) * imageInfo.width / imageInfo.height));
    }
    updateFields();
    if (!busy) { clearResult(); say('Input changed. Run the tool to update your result.'); }
  });
  for (const button of document.querySelectorAll('[data-preset]')) button.addEventListener('click', () => {
    if (!imageInfo) { say('Choose and inspect an image first.', true); return; }
    const preset = button.dataset.preset;
    const factor = preset.endsWith('px') ? Math.min(1, parseInt(preset, 10) / Math.max(imageInfo.width, imageInfo.height)) : Number(preset) / 100;
    $('width').value = Math.max(1, Math.round(imageInfo.width * factor));
    $('height').value = Math.max(1, Math.round(imageInfo.height * factor));
    $('keep_aspect').checked = true; resizeAnchor = 'width'; clearResult();
  });
  $('cancel').addEventListener('click', () => { cancelled = true; resetEngine(); });
  $('clear').addEventListener('click', () => {
    $('tool-form').reset();
    for (const textarea of $('tool-form').querySelectorAll('textarea')) textarea.value = '';
    selectedFile = imageInfo = undefined; resizeAnchor = 'width';
    if ($('file-info')) localizeText($('file-info'), 'No file selected');
    $('image-info')?.replaceChildren();
    clearResult(); updateFields(); resetEngine(); say('Cleared. Ready for a new input.');
  });
  $('copy').addEventListener('click', () => copyText($('result-text').value, $('copy')));
  updateFields();

  const download = (blob, extension, name = action) => {
    const url = makeUrl(blob);
    $('download').href = url;
    $('download').download = `${name}.${extension}`;
    localizeText($('download'), `Download ${extension.toUpperCase()} · ${bytesLabel(blob.size)} ↓`);
    $('download').hidden = false;
    return url;
  };
  const render = result => {
    if (typeof result.text === 'string') {
      let output = result.text;
      if (result.iso) {
        const date = new Date(result.iso);
        const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        output += `\nLocal time (${zone}): ${date.toLocaleString(undefined, {timeZoneName: 'short'})}`;
      }
      $('result-text').value = output; $('result-text').hidden = false; $('copy').hidden = false;
      if (!result.sensitive) download(new Blob([output], {type: 'text/plain;charset=utf-8'}), result.extension || (action === 'json' ? 'json' : 'txt'));
    }
    for (const message of result.details || []) detail(message);
    if (result.removed) detail(result.removed.length ? `Removed: ${result.removed.join(', ')}` : 'No known tracking parameters found.');
    for (const item of result.items || []) {
      const row = document.createElement('div'); row.className = 'uuid-row';
      const code = document.createElement('code'); code.textContent = item;
      const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary compact'; localizeText(button, 'Copy one');
      button.addEventListener('click', () => copyText(item, button)); row.append(code, button); $('result-details').append(row);
    }
    if (result.base64 !== undefined || result.blob) {
      const blob = result.blob || new Blob([Uint8Array.from(atob(result.base64), c => c.charCodeAt(0))], {type: result.mime});
      const stem = (selectedFile?.name || action).replace(/\.[^.]+$/, '');
      const url = download(blob, result.extension, `${stem}${isImage ? '-'+(action === 'image-metadata' ? 'clean' : 'processed') : ''}`);
      if (isImage || action === 'qr-generator') { $('preview').src = url; $('preview').hidden = false; }
      if (result.original_size !== undefined) {
        detail(`${result.width} × ${result.height} pixels · Original: ${bytesLabel(result.original_size)} · Result: ${bytesLabel(result.size)}`);
        const saved = (1 - result.size / result.original_size) * 100;
        detail(saved >= 0 ? `${saved.toFixed(1)}% smaller.` : `${Math.abs(saved).toFixed(1)}% larger.`);
        detail('Embedded metadata removed. Orientation applied.');
        metadata($('result-details'), result.metadata);
      }
    }
    if (result.svg) { $('download-svg').href = makeUrl(result.svg); $('download-svg').download = 'qr-code.svg'; $('download-svg').hidden = false; }
  };
  $('tool-form').addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    clearResult();
    const options = {};
    for (const input of $('tool-form').querySelectorAll('[name]')) options[input.name] = input.type === 'checkbox' ? input.checked : input.value;
    options.resize_anchor = resizeAnchor;
    const needsFile = action === 'hash' || isImage || (action === 'base64' && options.mode === 'encode-file');
    if (needsFile && !selectedFile) { say('Choose a file first.', true); $('file').focus(); return; }
    if (action === 'base64' && needsFile) delete options.text;
    for (const key of ['text','modified']) if (new TextEncoder().encode(options[key] || '').byteLength > 8 * 1024 ** 2) { say('Text must be 8 MiB or smaller.', true); return; }
    cancelled = false; lock(true); $('result-empty').hidden = true; say('Preparing your input…');
    try {
      let result;
      if (action === 'qr-generator') {
        const { generateQR } = await import('./qr-tool.js'); result = await generateQR(options);
      } else if (action === 'hash') {
        await runPython('hash-start', options, undefined, say); guard();
        $('progress').hidden = false;
        const chunkSize = 4 * 1024 ** 2;
        for (let start = 0; start < selectedFile.size; start += chunkSize) {
          const buffer = await selectedFile.slice(start, start + chunkSize).arrayBuffer(); guard();
          await runPython('hash-chunk', {}, buffer); guard();
          const percent = Math.min(100, (start + chunkSize) / selectedFile.size * 100);
          $('progress').value = percent; say(`Hashing locally… ${percent.toFixed(0)}%`);
        }
        result = await runPython('hash-finish', {});
      } else {
        const buffer = needsFile ? await selectedFile.arrayBuffer() : undefined; guard();
        result = await runPython(action, options, buffer, say);
      }
      guard(); render(result); say('Done. Your input was processed on this device.');
    } catch (error) { clearResult(); say(error.message || 'Something went wrong. Please try again.', true); }
    finally { lock(false); }
  });
  window.addEventListener('pagehide', () => {
    cancelled = true; resetEngine();
    for (const url of urls) URL.revokeObjectURL(url);
  });
}
