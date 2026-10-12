"""Cut a Playwright screen recording (screen.webm + nav_log.json + offset.json) to a block-by-block narration.

The timeline is the narration clock: each block gets its narration length plus a short gap; the shots listed for the
block are fitted to it (mild speed change, then a hold on one frame). Captions are drawn on the final timeline.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.io import wavfile
from scipy.signal import resample_poly

FONT = os.environ.get("FILM_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FPS = 30
BAND = "0x10192B"


def probe_duration(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True).stdout.strip())


class Recording:
    def __init__(self, rec_dir: Path, work: Path):
        self.src = rec_dir / "screen.webm"
        self.nav = json.load(open(rec_dir / "nav_log.json"))
        meta = json.load(open(rec_dir / "offset.json"))
        self.off = meta["offset"]
        self.headless = bool(meta.get("headless"))
        self.k = 1.0                       # video seconds per wall-clock second (headless screencasts run a little slow)
        self.length = probe_duration(self.src)
        self.work = work
        self._heights: dict[float, int] = {}
        self._ink: dict[float, float] = {}

    def L(self, label: str, k: int = 0, default: float | None = None) -> float:
        """Video time of the k-th nav_log entry whose label starts with `label`."""
        hits = [t for lab, t in self.nav if lab.startswith(label)]
        if len(hits) <= k:
            if default is None:
                raise KeyError(f"nav_log has no '{label}' #{k}")
            return default
        return hits[k] * self.k + self.off

    def ink(self, t: float) -> float:
        """Fraction of dark pixels in the frame at t: ~0 for a blank page, >= 0.01 for a rendered one."""
        t = round(t, 2)
        if t not in self._ink:
            p = self.work / "ink.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(self.src), "-frames:v", "1", "-vf", "scale=400:225", str(p)], check=True)
            a = np.array(Image.open(p).convert("RGB")).astype(int)
            self._ink[t] = float((a.min(axis=2) < 160).mean())
        return self._ink[t]

    def content_span(self, a: float, b: float, thr: float = 0.010, step: float = 0.25) -> tuple[float, float]:
        """(first rendered frame at or after a, last rendered frame at or before b): trims the blank loading frames."""
        a, b = max(0.0, a), min(b, self.length - 0.05)
        t0 = a
        while t0 < b and self.ink(t0) < thr:
            t0 += step
        t1 = b
        while t1 > t0 and self.ink(t1) < thr:
            t1 -= step
        t0, t1 = t0 + 0.15, t1 - 0.3                      # stay clear of the transition frames
        return (t0, t1) if t1 - t0 > 0.3 else (a, b)

    def times(self, label: str) -> list[float]:
        return [t * self.k + self.off for lab, t in self.nav if lab.startswith(label)]

    def wall(self, label: str, k: int = 0) -> float:
        hits = [t for lab, t in self.nav if lab.startswith(label)]
        return hits[k]

    def fit_drift(self, last_page_label: str, settle: float, k: int = 0) -> float:
        """A headless screencast stops at the last frame that changed, and its clock runs a little slow. The last page
        the recorder opened rendered about (settle - 1) s before its mark; the video ends when that render landed."""
        try:
            w = self.wall(last_page_label, k) - settle + 1.0
            kk = (self.length - self.off) / w
        except Exception:
            return 1.0
        if self.headless and 1.0 < kk < 1.05:
            self.k = kk
        print(f"timeline: offset {self.off:.2f}s, drift x{self.k:.4f}, video {self.length:.1f}s")
        return self.k

    def has(self, label: str) -> bool:
        return any(lab.startswith(label) for lab, _ in self.nav)

    def content_height(self, t: float) -> int:
        """Rows of real page content in the frame at t (Playwright pads a short viewport with grey)."""
        t = round(t, 1)
        if t not in self._heights:
            p = self.work / "probe.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(self.src), "-frames:v", "1", str(p)], check=True)
            a = np.array(Image.open(p).convert("RGB"))
            col = a[:, 800, :]
            grey = np.where((col == 128).all(axis=1))[0]
            self._heights[t] = int(grey.min()) if len(grey) > 60 else a.shape[0]
        return self._heights[t]


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def compose(rec_dir: Path, narr_dir: Path, out: Path, blocks: list[str], gap_after: dict[str, float], lead: float,
            shots_for, vf_for, captions_for, end_pad: float = 0.0, prepare=None) -> dict:
    work = out.parent / (out.stem + "_work")
    work.mkdir(parents=True, exist_ok=True)
    rec = Recording(rec_dir, work)
    if prepare:
        prepare(rec)
    dur = json.load(open(narr_dir / "durations.json"))

    timeline, t = [], lead
    for b in blocks:
        budget = dur[b] + gap_after[b]
        timeline.append((b, t, dur[b], budget))
        t += budget
    total = t + end_pad
    print(f"film length {total:.1f}s")

    files, idx, starts = [], 0, {}
    for b, start, nlen, budget in timeline:
        shots = [tuple(sh) + ("",) * (4 - len(sh)) for sh in shots_for(rec, b)]
        shots = [(max(0.0, i), min(o, rec.length - 0.05), k, hh) for i, o, k, hh in shots]
        shots = [sh for sh in shots if sh[1] - sh[0] > 0.2]
        if b == blocks[-1]:
            budget += end_pad
        raw = sum(o - i for i, o, _, _ in shots)
        speed, hold = 1.0, 0.0
        if raw > budget:
            speed = min(1.25, raw / budget)
            extra = raw / speed - budget
            if extra > 0.02:                                  # still too long: shorten every shot from its end, in proportion
                f = (budget * speed) / raw
                shots = [(i, i + (o - i) * f, k, hh) for i, o, k, hh in shots]
                raw = sum(o - i for i, o, _, _ in shots)
        elif raw < budget:
            speed = max(0.9, raw / budget)
            hold = budget - raw / speed
        n = len(shots)
        hold_at = [j for j, sh in enumerate(shots) if sh[3] == "hold"] or [n - 1]   # the hold is shared by the marked shots
        print(f"{b:9s} start {start:6.1f}  narration {nlen:5.1f}  budget {budget:5.1f}  raw {raw:5.1f}  speed {speed:.3f}  hold {hold:4.1f}  shots {n}")
        starts[b] = start
        got_total = 0.0
        for j, (i, o, k, _) in enumerate(shots):
            f = work / f"shot{idx:02d}.mp4"
            h = hold / len(hold_at) if j in hold_at else 0.0
            vf = f"setpts=(PTS-STARTPTS)/{speed:.5f},{vf_for(rec, k, i)},fps={FPS}"
            if h > 0.01:
                vf += f",tpad=stop_mode=clone:stop_duration={h:.3f}"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{i:.3f}", "-t", f"{o - i:.3f}", "-i", str(rec.src), "-vf", vf,
                            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(f)], check=True)
            files.append(f)
            got_total += probe_duration(f)
            idx += 1
        print(f"          cut {got_total:5.1f}s")

    with open(work / "list.txt", "w") as fh:
        for f in files:
            fh.write(f"file '{f.resolve()}'\n")

    sr_out = 48000
    track = np.zeros(int((total + 1.0) * sr_out), dtype=np.float32)
    for b, start, nlen, budget in timeline:
        sr, s = wavfile.read(narr_dir / f"{b}.wav")
        s = s.astype(np.float32) / 32768.0
        if sr != sr_out:
            s = resample_poly(s, sr_out, sr).astype(np.float32)
        a = int(start * sr_out)
        track[a:a + len(s)] += s[: len(track) - a]
    track = track / (np.abs(track).max() or 1.0) * 0.89
    wavfile.write(str(work / "narration.wav"), sr_out, (np.stack([track, track], axis=1) * 32767).astype(np.int16))

    draw = []
    for s, e, text in captions_for(starts, total):
        size = 34 if len(text) <= 72 else (29 if len(text) <= 92 else 25)
        draw.append(f"drawtext=fontfile={FONT}:text='{esc(text)}':expansion=none:fontsize={size}:fontcolor=0xF6F3EC:box=1:boxcolor={BAND}@0.84:boxborderw=16"
                    f":x=40:y=h-96:enable='between(t,{s:.2f},{e:.2f})'")
    vf = f"fps={FPS}," + ",".join(draw) + f",fade=t=in:st=0:d=0.5,fade=t=out:st={total - 0.8:.2f}:d=0.8"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"), "-i", str(work / "narration.wav"),
           "-vf", vf, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-map", "0:v:0", "-map", "1:a:0", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("final rc", r.returncode, r.stderr[-800:])
    print(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "default=noprint_wrappers=1", str(out)],
                         capture_output=True, text=True).stdout)
    json.dump({"starts": starts, "total": total}, open(work / "timeline.json", "w"), indent=1)
    return {"starts": starts, "total": total}
