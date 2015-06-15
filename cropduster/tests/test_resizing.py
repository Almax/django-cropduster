import os

from django import test

from .helpers import CropdusterTestCaseMediaMixin
from cropduster.resizing import Crop, Box, Size


class TestResizing(CropdusterTestCaseMediaMixin, test.TestCase):

    def test_off_by_one_bug(self):
        img_path = os.path.join(self.TEST_IMG_DIR, 'best-fit-off-by-one-bug.png')
        crop = Crop(Box(x1=0, y1=0, x2=960, y2=915), img_path)
        size = Size('960', w=960, h=594)
        new_crop = size.fit_to_crop(crop)
        self.assertNotEqual(new_crop.box.h, 593, "Calculated best fit height is 1 pixel too short")
        self.assertEqual(new_crop.box.h, 594)
