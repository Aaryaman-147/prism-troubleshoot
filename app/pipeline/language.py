"""
Non-English complaint support. Detection is local and free; translation is
one small LLM call, cached per distinct text.

needs_translation():
  - any non-Latin script (Devanagari, Korean, CJK, Arabic, Cyrillic, ...), or
  - a Latin-script complaint of 5+ words with no common English function
    words (Spanish, romanized Hinglish, ...).
A false positive costs one call that returns the text unchanged as English.
"""
import re

from app.core.llm_client import TokenUsage, generate_json_async

_NON_LATIN = re.compile(r"[\u0370-\u03FF\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0900-\u0DFF"
                        r"\u0E00-\u0E7F\u1100-\u11FF\u3040-\u30FF\u3130-\u318F\u4E00-\u9FFF\uAC00-\uD7AF]")
_EN_FUNCTION = {"the", "a", "an", "my", "is", "it", "its", "and", "or", "to", "of", "in", "on", "at", "for",
                "when", "after", "before", "with", "not", "no", "i", "me", "this", "that", "keeps", "won't",
                "doesn't", "can't", "dies", "are", "was", "gets", "get", "very", "too", "so", "but", "from",
                "up", "down", "off", "out", "how", "why", "what", "does", "do", "have", "has", "will", "be"}
_WORD = re.compile(r"[A-Za-z']+")
_CACHE: dict[str, tuple[str, str, TokenUsage]] = {}

PROMPT = """Detect the language of this device-support complaint and translate it into
natural English. Keep product and model names (e.g. Nexa X1, Galaxy) unchanged.
If it is already English, return it unchanged with language "English".

Complaint: "{q}"

Return ONLY JSON: {{"language": "<language name in English>", "english": "<translation>"}}"""


# Common English + device-support vocabulary. Short technical phrases often
# have no function words ("fingerprint sensor stopped recognizing thumb"),
# which the first version wrongly sent for translation.
_EN_LEXICON = _EN_FUNCTION | set("""
phone device tablet screen display battery charge charger charging power camera photo picture video
app apps setting settings sensor fingerprint face unlock thumb finger touch tap swipe gesture button
key keyboard language notification call calls sound speaker mic microphone volume audio music wifi
bluetooth network signal sim data internet mobile hotspot nfc pay payment card storage memory update
software system restart reboot reset mode safe slow fast lag lags laggy freeze frozen crash crashes
hang stuck black blank white dark bright brightness flicker flickers flickering flash flashes glitch
broken cracked shattered water damage hot heat overheat warm cold drain drains dies dead stop stopped
working work won wont doesnt cant keep keeps turn turns off on open close closes start starts
recognize recognizing recognise connect connected connection disconnect disconnects disconnecting
drop drops dropping delay delayed late wrong error issue problem help bad please fix new old after
since every time day minute minutes hour hours second seconds week month random randomly itself
compass gps location map clock time zone alarm watch smartwatch car headphones earbuds case cable
port usb slower faster than max speed full small big inner outer cover fold unusable fine ok again
only just all some any more less other also still even much many same first last one two three four
five ten icon icons light lit dim loud quiet noise noisy blurry grainy clear top bottom left right
half part whole side back front load loads loading show shows showing look looks seem seems
touchscreen response respond responsive unresponsive input inputs output delay shortcut circle floating
carrier deactivated activation distorted warped unboxing box ring rings unfold folded outer
terrible awful life quick quickly flashing stop why does die dying poor
""".split())
# Product / brand tokens carry no language signal ("Nexa X1 touchscreen slow
# response" was sent for translation because "Nexa" and "X" counted as non-English).
_NEUTRAL = {"nexa", "techcorp", "galaxy", "samsung", "ultra", "pro", "plus", "lite", "gmail", "qr"}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s", "ly"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def needs_translation(query: str) -> bool:
    q = str(query or "")
    if _NON_LATIN.search(q):
        return True
    words = [w.lower() for w in _WORD.findall(q) if len(w) > 1 and w.lower() not in _NEUTRAL]
    if len(words) < 4 or any(w in _EN_FUNCTION for w in words):
        return False
    english = sum(1 for w in words if w in _EN_LEXICON or _stem(w) in _EN_LEXICON)
    # Hinglish keeps English loanwords ("phone", "screen") but they stay a
    # minority (~30-38% in real examples); an English phrase is mostly English words.
    return english / len(words) < 0.4


async def translate_query(query: str) -> tuple[str, str, TokenUsage]:
    key = " ".join(query.split())
    if key in _CACHE:
        lang, en, _ = _CACHE[key]
        return lang, en, TokenUsage()
    data, usage = await generate_json_async(PROMPT.format(q=query), max_output_tokens=300,
                                            required_keys=("english",))
    lang = str(data.get("language") or "").strip() or "Unknown"
    en = str(data.get("english") or "").strip() or query
    _CACHE[key] = (lang, en, usage)
    print(f"[translation] {lang}: {query!r} -> {en!r}")
    return lang, en, usage
