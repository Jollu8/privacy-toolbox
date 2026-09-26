import { ru } from './translations.js';
const storageKey = 'privacy-toolbox-language';
let language = 'en';
try { language = localStorage.getItem(storageKey) === 'ru' ? 'ru' : 'en'; } catch { /* Storage can be disabled. */ }
const records = [];
export function t(text) {
  if (language !== 'ru') return text;
  if (ru[text]) return ru[text];
  if (/^\d+ tools?$/.test(text)) return `Инструменты: ${text.split(' ')[0]}`;
  if (text.startsWith('Hashing locally… ')) return text.replace('Hashing locally…', 'Хеширование на устройстве…');
  if (text.startsWith('Download ')) return text.replace('Download ', 'Скачать ');
  const patterns = [
    [/^Removed: (.*)$/, (_, value) => `Удалено: ${value}`],
    [/^Before: (\d+) characters · After: (\d+) characters$/, (_, a, b) => `До: ${a} символов · После: ${b} символов`],
    [/^Input lines: (\d+)$/, (_, n) => `Исходных строк: ${n}`],
    [/^Unique lines: (\d+)$/, (_, n) => `Уникальных строк: ${n}`],
    [/^Duplicates removed: (\d+)$/, (_, n) => `Удалено повторов: ${n}`],
    [/^Added: (\d+) lines · Removed: (\d+) lines · Changed pairs: (\d+)$/, (_, a, b, c) => `Добавлено строк: ${a} · Удалено: ${b} · Изменено пар: ${c}`],
    [/^(\d+) characters · cryptographic randomness$/, (_, n) => `${n} символов · криптографическая случайность`],
    [/^Estimated strength: (.+) · ([\d.]+) bits of generation entropy$/, (_, strength, n) => `Оценка надёжности: ${t(strength)} · Энтропия генерации: ${n} бит`],
    [/^(\d+) UUID v4 values$/, (_, n) => `Идентификаторов UUID v4: ${n}`],
    [/^Entropy: (\d+) bits · (\d+) random bytes$/, (_, a, b) => `Энтропия: ${a} бит · Случайных байтов: ${b}`],
    [/^(\d+) × (\d+) pixels · QR version (\d+)$/, (_, w, h, v) => `${w} × ${h} пикселей · Версия QR: ${v}`],
    [/^Original: (\d+) × (\d+) pixels · (.+)$/, (_, w, h, f) => `Исходное изображение: ${w} × ${h} пикселей · ${f}`],
    [/^(\d+) × (\d+) pixels · Original: (.+) · Result: (.+)$/, (_, w, h, a, b) => `${w} × ${h} пикселей · Исходный размер: ${a} · Результат: ${b}`],
    [/^([\d.]+)% smaller\.$/, (_, n) => `На ${n}% меньше.`],
    [/^([\d.]+)% larger\.$/, (_, n) => `На ${n}% больше.`],
  ];
  for (const [pattern, replacement] of patterns) if (pattern.test(text)) return text.replace(pattern, replacement);
  return text;
}
// Bind only interface text. Never traverse user input or generated results.
export function localizeText(node, source) {
  node.textContent = t(source);
  node.dataset.message = source;
}
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
while (walker.nextNode()) {
  const node = walker.currentNode;
  if (node.parentElement.closest('script, style, textarea, .language-switch, [aria-hidden="true"]')) continue;
  const source = node.textContent;
  if (ru[source.trim()]) records.push({ node, source });
}
for (const node of document.querySelectorAll('[placeholder], [aria-label], [alt], meta[name="description"]')) {
  for (const attribute of ['placeholder', 'aria-label', 'alt', 'content']) {
    const source = node.getAttribute(attribute);
    if (source && ru[source]) records.push({ node, attribute, source });
  }
}
const title = document.title;
function applyLanguage() {
  document.documentElement.lang = language;
  document.title = title.split(' · ').map(t).join(' · ');
  for (const { node, attribute, source } of records) {
    if (attribute) node.setAttribute(attribute, t(source));
    else if (node.isConnected) node.textContent = source.replace(source.trim(), t(source.trim()));
  }
  for (const node of document.querySelectorAll('[data-message]')) node.textContent = t(node.dataset.message);
  for (const select of document.querySelectorAll('.language-switch')) select.value = language;
  document.dispatchEvent(new Event('languagechange'));
}
for (const select of document.querySelectorAll('.language-switch')) select.addEventListener('change', () => {
  language = select.value === 'ru' ? 'ru' : 'en';
  try { localStorage.setItem(storageKey, language); } catch { /* Keep the choice for this page. */ }
  applyLanguage();
});
applyLanguage();
