"""Android screenshot observation using native Termux OCR."""
from dataclasses import dataclass, field, asdict
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, Optional

try:
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
except ImportError:
    Image = None


@dataclass
class Observation:
    village: str = "unknown"
    orientation: str = "unknown"
    screen_size: str = "unknown"
    game_viewport: str = "unknown"
    resources: Dict[str, Optional[int]] = field(default_factory=lambda: {
        "gold": None, "elixir": None, "dark_elixir": None,
        "builder_gold": None, "builder_elixir": None,
    })
    text: str = ""
    confidence: float = 0.0
    source: str = "none"
    regions_read: int = 0
    diagnostics: str = ""

    def to_dict(self):
        return asdict(self)


class ScreenDetector:
    """Capture screenshots, isolate the game viewport, then OCR its HUD."""

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        self.regions = self.config.get("regions", {})
        ocr = self.config.get("ocr", {})
        self.psm = int(ocr.get("psm", 7))
        self.scale = max(1, int(ocr.get("scale", 3)))

    @staticmethod
    def _load_config(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def capture(self, filename="autoc_observation.png"):
        return self.controller.take_screenshot(filename)

    @staticmethod
    def _screen_geometry(image_path):
        with Image.open(image_path) as image:
            width, height = image.size
        orientation = "landscape" if width > height else "portrait" if height > width else "square"
        return width, height, orientation

    @staticmethod
    def parse_number(text: str):
        if not text:
            return None
        cleaned = text.upper()
        cleaned = cleaned.replace("O", "0").replace("I", "1").replace("L", "1")
        cleaned = cleaned.replace("S", "5").replace("B", "8")
        match = re.search(r"\d[\d,\.]*\s*[KMB]?", cleaned)
        if not match:
            return None
        token = match.group(0).replace(",", "").replace(" ", "")
        suffix = token[-1:] if token else ""
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
        if suffix in "KMB":
            token = token[:-1]
        try:
            return int(float(token) * multiplier)
        except ValueError:
            return None

    @staticmethod
    def _find_game_viewport(image):
        """Find the largest saturated rectangular game area in a phone screenshot.

        The observed cloud-phone layout places the game as a rotated landscape surface
        with black bars around it and a control strip on the right. This method does not
        rely on the exact 691x1536 screenshot dimensions.
        """
        width, height = image.size
        rgb = image.convert("RGB")
        # Downsample for inexpensive row/column analysis.
        sample_w = min(256, width)
        sample_h = min(256, height)
        small = rgb.resize((sample_w, sample_h))
        px = small.load()

        row_hits = []
        for y in range(sample_h):
            hits = 0
            for x in range(sample_w):
                r, g, b = px[x, y]
                if max(r, g, b) - min(r, g, b) >= 25 and (r + g + b) >= 75:
                    hits += 1
            row_hits.append(hits / sample_w)

        col_hits = []
        for x in range(sample_w):
            hits = 0
            for y in range(sample_h):
                r, g, b = px[x, y]
                if max(r, g, b) - min(r, g, b) >= 25 and (r + g + b) >= 75:
                    hits += 1
            col_hits.append(hits / sample_h)

        def longest_segment(values, threshold=0.20):
            best = (0, len(values) - 1)
            start = None
            for i, value in enumerate(values + [0.0]):
                if value >= threshold and start is None:
                    start = i
                elif value < threshold and start is not None:
                    candidate = (start, i - 1)
                    if candidate[1] - candidate[0] > best[1] - best[0]:
                        best = candidate
                    start = None
            return best

        ys = longest_segment(row_hits)
        xs = longest_segment(col_hits)
        x1 = int(xs[0] * width / sample_w)
        x2 = int((xs[1] + 1) * width / sample_w)
        y1 = int(ys[0] * height / sample_h)
        y2 = int((ys[1] + 1) * height / sample_h)

        # Refine each edge inward/outward with a small safety margin. Avoid tiny or
        # implausible crops; fall back to the whole image if detection is uncertain.
        if x2 - x1 < width * 0.45 or y2 - y1 < height * 0.35:
            return image, (0, 0, width, height), "full-screen-fallback"
        viewport = image.crop((x1, y1, x2, y2))
        if viewport.height > viewport.width:
            viewport = viewport.rotate(90, expand=True)
            rotated = "ccw"
        else:
            rotated = "none"
        return viewport, (x1, y1, x2, y2), rotated

    def _read_region(self, image, region=None):
        if not shutil.which("tesseract"):
            return ""
        source = None
        temporary = None
        try:
            if region and Image is not None:
                x, y, w, h = [float(v) for v in region]
                crop = image.crop((
                    max(0, int(x * image.width)),
                    max(0, int(y * image.height)),
                    min(image.width, int((x + w) * image.width)),
                    min(image.height, int((y + h) * image.height)),
                ))
                gray = ImageOps.grayscale(crop)
                gray = ImageEnhance.Contrast(gray).enhance(2.8)
                gray = gray.filter(ImageFilter.SHARPEN)
                gray = gray.resize((max(1, gray.width * self.scale), max(1, gray.height * self.scale)))
                fd, temporary = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                gray.save(temporary)
                source = temporary
            else:
                source = image

            outputs = []
            for psm in (self.psm, 6, 7, 11):
                result = subprocess.run(
                    ["tesseract", source, "stdout", "--psm", str(psm),
                     "-c", "tessedit_char_whitelist=0123456789KMBkmb,."],
                    capture_output=True, text=True, timeout=15,
                )
                text = result.stdout.strip()
                if text:
                    outputs.append(text)
            return " | ".join(dict.fromkeys(outputs))
        except (OSError, subprocess.SubprocessError):
            return ""
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    @staticmethod
    def _default_hud_regions():
        """Normalized regions for the rotated landscape Clash HUD seen on the device."""
        return {
            # Gold, elixir, dark elixir, gems are stacked at the upper-right.
            "gold": [0.83, 0.005, 0.17, 0.070],
            "elixir": [0.83, 0.075, 0.17, 0.070],
            "dark_elixir": [0.83, 0.145, 0.17, 0.070],
            "gems": [0.86, 0.215, 0.14, 0.070],
            # Builder count is near the top center-right.
            "builders": [0.43, 0.005, 0.18, 0.085],
        }

    def observe(self, image_path=None) -> Observation:
        path = image_path or self.capture()
        if not path or not os.path.exists(path):
            return Observation(source="screenshot_failed")
        if not shutil.which("tesseract"):
            return Observation(source="tesseract_missing")
        if Image is None:
            return Observation(source="pillow_missing")

        try:
            with Image.open(path) as original:
                original = original.convert("RGB")
                width, height = original.size
                screen_orientation = "landscape" if width > height else "portrait" if height > width else "square"
                game, bounds, rotation = self._find_game_viewport(original)
                game_path_fd, game_path = tempfile.mkstemp(suffix=".png")
                os.close(game_path_fd)
                game.save(game_path)
                try:
                    regions = self._default_hud_regions()
                    # User config can override any normalized region.
                    for name, region in self.regions.items():
                        if isinstance(region, (list, tuple)) and len(region) == 4:
                            regions[name] = region

                    texts = {name: self._read_region(game, region) for name, region in regions.items()}
                    resources = {
                        "gold": self.parse_number(texts.get("gold", "")),
                        "elixir": self.parse_number(texts.get("elixir", "")),
                        "dark_elixir": self.parse_number(texts.get("dark_elixir", "")),
                        "builder_gold": self.parse_number(texts.get("builder_gold", "")),
                        "builder_elixir": self.parse_number(texts.get("builder_elixir", "")),
                    }
                    home_hits = sum(resources[k] is not None for k in ("gold", "elixir", "dark_elixir"))
                    bb_hits = sum(resources[k] is not None for k in ("builder_gold", "builder_elixir"))
                    village = "builder_base" if bb_hits > home_hits else "home" if home_hits else "unknown"
                    readable = sum(bool(texts.get(k)) for k in ("gold", "elixir", "dark_elixir", "builders"))
                    confidence = readable / 4.0
                    diagnostics = (
                        f"viewport={bounds[0]},{bounds[1]}-{bounds[2]},{bounds[3]}; "
                        f"rotation={rotation}; hud=" + " || ".join(
                            f"{k}:{v[:120]}" for k, v in texts.items() if v
                        )
                    )
                    return Observation(
                        village=village,
                        orientation="landscape" if game.width > game.height else screen_orientation,
                        screen_size=f"{width}x{height}",
                        game_viewport=f"{game.width}x{game.height}",
                        resources=resources,
                        text=" ".join(v for v in texts.values() if v),
                        confidence=confidence,
                        source="tesseract",
                        regions_read=readable,
                        diagnostics=diagnostics,
                    )
                finally:
                    try:
                        os.unlink(game_path)
                    except OSError:
                        pass
        except Exception as exc:
            return Observation(source="image_error", diagnostics=str(exc))
