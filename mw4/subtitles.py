"""Lokale englische Spracherkennung + deutsche TikTok-Untertitel.

Keine bezahlte API.

Pipeline:
1. OpenAI Whisper läuft lokal auf dem GitHub Runner.
2. Englische Sprache wird transkribiert.
3. Helsinki-NLP übersetzt lokal nach Deutsch.
4. Der deutsche Text wird in kurze TikTok-Untertitel zerlegt.
5. Timings werden auf die originale Sprache verteilt.

Die visuelle Position/Schrift wird anschließend in bot.py über ASS definiert.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


_WHISPER_MODEL = None
_TRANSLATOR_MODEL = None
_TRANSLATOR_TOKENIZER = None


def _clean(text: str) -> str:
    text = re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()

    text = re.sub(
        r"^[-–—]+\s*",
        "",
        text,
    )

    return text


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
            "Whisper model:",
            model_name,
        )

        _WHISPER_MODEL = (
            whisper.load_model(
                model_name
            )
        )

    return _WHISPER_MODEL


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
        )

        if not model_name:
            model_name = (
                "Helsinki-NLP/"
                "opus-mt-en-de"
            )

        print(
            "MW4 subtitles | "
            "Translation model:",
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


def transcribe(
    path: Path,
) -> list[dict[str, Any]]:
    model = _load_whisper()

    result = model.transcribe(
        str(path),
        language="en",
        task="transcribe",
        fp16=False,
        verbose=False,
        temperature=0,
        condition_on_previous_text=False,
    )

    segments: list[
        dict[str, Any]
    ] = []

    for raw in result.get(
        "segments",
        [],
    ):
        text = _clean(
            str(
                raw.get(
                    "text",
                    "",
                )
            )
        )

        if not text:
            continue

        no_speech = float(
            raw.get(
                "no_speech_prob",
                0.0,
            )
            or 0.0
        )

        if no_speech >= 0.80:
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

        end = max(
            start + 0.35,
            float(
                raw.get(
                    "end",
                    start + 0.35,
                )
                or (
                    start + 0.35
                )
            ),
        )

        segments.append(
            {
                "start": start,
                "end": end,
                "text": text,
            }
        )

    return segments


def translate_english_to_german(
    texts: list[str],
) -> list[str]:
    if not texts:
        return []

    (
        tokenizer,
        model,
    ) = _load_translator()

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
    )

    translated = (
        tokenizer.batch_decode(
            generated,
            skip_special_tokens=True,
        )
    )

    return [
        _clean(text)
        for text in translated
    ]


def _split_words(
    text: str,
    max_words: int = 4,
    max_chars: int = 28,
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
                " ".join(current)
            )

            current = [
                word
            ]

        else:
            current.append(
                word
            )

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
                " ".join(current)
            )

            current = []

    if current:
        chunks.append(
            " ".join(current)
        )

    return [
        chunk
        for chunk in chunks
        if chunk
    ]


def build_german_subtitles(
    path: Path,
) -> list[dict[str, Any]]:
    """Erzeugt kurze deutsche TikTok-Untertitel."""

    segments = transcribe(
        path
    )

    if not segments:
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

    for segment, text in zip(
        segments,
        german,
    ):
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

        weight_sum = sum(
            weights
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
                < 0.30
            ):
                chunk_end = min(
                    end,
                    cursor + 0.30,
                )

            if chunk_end > cursor:
                output.append(
                    {
                        "start": cursor,
                        "end": chunk_end,
                        "text": chunk,
                    }
                )

            cursor = chunk_end

    # Sicherheit:
    # Keine sich überschneidenden
    # Untertitel-Events.

    for index in range(
        1,
        len(output),
    ):
        previous = output[
            index - 1
        ]

        current = output[
            index
        ]

        if (
            current["start"]
            < previous["end"]
        ):
            current[
                "start"
            ] = previous[
                "end"
            ]

        current[
            "end"
        ] = max(
            current["end"],
            current["start"]
            + 0.25,
        )

    return output
