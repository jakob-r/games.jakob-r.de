"""AI guesser for Emoji Charades: asks an LLM (OpenRouter) to guess from the visible hints only."""

from __future__ import annotations

import json
import logging
from typing import Any

from games_platform.core.llm import LlmError, chat

logger = logging.getLogger(__name__)

AI_PLAYER_ID = "ai:emoji-charades"
AI_PLAYER_NAME = "AI 🤖"
AI_PLAYER_COLOR = "#7c3aed"
MAX_GUESS_CHARS = 80
MAX_PROMPT_GUESSES = 30

CATEGORY_NAMES = {
    "object": "object",
    "food": "food",
    "animal": "animal",
    "brand": "brand",
    "person": "famous person",
    "movie": "movie title",
    "tv_show": "TV show",
    "quote": "famous quote or saying",
}
# What a complete answer looks like per category (the explained term is often not one word).
CATEGORY_ANSWER_HINTS = {
    "quote": (
        "This is NOT a single word: it is a whole well-known phrase, such as a proverb, "
        "idiom, saying or famous movie line. Each emoji sentence may stand for part of it. "
        "Answer with the complete phrase as people commonly say it."
    ),
    "movie": "Answer with the full movie title as commonly known in that language.",
    "tv_show": "Answer with the full TV show title as commonly known in that language.",
    "person": "Answer with the person's full name.",
    "brand": "Answer with the brand name.",
}
LANGUAGE_NAMES = {"de": "German", "en": "English"}

SYSTEM_PROMPT = (
    "You are a player in Emoji Charades. Another player explains a secret term using only "
    "emoji sentences. The first sentence is the main concept; later sentences add details. "
    "Emojis may stand for their meaning, a sound-alike word or a syllable. "
    "The term can be a single word, a name, a title or a whole phrase. "
    "Reply with exactly one guess: just the term itself, no explanation, no quotes, no emoji."
)


def hint_signature(view: dict[str, Any]) -> str:
    """What the AI reacts to: a new guess is only worth asking for when this changes."""
    word = view.get("word") or {}
    return json.dumps(
        [view.get("round_number"), word.get("category"), view.get("sentences") or []],
        ensure_ascii=False,
    )


def has_hints(view: dict[str, Any]) -> bool:
    return any(len(s) > 0 for s in view.get("sentences") or [])


def build_messages(view: dict[str, Any]) -> list[dict[str, str]]:
    """Build the prompt from the guesser's view (never contains the answer)."""
    language = LANGUAGE_NAMES.get(str(view.get("language")), "German")
    category = (view.get("word") or {}).get("category")
    lines = [f"The secret term is in {language}; answer in {language}."]
    if category:
        lines.append(f"It is a {CATEGORY_NAMES.get(category, category)}.")
        if hint := CATEGORY_ANSWER_HINTS.get(category):
            lines.append(hint)
    lines.append("Emoji sentences:")
    for i, sentence in enumerate(view.get("sentences") or [], start=1):
        if sentence:
            lines.append(f"{i}. {' '.join(sentence)}")
    wrong = [
        str(g["text"])
        for g in view.get("guesses") or []
        if g.get("text") and not g.get("correct")
    ][-MAX_PROMPT_GUESSES:]
    if wrong:
        lines.append("Already guessed (wrong, do not repeat): " + "; ".join(wrong))
    lines.append("Your guess:")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


def clean_guess(raw: str) -> str:
    """Take the first non-empty line and strip quotes, labels and trailing punctuation."""
    line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    for prefix in ("guess:", "answer:", "antwort:", "tipp:"):
        if line.lower().startswith(prefix):
            line = line[len(prefix) :].strip()
    line = line.rstrip(".!").strip("\"'„“”‚‘’«»*`").rstrip(".!").strip()
    return line[:MAX_GUESS_CHARS]


async def ask_guess(view: dict[str, Any]) -> str | None:
    try:
        raw = await chat(build_messages(view))
    except LlmError as e:
        logger.warning("AI guess failed: %s", repr(e))
        return None
    guess = clean_guess(raw)
    return guess or None
