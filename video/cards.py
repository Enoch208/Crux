from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from crux.evidence.validator import validate_evidence

ROOT = Path(__file__).parent
OUT = ROOT / "work" / "gfx"
MANIFEST = ROOT.parent / "evidence" / "manifest.json"
W, H = 1920, 1080
BG = (13, 17, 23)
FG = (230, 237, 243)
DIM = (139, 148, 158)
ACCENT = (237, 28, 36)
GREEN = (63, 185, 80)
AMBER = (210, 153, 34)
BAR_RGBA = (13, 17, 23, 216)
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
ARIAL_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MENLO = "/System/Library/Fonts/Menlo.ttc"
REPO = "github.com/Enoch208/Crux"

Line = tuple[str, ImageFont.FreeTypeFont, tuple[int, int, int], int]


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def centered(draw: ImageDraw.ImageDraw, lines: list[Line], height: int) -> None:
    total = sum(gap + f.size for _, f, _, gap in lines)
    y = (height - total) // 2
    for text, f, color, gap in lines:
        y += gap
        x = (W - draw.textlength(text, font=f)) // 2
        draw.text((x, y), text, font=f, fill=color)
        y += f.size


def card(name: str, lines: list[Line]) -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    centered(draw, lines, H)
    small = font(ARIAL, 28)
    draw.text((W - draw.textlength(REPO, font=small) - 40, 32), REPO, font=small, fill=DIM)
    img.save(OUT / f"{name}.png")


def caption(name: str, left: str, right: str, right_color: tuple[int, int, int]) -> None:
    img = Image.new("RGBA", (W, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, W, 96), fill=BAR_RGBA)
    f = font(ARIAL_BOLD, 38)
    draw.text((48, 26), left, font=f, fill=FG)
    draw.text((W - 48 - draw.textlength(right, font=f), 26), right, font=f, fill=right_color)
    img.save(OUT / f"{name}.png")


def watermark() -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = font(ARIAL, 28)
    text_w = draw.textlength(REPO, font=f)
    draw.rectangle((W - text_w - 72, 20, W - 24, 72), fill=(13, 17, 23, 150))
    draw.text((W - text_w - 48, 32), REPO, font=f, fill=(230, 237, 243, 220))
    img.save(OUT / "watermark.png")


def split_labels() -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = font(ARIAL_BOLD, 44)
    sub = font(ARIAL, 30)
    for x0, title, color, seed in (
        (0, "BASELINE", AMBER, "baseline-v1 · virgin seed 505"),
        (960, "OURS", GREEN, "candidate-v4 · virgin seed 505"),
    ):
        draw.rectangle((x0 + 24, 110, x0 + 936, 226), fill=(13, 17, 23, 190))
        draw.text((x0 + 48, 128), title, font=f, fill=color)
        draw.text((x0 + 48, 180), seed, font=sub, fill=FG)
    bar = font(ARIAL_BOLD, 34)
    note = "the same seed, the same scene · synchronized at the grasp"
    draw.rectangle((0, H - 84, W, H), fill=BAR_RGBA)
    draw.text(((W - draw.textlength(note, font=bar)) // 2, H - 62), note, font=bar, fill=FG)
    img.save(OUT / "split_labels.png")


TELEMETRY_LINES = (
    "$ rocm-smi   — sampled live during the sweep (06:15:51)",
    "GPU[0] : GPU use (%): 100",
    "GPU[0] : Average Graphics Package Power (W): 47.0",
    "GPU[0] : Temperature edge/junction/memory (C): 26 / 32 / 27",
    "GPU[0] : GPU Memory Allocated (VRAM%): 2",
)


def telemetry_panel() -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    mono = font(MENLO, 26)
    panel_w = 880
    panel_h = 40 + 44 * len(TELEMETRY_LINES)
    draw.rectangle((40, 40, 40 + panel_w, 40 + panel_h), fill=(13, 17, 23, 210))
    y = 62
    for index, line in enumerate(TELEMETRY_LINES):
        color = FG if index == 0 else GREEN
        draw.text((64, y), line, font=mono, fill=color)
        y += 44
    img.save(OUT / "telemetry_panel.png")


def money_overlay() -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = font(ARIAL_BOLD, 38)
    mono = font(MENLO, 30)
    draw.rectangle((0, H - 168, W, H), fill=BAR_RGBA)
    draw.text((48, H - 148), "candidate-v4 · virgin seed · UNCUT · REAL-TIME", font=f, fill=FG)
    chip = "SUCCESS · 13/32 vs 0/32 · p = 0.0002"
    draw.text((W - 48 - draw.textlength(chip, font=f), H - 148), chip, font=f, fill=GREEN)
    repro = "$ uv run crux validate evidence/manifest.json   ->   9/9 checks passed"
    draw.text((48, H - 76), repro, font=mono, fill=GREEN)
    img.save(OUT / "money_overlay.png")


def intro() -> None:
    card(
        "card_intro",
        [
            ("A robot. A cable. Two clips. A socket.", font(ARIAL_BOLD, 76), FG, 0),
            (
                "Contact-rich manipulation breaks in ways specs don't predict.",
                font(ARIAL, 44),
                FG,
                48,
            ),
            (
                "Finding and repairing those failures is still mostly manual.",
                font(ARIAL, 44),
                DIM,
                16,
            ),
        ],
    )


def results() -> None:
    card(
        "card_results",
        [
            ("The robot completes the task", font(ARIAL_BOLD, 66), FG, 0),
            (
                "32 virgin seeds per arm (701-732) · matched pairs · never seen before",
                font(ARIAL, 38),
                DIM,
                20,
            ),
            ("task success:  0/32  ->  13/32", font(ARIAL_BOLD, 64), FG, 62),
            ("+40.6 pp · exact McNemar p = 0.0002", font(ARIAL_BOLD, 52), GREEN, 18),
            (
                "replicates on three further suites: 12/32, 9/32, and 6/32 on a second task",
                font(ARIAL, 38),
                FG,
                48,
            ),
            (
                "every discordant pair favours the candidate — 0 against, 13 for",
                font(ARIAL, 38),
                FG,
                16,
            ),
            (
                "release gate: APPROVED — after rejecting the two candidates before it",
                font(ARIAL, 38),
                AMBER,
                20,
            ),
            ("~200k-293k env-steps/s at 4,096 batched environments", font(ARIAL, 38), ACCENT, 48),
        ],
    )


VALIDATE_DETAIL_WIDTH = 60


def wrapped(detail: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in detail.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def validate_lines() -> list[tuple[str, tuple[int, int, int]]]:
    """Render the card from a live run of the validator, never from transcribed text."""
    report = validate_evidence(MANIFEST)
    lines: list[tuple[str, tuple[int, int, int]]] = [
        (f"$ crux validate {MANIFEST.parent.name}/{MANIFEST.name}", FG),
        ("", FG),
    ]
    for result in report.results:
        colour = GREEN if result.passed else ACCENT
        for index, chunk in enumerate(wrapped(result.detail, VALIDATE_DETAIL_WIDTH)):
            head = f"{result.status:<4} {result.name:<22} " if index == 0 else " " * 28
            lines.append((f"{head}{chunk}", colour))
    passed = sum(result.passed for result in report.results)
    lines.append(("", FG))
    lines.append((f"{passed}/{len(report.results)} checks passed", FG))
    return lines


DEVICE_BANNER = (
    "[Genesis] Running on [AMD Radeon Graphics] with backend gs.amdgpu. Device memory: 47.98 GB."
)


def validator() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    title_font = font(ARIAL_BOLD, 60)
    sub_font = font(ARIAL, 36)
    mono = font(MENLO, 24)
    title = "Verify it yourself — CPU only"
    draw.text(
        ((W - draw.textlength(title, font=title_font)) // 2, 96), title, font=title_font, fill=FG
    )
    sub = "the bundle recomputes its own headline numbers from raw episode records"
    draw.text(((W - draw.textlength(sub, font=sub_font)) // 2, 180), sub, font=sub_font, fill=DIM)
    y = 268
    for text, color in validate_lines():
        draw.text((120, y), text, font=mono, fill=color)
        y += 40
    draw.text((120, y + 30), DEVICE_BANNER, font=font(MENLO, 22), fill=ACCENT)
    small = font(ARIAL, 28)
    draw.text((W - draw.textlength(REPO, font=small) - 40, 32), REPO, font=small, fill=DIM)
    img.save(OUT / "card_validator.png")


def honesty() -> None:
    card(
        "card_honesty",
        [
            ("What we can't claim, we don't", font(ARIAL_BOLD, 66), FG, 0),
            ("the cable is an articulated chain, not a deformable body", font(ARIAL, 42), FG, 60),
            (
                "contact rollouts are not reproducible on this stack — measured, disclosed",
                font(ARIAL, 42),
                FG,
                18,
            ),
            (
                "our success metric was geometrically impossible — the campaign caught it",
                font(ARIAL, 42),
                AMBER,
                18,
            ),
            (
                "a repair we called falsified five times had always worked — mismeasured",
                font(ARIAL, 42),
                FG,
                18,
            ),
            (
                "failed episodes are never deleted · every clip is a fresh rollout",
                font(ARIAL, 42),
                DIM,
                18,
            ),
        ],
    )


def outro() -> None:
    card(
        "card_outro",
        [
            ("CRUX", font(ARIAL_BOLD, 160), FG, 0),
            (
                "reliability engineering for robot manipulation — on one Radeon",
                font(ARIAL, 46),
                FG,
                40,
            ),
            (REPO, font(ARIAL_BOLD, 54), ACCENT, 64),
            ("Track 3 · Physical AI · AMD AI DevMaster Hackathon 2026", font(ARIAL, 34), DIM, 20),
        ],
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    intro()
    results()
    validator()
    honesty()
    outro()
    watermark()
    split_labels()
    money_overlay()
    telemetry_panel()
    caption(
        "cap_hook",
        "candidate-v4 · virgin seed 506 · real-time",
        "one AMD Radeon PRO W7900",
        ACCENT,
    )
    caption(
        "cap_baseline",
        "baseline-v1 · virgin seed 512 · real-time",
        "outcome: CABLE_SLIP during routing",
        AMBER,
    )
    caption(
        "cap_discovery",
        "discovery B-roll · candidate-v2 seed 312",
        "19 matched sweeps · ~1,230 episodes · 10 mechanisms",
        FG,
    )
    caption(
        "cap_scale",
        "16 simultaneous environments · visualization run",
        "sweeps ran 32-128 · throughput measured at 4,096",
        FG,
    )
    for name in sorted(OUT.glob("*.png")):
        print(name.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
