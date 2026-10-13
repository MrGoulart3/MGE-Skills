#!/usr/bin/env python3
"""Narration with verified pronunciation: Chatterbox Multilingual TTS + faster-whisper check.

For each sentence, generate N takes (different seeds), transcribe each with Whisper,
score it (required keywords present + word error rate against the script) and keep
the BEST take, not merely the first acceptable one. Word timings from Whisper are
projected onto the exact script words with difflib, so captions always show the
script spelling.

Input  (--script): JSON list of {"text": "...", "keywords": ["term", ...], "tts": optional}
                   "tts" is a respelled text (or a list of variants, cycled over the takes)
                   used ONLY for synthesis, e.g. "ênbôlo" for "êmbolo"; captions, keyword
                   and WER checks always use "text".
Output (--out):    sentNN.wav, sentNN.json ({text, words:[{word,start,end}], take, score}),
                   report.json (all takes, transcripts and scores).

Example:
  python3 tts_verified.py --script narration.json --out narration/ --lang pt \
      --takes 6 --exaggeration 0.7 --cfg 0.4 [--voice reference.wav] [--threads 16]
Requires: torch, torchaudio, chatterbox-tts, faster-whisper (CPU is fine; ~1 min/sentence).
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from pathlib import Path


def fold(text: str) -> str:
    """Lowercase and strip accents: Whisper often drops diacritics (êmbolo -> embolo)."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def norm(word: str) -> str:
    return re.sub(r"[^\w]", "", fold(word))


def wer(ref: list[str], hyp: list[str]) -> float:
    """Word error rate via edit distance (normalized words)."""
    r, h = [norm(w) for w in ref], [norm(w) for w in hyp]
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        row = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
        prev = row
    return prev[-1] / max(1, len(r))


def project_timings(script_words: list[str], asr_words: list) -> list[tuple[float, float]]:
    """Map ASR word timestamps onto the script words; interpolate unmatched ones."""
    sm = difflib.SequenceMatcher(None, [norm(w) for w in script_words],
                                 [norm(w.word) for w in asr_words], autojunk=False)
    t: list[tuple[float, float] | None] = [None] * len(script_words)
    for a, b, k in sm.get_matching_blocks():
        for j in range(k):
            t[a + j] = (asr_words[b + j].start, asr_words[b + j].end)
    for k in range(len(script_words)):
        if t[k] is None:
            before = next((t[j][1] for j in range(k - 1, -1, -1) if t[j]), 0.0)
            after = next((t[j][0] for j in range(k + 1, len(script_words)) if t[j]), before + 0.3)
            t[k] = (before, max(before + 0.05, after))
    return t  # type: ignore[return-value]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="pt")
    ap.add_argument("--takes", type=int, default=6)
    ap.add_argument("--exaggeration", type=float, default=0.7)
    ap.add_argument("--cfg", type=float, default=0.4)
    ap.add_argument("--voice", help="reference WAV (5-15 s, clean) for zero-shot voice cloning")
    ap.add_argument("--seed", type=int, default=500)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--whisper", default="small")
    ap.add_argument("--only", type=int, nargs="*", help="regenerate only these sentence numbers (1-based)")
    args = ap.parse_args()

    import torch
    import torchaudio as ta
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    from faster_whisper import WhisperModel

    torch.set_num_threads(args.threads)
    sentences = json.loads(Path(args.script).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tts = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    asr = WhisperModel(args.whisper, device="cpu", compute_type="int8", cpu_threads=args.threads)
    report = []
    for i, item in enumerate(sentences, 1):
        if args.only and i not in args.only:
            continue
        text, keys = item["text"], [k.lower() for k in item.get("keywords", [])]
        variants = item.get("tts") or [text]
        variants = [variants] if isinstance(variants, str) else variants
        best = None
        for take in range(args.takes):
            torch.manual_seed(args.seed + 10 * i + take)
            kw = dict(language_id=args.lang, exaggeration=args.exaggeration, cfg_weight=args.cfg)
            if args.voice:
                kw["audio_prompt_path"] = args.voice
            wav = tts.generate(variants[take % len(variants)], **kw)
            tmp = out / f"_take{i:02d}_{take}.wav"
            ta.save(str(tmp), wav, tts.sr, encoding="PCM_S", bits_per_sample=16)
            segs = list(asr.transcribe(str(tmp), language=args.lang, word_timestamps=True)[0])
            words = [w for s in segs for w in s.words]
            heard = " ".join(s.text for s in segs).strip()
            missing = [k for k in keys if fold(k) not in fold(heard)]
            score = len(missing) * 10 + wer(text.split(), heard.split())  # lower is better
            report.append({"sentence": i, "take": take, "tts": variants[take % len(variants)], "heard": heard, "missing": missing, "score": round(score, 3)})
            print(f"[{i}.{take}] score={score:.3f} missing={missing} | {heard}", flush=True)
            if best is None or score < best[0]:
                best = (score, take, tmp, words)
            if score == 0:
                break
        score, take, tmp, words = best
        tmp.replace(out / f"sent{i:02d}.wav")
        for f in out.glob(f"_take{i:02d}_*.wav"):
            f.unlink()
        script_words = text.split()
        timings = project_timings(script_words, words)
        (out / f"sent{i:02d}.json").write_text(json.dumps({
            "text": text, "take": take, "score": round(score, 3),
            "words": [{"word": w, "start": round(s, 3), "end": round(e, 3)} for w, (s, e) in zip(script_words, timings)],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        if score >= 10:
            print(f"WARNING sentence {i}: required keyword still missing; reword it or respell the term.", flush=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("DONE")


if __name__ == "__main__":
    main()
