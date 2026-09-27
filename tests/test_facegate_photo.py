"""Real raster decoding/conversion; synthetic pixels, no employee images."""
from io import BytesIO
import random
import unittest

from PIL import Image

from vera_facegate_photo import CapturePhotoError, MAX_CAPTURE_BYTES, prepare_capture_photo


def raster(file_format='BMP', size=(83, 117), *, noise=False):
    if noise:
        image = Image.frombytes('RGB', size, random.Random(7).randbytes(size[0] * size[1] * 3))
    else:
        image = Image.new('RGB', size, '#115533')
        image.putpixel((0, 0), (255, 0, 0))
        image.putpixel((size[0]-1, size[1]-1), (0, 0, 255))
    output = BytesIO()
    image.save(output, format=file_format)
    return output.getvalue()


class CapturePhotoTests(unittest.TestCase):
    def prepare(self, content, media='image/bmp', limit=700*1024):
        return prepare_capture_photo(content, media, max_bytes=limit)

    def test_small_square_and_landscape_bmp_and_static_gif_keep_all_pixels(self):
        for file_format, media in [('BMP','image/bmp'), ('BMP','image/x-ms-bmp'), ('GIF','image/gif')]:
            for size in [(83,117), (117,83), (47,47)]:
                with self.subTest(format=file_format, media=media, size=size):
                    original = raster(file_format, size)
                    content, content_type = self.prepare(original, media)
                    self.assertEqual(content_type, 'image/png')
                    with Image.open(BytesIO(original)) as before, Image.open(BytesIO(content)) as after:
                        self.assertEqual(after.size, size)
                        self.assertEqual(after.convert('RGB').tobytes(), before.convert('RGB').tobytes())
                    self.assertEqual(self.prepare(original, media), (content, content_type))

    def test_supported_originals_keep_exact_bytes_and_decoder_corrects_mime(self):
        for file_format, media in [('JPEG','image/jpeg'), ('PNG','image/png'), ('WEBP','image/webp')]:
            original = raster(file_format)
            self.assertEqual(self.prepare(original, media), (original, media))
            self.assertEqual(self.prepare(original, 'image/bmp'), (original, media))

    def test_larger_bmp_can_compress_without_resizing(self):
        original = raster(size=(181,133), noise=True)
        content, media = self.prepare(original, limit=20000)
        self.assertLessEqual(len(content), 20000)
        self.assertEqual(media, 'image/webp')
        with Image.open(BytesIO(content)) as after:
            self.assertEqual(after.size, (181,133))
        with self.assertRaises(CapturePhotoError) as error:
            self.prepare(original, limit=1)
        self.assertEqual(error.exception.status_code, 413)

    def test_empty_mislabeled_unsupported_and_truncated_payloads_are_rejected(self):
        original = raster()
        for content, media in [(b'', 'image/bmp'), (b'BMbad', 'image/bmp'),
                               (b'<html>login</html>', 'image/jpeg'), (b'<svg/>','image/svg+xml'),
                               (original[:80], 'image/bmp'), (raster('PNG')[:-15], 'image/png'),
                               (raster('JPEG')[:200], 'image/jpeg'), (raster('TIFF'), 'image/bmp')]:
            with self.subTest(media=media, length=len(content)), self.assertRaises(CapturePhotoError):
                self.prepare(content, media)

    def test_limits_before_decode_and_no_animated_capture(self):
        with self.assertRaises(CapturePhotoError) as error:
            self.prepare(b'B'*(MAX_CAPTURE_BYTES+1))
        self.assertEqual(error.exception.status_code, 413)
        for size in [(6001,1), (5000,5000)]:
            with self.subTest(size=size), self.assertRaises(CapturePhotoError):
                self.prepare(raster('PNG', size), 'image/png')
        output = BytesIO()
        Image.new('RGB',(10,10),'red').save(output,format='GIF',save_all=True,
            append_images=[Image.new('RGB',(10,10),'blue')],duration=100,loop=0)
        with self.assertRaisesRegex(CapturePhotoError, 'động'):
            self.prepare(output.getvalue(), 'image/gif')

    def test_transparency_is_preserved(self):
        original = BytesIO()
        Image.new('RGBA', (20,30), (255,0,0,0)).save(original,format='GIF',transparency=0)
        content, media = self.prepare(original.getvalue(),'image/gif')
        self.assertEqual(media,'image/png')
        with Image.open(BytesIO(content)) as image:
            self.assertEqual(image.convert('RGBA').getpixel((0,0))[3],0)


if __name__ == '__main__':
    unittest.main()
