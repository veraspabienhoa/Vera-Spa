"""Prepare a selected device raster for Face ID without cropping or device I/O."""
from io import BytesIO

from PIL import Image, ImageOps

MAX_CAPTURE_BYTES = 4 * 1024 * 1024
CAPTURE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/bmp',
                 'image/x-ms-bmp', 'image/gif'}
STORED_TYPES = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}


class CapturePhotoError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def prepare_capture_photo(content, content_type, *, max_bytes):
    """Validate decoded pixels; preserve supported originals, convert BMP/static GIF.

    All work runs outside database transactions. MIME comes from the decoder,
    not a renamed extension or the device's sometimes inaccurate response header.
    Conversion preserves the entire frame and never enlarges or resizes it.
    """
    if not content or content_type not in CAPTURE_TYPES:
        raise CapturePhotoError('Ảnh Capture trống hoặc không đúng định dạng ảnh được hỗ trợ.')
    if len(content) > MAX_CAPTURE_BYTES:
        raise CapturePhotoError('Ảnh Capture vượt giới hạn 4 MB.', 413)
    try:
        with Image.open(BytesIO(content), formats=['JPEG', 'PNG', 'WEBP', 'BMP', 'GIF']) as source:
            width, height = source.size
            if not (1 <= width <= 6000 and 1 <= height <= 6000 and width * height <= 24_000_000):
                raise CapturePhotoError('Ảnh có độ phân giải quá lớn; vui lòng nén ảnh trước khi tải lên.')
            if getattr(source, 'is_animated', False):
                raise CapturePhotoError('Ảnh Capture động không được hỗ trợ; hãy chọn một ảnh tĩnh.')
            source_format = source.format
            source.verify()
        with Image.open(BytesIO(content), formats=['JPEG', 'PNG', 'WEBP', 'BMP', 'GIF']) as source:
            # verify() alone does not decode all BMP/JPEG pixels.
            source.load()
            if source_format in STORED_TYPES and len(content) <= max_bytes:
                return content, STORED_TYPES[source_format]
            image = ImageOps.exif_transpose(source)
            image = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
            # Prefer a lossless encoding. Larger rasters can use bounded WebP
            # compression at the same dimensions; no compulsory crop/editor.
            encodings = [('PNG', {}), ('WEBP', {'lossless': True, 'method': 0})]
            encodings += [('WEBP', {'quality': quality, 'method': 0}) for quality in (90, 80, 70, 60)]
            for file_format, options in encodings:
                output = BytesIO()
                image.save(output, format=file_format, **options)
                if output.tell() <= max_bytes:
                    return output.getvalue(), STORED_TYPES[file_format]
    except CapturePhotoError:
        raise
    except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError) as exc:
        raise CapturePhotoError('Không đọc được dữ liệu ảnh Capture hợp lệ.') from exc
    raise CapturePhotoError('Ảnh Capture sau nén vẫn quá lớn; hãy dùng Cắt / xoay ảnh để nén thêm.', 413)
