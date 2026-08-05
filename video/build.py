from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent
RENDER = ROOT.parent / "evidence-dev" / "render"
WORK = ROOT / "work"
GFX = WORK / "gfx"
AUDIO = WORK / "audio"
SEG = WORK / "seg"
OUT = ROOT / "out"

ENCODE = [
    "-r",
    "30",
    "-c:v",
    "libx264",
    "-crf",
    "18",
    "-preset",
    "medium",
    "-pix_fmt",
    "yuv420p",
    "-video_track_timescale",
    "15360",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    "-ar",
    "48000",
    "-ac",
    "2",
]
NORMALIZE = (
    "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
)
VOICE_CHAIN = (
    "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,adelay=300:all=1,apad"
)
VO_DELAY_S = 0.3
CARD_TAIL_S = 1.3
CLIP_TAIL_S = 1.0
FADE_S = 0.5
MUSIC_EXTRA_S = 10.0


@dataclass(frozen=True)
class Card:
    scene: str
    image: str


@dataclass(frozen=True)
class Clip:
    scene: str
    source: str
    in_point: float
    overlays: tuple[str, ...]
    full_length: bool = False


@dataclass(frozen=True)
class Split:
    scene: str
    left: str
    left_in: float
    right: str
    right_in: float
    overlays: tuple[str, ...]


SCENES: tuple[Card | Clip | Split, ...] = (
    Card("s01_intro", "card_intro"),
    Clip("s02_hook", "candidate-v2-scene2-seed312", 23.5, ("cap_hook", "watermark")),
    Clip("s03_baseline", "baseline-v1-scene2-seed313", 6.0, ("cap_baseline", "watermark")),
    Clip("s04_discovery", "candidate-v2-scene2-seed312", 1.2, ("cap_discovery", "watermark")),
    Split(
        "s05_sidebyside",
        "baseline-v1-scene2-seed313",
        7.0,
        "candidate-v2-scene2-seed303",
        2.5,
        ("split_labels", "watermark"),
    ),
    Card("s06_results", "card_results"),
    Card("s07_validator", "card_validator"),
    Card("s08_honesty", "card_honesty"),
    Clip(
        "s09_money",
        "candidate-v2-scene2-seed303",
        1.5,
        ("money_overlay", "watermark"),
        full_length=True,
    ),
    Card("s10_outro", "card_outro"),
)


def run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True, text=True)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def overlay_chain(overlays: tuple[str, ...], base: str) -> tuple[str, list[str], str]:
    inputs: list[str] = []
    chain = ""
    label = base
    for index, name in enumerate(overlays):
        inputs.extend(["-i", str(GFX / f"{name}.png")])
        target = f"ov{index}"
        position = "0:main_h-overlay_h" if name.startswith("cap_") else "0:0"
        chain += f"[{label}][{2 + index}:v]overlay={position}[{target}];"
        label = target
    return chain, inputs, label


def build_card(card: Card, vo_len: float) -> float:
    duration = max(vo_len + VO_DELAY_S + CARD_TAIL_S, 7.0)
    fade_out = duration - FADE_S
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-loop",
            "1",
            "-i",
            str(GFX / f"{card.image}.png"),
            "-i",
            str(AUDIO / f"{card.scene}.mp3"),
            "-filter_complex",
            f"[0:v]fps=30,setsar=1,fade=t=in:st=0:d={FADE_S},fade=t=out:st={fade_out:.2f}:d={FADE_S}[v];"
            f"[1:a]{VOICE_CHAIN}[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{duration:.2f}",
            *ENCODE,
            str(SEG / f"{card.scene}.mp4"),
        ]
    )
    return duration


def build_clip(clip: Clip, vo_len: float) -> float:
    source = RENDER / f"{clip.source}.mp4"
    available = probe_duration(source) - clip.in_point
    wanted = vo_len + VO_DELAY_S + CLIP_TAIL_S
    duration = max(available, wanted) if clip.full_length else max(min(available, 40.0), wanted)
    pad = max(0.0, duration - available)
    chain, inputs, label = overlay_chain(clip.overlays, "norm")
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{clip.in_point:.2f}",
            "-i",
            str(source),
            "-i",
            str(AUDIO / f"{clip.scene}.mp3"),
            *inputs,
            "-filter_complex",
            f"[0:v]{NORMALIZE},tpad=stop_mode=clone:stop_duration={pad:.2f}[norm];"
            f"{chain}[1:a]{VOICE_CHAIN}[a]",
            "-map",
            f"[{label}]",
            "-map",
            "[a]",
            "-t",
            f"{duration:.2f}",
            *ENCODE,
            str(SEG / f"{clip.scene}.mp4"),
        ]
    )
    return duration


def build_split(split: Split, vo_len: float) -> float:
    duration = vo_len + VO_DELAY_S + CLIP_TAIL_S
    chain, inputs, label = overlay_chain(split.overlays, "stacked")
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{split.left_in:.2f}",
            "-i",
            str(RENDER / f"{split.left}.mp4"),
            "-ss",
            f"{split.right_in:.2f}",
            "-i",
            str(RENDER / f"{split.right}.mp4"),
            *inputs,
            "-i",
            str(AUDIO / f"{split.scene}.mp3"),
            "-filter_complex",
            "[0:v]fps=30,setsar=1[l];[1:v]fps=30,setsar=1[r];"
            f"[l][r]hstack,pad=1920:1080:0:180,setsar=1[stacked];{chain}"
            f"[{2 + len(split.overlays)}:a]{VOICE_CHAIN}[a]",
            "-map",
            f"[{label}]",
            "-map",
            "[a]",
            "-t",
            f"{duration:.2f}",
            *ENCODE,
            str(SEG / f"{split.scene}.mp4"),
        ]
    )
    return duration


def mix_music(base: Path, music: Path, target: Path, total: float) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(base),
            "-i",
            str(music),
            "-filter_complex",
            f"[1:a]atrim=0:{total:.2f},aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.5,apad[m];"
            "[0:a]asplit[vo1][vo2];"
            "[m][vo2]sidechaincompress=threshold=0.02:ratio=10:attack=5:release=400[duck];"
            "[vo1][duck]amix=inputs=2:duration=first:normalize=0,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(target),
        ]
    )


def main() -> int:
    SEG.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    vo_lengths: dict[str, float] = json.loads((AUDIO / "manifest.json").read_text())

    total = 0.0
    for scene in SCENES:
        vo_len = vo_lengths[scene.scene]
        if isinstance(scene, Card):
            build_card(scene, vo_len)
        elif isinstance(scene, Clip):
            build_clip(scene, vo_len)
        else:
            build_split(scene, vo_len)
        actual = probe_duration(SEG / f"{scene.scene}.mp4")
        if actual + 0.05 < vo_len + VO_DELAY_S:
            raise RuntimeError(
                f"{scene.scene}: segment {actual:.2f}s shorter than narration {vo_len:.2f}s"
            )
        total += actual
        print(f"  {scene.scene}: {actual:.2f}s (vo {vo_len:.2f}s)", flush=True)

    concat_list = WORK / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{(SEG / f'{s.scene}.mp4').resolve()}'\n" for s in SCENES)
    )
    base = WORK / "demo_base.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(base),
        ]
    )
    base_len = probe_duration(base)
    print(f"  assembled: {base_len:.2f}s", flush=True)

    music = AUDIO / "music.mp3"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = OUT / f"demo-{stamp}.mp4"
    if music.exists():
        mix_music(base, music, target, base_len)
    else:
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(base),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(target),
            ]
        )
        print("  WARNING: no music bed found, VO-only mix", flush=True)
    print(f"  final: {target} ({probe_duration(target):.2f}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
