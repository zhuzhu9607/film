from pathlib import Path
import tempfile

import cv2
import numpy as np
import tifffile

from filmcut.detector import _estimate_35mm_count, _periodic_bounds, apply_expansion, detect_frames
from filmcut.image_io import invert_image, load_image, make_preview, save_crop


def synthetic_strip(count=6, horizontal=True):
    frame_w, frame_h, gap, edge = 360, 240, 28, 55
    h = frame_h + edge * 2
    w = count * frame_w + (count + 1) * gap
    strip = np.full((h, w, 3), 4, np.uint8)
    rng = np.random.default_rng(42)
    for i in range(count):
        x1 = gap + i * (frame_w + gap)
        texture = rng.integers(35, 235, (frame_h, frame_w, 3), dtype=np.uint8)
        texture = cv2.GaussianBlur(texture, (31, 31), 0)
        strip[edge:edge + frame_h, x1:x1 + frame_w] = texture
    for x in range(18, w - 18, 42):
        strip[10:35, x:x + 20] = 230
        strip[-35:-10, x:x + 20] = 230
    return strip if horizontal else np.rot90(strip).copy()


def test_detector_horizontal_and_vertical():
    for horizontal in (True, False):
        image = synthetic_strip(horizontal=horizontal)
        boxes = detect_frames(image)
        assert len(boxes) == 6, (horizontal, boxes)
        assert all(0 <= v <= 1 for box in boxes for v in box)


def test_detector_is_stable_for_negative_polarity():
    positive = synthetic_strip(count=6, horizontal=True)
    gray = cv2.cvtColor(positive, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    positive_bounds = _periodic_bounds(gray, True, 6)
    negative_bounds = _periodic_bounds(1.0 - gray, True, 6)
    assert len(positive_bounds) == len(negative_bounds) == 6
    assert np.max(np.abs(np.asarray(positive_bounds) - np.asarray(negative_bounds))) < positive.shape[1] * .035


def test_expected_count_fallback():
    image = synthetic_strip(count=5)
    image = cv2.copyMakeBorder(image, 0, 0, 140, 210, cv2.BORDER_CONSTANT, value=0)
    boxes = detect_frames(image, expected_count=5)
    assert len(boxes) == 5
    assert boxes[0][0] > .03 and boxes[-1][2] < .97


def test_two_parallel_strips():
    top = synthetic_strip(count=6)
    bottom = synthetic_strip(count=6)
    combined = np.vstack([top, np.zeros((100, top.shape[1], 3), np.uint8), bottom])
    boxes = detect_frames(combined)
    assert len(boxes) == 12, boxes
    assert len({round(box[1], 2) for box in boxes}) == 2


def test_parallel_strips_can_have_different_frame_counts():
    # Same scan width, but two physical strips can have different detected
    # heights/scales. They must therefore be estimated independently.
    five_frame_lane = np.zeros((270, 2000), np.float32)
    six_frame_lane = np.zeros((220, 2000), np.float32)
    assert _estimate_35mm_count(five_frame_lane, True) == 5
    assert _estimate_35mm_count(six_frame_lane, True) == 6


def test_light_leak_keeps_uniform_geometry():
    image = synthetic_strip(count=6, horizontal=False)
    h = image.shape[0]
    image[int(h * .84):int(h * .98), :, :] = 255
    boxes = detect_frames(image, expected_count=6)
    heights = [b[3] - b[1] for b in boxes]
    widths = [b[2] - b[0] for b in boxes]
    assert len(boxes) == 6
    assert max(heights) - min(heights) < .002
    assert max(widths) - min(widths) < .002


def test_dark_content_does_not_shrink_strip_width():
    image = synthetic_strip(count=6, horizontal=False)
    image[:, :image.shape[1] // 3] = 0
    boxes = detect_frames(image, expected_count=6)
    widths = [b[2] - b[0] for b in boxes]
    assert min(widths) > .65
    assert max(widths) - min(widths) < .002


def test_16bit_tiff_roundtrip_and_crop_mapping():
    image = (np.arange(320 * 120 * 3, dtype=np.uint32) % 65536).astype(np.uint16).reshape(120, 320, 3)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.tif"
        target = Path(tmp) / "crop.tif"
        tifffile.imwrite(source, image, photometric="rgb")
        loaded = load_image(source)
        coords = apply_expansion((.25, .25, .75, .75), 0, 0, loaded.shape[:2])
        assert coords == (80, 30, 240, 90)
        x1, y1, x2, y2 = coords
        save_crop(target, loaded[y1:y2, x1:x2], "TIFF", tiff_depth="原始位深")
        result = tifffile.imread(target)
        assert result.dtype == np.uint16
        assert np.array_equal(result, image[30:90, 80:240])
        assert make_preview(result).dtype == np.uint8


def test_negative_inversion_preserves_depth_and_alpha():
    image8 = np.array([[[0, 10, 255, 77]]], dtype=np.uint8)
    inverted8 = invert_image(image8)
    assert inverted8.dtype == np.uint8
    assert inverted8.tolist() == [[[255, 245, 0, 77]]]

    image16 = np.array([[0, 1234, 65535]], dtype=np.uint16)
    inverted16 = invert_image(image16)
    assert inverted16.dtype == np.uint16
    assert inverted16.tolist() == [[65535, 64301, 0]]


if __name__ == "__main__":
    test_detector_horizontal_and_vertical()
    test_detector_is_stable_for_negative_polarity()
    test_expected_count_fallback()
    test_two_parallel_strips()
    test_parallel_strips_can_have_different_frame_counts()
    test_light_leak_keeps_uniform_geometry()
    test_dark_content_does_not_shrink_strip_width()
    test_16bit_tiff_roundtrip_and_crop_mapping()
    test_negative_inversion_preserves_depth_and_alpha()
    print("core tests: PASS")
