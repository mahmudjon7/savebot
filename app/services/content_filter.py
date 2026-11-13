"""Content policy for downloads (pure Python, no model).

Blocks, before a video is downloaded:
  * age_restricted  - yt-dlp reports age_limit >= 18
  * adult           - sexual content
  * other_religion  - content of religions other than Islam
  * customs         - content against local customs (starter list: LGBT propaganda,
                      gambling, fortune-telling) - edit to taste

Matching is done on the video's title, tags, categories, channel and description
(and on the user's message text / URL words).  Terms live in DEFAULT_TERMS below and
in an optional text file (one `category|term` per line) that admins can edit without
touching code.  It is a keyword filter: it catches the obvious, not everything
(misspellings, other languages, videos with an innocent title).  Matched terms are for
logs only and are never shown to users.

Term syntax: lowercase; `word*` = any word starting with "word"; spaces = a phrase.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

ADULT = "adult"
AGE_RESTRICTED = "age_restricted"
OTHER_RELIGION = "other_religion"
CUSTOMS = "customs"
ALL_CATEGORIES: Tuple[str, ...] = (ADULT, AGE_RESTRICTED, OTHER_RELIGION, CUSTOMS)

# Weak fields (long free text) must match this many DISTINCT terms before they block.
WEAK_MIN_HITS: Dict[str, int] = {ADULT: 1, OTHER_RELIGION: 2, CUSTOMS: 2}
STRONG_FIELDS = ("title", "fulltitle", "tags", "categories", "uploader", "channel", "playlist_title")
DESCRIPTION_CHARS = 1000

DEFAULT_TERMS: Dict[str, List[str]] = {
    ADULT: [
        # English
        "porn*", "xxx", "nsfw", "hentai", "erotic*", "nude", "nudes", "nudity", "naked", "striptease",
        "strip tease", "stripper*", "sex tape", "sex video*", "sex scene*", "sexy*", "milf", "blowjob",
        "orgasm*", "fetish*", "onlyfans", "only fans", "pornhub", "xvideos", "xnxx", "xhamster", "redtube",
        "brazzers", "playboy", "18+", "adults only", "adult only",
        # Russian
        "порно*", "порнух*", "секс видео", "секс-видео", "эротик*", "эротическ*", "голая", "голые", "голый",
        "обнажен*", "обнажён*", "стриптиз*", "интим видео", "онлифанс", "хентай", "минет", "оргазм*",
        "проститут*", "шлюх*",
        # Uzbek (Latin)
        "porno*", "seks video*", "seksi*", "yalang'och*", "yalangoch*", "erotik*", "shahvoniy", "shahvat*",
        "behayo*", "fohisha*", "fahsh*", "intim video*",
        # Uzbek (Cyrillic)
        "ялангоч*", "шаҳвоний", "шаҳват*", "бехаё*", "фоҳиша*", "эротик*",
    ],
    OTHER_RELIGION: [
        # English (exact words, to avoid names like Churchill / Christian Bale)
        "church", "churches", "cathedral", "christianity", "christians", "bible", "biblical", "gospel",
        "jesus", "pastor", "pastors", "baptism", "missionary", "missionaries", "jehovah", "buddha",
        "buddhism", "buddhist", "buddhists", "hindu", "hinduism", "synagogue", "rabbi", "crucifix",
        "rosary", "satanic*", "satanism",
        # Russian
        "церков*", "христианств*", "христиан*", "библи*", "евангели*", "иисус*", "пастор*", "баптист*",
        "иегов*", "будда*", "буддизм*", "буддист*", "индуизм*", "индуист*", "синагог*", "раввин*",
        "православ*", "католи*", "миссионер*", "сатанизм*", "сатанист*", "крещени*",
        # Uzbek (Latin)
        "cherkov*", "xristian*", "nasroniy*", "injil*", "bibliya*", "iso masih*", "pastor*", "missioner*",
        "buddizm*", "buddist*", "hinduizm*", "induizm*", "sinagoga*", "pravoslav*", "katolik*", "satanizm*",
        "sotonizm*", "iegova*", "baptist*",
        # Uzbek (Cyrillic)
        "черков*", "насроний*", "инжил*", "будда*",
    ],
    CUSTOMS: [
        "lgbt*", "лгбт*", "gey parad*", "gay parade*", "gay pride", "гей парад*", "гей-парад*",
        "kazino*", "casino*", "казино*", "bukmeker*", "букмекер*", "stavka*", "ставк*", "1xbet",
        "mostbet", "melbet", "linebet", "betting",
        "folbin*", "falchi*", "фолбин*", "tarot*", "гадани*",
    ],
}


def normalize(text: str) -> str:
    """Casefold and unify look-alike apostrophes (o' / o‘ / oʻ) and ё."""
    t = (text or "").casefold()
    for ch in "ʻʼ’‘`´":
        t = t.replace(ch, "'")
    t = t.replace("ё", "е").replace("​", "").replace("­", "")
    return t


def _compile(terms: Iterable[str]) -> Optional[re.Pattern[str]]:
    alts: Dict[str, None] = {}
    for raw in terms:
        t = normalize(raw).strip()
        if not t:
            continue
        variants = {t, t.replace("'", "")}  # "yalang'och" also matches "yalangoch"
        for v in variants:
            prefix = v.endswith("*")
            body = re.escape(v[:-1] if prefix else v).replace(r"\ ", r"\s+").replace(r"\-", r"[-\s]?")
            alts[body + (r"\w*" if prefix else "")] = None
    if not alts:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(sorted(alts, key=len, reverse=True)) + r")(?!\w)")


@dataclass(frozen=True)
class Verdict:
    blocked: bool
    category: Optional[str] = None
    term: Optional[str] = None     # for logs / admins only
    source: Optional[str] = None   # which field matched


ALLOW = Verdict(False)


def load_extra_terms(path: Optional[str]) -> Dict[str, List[str]]:
    """Read `category|term` lines (`#` comments allowed) from an admin-editable file."""
    out: Dict[str, List[str]] = {}
    if not path:
        return out
    p = Path(path)
    if not p.is_file():
        return out
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cat, sep, term = line.partition("|")
        cat, term = cat.strip(), term.strip()
        if not sep or cat not in DEFAULT_TERMS or not term:
            logger.warning("blocked terms file %s line %d ignored: %r", path, n, line)
            continue
        out.setdefault(cat, []).append(term)
    return out


class ContentFilter:
    def __init__(
        self,
        categories: Sequence[str] = ALL_CATEGORIES,
        terms: Optional[Mapping[str, Sequence[str]]] = None,
        extra_terms_file: Optional[str] = None,
        min_age_limit: int = 18,
    ) -> None:
        self.categories = tuple(c for c in categories if c in ALL_CATEGORIES)
        self.min_age_limit = min_age_limit
        base = {k: list(v) for k, v in (terms if terms is not None else DEFAULT_TERMS).items()}
        for cat, extra in load_extra_terms(extra_terms_file).items():
            base.setdefault(cat, []).extend(extra)
        self._patterns = {c: p for c in self.categories if c in base and (p := _compile(base[c]))}

    # -- helpers ---------------------------------------------------------
    def _hits(self, category: str, text: str) -> List[str]:
        pat = self._patterns.get(category)
        if not pat or not text:
            return []
        seen: Dict[str, None] = {}
        for m in pat.finditer(normalize(text)):
            seen[re.sub(r"\s+", " ", m.group(0))] = None
        return list(seen)

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return " \n ".join(str(v) for v in value)
        return str(value)

    # -- public API ------------------------------------------------------
    def check_text(self, text: str) -> Verdict:
        """Check free text the user sent (message text and URL words); any hit blocks."""
        words = re.sub(r"[/_.?&=%#+-]+", " ", text or "") if text else ""
        for cat in self._patterns:
            hits = self._hits(cat, text or "") or self._hits(cat, words)
            if hits:
                return Verdict(True, cat, hits[0], "message")
        return ALLOW

    def check_info(self, info: Mapping[str, Any]) -> Verdict:
        """Check yt-dlp metadata. Missing fields are fine (early extraction stages)."""
        if AGE_RESTRICTED in self.categories:
            age = info.get("age_limit")
            if isinstance(age, (int, float)) and age >= self.min_age_limit:
                return Verdict(True, AGE_RESTRICTED, f"age_limit={int(age)}", "age_limit")
        for cat in self._patterns:
            for field in STRONG_FIELDS:
                hits = self._hits(cat, self._as_text(info.get(field)))
                if hits:
                    return Verdict(True, cat, hits[0], field)
            desc = self._as_text(info.get("description"))[:DESCRIPTION_CHARS]
            hits = self._hits(cat, desc)
            if len(hits) >= WEAK_MIN_HITS.get(cat, 1):
                return Verdict(True, cat, hits[0], "description")
        return ALLOW


_default: Optional[ContentFilter] = None


def get_filter() -> Optional[ContentFilter]:
    """Filter configured from settings, or None when disabled."""
    global _default
    from app.config import settings  # late import: keeps this module testable on its own

    if not settings.content_filter_enabled:
        return None
    if _default is None:
        _default = ContentFilter(settings.content_filter_categories, extra_terms_file=settings.blocked_terms_file)
    return _default
