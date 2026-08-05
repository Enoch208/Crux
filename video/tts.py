from __future__ import annotations

import json
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import certifi

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

ROOT = Path(__file__).parent
AUDIO_DIR = ROOT / "work" / "audio"
ENV_PATH = ROOT / ".env.local"
API_BASE = "https://api.elevenlabs.io"
OUTPUT_FORMAT = "mp3_44100_128"
VOICE_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.8,
    "style": 0.3,
    "use_speaker_boost": True,
}
MAX_ATTEMPTS = 4
BACKOFF_S = 8.0

NARRATION: dict[str, str] = {
    "s01_intro": (
        "Cable routing looks trivial — until you try it with a robot. "
        "Contact makes everything fragile: friction, tension, alignment. "
        "One physical detail changes, and a working controller quietly stops working."
    ),
    "s02_hook": (
        "CRUX is a harness that finds those failures, repairs them, "
        "and proves the repair — end to end, on one AMD Radeon GPU."
    ),
    "s03_baseline": (
        "This is the baseline controller, on a fresh held-out seed — "
        "conditions it has never seen. "
        "Watch the cable during routing. "
        "The strand slips out of the grip, and the episode dies. "
        "Across thirty-two held-out episodes, the baseline reached "
        "the final seating stage exactly zero times."
    ),
    "s04_discovery": (
        "CRUX ran sixteen matched, batched sweeps and an instrumented post-mortem — "
        "about nine hundred batched episodes on the Radeon. "
        "Eight failure mechanisms fell out. "
        "Diagonal transport wedged the strand at the gate — "
        "so transport became lift, then translate. "
        "Release recoil threw the connector — so the policy grips the connector link. "
        "And single-shot regrasps closed on air — "
        "so the controller now re-observes, and retries. "
        "Every repair is named, mechanism-backed, and tested under matched conditions."
    ),
    "s04b_scale": (
        "Sixteen environments run here side by side — the sweeps ran up to "
        "four thousand and ninety-six. One Radeon, one hundred percent busy, "
        "sampled live during the campaign."
    ),
    "s05_sidebyside": (
        "The same held-out seed. The same scene. Synchronized at the grasp. "
        "On the left, the baseline misses its regrasp at the second clip — and dies. "
        "On the right, the repaired controller re-observes, retries, and recovers — "
        "and keeps going."
    ),
    "s06_results": (
        "The numbers, on thirty-two virgin seeds per arm: "
        "zero of thirty-two, against seventeen of thirty-two. "
        "Plus fifty-three percentage points — exact McNemar p, below ten to the minus four. "
        "It replicates on a second, independent suite, at plus thirty-four. "
        "The final repair's increment is itself significant. "
        "And task success is still zero for every controller — "
        "our own release gate refused to certify the candidate. "
        "That refusal is the system working."
    ),
    "s07_validator": (
        "Every number in this video is recomputed from raw, hash-verified episode records — "
        "on CPU, in seconds. Change one byte of the evidence, and the validator fails."
    ),
    "s08_honesty": (
        "What we can't claim, we don't. "
        "The cable is an articulated chain, not a deformable body. "
        "Contact rollouts on this stack are not reproducible — we measured the divergence. "
        "So every clip you've seen is a fresh rollout, honestly labeled — "
        "never a cherry-picked replay."
    ),
    "s09_money": (
        "One uncut episode, in real time. "
        "Grasp. Route clip one. Route clip two. Regrasp the connector. Align. Insert. "
        "Seating verification — a stage the baseline never reached. "
        "Clone the repo. Run one command. Check us."
    ),
    "s10_outro": ("CRUX. Reliability engineering for robot manipulation — on one Radeon."),
}


def env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def post(url: str, payload: dict[str, object], api_key: str) -> bytes:
    body = json.dumps(payload).encode()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            data=body,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=180, context=SSL_CONTEXT) as response:
                data: bytes = response.read()
                return data
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            if error.code == 429 and attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_S * attempt)
                continue
            raise RuntimeError(f"{url} -> HTTP {error.code}: {detail}") from error
    raise RuntimeError(f"{url}: retries exhausted")


def duration_s(path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(probe.stdout.strip())


def synthesize(scene: str, text: str, settings: dict[str, str]) -> Path:
    target = AUDIO_DIR / f"{scene}.mp3"
    if target.exists():
        return target
    audio = post(
        f"{API_BASE}/v1/text-to-speech/{settings['ELEVENLABS_VOICE_ID']}"
        f"?output_format={OUTPUT_FORMAT}",
        {
            "text": text,
            "model_id": settings["ELEVENLABS_MODEL"],
            "voice_settings": VOICE_SETTINGS,
        },
        settings["ELEVENLABS_API_KEY"],
    )
    target.write_bytes(audio)
    return target


def compose_music(length_ms: int, settings: dict[str, str]) -> Path:
    target = AUDIO_DIR / "music.mp3"
    if target.exists():
        return target
    prompt = (
        "Minimal, understated electronic underscore for a technology documentary. "
        "Slow steady pulse, warm pads, no melody, no drums drama, consistent energy."
    )
    try:
        audio = post(
            f"{API_BASE}/v1/music",
            {"prompt": prompt, "music_length_ms": length_ms},
            settings["ELEVENLABS_API_KEY"],
        )
    except RuntimeError as error:
        if "402" not in str(error):
            raise
        audio = post(
            f"{API_BASE}/v1/sound-generation",
            {"text": prompt, "duration_seconds": min(30, length_ms // 1000)},
            settings["ELEVENLABS_API_KEY"],
        )
    target.write_bytes(audio)
    return target


def main() -> int:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    settings = env()
    only = set(sys.argv[1:])
    manifest: dict[str, float] = {}
    for scene, text in NARRATION.items():
        if only and scene not in only and "music" not in only:
            continue
        if only and scene not in only:
            continue
        path = synthesize(scene, text, settings)
        manifest[scene] = round(duration_s(path), 2)
        print(f"  {scene}: {manifest[scene]:.2f}s", flush=True)
    existing = AUDIO_DIR / "manifest.json"
    merged: dict[str, float] = {}
    if existing.exists():
        merged = json.loads(existing.read_text())
    merged.update(manifest)
    existing.write_text(json.dumps(merged, indent=2))
    if "music" in only:
        total_ms = int((sum(merged.values()) + 45.0 + 10.0) * 1000)
        path = compose_music(total_ms, settings)
        print(f"  music: {duration_s(path):.2f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
