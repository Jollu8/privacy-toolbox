import { qrcodegen } from '../vendor/qrcodegen.js';

export async function generateQR(options) {
  const text = options.text || '';
  if (!text) throw new Error('Enter text or a URL first.');
  if (new TextEncoder().encode(text).length > 2953) throw new Error('Text is too long for a QR code. Shorten it to at most 2953 UTF-8 bytes.');
  const size = Number(options.size);
  if (![256, 512, 1024].includes(size)) throw new Error('Choose a supported size.');
  const correction = qrcodegen.QrCode.Ecc[options.correction];
  if (!correction) throw new Error('Choose an error correction level.');
  let qr;
  try { qr = qrcodegen.QrCode.encodeText(text, correction); }
  catch { throw new Error('Text exceeds QR capacity at this correction level. Shorten it or lower error correction.'); }
  const scale = Math.floor(size / (qr.size + 8));
  if (scale < 1) throw new Error('Choose a larger image size.');
  const offset = Math.floor((size - qr.size * scale) / 2);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, size, size); ctx.fillStyle = '#000';
  const paths = [];
  for (let y = 0; y < qr.size; y++) for (let x = 0; x < qr.size; x++) if (qr.getModule(x, y)) {
    const px = offset + x * scale, py = offset + y * scale;
    ctx.fillRect(px, py, scale, scale);
    paths.push(`M${px},${py}h${scale}v${scale}h-${scale}z`);
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><rect width="100%" height="100%" fill="white"/><path d="${paths.join('')}" fill="black"/></svg>`;
  const png = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  if (!png) throw new Error('The browser could not encode the QR image.');
  return { blob: png, svg: new Blob([svg], { type: 'image/svg+xml' }), extension: 'png', details: [`${size} × ${size} pixels · QR version ${qr.version}`] };
}
