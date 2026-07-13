from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
import rawpy
import tifffile


RAW_EXTENSIONS = {
    ".3fr", ".ari", ".arw", ".bay", ".cr2", ".cr3", ".crw", ".dcr",
    ".dng", ".erf", ".fff", ".iiq", ".k25", ".kdc", ".mef", ".mos",
    ".mrw", ".nef", ".nrw", ".orf", ".pef", ".raf", ".raw", ".rw2",
    ".rwl", ".sr2", ".srf", ".srw", ".x3f",
}
TIFF_EXTENSIONS = {".tif", ".tiff"}
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | TIFF_EXTENSIONS | {
    ".jpg", ".jpeg", ".png", ".bmp", ".webp"
}


def invert_image(image: np.ndarray) -> np.ndarray:
    """Invert image tones without changing bit depth or an alpha channel."""
    source = np.asarray(image)

    def invert_values(values: np.ndarray) -> np.ndarray:
        if values.dtype == np.bool_:
            return np.logical_not(values)
        if values.dtype.kind == "u":
            return np.iinfo(values.dtype).max - values
        if values.dtype.kind == "i":
            info = np.iinfo(values.dtype)
            return (info.max + info.min - values.astype(np.int64)).astype(values.dtype)
        if values.dtype.kind == "f":
            return 1.0 - values
        raise ValueError(f"不支持反色的数据类型：{values.dtype}")

    if source.ndim == 3 and source.shape[2] == 4:
        result = source.copy()
        result[:, :, :3] = invert_values(source[:, :, :3])
        return np.ascontiguousarray(result)
    return np.ascontiguousarray(invert_values(source))


def load_image(path: str | Path) -> np.ndarray:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in RAW_EXTENSIONS:
        with rawpy.imread(str(path)) as raw:
            image = raw.postprocess(
                output_bps=16,
                use_camera_wb=True,
                no_auto_bright=True,
                gamma=(1, 1),
            )
    elif ext in TIFF_EXTENSIONS:
        image = tifffile.imread(path)
    else:
        data = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        if image is None:
            raise ValueError("无法解码该图片")
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA if image.shape[2] == 4 else cv2.COLOR_BGR2RGB)
    return normalize_shape(image)


def normalize_shape(image: np.ndarray) -> np.ndarray:
    image = np.asarray(image)
    while image.ndim > 3:
        image = image[0]
    if image.ndim == 3 and image.shape[0] in (3, 4) and image.shape[-1] not in (3, 4):
        image = np.moveaxis(image, 0, -1)
    if image.ndim not in (2, 3):
        raise ValueError(f"不支持的图像维度：{image.shape}")
    if image.ndim == 3 and image.shape[2] > 4:
        image = image[:, :, :3]
    if image.dtype.kind == "f":
        finite = image[np.isfinite(image)]
        if finite.size == 0:
            raise ValueError("图像没有有效像素")
        lo, hi = np.percentile(finite, (0.05, 99.95))
        image = np.clip((image - lo) / max(hi - lo, 1e-12), 0, 1)
        image = (image * 65535).astype(np.uint16)
    return np.ascontiguousarray(image)


def make_preview(image: np.ndarray, max_side: int = 2200) -> np.ndarray:
    h, w = image.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    view = image
    if image.dtype != np.uint8:
        finite = image[np.isfinite(image)]
        lo, hi = np.percentile(finite, (0.2, 99.8)) if finite.size else (0, 1)
        view = np.clip((image.astype(np.float32) - lo) / max(float(hi - lo), 1.0), 0, 1)
        view = (view * 255).astype(np.uint8)
    if scale < 1:
        view = cv2.resize(view, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    if view.ndim == 2:
        view = cv2.cvtColor(view, cv2.COLOR_GRAY2RGB)
    elif view.shape[2] == 4:
        view = cv2.cvtColor(view, cv2.COLOR_RGBA2RGB)
    return np.ascontiguousarray(view)


def to_uint8(image: np.ndarray) -> np.ndarray:
    if image.dtype == np.uint8:
        return image
    info_max = np.iinfo(image.dtype).max if image.dtype.kind in "ui" else 1.0
    return np.clip(image.astype(np.float64) / info_max * 255, 0, 255).astype(np.uint8)


def to_uint16(image: np.ndarray) -> np.ndarray:
    if image.dtype == np.uint16:
        return image
    if image.dtype.kind in "ui":
        maxv = np.iinfo(image.dtype).max
        return np.clip(image.astype(np.float64) / maxv * 65535, 0, 65535).astype(np.uint16)
    return np.clip(image, 0, 1).astype(np.float64).__mul__(65535).astype(np.uint16)


def save_crop(path: str | Path, image: np.ndarray, fmt: str, quality: int = 98,
              tiff_depth: str = "原始位深") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "TIFF":
        output = image
        if tiff_depth == "16 位":
            output = to_uint16(image)
        elif tiff_depth == "8 位":
            output = to_uint8(image)
        tifffile.imwrite(path, output, photometric="rgb" if output.ndim == 3 else "minisblack",
                         compression="deflate", metadata=None)
    else:
        output = to_uint8(image)
        if output.ndim == 3 and output.shape[2] == 4:
            output = output[:, :, :3]
        if output.ndim == 3:
            output = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
        ok, encoded = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        if not ok:
            raise ValueError("JPG 编码失败")
        encoded.tofile(path)
