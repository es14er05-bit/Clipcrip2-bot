"""Robuste lokale EN->DE TikTok-Untertitel für MW4.

Ziel:
- nur echte, ausreichend sichere Sprache untertiteln
- Whisper-Halluzinationen konsequent verwerfen
- unvollständige Fragmente zusammenfassen
- Übersetzungs-Müll lieber NICHT anzeigen
- kurze TikTok-Chunks erzeugen
- keine bezahlte API

Wichtig:
Wenn ein Sprachabschnitt nicht zuverlässig verstanden/übersetzt
werden kann, wird absichtlich KEIN Untertitel eingeblendet.
Das ist besser als falscher oder peinlicher Text im fertigen TikTok.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


_WHISPER_MODEL = None
_TRANSLATOR_MODEL = None
_TRANSLATOR_TOKENIZER = None


# ============================================================
# TEXT CLEANING
# ============================================================

def _clean(text: str) -> str:
    text = str(
        text or ""
    )

    text = text.replace(
        "\n",
        " ",
    )

    text = text.replace(
        "\r",
        " ",
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    text = re.sub(
        r"^[-–—]+\s*",
        "",
        text,
    )

    return text


def _word_count(
    text: str,
) -> int:
    return len(
        re.findall(
            r"[A-Za-zÄÖÜäöüß0-9']+",
            text,
        )
    )


def _looks_like_real_speech(
    text: str,
) -> bool:
    text = _clean(
        text
    )

    if not text:
        return False

    if len(text) < 3:
        return False

    if len(text) > 220:
        return False

    words = re.findall(
        r"[A-Za-z']+",
        text,
    )

    if len(words) < 2:
        return False

    letters = sum(
        character.isalpha()
        for character in text
    )

    if (
        letters
        / max(
            len(text),
            1,
        )
        < 0.45
    ):
        return False

    lowered = [
        word.lower()
        for word in words
    ]

    # Whisper-Halluzinationen enthalten
    # häufig dasselbe Wort mehrfach.
    for index in range(
        len(lowered) - 2
    ):
        if (
            lowered[index]
            == lowered[index + 1]
            == lowered[index + 2]
        ):
            return False

    return True


# ============================================================
# WHISPER
# ============================================================

def _load_whisper():
    global _WHISPER_MODEL

    if _WHISPER_MODEL is None:
        import whisper

        model_name = (
            os.environ.get(
                "MW4_WHISPER_MODEL",
                "base.en",
            )
            .strip()
            or "base.en"
        )

        print(
            "MW4 subtitles | "
            "Whisper:",
            model_name,
        )

        _WHISPER_MODEL = (
            whisper.load_model(
                model_name
            )
        )

    return _WHISPER_MODEL


def _merge_segments(
    segments: list[
        dict[str, Any]
    ],
) -> list[
    dict[str, Any]
]:
    """Fasst Whisper-Fragmente zu sinnvolleren Phrasen zusammen."""

    if not segments:
        return []

    merged: list[
        dict[str, Any]
    ] = []

    current = dict(
        segments[0]
    )

    for segment in segments[1:]:
        gap = (
            float(
                segment["start"]
            )
            - float(
                current["end"]
            )
        )

        combined_text = (
            str(
                current["text"]
            )
            + " "
            + str(
                segment["text"]
            )
        )

        combined_duration = (
            float(
                segment["end"]
            )
            - float(
                current["start"]
            )
        )

        can_merge = (
            gap <= 0.40
            and _word_count(
                combined_text
            ) <= 18
            and combined_duration <= 6.0
        )

        if can_merge:
            current[
                "text"
            ] = _clean(
                combined_text
            )

            current[
                "end"
            ] = float(
                segment["end"]
            )

        else:
            merged.append(
                current
            )

            current = dict(
                segment
            )

    merged.append(
        current
    )

    return merged


def transcribe(
    path: Path,
) -> list[
    dict[str, Any]
]:
    model = _load_whisper()

    result = model.transcribe(
        str(path),

        language="en",

        task="transcribe",

        fp16=False,

        verbose=False,

        temperature=0,

        condition_on_previous_text=False,

        compression_ratio_threshold=2.4,

        logprob_threshold=-0.75,

        no_speech_threshold=0.50,

        initial_prompt=(
            "Call of Duty Modern Warfare 4 "
            "multiplayer gameplay commentary. "
            "Gaming vocabulary may include "
            "sniper, pistol, movement, mantling, "
            "clutch, no-scope, kill, enemy, "
            "weapon and multiplayer."
        ),
    )

    accepted: list[
        dict[str, Any]
    ] = []

    for raw in result.get(
        "segments",
        [],
    ):
        text = _clean(
            raw.get(
                "text",
                "",
            )
        )

        if not _looks_like_real_speech(
            text
        ):
            continue

        no_speech = float(
            raw.get(
                "no_speech_prob",
                0.0,
            )
            or 0.0
        )

        avg_logprob = float(
            raw.get(
                "avg_logprob",
                -99.0,
            )
            or -99.0
        )

        compression_ratio = float(
            raw.get(
                "compression_ratio",
                0.0,
            )
            or 0.0
        )

        # Strenger als Whisper selbst:
        # Unsicher = lieber kein Untertitel.
        if no_speech > 0.45:
            continue

        if avg_logprob < -0.72:
            continue

        if compression_ratio > 2.35:
            continue

        start = max(
            0.0,
            float(
                raw.get(
                    "start",
                    0.0,
                )
                or 0.0
            ),
        )

        end = float(
            raw.get(
                "end",
                start + 0.5,
            )
            or (
                start + 0.5
            )
        )

        end = max(
            start + 0.35,
            end,
        )

        # Winzige Fragmente sind für TikTok
        # praktisch nie hilfreich.
        if (
            end - start
            < 0.35
        ):
            continue

        accepted.append(
            {
                "start": start,
                "end": end,
                "text": text,
            }
        )

    return _merge_segments(
        accepted
    )


# ============================================================
# EN -> DE
# ============================================================

def _load_translator():
    global _TRANSLATOR_MODEL
    global _TRANSLATOR_TOKENIZER

    if (
        _TRANSLATOR_MODEL is None
        or _TRANSLATOR_TOKENIZER is None
    ):
        from transformers import (
            AutoModelForSeq2SeqLM,
            AutoTokenizer,
        )

        model_name = (
            os.environ.get(
                "MW4_TRANSLATION_MODEL",
                (
                    "Helsinki-NLP/"
                    "opus-mt-en-de"
                ),
            )
            .strip()
            or (
                "Helsinki-NLP/"
                "opus-mt-en-de"
            )
        )

        print(
            "MW4 subtitles | "
            "Translator:",
            model_name,
        )

        _TRANSLATOR_TOKENIZER = (
            AutoTokenizer
            .from_pretrained(
                model_name
            )
        )

        _TRANSLATOR_MODEL = (
            AutoModelForSeq2SeqLM
            .from_pretrained(
                model_name
            )
        )

    return (
        _TRANSLATOR_TOKENIZER,
        _TRANSLATOR_MODEL,
    )


def translate_english_to_german(
    texts: list[str],
) -> list[str]:
    if not texts:
        return []

    tokenizer, model = (
        _load_translator()
    )

    encoded = tokenizer(
        texts,

        return_tensors="pt",

        padding=True,

        truncation=True,

        max_length=256,
    )

    generated = model.generate(
        **encoded,

        max_new_tokens=128,

        num_beams=4,

        do_sample=False,

        early_stopping=True,
    )

    translated = (
        tokenizer.batch_decode(
            generated,
            skip_special_tokens=True,
        )
    )

    return [
        _clean(
            text
        )
        for text in translated
    ]


# ============================================================
# ÜBERSETZUNGS-QC
# ============================================================

def _translation_is_safe(
    source: str,
    target: str,
) -> bool:
    source = _clean(
        source
    )

    target = _clean(
        target
    )

    if not target:
        return False

    if len(target) < 3:
        return False

    if len(target) > 160:
        return False

    source_words = max(
        1,
        _word_count(
            source
        ),
    )

    target_words = (
        _word_count(
            target
        )
    )

    if target_words < 2:
        return False

    ratio = (
        target_words
        / source_words
    )

    if ratio < 0.40:
        return False

    if ratio > 2.60:
        return False

    # Beispiel des fehlerhaften B-Videos:
    # "I. ENTWICKLUNG DER"
    if re.match(
        r"^\s*[IVXLCDM]+\.\s+",
        target,
        flags=re.IGNORECASE,
    ):
        return False

    # Ebenso nummerierte Fragmente,
    # die wie Listen/OCR statt Sprache wirken.
    if re.match(
        r"^\s*\d+\.\s+[A-ZÄÖÜ]",
        target,
    ):
        return False

    alpha = [
        character
        for character in target
        if character.isalpha()
    ]

    if (
        len(alpha) >= 8
        and target.upper()
        == target
    ):
        return False

    # Unvollständige Marian-Fragmente
    # lieber komplett auslassen.
    bad_endings = (
        " der",
        " die",
        " das",
        " den",
        " dem",
        " des",
        " ein",
        " eine",
        " einen",
        " einem",
        " einer",
        " eines",
        " von",
        " für",
        " mit",
        " und",
        " oder",
        " zu",
        " im",
        " am",
        " auf",
    )

    lowered = target.lower()

    if lowered.endswith(
        bad_endings
    ):
        return False

    words = re.findall(
        r"[A-Za-zÄÖÜäöüß']+",
        lowered,
    )

    for index in range(
        len(words) - 2
    ):
        if (
            words[index]
            == words[index + 1]
            == words[index + 2]
        ):
            return False

    return True


# ============================================================
# TIKTOK CHUNKS
# ============================================================

def _split_words(
    text: str,

    max_words: int = 4,

    max_chars: int = 27,
) -> list[str]:
    words = text.split()

    chunks: list[str] = []

    current: list[str] = []

    for word in words:
        proposed = " ".join(
            current + [word]
        )

        if (
            current
            and (
                len(current)
                >= max_words
                or len(proposed)
                > max_chars
            )
        ):
            chunks.append(
                " ".join(
                    current
                )
            )

            current = [
                word
            ]

        else:
            current.append(
                word
            )

        # Satzzeichen eignen sich als
        # natürlicher Untertitelwechsel.
        if (
            current
            and current[-1].endswith(
                (
                    ".",
                    "!",
                    "?",
                    ",",
                )
            )
            and len(current) >= 2
        ):
            chunks.append(
                " ".join(
                    current
                )
            )

            current = []

    if current:
        chunks.append(
            " ".join(
                current
            )
        )

    return [
        chunk
        for chunk in chunks
        if chunk
    ]


# ============================================================
# FINAL
# ============================================================

def build_german_subtitles(
    path: Path,
) -> list[
    dict[str, Any]
]:
    segments = transcribe(
        path
    )

    if not segments:
        print(
            "MW4 subtitles | "
            "Keine ausreichend sichere "
            "Sprache erkannt."
        )

        return []

    german = (
        translate_english_to_german(
            [
                segment["text"]
                for segment in segments
            ]
        )
    )

    output: list[
        dict[str, Any]
    ] = []

    rejected = 0

    for segment, text in zip(
        segments,
        german,
    ):
        source_text = (
            segment["text"]
        )

        if not _translation_is_safe(
            source_text,
            text,
        ):
            rejected += 1

            print(
                "MW4 subtitles | "
                "Unsichere Übersetzung "
                "verworfen:",
                repr(source_text),
                "->",
                repr(text),
            )

            continue

        chunks = _split_words(
            text
        )

        if not chunks:
            continue

        start = float(
            segment["start"]
        )

        end = float(
            segment["end"]
        )

        total = max(
            0.45,
            end - start,
        )

        weights = [
            max(
                1,
                len(
                    chunk.replace(
                        " ",
                        "",
                    )
                ),
            )
            for chunk in chunks
        ]

        weight_sum = max(
            1,
            sum(weights),
        )

        cursor = start

        for index, (
            chunk,
            weight,
        ) in enumerate(
            zip(
                chunks,
                weights,
            )
        ):
            if (
                index
                == len(chunks) - 1
            ):
                chunk_end = end

            else:
                share = (
                    total
                    * (
                        weight
                        / weight_sum
                    )
                )

                chunk_end = min(
                    end,
                    cursor
                    + max(
                        0.45,
                        share,
                    ),
                )

            if (
                chunk_end
                - cursor
                >= 0.30
            ):
                output.append(
                    {
                        "start": cursor,
                        "end": chunk_end,
                        "text": chunk,
                    }
                )

            cursor = chunk_end

    # Keine Überlappungen.
    cleaned: list[
        dict[str, Any]
    ] = []

    for event in output:
        event = dict(
            event
        )

        if cleaned:
            event[
                "start"
            ] = max(
                float(
                    event["start"]
                ),
                float(
                    cleaned[-1]["end"]
                ),
            )

        if (
            float(
                event["end"]
            )
            - float(
                event["start"]
            )
            < 0.25
        ):
            continue

        cleaned.append(
            event
        )

    print(
        "MW4 subtitles |",
        len(cleaned),
        "TikTok-Chunks erzeugt |",
        rejected,
        "unsichere Übersetzungen verworfen",
    )

    return cleaned