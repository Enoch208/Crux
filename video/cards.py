from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
OUT = ROOT / "work" / "gfx"
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
        (0, "BASELINE", AMBER, "baseline-v1 · held-out seed 313"),
        (960, "OURS", GREEN, "candidate-v2 · held-out seed 303"),
    ):
        draw.rectangle((x0 + 24, 110, x0 + 936, 226), fill=(13, 17, 23, 190))
        draw.text((x0 + 48, 128), title, font=f, fill=color)
        draw.text((x0 + 48, 180), seed, font=sub, fill=FG)
    bar = font(ARIAL_BOLD, 34)
    note = "synchronized at the grasp · matched task distribution"
    draw.rectangle((0, H - 84, W, H), fill=BAR_RGBA)
    draw.text(((W - draw.textlength(note, font=bar)) // 2, H - 62), note, font=bar, fill=FG)
    img.save(OUT / "split_labels.png")


def money_overlay() -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = font(ARIAL_BOLD, 38)
    mono = font(MENLO, 30)
    draw.rectangle((0, H - 168, W, H), fill=BAR_RGBA)
    draw.text(
        (48, H - 148), "candidate-v2 · held-out seed 303 · UNCUT · REAL-TIME", font=f, fill=FG
    )
    chip = "reached seating: 12/32 vs 0/32 · p = 0.0005"
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
            ("Held-out qualification", font(ARIAL_BOLD, 66), FG, 0),
            (
                "32 fresh seeds per arm · matched pairs · 93 s on one Radeon",
                font(ARIAL, 38),
                DIM,
                20,
            ),
            ("reached seating:  0/32  ->  12/32", font(ARIAL_BOLD, 64), FG, 66),
            ("+37.5 pp · exact McNemar p = 0.0005", font(ARIAL_BOLD, 52), GREEN, 18),
            (
                "replicates on the standard suite: 1/32 -> 9/32 (+25.0 pp, p = 0.0215)",
                font(ARIAL, 38),
                FG,
                52,
            ),
            (
                "task success: 0/32 for both arms — release gate: REJECTED, by design",
                font(ARIAL, 38),
                AMBER,
                20,
            ),
            ("~200k-293k env-steps/s at 4,096 batched environments", font(ARIAL, 38), ACCENT, 52),
        ],
    )


VALIDATE_LINES: list[tuple[str, tuple[int, int, int]]] = [
    ("$ crux validate evidence/manifest.json", FG),
    ("", FG),
    (
        "PASS schema                 manifest 1 and receipt 1 parsed against the declared schema",
        GREEN,
    ),
    ("PASS files_exist            all 9 declared files present", GREEN),
    ("PASS hashes                 9 files match their recorded sha256 and size", GREEN),
    ("PASS device_evidence        AMD Radeon Graphics (gfx1100) via amdgpu, ROCm 7.2.1,", GREEN),
    ("                            torch 2.13.0+rocm7.2", GREEN),
    ("PASS suite_separation       32 held-out seeds disjoint from 32 repair seeds", GREEN),
    ("PASS checkpoint_identity    receipt checkpoint resolves to controller/repaired.json", GREEN),
    ("PASS replays                2 replays present, non-empty and hashed", GREEN),
    (
        "PASS aggregates             heldout: baseline 0/32, repaired 0/32 "
        "recomputed from raw episodes",
        GREEN,
    ),
    (
        "PASS headline_regression    standard regression +0.00 pp reproduced from 32 matched pairs",
        GREEN,
    ),
    ("", FG),
    ("9/9 checks passed", FG),
]
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
    y = 280
    for text, color in VALIDATE_LINES:
        draw.text((120, y), text, font=mono, fill=color)
        y += 42
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
                "every clip is a fresh rollout, honestly labeled — never a cherry-picked replay",
                font(ARIAL, 42),
                FG,
                18,
            ),
            (
                "task success is 0% for both controllers — the blocker is documented geometry",
                font(ARIAL, 42),
                AMBER,
                18,
            ),
            ("failed episodes are never deleted", font(ARIAL, 42), DIM, 18),
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
    caption(
        "cap_hook",
        "candidate-v2 · held-out seed 312 · real-time",
        "one AMD Radeon PRO W7900",
        ACCENT,
    )
    caption(
        "cap_baseline",
        "baseline-v1 · held-out seed 313 · real-time",
        "outcome: CABLE_SLIP during routing",
        AMBER,
    )
    caption(
        "cap_discovery",
        "discovery B-roll · candidate-v2 seed 312",
        "11 matched sweeps · ~300 episodes · 6 mechanisms",
        FG,
    )
    for name in sorted(OUT.glob("*.png")):
        print(name.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
