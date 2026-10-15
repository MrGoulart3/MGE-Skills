#!/usr/bin/python3
"""Post-production of "Salt dissolving" (English showcase of the molecular-motion-video skill; adapted from montar_agua.py).

Lê timing/timing.json, timing/words.json, timing/narration.wav e anchors.json (gerados pela skill
molecular-motion-video e por agua_gas.py). ffmpeg/ffprobe vêm de $FFMPEG/$FFPROBE (padrão: micromamba env motion).
--teste usa somente quadros sintéticos em /tmp."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


SOX = Path(__file__).resolve().parents[1]  # cenas/agua_gas
ROOT = SOX.parents[1]
FPS = 24
SYMBOL_FONT = Path(os.environ.get("SYMBOL_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
MUSIC = Path(os.environ.get("MUSIC", str(ROOT / "cenas/hdl_v2/audio/trilha_ambiente.wav")))
WHITE = (255, 255, 255, 255)
AMBER = (242, 193, 78, 255)
BLUE = (127, 208, 236, 255)
Rect = tuple[float, float, float, float]
Run = tuple[str, float, float]
_PAINTER: Painter | None = None


@dataclass(frozen=True)
class Word:
    """Palavra com tempos absolutos."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Label:
    """Rótulo e sua janela de exibição."""

    name: str
    anchor: str
    start: float
    end: float
    runs: tuple[Run, ...]
    push: float = 0.0  # v2: afasta o rótulo do centro da molécula (px a 1920), para não cobrir átomos


HERO = ("hero_o", "hero_h1", "hero_h2")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _opacity(time: float, start: float, end: float, fade: float) -> float:
    if not start <= time < end:
        return 0.0
    return min(1.0, (time - start) / fade, (end - time) / fade)


def _fade(layer: Image.Image, opacity: float) -> Image.Image:
    alpha = np.asarray(layer.getchannel("A"), dtype=np.float32)
    layer.putalpha(Image.fromarray(np.rint(alpha * opacity).astype(np.uint8)))
    return layer


def _inside(box: Rect, size: tuple[int, int]) -> bool:
    return 0 <= box[0] <= box[2] <= size[0] and 0 <= box[1] <= box[3] <= size[1]


def _collides(first: Rect, second: Rect, gap: float = 0) -> bool:
    return (first[0] < second[2] + gap and first[2] + gap > second[0]
            and first[1] < second[3] + gap and first[3] + gap > second[1])


def _labels(times: dict[str, Any]) -> tuple[Label, ...]:
    # v2 (14/10): rótulos maiores; δ± presos à água em destaque enquanto o close dura (até o fim de C).
    scenes, events = times["scenes"], times["events"]
    delta_end = scenes["C"][0] + 0.93 * (scenes["C"][1] - scenes["C"][0])  # some antes do recuo da câmera
    return (
        Label("Na", "label_na", events["label_ions"], scenes["C"][0] - 0.3,
              (("Na", 38, 0), ("+", 25, -15))),
        Label("Cl", "label_cl", events["label_ions"] + 0.35, scenes["C"][0] - 0.3,
              (("Cl", 38, 0), ("−", 25, -15))),
        Label("dminus", "hero_o", events["delta_minus"], delta_end,
              (("δ−", 48, 0),), 150),
        Label("dplus", "hero_h1", events["delta_plus"], delta_end,
              (("δ+", 48, 0),), 150),
        Label("dplus2", "hero_h2", events["delta_plus"] + 0.2, delta_end,
              (("δ+", 48, 0),), 150),
        Label("shell", "ion1", events["shell"], scenes["F"][0] + 1.2,
              (("hydration shell", 36, 0),)),
    )


def _load_data() -> dict[str, Any]:
    times = _read_json(SOX / "timing" / "timing.json")
    anchors = _read_json(Path(os.environ.get("ANCHORS", str(SOX / "anchors.json"))))
    if times["fps"] != FPS or anchors["fps"] != FPS:
        raise ValueError("Timing and anchors must be 24 fps.")
    if len(anchors["frames"]) != times["frames"]:
        raise ValueError("anchors.json does not match timing.json (re-run the scene).")
    if (anchors["width"], anchors["height"]) != (1920, 1080):
        raise ValueError("Anchors must be in 1920×1080 pixels.")
    if anchors.get("synthetic"):
        raise ValueError("anchors.json comes from SYNTHETIC data; use the real-MD anchors.")
    words = tuple(Word(w["word"], float(w["start"]), float(w["end"]))
                  for w in _read_json(SOX / "timing" / "words.json"))
    if any(not w.text or w.end <= w.start for w in words) or any(
            b.start < a.end - 1e-6 for a, b in zip(words, words[1:])):
        raise ValueError("Tempos de palavras inválidos em words.json.")
    phrases = []
    for sentence in times["sentences"]:
        inside = tuple(w for w in words
                       if sentence["start"] - 1e-6 <= w.start < sentence["end"] + 1e-6)
        if not inside:
            raise ValueError(f"Frase {sentence['n']} sem palavras.")
        phrases.append((0.0, inside))
    return {"times": times, "anchors": anchors["frames"], "phrases": phrases}


class Painter:
    """Desenha e valida as camadas na resolução de entrada."""

    def __init__(self, size: tuple[int, int], data: dict[str, Any]) -> None:
        self.size = size
        self.scale = size[0] / 1920
        self.data = data
        self.fonts: dict[tuple[float, int], ImageFont.FreeTypeFont] = {}
        self.labels = _labels(data["times"])
        self.title_start = data["times"]["events"]["title"]
        self.blocks = self._blocks()

    def _font(self, pixels: float, weight: int) -> ImageFont.FreeTypeFont:
        key = (pixels, weight)
        if key not in self.fonts:
            font = ImageFont.truetype(str(ROOT / "assets/fontes/Manrope.ttf"),
                                      max(1, round(pixels * self.scale)))
            font.set_variation_by_axes([weight])
            self.fonts[key] = font
        return self.fonts[key]

    def _blank(self) -> Image.Image:
        return Image.new("RGBA", self.size)

    def _scrim(self) -> Image.Image:
        """Faixa escura suave no rodapé para a legenda ler sobre o cristal."""
        if getattr(self, "_scrim_cache", None) is None:
            width, height = self.size
            start = int(height * 0.68)
            alpha = np.zeros((height, 1), dtype=np.float32)
            ramp = np.linspace(0.0, 1.0, height - start, dtype=np.float32)
            alpha[start:, 0] = 0.6 * ramp ** 1.6
            rgba = np.zeros((height, width, 4), dtype=np.uint8)
            rgba[..., 0:3] = (4, 10, 18)
            rgba[..., 3] = np.repeat(alpha * 255, width, axis=1).astype(np.uint8)
            self._scrim_cache = Image.fromarray(rgba, "RGBA")
        return self._scrim_cache

    def _blocks(self) -> list[tuple[Word, ...]]:
        font = self._font(54, 700)
        blocks = []
        for _, words in self.data["phrases"]:
            current: list[Word] = []
            for word in words:
                text = " ".join(item.text for item in (*current, word))
                if current and (len(current) >= 6
                                or font.getlength(text) > self.size[0] * 0.9):
                    blocks.append(tuple(current))
                    current = []
                if font.getlength(word.text) > self.size[0] * 0.9:
                    raise ValueError(f"Palavra não cabe na legenda: {word.text}")
                current.append(word)
                if word.text.endswith((",", ".", ";", ":", "!", "?")):
                    blocks.append(tuple(current))
                    current = []
            if current:
                blocks.append(tuple(current))
        return blocks

    def _caption(self, time: float) -> tuple[Image.Image, Rect | None]:
        layer = self._blank()
        for block in self.blocks:
            start, end = block[0].start, block[-1].end
            opacity = _opacity(time, start, end, 0.15)
            if opacity <= 0:
                continue
            font = self._font(54, 700)
            text = " ".join(word.text for word in block)
            bounds = font.getbbox(text)
            x = (self.size[0] - font.getlength(text)) / 2
            y = self.size[1] * 0.88 - (bounds[3] - bounds[1]) / 2 - bounds[1]
            foreground, shadow = self._blank(), self._blank()
            shadow_draw = ImageDraw.Draw(shadow)
            shift = 2 * self.scale
            shadow_draw.text((x + shift, y + shift), text, font=font,
                             fill=(0, 0, 0, 180))
            shadow = shadow.filter(ImageFilter.GaussianBlur(2 * self.scale))
            draw = ImageDraw.Draw(foreground)
            cursor = x
            for word in block:
                color = AMBER if word.start <= time < word.end else WHITE
                draw.text((cursor, y), word.text, font=font, fill=color)
                cursor += font.getlength(word.text + " ")
            margin = 8 * self.scale
            box = (x + bounds[0] - margin, y + bounds[1] - margin,
                   x + bounds[2] + margin, y + bounds[3] + margin)
            if not _inside(box, self.size):
                raise ValueError(f"Legenda fora do quadro em {time:.3f}s: {box}")
            layer = Image.alpha_composite(shadow, foreground)
            return _fade(layer, opacity), box
        return layer, None

    def _run_metrics(self, runs: tuple[Run, ...], weight: int) -> Rect:
        cursor = 0.0
        boxes = []
        for text, pixels, offset in runs:
            font = self._font(pixels, weight)
            left, top, right, bottom = font.getbbox(text, anchor="ls")
            boxes.append((cursor + left, top + offset * self.scale,
                          cursor + right, bottom + offset * self.scale))
            cursor += font.getlength(text)
        return (min(box[0] for box in boxes), min(box[1] for box in boxes),
                max(cursor, max(box[2] for box in boxes)),
                max(box[3] for box in boxes))

    def _draw_runs(self, layer: Image.Image, position: tuple[float, float],
                   runs: tuple[Run, ...], weight: int, color: tuple) -> None:
        draw = ImageDraw.Draw(layer)
        cursor, baseline = position
        for text, pixels, offset in runs:
            font = self._font(pixels, weight)
            draw.text((cursor, baseline + offset * self.scale), text, font=font,
                      fill=color, anchor="ls")
            cursor += font.getlength(text)

    def _place_label(self, anchor: tuple[float, float], width: float,
                     height: float, occupied: list[Rect], slide: float) -> Rect:
        margin = 36 * self.scale
        ceiling = self.size[1] * 0.80
        if width > self.size[0] - 2 * margin or height > ceiling - margin:
            raise ValueError("Resolução insuficiente para os rótulos.")
        ax, ay = anchor
        candidates = []
        for dy in (-90, 45, -180, 135, -270, 225):
            for dx in (70 * self.scale, -70 * self.scale - width, -width / 2):
                x = min(max(margin, ax + dx), self.size[0] - margin - width)
                y = min(max(margin, ay + dy * self.scale + slide), ceiling - height)
                candidates.append((x, y, x + width, y + height))
        for box in candidates:
            if not any(_collides(box, other, 12 * self.scale) for other in occupied):
                return box
        raise ValueError("Não foi possível posicionar os rótulos sem colisões.")

    def _push_label(self, frame: int, label: Label, anchor: tuple[float, float],
                    width: float, height: float, occupied: list[Rect]) -> Rect | None:
        """Põe o rótulo para FORA da água em destaque (direção centro→átomo), girando se colidir."""
        entries = self.data["anchors"][str(frame)]
        center = np.mean([(entries[n]["x"] * self.scale, entries[n]["y"] * self.scale) for n in HERO], axis=0)
        direction = np.array(anchor) - center
        if np.linalg.norm(direction) < 1e-6:
            direction = np.array([1.0, -1.0])
        base = math.atan2(direction[1], direction[0])
        margin, ceiling = 36 * self.scale, self.size[1] * 0.80
        for turn in (0, 25, -25, 50, -50, 80, -80):
            angle = base + math.radians(turn)
            reach = label.push * self.scale + 0.5 * abs(width * math.cos(angle)) + 0.5 * abs(height * math.sin(angle))
            cx, cy = anchor[0] + reach * math.cos(angle), anchor[1] + reach * math.sin(angle)
            box = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
            if (margin <= box[0] and box[2] <= self.size[0] - margin and margin <= box[1] and box[3] <= ceiling
                    and not any(_collides(box, other, 12 * self.scale) for other in occupied)):
                return box
        return None

    def _technical(self, frame: int) -> tuple[Image.Image, list[Rect]]:
        time = (frame - 1) / FPS
        layer, occupied = self._blank(), []
        for label in self.labels:
            opacity = _opacity(time, label.start, label.end, 0.25)
            if opacity <= 0:
                continue
            entry = self.data["anchors"][str(frame)][label.anchor]
            if not entry["visivel"]:
                continue
            anchor = (entry["x"] * self.scale, entry["y"] * self.scale)
            if not all(math.isfinite(value) for value in anchor):
                raise ValueError(f"Âncora inválida no quadro {frame}.")
            if not (0 <= anchor[0] <= self.size[0]
                    and 0 <= anchor[1] <= self.size[1]):
                raise ValueError(f"Âncora visível fora do quadro {frame}.")
            metrics = self._run_metrics(label.runs, 600)
            padding = 14 * self.scale
            width = metrics[2] - metrics[0] + 2 * padding
            height = metrics[3] - metrics[1] + 2 * padding
            slide = 8 * self.scale * (1 - min(1.0, (time - label.start) / 0.25))
            box = None
            if label.push:
                box = self._push_label(frame, label, anchor, width, height, occupied)
            if box is None:
                box = self._place_label(anchor, width, height, occupied, slide)
            item = self._blank()
            draw = ImageDraw.Draw(item)
            endpoint = (min(max(anchor[0], box[0]), box[2]),
                        min(max(anchor[1], box[1]), box[3]))
            draw.line((anchor, endpoint), fill=(*BLUE[:3], 102),
                      width=max(1, round(2 * self.scale)))
            draw.rounded_rectangle(box, radius=height / 2,
                                   fill=(11, 22, 34, 179), outline=(*BLUE[:3], 102),
                                   width=max(1, round(self.scale)))
            self._draw_runs(item, (box[0] + padding - metrics[0],
                                  box[1] + padding - metrics[1]),
                            label.runs, 600, WHITE)
            layer = Image.alpha_composite(layer, _fade(item, opacity))
            occupied.append(box)
        for index, box in enumerate(occupied):
            if not _inside(box, self.size) or any(
                    _collides(box, other) for other in occupied[index + 1:]):
                raise ValueError(f"Rótulos inválidos no quadro {frame}.")
        return layer, occupied

    def _clock(self, frame: int) -> Image.Image:
        """Real MD time, so the time compression is honest (t = simulated picoseconds)."""
        layer = self._blank()
        time = (frame - 1) / FPS
        start = self.data["times"]["events"]["orient"] - 0.6
        opacity = _opacity(time, start, self.data["times"]["duration"] + 1, 0.4)
        if opacity <= 0:
            return layer
        ps = float(self.data["anchors"][str(frame)]["md_time_ps"])
        draw = ImageDraw.Draw(layer)
        right, top = self.size[0] - 64 * self.scale, 56 * self.scale
        big, small = self._font(34, 600), self._font(19, 500)
        text = f"t = {ps:5.1f} ps"
        draw.text((right - big.getlength(text), top), text, font=big, fill=WHITE)
        note = "molecular dynamics · 400 K"
        draw.text((right - small.getlength(note), top + 44 * self.scale), note, font=small, fill=BLUE)
        return _fade(layer, opacity)

    def _title(self, time: float) -> Image.Image:
        layer = self._blank()
        if time < self.title_start:
            return layer
        opacity = min(1.0, (time - self.title_start) / 0.8)
        draw = ImageDraw.Draw(layer)
        x = 150 * self.scale
        cursor = x
        font = self._font(26, 600)
        for letter in "HOW SALT DISSOLVES":
            draw.text((cursor, 330 * self.scale), letter, font=font, fill=BLUE)
            cursor += font.getlength(letter) + 3 * self.scale
        self._draw_runs(layer, (x, 470 * self.scale), (("Dissolving", 84, 0),), 700, WHITE)
        base, cursor = 545 * self.scale, x
        runs = (("NaCl(s)", 38, 0), ("  →  ", 38, 0), ("Na", 38, 0), ("+", 25, -15), ("(aq)", 38, 0),
                (" + ", 38, 0), ("Cl", 38, 0), ("−", 25, -15), ("(aq)", 38, 0))
        for text, pixels, offset in runs:
            color = AMBER if "→" in text else WHITE
            self._draw_runs(layer, (cursor, base), ((text, pixels, offset),), 500, color)
            cursor += self._font(pixels, 500).getlength(text)
        draw.text((x, 590 * self.scale), "motion replayed from a real molecular-dynamics simulation",
                  font=self._font(24, 400), fill=BLUE)
        draw.rectangle((x, 640 * self.scale, x + 90 * self.scale,
                        644 * self.scale), fill=AMBER)
        return _fade(layer, opacity)

    def render(self, frame: int) -> Image.Image:
        """Retorna o overlay após validar a geometria."""
        time = (frame - 1) / FPS
        caption, caption_box = self._caption(time)
        technical, boxes = self._technical(frame)
        if caption_box and any(_collides(caption_box, box) for box in boxes):
            raise ValueError(f"Rótulo sobre a legenda no quadro {frame}.")
        layer = Image.alpha_composite(self._scrim(), technical)
        layer = Image.alpha_composite(layer, self._clock(frame))
        layer = Image.alpha_composite(layer, caption)
        # O compositor herdado de hdl_previa.py já contém vinheta.
        return Image.alpha_composite(layer, self._title(time))


def _init_worker(size: tuple[int, int], data: dict[str, Any]) -> None:
    global _PAINTER
    _PAINTER = Painter(size, data)


def _save_overlay(job: tuple[int, str]) -> int:
    frame, directory = job
    if _PAINTER is None:
        raise RuntimeError("Processo de desenho não inicializado.")
    _PAINTER.render(frame).save(Path(directory) / f"{frame:04d}.png")
    return frame


def _inspect_frames(directory: Path) -> tuple[int, tuple[int, int], str]:
    files = sorted(directory.glob("*.png"))
    if not files or any(not re.fullmatch(r"\d{4,}\.png", path.name) for path in files):
        raise ValueError("Use PNGs numerados desde 0001.png, sem arquivos extras.")
    files.sort(key=lambda path: int(path.stem))
    digits = len(files[0].stem)
    for index, path in enumerate(files, 1):
        if path.name != f"{index:0{digits}d}.png":
            raise ValueError(f"Quadro ausente ou numeração inconsistente: {index}.")
    with Image.open(files[0]) as image:
        size = image.size
    if size[0] % 2 or size[1] % 2 or size[0] * 9 != size[1] * 16:
        raise ValueError("Os quadros devem ter proporção 16:9 e dimensões pares.")
    for path in files:
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != size:
                raise ValueError(f"Resolução ou formato inconsistente: {path}.")
            image.verify()
    return len(files), size, f"%0{digits}d.png"


def _media_command(program: str, arguments: list[str], cache: Path) -> str:
    environment = os.environ.copy()
    environment["XDG_CACHE_HOME"] = str(cache)
    tool = os.environ.get(program.upper())
    command = [tool] if tool else ["micromamba", "run", "-n", "motion", program]
    result = subprocess.run([*command, *arguments], env=environment, check=True,
                            capture_output=True, text=True)
    return result.stdout


def _encode_arguments(quadros: Path, pattern: str, overlays: Path, output: Path,
                      count: int, data: dict[str, Any]) -> list[str]:
    duration = count / FPS
    arguments = ["-hide_banner", "-loglevel", "error", "-y",
                 "-framerate", str(FPS), "-start_number", "1", "-i",
                 str(quadros / pattern), "-framerate", str(FPS),
                 "-start_number", "1", "-i", str(overlays / "%04d.png")]
    arguments += ["-i", str(SOX / "timing" / "narration.wav"), "-i", str(MUSIC)]
    filters = ["[0:v][1:v]overlay=shortest=1:format=auto[v]",
               f"anullsrc=r=48000:cl=stereo,atrim=duration={duration}[silence]",
               "[2:a]aresample=48000,aformat=channel_layouts=stereo[narr]",
               "[silence][narr]amix=inputs=2:duration=first:normalize=0,asplit=2[voice][sidechain]",
               f"[3:a]atrim=duration={duration},asetpts=PTS-STARTPTS,"
               "aresample=48000,aformat=channel_layouts=stereo,volume=0.28,"
               "afade=t=in:st=0:d=1.5,"
               f"afade=t=out:st={max(0, duration - 2)}:d={min(2, duration)}[music]",
               "[music][sidechain]sidechaincompress=threshold=0.025:ratio=8:"
               "attack=15:release=250[ducked]",
               "[voice][ducked]amix=inputs=2:duration=first:normalize=0,"
               "alimiter=limit=0.95:level=false:latency=true[a]"]
    return arguments + ["-filter_complex_threads", "1", "-filter_complex",
                        ";".join(filters), "-map", "[v]", "-map", "[a]",
                        "-frames:v", str(count), "-t", str(duration),
                        "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                        "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac",
                        "-b:a", "192k", "-movflags", "+faststart", str(output)]


def _validate_video(path: Path, count: int, cache: Path) -> dict[str, Any]:
    metadata = json.loads(_media_command("ffprobe", ["-v", "error",
        "-show_streams", "-show_format", "-of", "json", str(path)], cache))
    video = next(stream for stream in metadata["streams"]
                 if stream["codec_type"] == "video")
    audio = next(stream for stream in metadata["streams"]
                 if stream["codec_type"] == "audio")
    duration = count / FPS
    if (int(video["nb_frames"]) != count
            or video["avg_frame_rate"] != "24/1"
            or abs(float(video["duration"]) - duration) > 1 / 48000
            or abs(float(audio["duration"]) - duration) > 1024 / 48000
            or abs(float(metadata["format"]["duration"]) - duration) > 1 / FPS
            or video["codec_name"] != "h264" or video["pix_fmt"] != "yuv420p"
            or audio["codec_name"] != "aac"):
        raise ValueError("A saída não corresponde à duração ou aos codecs pedidos.")
    return metadata


def assemble(quadros: Path, saida: Path, procs: int = 2) -> None:
    """Gera overlays em paralelo, codifica e valida o MP4."""
    if procs < 1:
        raise ValueError("--procs deve ser positivo.")
    count, size, pattern = _inspect_frames(quadros)
    data = _load_data()
    for frame in range(1, count + 1):
        if str(frame) not in data["anchors"]:
            raise ValueError(f"Âncoras ausentes para o quadro {frame}.")
    if saida.suffix.lower() != ".mp4":
        raise ValueError("A saída deve ter extensão .mp4.")
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sal-pos-") as temporary:
        directory = Path(temporary)
        overlays = directory / "overlays"
        overlays.mkdir()
        # Fail fast: an exception inside the pool initializer makes multiprocessing respawn workers forever.
        Painter(size, data).render(1)
        with multiprocessing.get_context("spawn").Pool(
                processes=min(procs, count), initializer=_init_worker,
                initargs=(size, data)) as pool:
            jobs = ((frame, str(overlays)) for frame in range(1, count + 1))
            for _ in pool.imap_unordered(_save_overlay, jobs, chunksize=4):
                pass
        with tempfile.TemporaryDirectory(prefix=".sal-mp4-",
                                         dir=saida.parent) as staging:
            output = Path(staging) / "video.mp4"
            _media_command("ffmpeg", _encode_arguments(
                quadros, pattern, overlays, output, count, data), directory / "cache")
            _validate_video(output, count, directory / "cache")
            output.replace(saida)
    print(f"Validado: {count} quadros, {count / FPS:.3f}s, {size[0]}×{size[1]}; "
          f"legendas dentro do quadro e rótulos sem colisões. Saída: {saida}")


def self_test(procs: int) -> None:
    """Testa todas as janelas gráficas e codifica 30 PNGs pretos em /tmp."""
    data = _load_data()
    painter = Painter((640, 360), data)
    visible_labels: set[str] = set()
    for frame in range(1, len(data["anchors"]) + 1):
        painter.render(frame)
        time = (frame - 1) / FPS
        for label in painter.labels:
            if (label.start < time < label.end
                    and data["anchors"][str(frame)][label.anchor]["visivel"]):
                visible_labels.add(label.name)
        if time >= painter.title_start and painter._caption(time)[1] is not None:
            raise AssertionError("Legenda visível durante o título.")
    if visible_labels != {label.name for label in painter.labels}:
        raise AssertionError("Algum rótulo não foi exercitado pelo teste.")
    with tempfile.TemporaryDirectory(prefix="sal-teste-", dir="/tmp") as temporary:
        quadros = Path(temporary)
        for frame in range(1, 31):
            Image.new("RGB", (640, 360), "black").save(quadros / f"{frame:04d}.png")
        assemble(quadros, Path("/tmp/sal_pos_teste.mp4"), procs)


def main() -> None:
    """Executa a montagem solicitada ou o teste sintético."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quadros", type=Path, help="Pasta com PNGs desde 0001.png")
    parser.add_argument("--saida", type=Path, help="MP4 de saída")
    parser.add_argument("--procs", type=int, default=2, help="Processos de desenho")
    parser.add_argument("--teste", action="store_true", help="Teste sintético em /tmp")
    args = parser.parse_args()
    if args.procs < 1:
        parser.error("--procs deve ser positivo")
    if args.teste and (args.quadros or args.saida):
        parser.error("--teste não aceita --quadros nem --saida")
    if not args.teste and (args.quadros is None or args.saida is None):
        parser.error("informe --quadros e --saida, ou use --teste")
    try:
        if args.teste:
            self_test(args.procs)
        else:
            assemble(args.quadros.resolve(), args.saida.resolve(), args.procs)
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"Erro ao executar mídia: {error.stderr}\n")
    except (OSError, ValueError, KeyError, AssertionError) as error:
        parser.exit(1, f"Erro: {error}\n")


if __name__ == "__main__":
    main()
