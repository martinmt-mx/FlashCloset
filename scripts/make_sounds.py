"""Synthesise the interface sounds instead of sourcing a sample pack.

The Frutiger Aero palette is a handful of primitives — a water droplet, a glass bell,
a bubble, a soft blip, all sitting in a short bright reverb. Those are cheap to build
from oscillators and envelopes, which means no licences, a few kilobytes on the wire,
and the ability to retune them by editing numbers rather than hunting for another file.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 44_100
OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "sounds"


def envelope(length: int, attack: float = 0.004, decay: float = 0.25, curve: float = 4.0) -> np.ndarray:
    t = np.linspace(0, length / RATE, length, endpoint=False)
    rise = np.clip(t / max(attack, 1e-5), 0, 1)
    fall = np.exp(-curve * t / max(decay, 1e-5))
    return rise * fall


def tone(freq: np.ndarray | float, length: int) -> np.ndarray:
    t = np.linspace(0, length / RATE, length, endpoint=False)
    phase = np.cumsum(np.full(length, freq) if np.isscalar(freq) else freq) / RATE
    return np.sin(2 * np.pi * phase) if not np.isscalar(freq) else np.sin(2 * np.pi * freq * t)


def glide(start: float, end: float, length: int, curve: float = 2.5) -> np.ndarray:
    t = np.linspace(0, 1, length, endpoint=False)
    return start + (end - start) * (1 - np.exp(-curve * t)) / (1 - np.exp(-curve))


def reverb(signal: np.ndarray, seconds: float = 0.28, mix: float = 0.3) -> np.ndarray:
    """A short bright tail. Aero interfaces always sounded like a glass room."""
    n = int(RATE * seconds)
    rng = np.random.default_rng(7)
    tail = rng.normal(0, 1, n) * np.exp(-6.0 * np.linspace(0, 1, n))
    wet = np.convolve(signal, tail)[: len(signal)]
    wet /= max(np.abs(wet).max(), 1e-9)
    return (1 - mix) * signal + mix * wet


def bell(root: float, length: int, partials=(1.0, 2.76, 5.40), gains=(1.0, 0.5, 0.22)) -> np.ndarray:
    out = np.zeros(length)
    for partial, gain in zip(partials, gains):
        out += gain * tone(root * partial, length) * envelope(length, decay=0.5 / partial, curve=3.2)
    return out


def droplet() -> np.ndarray:
    """Selecting: a water drop, which rises in pitch as the cavity closes."""
    n = int(RATE * 0.22)
    body = tone(glide(520, 1500, n, curve=5.0), n) * envelope(n, decay=0.10, curve=5.0)
    return reverb(body * 0.9, mix=0.35)


def wear() -> np.ndarray:
    """Putting a garment on: a two-note glass bell, upward."""
    n = int(RATE * 0.55)
    out = bell(784, n) * 0.6                      # G5
    late = np.zeros(n)
    offset = int(RATE * 0.07)
    late[offset:] = bell(1046, n - offset) * 0.5  # C6
    return reverb(out + late, mix=0.34)


def remove() -> np.ndarray:
    """Taking it off: a bubble pop, noise burst over a low thump."""
    n = int(RATE * 0.18)
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, n) * envelope(n, decay=0.03, curve=9.0)
    thump = tone(glide(420, 140, n, curve=6.0), n) * envelope(n, decay=0.07, curve=7.0)
    return reverb(0.35 * noise + 0.8 * thump, mix=0.22)


def save() -> np.ndarray:
    """Saving: a small sparkle arpeggio."""
    notes = [1046, 1318, 1568, 2093]              # C6 E6 G6 C7
    n = int(RATE * 0.75)
    out = np.zeros(n)
    for index, freq in enumerate(notes):
        start = int(RATE * 0.055 * index)
        out[start:] += bell(freq, n - start) * (0.5 - 0.06 * index)
    return reverb(out, seconds=0.4, mix=0.4)


def open_sheet() -> np.ndarray:
    """Opening a panel: a soft blip, barely there."""
    n = int(RATE * 0.16)
    body = tone(glide(440, 700, n), n) * envelope(n, decay=0.08, curve=6.0)
    return reverb(body * 0.55, mix=0.25)


def nope() -> np.ndarray:
    """Refusing an action: falling, gentle, not a buzzer."""
    n = int(RATE * 0.30)
    body = tone(glide(420, 250, n, curve=3.0), n) * envelope(n, decay=0.16, curve=4.0)
    detune = tone(glide(424, 252, n, curve=3.0), n) * envelope(n, decay=0.16, curve=4.0)
    return reverb(0.5 * (body + detune) * 0.7, mix=0.25)


def write(name: str, signal: np.ndarray) -> None:
    peak = np.abs(signal).max()
    normalised = signal / peak * 0.85 if peak else signal

    # Fade the last few milliseconds so nothing ends on a click.
    tail = min(len(normalised), int(RATE * 0.01))
    normalised[-tail:] *= np.linspace(1, 0, tail)

    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes((normalised * 32767).astype("<i2").tobytes())
    size = (OUT / f"{name}.wav").stat().st_size
    print(f"  {name:11s} {len(normalised) / RATE:.2f}s  {size / 1024:5.1f} KB")


if __name__ == "__main__":
    for name, maker in [
        ("select", droplet), ("wear", wear), ("remove", remove),
        ("save", save), ("open", open_sheet), ("nope", nope),
    ]:
        write(name, maker())
