#!/usr/bin/env python3
"""Post-production of "SN2: the Walden inversion" (English showcase of the molecular-motion-video skill).

Lê timing/timing.json, timing/words.json, timing/narration.wav e anchors.json (gerados pela skill
molecular-motion-video e por sn2_en.py). ffmpeg/ffprobe vêm de $FFMPEG/$FFPROBE (padrão: PATH).
--teste usa somente quadros sintéticos no diretório temporário do sistema."""

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


PROJECT = Path(__file__).resolve().parents[1]
FPS = 24
FONT = os.environ.get("FONT", "DejaVuSans.ttf")
SYMBOL_FONT = os.environ.get("SYMBOL_FONT", "DejaVuSans-Bold.ttf")
MUSIC = Path(os.environ["MUSIC"]) if os.environ.get("MUSIC") else None
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


HERO = ("C", "Cl", "Br")


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
    e = times['events']
    return (
        Label('chloride', 'Cl', e['label_cl'], e['ts'],
              (('Cl', 38, 0), ('−', 25, -15))),
        Label('substrate', 'C', e['label_me'], e['bonds'],
              (('CH', 38, 0), ('3', 25, 8), ('Br', 38, 0))),
        Label('bromide', 'Br', e['leave'], times['duration']-1,
              (('Br', 38, 0), ('−', 25, -15))),
        Label('transition', 'C', e['ts']-.6, e['ts']+.6, (('‡', 38, 0),)),
    )


def _load_data(synthetic: bool = False) -> dict[str, Any]:
    times = _read_json(PROJECT / "timing" / "timing.json")
    if synthetic:
        frames = {}
        for frame in range(1, times['frames']+1):
            u = (frame-1)/max(1, times['frames']-1)
            entry = {name: dict(x=x, y=y, visivel=True) for name, x, y in (
                ('C', 1150, 530), ('Cl', 850, 530), ('Br', 1450, 530),
                ('H1', 1100, 450), ('H2', 1150, 600), ('H3', 1200, 450),
                ('mid_CCl', 1000, 530), ('mid_CBr', 1300, 530))}
            entry.update(t_fs=-500+1000*u, d_CCl=5-3.2*u,
                         d_CBr=1.95+4*u, xi=-3.05+7.2*u, umbrella=.3-.6*u)
            frames[str(frame)] = entry
        anchors = dict(fps=times['fps'], width=1920, height=1080, frames=frames)
    else:
        anchors = _read_json(Path(os.environ.get("ANCHORS", str(PROJECT / "anchors.json"))))
    if times["fps"] != FPS or anchors["fps"] != FPS:
        raise ValueError("Timing and anchors must be 24 fps.")
    if len(anchors["frames"]) != times["frames"]:
        raise ValueError("anchors.json does not match timing.json (re-run the scene).")
    if (anchors["width"], anchors["height"]) != (1920, 1080):
        raise ValueError("Anchors must be in 1920×1080 pixels.")
    if anchors.get("synthetic"):
        raise ValueError("anchors.json comes from SYNTHETIC data; use the real-MD anchors.")
    words = tuple(Word(w["word"], float(w["start"]), float(w["end"]))
                  for w in _read_json(PROJECT / "timing" / "words.json"))
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
    scan = sorted(_read_json(PROJECT/'calc/scan.json')['scan'], key=lambda v: v['xi'])
    if len(scan) < 2 or any(not math.isfinite(float(row[key]))
                            for row in scan for key in ('xi', 'E_rel')):
        raise ValueError('Scan inválido.')
    if any(b['xi'] <= a['xi'] for a, b in zip(scan, scan[1:])):
        raise ValueError('Scan com coordenadas repetidas.')
    return {"times": times, "anchors": anchors["frames"], "phrases": phrases, 'scan': scan}


class Painter:
    """Desenha e valida as camadas na resolução de entrada."""

    def __init__(self, size: tuple[int, int], data: dict[str, Any]) -> None:
        self.size = size
        self.scale = size[0] / 1920
        self.data = data
        self.fonts: dict[tuple[float, int, bool], ImageFont.FreeTypeFont] = {}
        self.labels = _labels(data["times"])
        self.title_start = data["times"]["events"]["title"]
        self.blocks = self._blocks()

    def _font(self, pixels: float, weight: int,
              symbol: bool = False) -> ImageFont.FreeTypeFont:
        key = (pixels, weight, symbol)
        if key not in self.fonts:
            font = ImageFont.truetype(SYMBOL_FONT if symbol else FONT,
                                      max(1, round(pixels * self.scale)))
            try:
                axes = font.get_variation_axes()
            except OSError:
                axes = []
            if axes:
                values = [weight if axis["name"] == b"Weight" else axis["default"]
                          for axis in axes]
                font.set_variation_by_axes(values)
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
            font = self._font(pixels, weight, symbol=any(c in text for c in "δ−→‡"))
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
            font = self._font(pixels, weight, symbol=any(c in text for c in "δ−→‡"))
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
        if label.name.startswith('distance_'):
            element = label.name.removeprefix('distance_')
            bond = np.array([entries[element]['x']-entries['C']['x'],
                             entries[element]['y']-entries['C']['y']])
            direction = np.array([-bond[1], bond[0]], dtype=float)
            others = [value for name, value in entries.items()
                      if isinstance(value, dict) and value.get('visivel')
                      and not name.startswith('mid_') and name not in ('C', element)]
            if others:
                centroid = np.mean([(v['x']*self.scale, v['y']*self.scale)
                                    for v in others], axis=0)
                if np.dot(direction, np.array(anchor)-centroid) < 0:
                    direction = -direction
        if np.linalg.norm(direction) < 1e-6:
            direction = np.array([1.0, -1.0])
        base = math.atan2(direction[1], direction[0])
        margin, ceiling = 36 * self.scale, self.size[1] * 0.80
        for offset, turn in ((offset, turn) for offset in (0, 40, 90, 150)
                             for turn in (0, 25, -25, 50, -50, 80, -80)):
            angle = base + math.radians(turn)
            reach = (label.push + offset) * self.scale + 0.5 * abs(width * math.cos(angle)) + 0.5 * abs(height * math.sin(angle))
            cx, cy = anchor[0] + reach * math.cos(angle), anchor[1] + reach * math.sin(angle)
            box = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
            if (margin <= box[0] and box[2] <= self.size[0] - margin and margin <= box[1] and box[3] <= ceiling
                    and not any(_collides(box, other, 12 * self.scale) for other in occupied)):
                return box
        return None

    def _technical(self, frame: int) -> tuple[Image.Image, list[Rect]]:
        time = (frame - 1) / FPS
        layer = self._blank()
        occupied = self._reserved(time)
        labels = list(self.labels)
        e = self.data['times']['events']
        if e['bonds'] <= time < e['flip']+1:
            entry = self.data['anchors'][str(frame)]
            for element in ('Cl', 'Br'):
                labels.append(Label('distance_'+element, 'mid_C'+element,
                    e['bonds'], e['flip']+1,
                    ((f"C–{element} {entry['d_C'+element]:.2f} Å", 30, 0),), push=100))
        for label in labels:
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
            obstacles = occupied
            if label.name.startswith('distance_'):
                radius = 60*self.scale
                obstacles = occupied + [
                    (value['x']*self.scale-radius, value['y']*self.scale-radius,
                     value['x']*self.scale+radius, value['y']*self.scale+radius)
                    for name, value in self.data['anchors'][str(frame)].items()
                    if name != label.anchor and not name.startswith('mid_')
                    and isinstance(value, dict) and value.get('visivel')]
            if label.push:
                box = self._push_label(frame, label, anchor, width, height, obstacles)
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

    def _reserved(self, time: float) -> list[Rect]:
        scale = self.scale
        boxes = [(920*scale, 28*scale, 1870*scale, 125*scale)]
        e = self.data['times']['events']
        if e['ts']-2 <= time < e['leave']+1:
            boxes.append((1410*scale, 150*scale, 1860*scale, 410*scale))
        if time >= self.title_start:
            boxes.append((100*scale, 330*scale, 1050*scale, 670*scale))
        return boxes

    def _clock(self, frame: int) -> Image.Image:
        layer = self._blank()
        time = (frame-1)/FPS
        e = self.data['times']['events']
        opacity = _opacity(time, e['clock'], self.data['times']['duration']+1, .4)
        draw = ImageDraw.Draw(layer)
        right = self.size[0]-64*self.scale
        fs = self.data['anchors'][str(frame)]['t_fs']
        for text, y, pixels, color in (
                (f"t = {fs:+.0f} fs".replace('-', '−'), 28, 34, WHITE),
                ('GFN2-xTB · 300 K · launched from the transition state', 78, 21, BLUE)):
            font = self._font(pixels, 500)
            draw.text((right-font.getlength(text), y*self.scale), text, font=font, fill=color)
        return _fade(layer, opacity)

    def _energy(self, frame: int) -> Image.Image:
        layer = self._blank()
        time = (frame-1)/FPS
        e = self.data['times']['events']
        opacity = _opacity(time, e['ts']-2, e['leave']+1, .3)
        if opacity <= 0:
            return layer
        scan = self.data['scan']
        xs = np.array([r['xi'] for r in scan])
        ys = np.array([r['E_rel'] for r in scan])
        lo, hi = float(ys.min()), float(ys.max())
        if hi <= lo:
            raise ValueError('Scan sem barreira de energia.')
        scale = self.scale
        def point(x, y):
            return ((1500+330*(x-xs[0])/(xs[-1]-xs[0]))*scale,
                    (325-135*(y-lo)/(hi-lo))*scale)
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle((1410*scale, 150*scale, 1860*scale, 410*scale),
                               radius=12*scale, fill=(11, 22, 34, 235))
        draw.line([point(x, y) for x, y in zip(xs, ys)], fill=BLUE, width=max(1, round(2*scale)))
        draw.line([(1500*scale, 180*scale), (1500*scale, 330*scale),
                   (1830*scale, 330*scale)], fill=WHITE)
        xi = float(np.clip(self.data['anchors'][str(frame)]['xi'], xs[0], xs[-1]))
        x, y = point(xi, np.interp(xi, xs, ys))
        r = 5*scale
        draw.ellipse((x-r, y-r, x+r, y+r), fill=AMBER)
        top = int(np.argmax(ys))
        x, y = point(xs[top], ys[top])
        draw.text((x, y-25*scale), '‡', font=self._font(23, 600), fill=AMBER)
        draw.text((1510*scale, 155*scale), 'energy',
                  font=self._font(21, 500), fill=WHITE)
        draw.text((1510*scale, 360*scale), 'reaction coordinate',
                  font=self._font(21, 500), fill=WHITE)
        return _fade(layer, opacity)

    def _title(self, time: float) -> Image.Image:
        layer = self._blank()
        if time < self.title_start:
            return layer
        opacity = min(1., (time-self.title_start)/.8)
        x = 110*self.scale
        self._draw_runs(layer, (x, 460*self.scale), (('SN2', 94, 0),), 700, WHITE)
        runs = (('Cl', 32, 0), ('−', 21, -12), (' + CH', 32, 0),
                ('3', 21, 7), ('Br → ClCH', 32, 0), ('3', 21, 7),
                (' + Br', 32, 0), ('−', 21, -12))
        self._draw_runs(layer, (x, 540*self.scale), runs, 500, WHITE)
        draw = ImageDraw.Draw(layer)
        draw.text((x, 590*self.scale), 'one step · inversion of configuration',
                  font=self._font(26, 500), fill=BLUE)
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
        layer = Image.alpha_composite(layer, self._energy(frame))
        layer = Image.alpha_composite(layer, caption)
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
    command = [os.environ.get(program.upper()) or program]
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
    arguments += ["-i", str(PROJECT / "timing" / "narration.wav")]
    if MUSIC is not None:
        arguments += ["-i", str(MUSIC)]
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
    if MUSIC is None:
        filters = filters[:3] + [
            "[silence][narr]amix=inputs=2:duration=first:normalize=0,"
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
    if count != data['times']['frames']:
        raise ValueError('A montagem exige todos os quadros do timing.')
    if not (PROJECT/'timing/narration.wav').is_file():
        raise ValueError('Narração ausente.')
    if MUSIC is not None and not MUSIC.is_file():
        raise ValueError("Trilha definida em MUSIC não encontrada.")
    if saida.suffix.lower() != ".mp4":
        raise ValueError("A saída deve ter extensão .mp4.")
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sal-pos-") as temporary:
        directory = Path(temporary)
        overlays = directory / "overlays"
        overlays.mkdir()
        # Fail fast: an exception inside the pool initializer makes multiprocessing respawn workers forever.
        painter = Painter(size, data)
        for frame in range(1, count+1):
            painter.render(frame)
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
    """Exercita todas as janelas sem depender de anchors.json nem de áudio real."""
    data = _load_data(synthetic=True)
    painter = Painter((640, 360), data)
    visible = set()
    for frame in range(1, data['times']['frames']+1):
        painter.render(frame)
        time = (frame-1)/FPS
        visible.update(label.name for label in painter.labels if label.start < time < label.end)
    assert visible == {label.name for label in painter.labels}
    with tempfile.TemporaryDirectory(prefix='sn2-teste-') as temporary:
        directory = Path(temporary)
        overlays = directory/'overlays'
        overlays.mkdir()
        painter.render(1)
        with multiprocessing.get_context('spawn').Pool(
                processes=min(procs, 2), initializer=_init_worker,
                initargs=((640, 360), data)) as pool:
            list(pool.imap_unordered(_save_overlay,
                ((frame, str(overlays)) for frame in range(1, 13))))
        for frame in range(1, 13):
            Image.new('RGB', (640, 360), 'black').save(directory/f'{frame:04d}.png')
        output = directory/'test.mp4'
        arguments = ['-y', '-v', 'error', '-framerate', str(FPS), '-i',
            str(directory/'%04d.png'), '-framerate', str(FPS), '-i',
            str(overlays/'%04d.png'), '-f', 'lavfi', '-i',
            'anullsrc=r=48000:cl=stereo', '-filter_complex_threads', '1',
            '-filter_complex', '[0:v][1:v]overlay=shortest=1[v]',
            '-map', '[v]', '-map', '2:a', '-t', str(12/FPS),
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(output)]
        _media_command('ffmpeg', arguments, directory/'cache')
        _validate_video(output, 12, directory/'cache')
    print('Teste sintético: todas as janelas, Pool, 12 quadros e ffprobe OK.')


def main() -> None:
    """Executa a montagem solicitada ou o teste sintético."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quadros", type=Path, help="Pasta com PNGs desde 0001.png")
    parser.add_argument("--saida", type=Path, help="MP4 de saída")
    parser.add_argument("--procs", type=int, default=2, help="Processos de desenho")
    parser.add_argument("--teste", action="store_true", help="Teste sintético no diretório temporário do sistema")
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
