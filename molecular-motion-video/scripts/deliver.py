#!/usr/bin/env python3
"""Automated QA and final deliverables for a narrated video.

  qa        objective checks -> qa_report.json; exit 1 if any check fails
            (resolution, fps, codecs, duration, black frames, frozen stretches,
             integrated loudness, true peak)
  finalize  from the assembled master: two-pass loudness normalization
            (default -16 LUFS / -1.5 dBTP, web standard), then
            master.mp4 (CRF 16), web.mp4 (CRF 23, faststart),
            optional vertical 9:16 crop, optional soft-subtitle track from an .srt.

Examples:
  python3 deliver.py qa video.mp4 --width 1920 --height 1080 --fps 24 --duration 30.6
  python3 deliver.py finalize assembled.mp4 --out final/ --srt captions.srt --vertical-center 0.68
Requires ffmpeg/ffprobe on PATH (or --ffmpeg/--ffprobe).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(ffprobe: str, path: str) -> dict:
    r = run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    if r.returncode:
        raise SystemExit(r.stderr)
    return json.loads(r.stdout)


def loudness(ffmpeg: str, path: str) -> dict:
    r = run([ffmpeg, "-hide_banner", "-nostats", "-i", path, "-af",
             "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    block = r.stderr[r.stderr.rfind("{"): r.stderr.rfind("}") + 1]
    return json.loads(block)


def qa(args: argparse.Namespace) -> int:
    info = probe(args.ffprobe, args.video)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    num, den = map(int, v["r_frame_rate"].split("/"))
    dur = float(info["format"]["duration"])
    checks = {
        "resolution": (f"{v['width']}x{v['height']}", (v["width"], v["height"]) == (args.width, args.height)),
        "fps": (round(num / den, 3), abs(num / den - args.fps) < 0.01),
        "video_codec": (f"{v['codec_name']} {v.get('pix_fmt')}", v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p"),
        "audio": (a["codec_name"] if a else None, a is not None),
    }
    if args.duration:
        checks["duration"] = (round(dur, 3), abs(dur - args.duration) <= 0.1)
    r = run([args.ffmpeg, "-hide_banner", "-nostats", "-i", args.video, "-vf",
             "blackdetect=d=0.25:pix_th=0.04,freezedetect=n=0.0005:d=%s" % args.freeze, "-an", "-f", "null", "-"])
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)
    blacks = [(float(s), float(e)) for s, e in blacks if not (float(s) < 0.05 and args.allow_black_intro)]
    freezes = re.findall(r"freeze_start: ([\d.]+)", r.stderr)
    checks["black_segments"] = (blacks, not blacks)
    checks["frozen_segments"] = ([float(x) for x in freezes], not freezes or args.allow_freeze)
    if a:
        L = loudness(args.ffmpeg, args.video)
        i, tp = float(L["input_i"]), float(L["input_tp"])
        checks["loudness_LUFS"] = (i, abs(i - args.lufs) <= 1.0)
        checks["true_peak_dBTP"] = (tp, tp <= -1.0)
    report = {k: {"value": val, "ok": ok} for k, (val, ok) in checks.items()}
    Path(args.report).write_text(json.dumps(report, indent=1))
    for k, (val, ok) in checks.items():
        print(f"{'OK ' if ok else 'FAIL'} {k}: {val}")
    return 0 if all(ok for _, ok in checks.values()) else 1


def finalize(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    L = loudness(args.ffmpeg, args.video)
    norm = (f"loudnorm=I={args.lufs}:TP=-1.5:LRA=11:measured_I={L['input_i']}:measured_TP={L['input_tp']}:"
            f"measured_LRA={L['input_lra']}:measured_thresh={L['input_thresh']}:offset={L['target_offset']}:linear=true")
    common = [args.ffmpeg, "-y", "-v", "error", "-threads", str(args.threads), "-i", args.video]
    jobs = {
        "master.mp4": ["-c:v", "libx264", "-crf", "16", "-preset", "slow"],
        "web.mp4": ["-c:v", "libx264", "-crf", "23", "-preset", "slow"],
    }
    for name, vopts in jobs.items():
        if args.srt:
            cmd = common + ["-i", args.srt]
            # map: video/audio from input 0, subtitles from input 1
            extra = ["-map", "0:v", "-map", "0:a", "-map", "1:s", "-c:s", "mov_text", "-metadata:s:s:0", f"language={args.lang}"]
        else:
            cmd, extra = common[:], []
        cmd += extra + vopts + ["-pix_fmt", "yuv420p", "-af", norm, "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
                                "-movflags", "+faststart", str(out / name)]
        r = run(cmd)
        print(("OK " if r.returncode == 0 else "FAIL ") + name, r.stderr[-300:])
    if args.vertical_center is not None:
        # 9:16 crop keeping the subject (horizontal centre as a fraction of width)
        crop = f"crop=ih*9/16:ih:max(0\\,min(iw-ih*9/16\\,iw*{args.vertical_center}-ih*9/32)):0,scale=1080:1920"
        r = run(common + ["-vf", crop, "-c:v", "libx264", "-crf", "20", "-preset", "slow", "-pix_fmt", "yuv420p",
                          "-af", norm, "-ar", "48000", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                          str(out / "vertical_9x16.mp4")])
        print(("OK " if r.returncode == 0 else "FAIL ") + "vertical_9x16.mp4", r.stderr[-300:])
        print("NOTE: burned-in captions/titles were laid out for 16:9; re-run post-production at 1080x1920 for a polished vertical cut.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--lufs", type=float, default=-16.0)
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("qa")
    q.add_argument("video")
    q.add_argument("--width", type=int, default=1920)
    q.add_argument("--height", type=int, default=1080)
    q.add_argument("--fps", type=float, default=24)
    q.add_argument("--duration", type=float)
    q.add_argument("--freeze", type=float, default=2.5, help="flag still stretches longer than this (s)")
    q.add_argument("--allow-freeze", action="store_true", help="intentional holds (e.g. final title card)")
    q.add_argument("--allow-black-intro", action="store_true")
    q.add_argument("--report", default="qa_report.json")
    f = sub.add_parser("finalize")
    f.add_argument("video")
    f.add_argument("--out", required=True)
    f.add_argument("--srt")
    f.add_argument("--lang", default="por")
    f.add_argument("--vertical-center", type=float, help="subject centre x (0-1) for the 9:16 crop")
    args = ap.parse_args()
    sys.exit(qa(args) if args.cmd == "qa" else finalize(args))


if __name__ == "__main__":
    main()
