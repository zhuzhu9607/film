from __future__ import annotations

import cv2
import numpy as np


def _smooth(signal: np.ndarray, radius: int) -> np.ndarray:
    radius = max(2, int(radius))
    kernel = np.ones(radius, dtype=np.float32) / radius
    return np.convolve(signal, kernel, mode="same")


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    padded = np.pad(mask.astype(np.int8), (1, 1))
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return [(int(a), int(b)) for a, b in zip(starts, ends) if b - a >= min_len]


def _projection_bounds(gray: np.ndarray, horizontal: bool, sensitivity: int) -> list[tuple[int, int]]:
    # Only sample the central band so sprocket holes do not dominate separation detection.
    h, w = gray.shape
    if horizontal:
        band = gray[int(h * .22):int(h * .78), :]
        axis_len = w
        mean = band.mean(axis=0)
        texture = band.std(axis=0)
    else:
        band = gray[:, int(w * .22):int(w * .78)]
        axis_len = h
        mean = band.mean(axis=1)
        texture = band.std(axis=1)

    window = max(5, axis_len // 450)
    mean = _smooth(mean, window)
    texture = _smooth(texture, window)
    mean = (mean - mean.min()) / max(float(np.ptp(mean)), 1e-6)
    texture = (texture - texture.min()) / max(float(np.ptp(texture)), 1e-6)
    # A separator is usually both flat and close to an intensity extreme. Using
    # the stronger cue avoids splitting naturally low-texture photographs.
    activity = np.maximum(mean, texture * .72)

    # Sensitivity adjusts how readily dark/flat separator bands are accepted.
    quantile = np.clip(.16 + (sensitivity - 50) * .0022, .07, .30)
    threshold = np.quantile(activity, quantile)

    # Prefer contiguous active regions. A little 1-D morphology removes tiny dark
    # details inside a photo without bridging genuine inter-frame gaps.
    active = (activity > threshold).astype(np.uint8)[None, :]
    close_size = max(3, axis_len // 500)
    open_size = max(2, axis_len // 1000)
    active = cv2.morphologyEx(active, cv2.MORPH_CLOSE, np.ones((1, close_size), np.uint8))
    active = cv2.morphologyEx(active, cv2.MORPH_OPEN, np.ones((1, open_size), np.uint8))[0].astype(bool)
    content_runs = _runs(active, max(12, int(axis_len * .045)))
    if len(content_runs) >= 2:
        widths = np.array([b - a for a, b in content_runs])
        typical = np.median(widths)
        consistent = [(a, b) for a, b in content_runs if typical * .48 <= b - a <= typical * 1.75]
        if len(consistent) >= 2:
            return consistent

    separator = activity < np.quantile(activity, quantile)
    sep_runs = _runs(separator, max(2, axis_len // 1200))
    centers = [0]
    centers.extend((a + b) // 2 for a, b in sep_runs if a > axis_len * .01 and b < axis_len * .99)
    centers.append(axis_len)
    centers = sorted(set(centers))

    # Collapse clusters of separators belonging to one inter-frame gap.
    merged = [centers[0]]
    min_gap = max(8, axis_len // 80)
    for c in centers[1:]:
        if c - merged[-1] < min_gap:
            merged[-1] = (merged[-1] + c) // 2
        else:
            merged.append(c)
    widths = np.diff(merged)
    if widths.size == 0:
        return [(0, axis_len)]

    plausible = widths[widths > axis_len * .04]
    typical = float(np.median(plausible)) if plausible.size else axis_len
    result: list[tuple[int, int]] = []
    for a, b in zip(merged[:-1], merged[1:]):
        width = b - a
        if width >= max(axis_len * .045, typical * .38):
            # Very wide intervals probably contain missed separators; split regularly.
            pieces = max(1, round(width / typical)) if typical > 0 else 1
            for i in range(pieces):
                x1 = round(a + width * i / pieces)
                x2 = round(a + width * (i + 1) / pieces)
                result.append((x1, x2))
    return result or [(0, axis_len)]


def _periodic_bounds(gray: np.ndarray, horizontal: bool, count: int) -> list[tuple[int, int]]:
    """Fit a regularly spaced frame grid without assuming zero start/end margins."""
    h, w = gray.shape
    if horizontal:
        band = gray[int(h * .22):int(h * .78), :]
        signal = band.mean(axis=0) + band.std(axis=0) * .65
        axis_len = w
    else:
        band = gray[:, int(w * .22):int(w * .78)]
        signal = band.mean(axis=1) + band.std(axis=1) * .65
        axis_len = h

    signal = _smooth(signal.astype(np.float32), max(5, axis_len // 600))
    lo, hi = np.percentile(signal, (2, 98))
    signal = np.clip((signal - lo) / max(float(hi - lo), 1e-6), 0, 1)

    def region_mean(fit_signal: np.ndarray, center: float, radius: float) -> float:
        a = max(0, int(center - radius)); b = min(axis_len, int(center + radius) + 1)
        return float(fit_signal[a:b].mean()) if b > a else 0.0

    # Pitch may be smaller than axis/count because excess leader/trailer is allowed.
    min_pitch = axis_len / (count + 2.2)
    max_pitch = axis_len / max(count - .35, 1)
    short_len = h if horizontal else w
    geometry_pitch = short_len * 1.48
    geometry_min = geometry_pitch * .94
    geometry_max = geometry_pitch * 1.18
    constrained_min = max(min_pitch, geometry_min)
    constrained_max = min(max_pitch, geometry_max)
    if constrained_min <= constrained_max:
        min_pitch, max_pitch = constrained_min, constrained_max
    best_score = -1e9
    best = (0.0, axis_len / count)
    best_signal = signal
    # Positive scans usually have dark separators; unconverted negatives have
    # bright orange separators. Fit both polarities so crop geometry does not
    # depend on whether the user has already enabled the display inversion.
    for fit_signal in (signal, 1.0 - signal):
        for pitch in np.linspace(min_pitch, max_pitch, 170):
            remaining = axis_len - count * pitch
            if remaining < 0:
                continue
            offsets = np.linspace(0, remaining, max(24, min(140, int(remaining / 2) + 1)))
            boundary_radius = max(2.0, pitch * .025)
            sample_radius = pitch * .22
            for start in offsets:
                frame_scores = [region_mean(fit_signal, start + (i + .5) * pitch, sample_radius)
                                for i in range(count)]
                gap_scores = [region_mean(fit_signal, start + i * pitch, boundary_radius)
                              for i in range(count + 1)]
                # Reward active frame interiors and dark/flat separators. The small
                # margin reward breaks ties in favor of excluding leader/trailer.
                score = float(np.mean(frame_scores) - 1.35 * np.mean(gap_scores))
                score -= float(np.std(frame_scores)) * .08
                score -= abs(pitch - geometry_pitch) / max(geometry_pitch, 1) * .15
                score += min(start, remaining - start) / max(axis_len, 1) * .025
                if score > best_score:
                    best_score = score
                    best = (float(start), float(pitch))
                    best_signal = fit_signal
    start, pitch = best
    signal = best_signal
    # Refine against all real separator minima, but keep one shared pitch. A
    # light leak, blank frame, or dark photograph therefore cannot resize itself.
    if count >= 3:
        local_positions: list[tuple[int, float]] = []
        radius = max(3, round(pitch * .075))
        for i in range(1, count):
            predicted = start + i * pitch
            a = max(0, round(predicted - radius)); b = min(axis_len, round(predicted + radius) + 1)
            if b > a:
                local_positions.append((i, float(a + np.argmin(signal[a:b]))))
        slopes = []
        for left in range(len(local_positions)):
            for right in range(left + 1, len(local_positions)):
                i1, p1 = local_positions[left]; i2, p2 = local_positions[right]
                slopes.append((p2 - p1) / (i2 - i1))
        if slopes:
            refined_pitch = float(np.median(slopes))
            if pitch * .88 <= refined_pitch <= pitch * 1.12:
                refined_start = float(np.median([p - i * refined_pitch for i, p in local_positions]))
                if refined_start >= -pitch * .08 and refined_start + count * refined_pitch <= axis_len + pitch * .08:
                    start = max(0.0, refined_start)
                    pitch = min(refined_pitch, (axis_len - start) / count)
    return [(round(start + i * pitch), round(start + (i + 1) * pitch)) for i in range(count)]


def _detect_lanes(gray: np.ndarray, horizontal: bool) -> list[tuple[int, int]]:
    """Detect parallel film strips before splitting frames along their shared direction."""
    h, w = gray.shape
    if horizontal:
        band = gray[:, int(w * .03):int(w * .97)]
        mean = band.mean(axis=1); texture = band.std(axis=1)
        short_len = h
    else:
        band = gray[int(h * .03):int(h * .97), :]
        mean = band.mean(axis=0); texture = band.std(axis=0)
        short_len = w
    mean = _smooth(mean, max(3, short_len // 180))
    texture = _smooth(texture, max(3, short_len // 180))
    mean = (mean - mean.min()) / max(float(np.ptp(mean)), 1e-6)
    texture = (texture - texture.min()) / max(float(np.ptp(texture)), 1e-6)
    activity = np.maximum(mean, texture * .65)
    threshold = np.quantile(activity, .16)
    active = (activity > threshold).astype(np.uint8)[None, :]
    close_size = max(3, short_len // 100)
    active = cv2.morphologyEx(active, cv2.MORPH_CLOSE, np.ones((1, close_size), np.uint8))[0].astype(bool)
    lanes = _runs(active, max(18, int(short_len * .14)))
    if not lanes:
        return [(0, short_len)]

    # Suppress narrow false bands and slightly pad the detected photographic area.
    widths = np.array([b - a for a, b in lanes])
    typical = float(np.median(widths))
    lanes = [(a, b) for a, b in lanes if b - a >= typical * .55]
    padding = max(2, round(typical * .025))
    return [(max(0, a - padding), min(short_len, b + padding)) for a, b in lanes]


def _estimate_35mm_count(gray: np.ndarray, horizontal: bool) -> int:
    """Estimate frame count from the physical 3:2 geometry, then let grid fitting align it."""
    axis_len = gray.shape[1] if horizontal else gray.shape[0]
    short_len = gray.shape[0] if horizontal else gray.shape[1]
    # Automatic mode assumes most of the long axis is occupied by frames. Very
    # long leaders/trailers are handled by the explicit total-count control.
    active_span = axis_len
    # A 35 mm frame is 36x24 mm; scanner borders make this a soft prior.
    count = round(active_span / max(short_len * 1.48, 1))
    return max(1, min(100, count))


def detect_frames(preview_rgb: np.ndarray, orientation: str = "自动", sensitivity: int = 50,
                  expected_count: int = 0) -> list[tuple[float, float, float, float]]:
    gray = cv2.cvtColor(preview_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    h, w = gray.shape
    horizontal = w >= h if orientation == "自动" else orientation == "横向"
    lanes = _detect_lanes(gray, horizontal)
    lane_counts = [0] * len(lanes)
    if expected_count > 0:
        base, remainder = divmod(expected_count, len(lanes))
        lane_counts = [base + (1 if i < remainder else 0) for i in range(len(lanes))]
    boxes = []
    for lane_index, (lane_a, lane_b) in enumerate(lanes):
        if horizontal:
            lane_gray = gray[lane_a:lane_b, :]
        else:
            lane_gray = gray[:, lane_a:lane_b]
        count = lane_counts[lane_index]
        if count > 0:
            bounds = _periodic_bounds(lane_gray, horizontal, count)
        else:
            auto_count = _estimate_35mm_count(lane_gray, horizontal)
            bounds = _periodic_bounds(lane_gray, horizontal, auto_count)
        # Short-axis bounds come only from the physical strip/background edge.
        # Photograph content is deliberately ignored: dark scenes, rotated frames,
        # and light leaks are not reliable evidence of the film's actual width.
        refined_a, refined_b = 0, lane_b - lane_a
        for a, b in bounds:
            if horizontal:
                boxes.append((a / w, (lane_a + refined_a) / h, b / w, (lane_a + refined_b) / h))
            else:
                boxes.append(((lane_a + refined_a) / w, a / h, (lane_a + refined_b) / w, b / h))
    return boxes


def expand_normalized(box: tuple[float, float, float, float], x_percent: float,
                      y_percent: float) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    dx = (x2 - x1) * x_percent / 100.0
    dy = (y2 - y1) * y_percent / 100.0
    return (max(0.0, x1 - dx), max(0.0, y1 - dy), min(1.0, x2 + dx), min(1.0, y2 + dy))


def apply_expansion(box: tuple[float, float, float, float], x_percent: float, y_percent: float,
                    shape: tuple[int, int]) -> tuple[int, int, int, int]:
    h, w = shape
    x1, y1, x2, y2 = box
    dx = (x2 - x1) * x_percent / 100.0
    dy = (y2 - y1) * y_percent / 100.0
    return (
        max(0, min(w - 1, round((x1 - dx) * w))),
        max(0, min(h - 1, round((y1 - dy) * h))),
        max(1, min(w, round((x2 + dx) * w))),
        max(1, min(h, round((y2 + dy) * h))),
    )
