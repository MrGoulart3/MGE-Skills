#!/usr/bin/env python3
"""Turn verified narration into the master timeline the 3D scene and post-production read.

Reads sentNN.json/sentNN.wav (from tts_verified.py), lays the sentences end to end
(lead-in, gaps, tail), and writes:
  timing.json   {fps, duration, sentences:[{n,start,end}], scenes:{A:[t0,t1]...}, events:{name:t}}
  captions.srt  word-accurate subtitle sidecar (accessibility / journals / social)
  narration.wav the assembled voice track (same sample rate as the takes)

Scenes map to sentences; events anchor to a word, so animation lands exactly on
the spoken word and survives any re-recording (just rerun this script).

Example:
  python3 build_timing.py --narration narration/ --out timing/ --fps 24 \
     --scenes A=1 B=2 C=3 D=4 E=5 \
     --events so2_enters=4:galerias:start co2_leaves=4:carbonato:end+0.3 \
     --lead 0.6 --gap 0.45 --tail 1.5
"""
from __future__ import annotations

import argparse
import json
import re
import wave
from pathlib import Path


def norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def read_wav(path: Path) -> tuple[int, int, bytes]:
    """Read PCM16 or float32 WAV (torchaudio's default) -> (rate, channels, PCM16 bytes)."""
    import array
    import struct
    raw = path.read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise SystemExit(f"{path.name}: not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(raw):
        cid, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            data = body
        pos += 8 + size + (size & 1)
    tag, ch, rate, _, _, bits = fmt
    if tag == 1 and bits == 16:
        return rate, ch, data
    if tag == 3 and bits == 32:
        f = array.array("f", data[: len(data) // 4 * 4])
        return rate, ch, array.array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in f)).tobytes()
    raise SystemExit(f"{path.name}: unsupported WAV (format {tag}, {bits} bit)")


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def chunk_words(words: list[dict], max_words: int = 6, max_chars: int = 42) -> list[list[dict]]:
    """Caption blocks: break at punctuation or length limits."""
    blocks, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x["word"] for x in cur)
        if len(cur) >= max_words or len(text) >= max_chars or w["word"][-1] in ".,;:!?":
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--narration", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--lead", type=float, default=0.6, help="silence before the first sentence (s)")
    ap.add_argument("--gap", type=float, default=0.45, help="pause between sentences (s)")
    ap.add_argument("--tail", type=float, default=1.5, help="hold after the last sentence (s)")
    ap.add_argument("--scenes", nargs="+", required=True, help="SCENE=sentence_number, in order")
    ap.add_argument("--events", nargs="*", default=[], help="name=sentence:word[:start|end][+/-offset]")
    args = ap.parse_args()

    nar, out = Path(args.narration), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(nar.glob("sent[0-9][0-9].json"))
    if not files:
        raise SystemExit("no sentNN.json found")

    sentences, t, frames, params = [], args.lead, [], None
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        rate, ch, pcm = read_wav(f.with_suffix(".wav"))
        params = params or (rate, ch)
        if (rate, ch) != params:
            raise SystemExit(f"{f.name}: audio format differs from the first take")
        dur = len(pcm) / (2 * ch * rate)
        frames.append((t, pcm))
        first = data["words"][0]["start"]  # trim Whisper's leading silence from timings
        words = [{"word": x["word"], "start": round(t + x["start"] - first, 3), "end": round(t + x["end"] - first, 3)} for x in data["words"]]
        # audio itself keeps its leading silence; shift audio so the first word lands at t
        frames[-1] = (t - first, frames[-1][1])
        spoken = data["words"][-1]["end"] - first  # trailing silence of the take is ignored
        sentences.append({"n": len(sentences) + 1, "start": round(t, 3), "end": round(t + spoken, 3), "words": words})
        t += spoken + args.gap
    duration = round(sentences[-1]["end"] + args.tail, 3)

    scene_of = [s.split("=") for s in args.scenes]
    scenes = {}
    for k, (name, n) in enumerate(scene_of):
        s = sentences[int(n) - 1]
        start = 0.0 if k == 0 else round(s["start"] - args.gap / 2, 3)
        scenes[name] = [start, None]
        if k:
            scenes[scene_of[k - 1][0]][1] = start
    scenes[scene_of[-1][0]][1] = duration

    events = {}
    for spec in args.events:
        name, rest = spec.split("=", 1)
        m = re.match(r"(\d+):([^:+\-]+)(?::(start|end))?([+\-][\d.]+)?$", rest)
        if not m:
            raise SystemExit(f"bad event spec: {spec}")
        n, word, edge, off = int(m[1]), norm(m[2]), m[3] or "start", float(m[4] or 0)
        hit = next((w for w in sentences[n - 1]["words"] if norm(w["word"]) == word), None)
        if hit is None:
            raise SystemExit(f"event {name}: word '{m[2]}' not in sentence {n}")
        events[name] = round(hit[edge] + off, 3)

    timing = {"fps": args.fps, "duration": duration, "frames": round(duration * args.fps),
              "sentences": [{k: s[k] for k in ("n", "start", "end")} for s in sentences],
              "scenes": scenes, "events": events}
    (out / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")
    (out / "words.json").write_text(json.dumps([w for s in sentences for w in s["words"]], ensure_ascii=False, indent=1), encoding="utf-8")

    srt, k = [], 1
    for s in sentences:
        for block in chunk_words(s["words"]):
            srt.append(f"{k}\n{srt_time(block[0]['start'])} --> {srt_time(block[-1]['end'] + 0.15)}\n{' '.join(w['word'] for w in block)}\n")
            k += 1
    (out / "captions.srt").write_text("\n".join(srt), encoding="utf-8")

    (rate, ch), width = params, 2
    import array
    total = array.array("i", bytes(4 * int(duration * rate) * ch))  # 32-bit accumulator: takes may overlap
    for start, pcm in frames:
        src = array.array("h", pcm)
        skip = max(0, -int(round(start * rate))) * ch
        pos = max(0, int(round(start * rate))) * ch
        for k, v in enumerate(src[skip: skip + max(0, len(total) - pos)]):
            total[pos + k] += v
    total = array.array("h", (max(-32768, min(32767, v)) for v in total)).tobytes()
    with wave.open(str(out / "narration.wav"), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(total)
    print(json.dumps({"duration": duration, "frames": timing["frames"], "scenes": scenes, "events": events}, indent=1))


if __name__ == "__main__":
    main()
