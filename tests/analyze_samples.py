from __future__ import annotations

import gc
from pathlib import Path
import sys

import cv2

from filmcut.detector import detect_frames
from filmcut.image_io import load_image, make_preview


def main(paths: list[str]):
    out = Path("build")
    out.mkdir(exist_ok=True)
    for index, path in enumerate(paths, 1):
        candidate = Path(path)
        if candidate.is_dir():
            candidate = next(candidate.glob("*.tif"))
        path = str(candidate)
        image = load_image(path)
        preview = make_preview(image)
        boxes = detect_frames(preview)
        overlay = preview.copy()
        h, w = overlay.shape[:2]
        for number, (x1, y1, x2, y2) in enumerate(boxes, 1):
            p1 = (round(x1 * w), round(y1 * h)); p2 = (round(x2 * w), round(y2 * h))
            cv2.rectangle(overlay, p1, p2, (98, 214, 167), max(2, w // 1000))
            cv2.putText(overlay, str(number), (p1[0] + 8, p1[1] + 26),
                        cv2.FONT_HERSHEY_SIMPLEX, .75, (255, 178, 74), 2, cv2.LINE_AA)
        cv2.imwrite(str(out / f"sample_{index}_overlay.jpg"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 94])
        print(index, Path(path).name, image.shape, image.dtype, "auto_boxes", len(boxes))
        del image, preview, overlay
        gc.collect()


if __name__ == "__main__":
    main(sys.argv[1:])
