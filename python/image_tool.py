"""Inspect and transform still raster images without carrying source metadata."""
import base64
import warnings
from io import BytesIO
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 20_000_000
SUPPORTED = {'JPEG', 'PNG', 'WEBP', 'BMP'}


def _gps(exif):
    if 34853 not in exif:
        return 'Not found'
    try:
        gps = exif.get_ifd(34853)
        def degrees(value):
            return float(value[0]) + float(value[1]) / 60 + float(value[2]) / 3600
        lat, lon = degrees(gps[2]), degrees(gps[4])
        if gps[1] == 'S': lat = -lat
        if gps[3] == 'W': lon = -lon
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError()
        return f'{lat:.6f}, {lon:.6f}'
    except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError):
        return 'Present (coordinates unavailable)'


def process_image(data: bytes, action: str, quality: int = 75, output: str = 'JPEG', settings=None) -> dict:
    settings = settings or {}
    if action not in {'image-inspect', 'image-metadata', 'image-compressor', 'image-resizer', 'image-converter'}:
        raise ValueError('Unsupported image operation.')
    if output not in SUPPORTED | {'original'} or not 1 <= quality <= 100:
        raise ValueError('Choose a supported format and quality from 1 to 100.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in SUPPORTED:
                    raise ValueError('Use a JPEG, PNG, WebP, or BMP image.')
                if getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Animated images are not supported. Choose a still image.')
                source.load()
                exif = source.getexif()
                metadata = {'Format': source.format, 'EXIF': bool(exif), 'GPS': 34853 in exif,
                            'GPS coordinates': _gps(exif), 'Camera': str(exif.get(272, 'Not found')),
                            'Date': str(exif.get(36867, exif.get(306, 'Not found'))),
                            'Software': str(exif.get(305, 'Not found')), 'Other metadata fields': len(source.info)}
                oriented = ImageOps.exif_transpose(source)
                if action == 'image-inspect':
                    return {'metadata': metadata, 'width': oriented.width, 'height': oriented.height,
                            'original_size': len(data), 'format': source.format,
                            'details': [f'Original size: {oriented.width} × {oriented.height} pixels']}
                target = source.format if action == 'image-metadata' or output == 'original' else output
                rgba = oriented.convert('RGBA')
                if action == 'image-resizer':
                    width = int(settings.get('width', rgba.width))
                    height = int(settings.get('height', rgba.height))
                    if settings.get('keep_aspect', True):
                        if settings.get('resize_anchor') == 'height':
                            width = max(1, round(height * rgba.width / rgba.height))
                        else:
                            height = max(1, round(width * rgba.height / rgba.width))
                    if width < 1 or height < 1 or width * height > Image.MAX_IMAGE_PIXELS:
                        raise ValueError('Output dimensions must be positive and at most 20 megapixels.')
                    rgba = rgba.resize((width, height), Image.Resampling.LANCZOS)
                if target in {'JPEG', 'BMP'}:
                    pixels = Image.new('RGB', rgba.size, 'white')
                    pixels.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    pixels = Image.new('RGBA', rgba.size)
                    pixels.paste(rgba)
                buffer = BytesIO()
                options = {'optimize': True} if target in {'JPEG', 'PNG'} else {}
                if target in {'JPEG', 'WEBP'}:
                    options['quality'] = 95 if action == 'image-metadata' else quality
                if target == 'WEBP' and action == 'image-metadata':
                    options['lossless'] = True
                pixels.save(buffer, format=target, **options)
                result = buffer.getvalue()
                return {'base64': base64.b64encode(result).decode('ascii'),
                        'mime': Image.MIME[target], 'extension': {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'BMP': 'bmp'}[target],
                        'size': len(result), 'original_size': len(data), 'metadata': metadata,
                        'width': pixels.width, 'height': pixels.height}
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Image is too large. Use an image with at most 20 megapixels.') from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError('Cannot read this image. It may be damaged or unsupported.') from exc
