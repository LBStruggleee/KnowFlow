"""Rule-based prompt-injection screening for ingested document chunks.

The guard is deliberately cheap and explainable: weighted regular expressions
over normalized text, no model, no network, no LLM cost. It runs at ingestion
time so the retrieval layer can downweight flagged chunks instead of serving
them as trusted evidence, and at migration time to cover pre-existing chunks.

Design decisions come from an offline probe against a real document plus 496
chunks of Chinese technical writing (2026-11-06):

* text is NFKC-normalized and zero-width characters are stripped before
  matching, while the raw zero-width characters are still a signal of their own;
* whitespace is collapsed so a phrase broken across a PDF line break
  (``忽略\\n以上指令``) still matches;
* the fake-boundary rule only fires in structural positions (line start or
  ``<source id="N">``). Documentation that *mentions* ``</source>`` inside
  backticks was the dominant false-positive source, and prose mentions are not
  structural forgeries;
* matches inside descriptive contexts (``指的是…``, ``忽略指令类``) are damped
  rather than ignored: a security textbook quoting an attack should stay below
  threshold, while a real instruction still clears it.

Known gaps (documented, not hidden): non-Chinese/English payloads and semantic
inducements without trigger words are not detected; the rule set is a
best-effort filter, not a guarantee.
"""

import re
import unicodedata
from typing import NamedTuple

DEFAULT_INJECTION_THRESHOLD = 2.0
DAMPING_FACTOR = 0.3
DESCRIPTIVE_WINDOW = 30
DESCRIPTIVE_MARKERS = ("指的是", "是指", "定义为", "称为", "例如", "比如", "这类", "所谓", "属于")
SUFFIX_MARKERS = ("类", "等", "之类", "这种", "这类")
ZERO_WIDTH_PATTERN = r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]"

_ZERO_WIDTH_RE = re.compile(ZERO_WIDTH_PATTERN)
_WHITESPACE_RE = re.compile(r"\s+")


class InjectionRule(NamedTuple):
    name: str
    weight: float
    pattern: re.Pattern[str]


class InjectionScan(NamedTuple):
    score: float
    rules: list[str]
    flagged: bool


RULES: tuple[InjectionRule, ...] = (
    InjectionRule(
        "override_instruction",
        2.0,
        re.compile(
            r"(忽略|无视|忘记|忘掉|不要理会|不用管).{0,16}"
            r"(以上|上述|之前|前面|此前|所有|全部|用户)?(指令|指示|提示词|要求|规则|设定|问题)"
            r"|(指令|规则|设定|约束).{0,8}(作废|失效|不适用|不再有效)"
            r"|(ignore|disregard)\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
            r"(instructions|prompts|rules|directions)",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        "role_hijack",
        1.5,
        re.compile(
            r"你现在是|你现在扮演|你扮演|从现在开始你是|you are now (a|an|the) ", re.IGNORECASE
        ),
    ),
    InjectionRule(
        "system_prompt_leak",
        2.0,
        re.compile(
            r"(输出|泄露|泄漏|打印|复述|reveal|print|output|repeat).{0,12}"
            r"(系统提示|system prompt|初始指令|developer message)"
            r"|(系统提示词|system prompt).{0,12}(全文|原样|verbatim)",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        "fake_boundary",
        2.0,
        re.compile(
            r"(?m)^[ \t]*</?source\b[^>]*>|<source\s+id\s*=\s*[\"']?\d",
            re.IGNORECASE,
        ),
    ),
    InjectionRule("fake_citation", 1.0, re.compile(r"\[资料\s*\d+\]")),
    InjectionRule("zero_width", 2.5, re.compile(ZERO_WIDTH_PATTERN)),
    InjectionRule(
        "html_comment_instruction",
        2.0,
        re.compile(
            r"<!--(?=[^>]{0,120}(指令|忽略|ignore|prompt|instruct|system))[^>]*-->",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        "data_exfil",
        2.0,
        re.compile(
            r"(列出|导出|发送).{0,16}(所有|全部).{0,10}(文档|资料|笔记)"
            r"|list (every|all) (document|documents|notes).{0,80}(email|send)",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        "link_instruction",
        2.0,
        re.compile(
            r"(打开|访问|点击).{0,10}(链接|网址|页面).{0,40}(指令|命令|要求)"
            r"|follow (this|the) link.{0,30}(instruction|command)",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        "verbatim_context",
        1.5,
        re.compile(r"(完整|原样|逐字).{0,8}(复述|重复|输出).{0,10}(上下文|资料|对话)"),
    ),
)


def normalize_lined(text: str) -> str:
    """NFKC + zero-width removal, keeping line boundaries for structural rules."""
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    return "\n".join(line.rstrip() for line in normalized.splitlines())


def normalize_flat(text: str) -> str:
    """Collapse every whitespace run so phrases split across lines still match."""
    return _WHITESPACE_RE.sub(" ", normalize_lined(text)).strip()


def scan_text(
    text: str,
    threshold: float = DEFAULT_INJECTION_THRESHOLD,
) -> InjectionScan:
    """Score one chunk and report which rules fired.

    ``flagged`` is the only value storage needs; ``rules`` names are kept so a
    reviewer can explain why a chunk was downgraded, and ``score`` supports
    tuning the threshold later.
    """
    raw = text or ""
    lined = normalize_lined(raw)
    flat = normalize_flat(raw)
    hits: list[tuple[str, float]] = []

    for rule in RULES:
        target = (
            raw if rule.name == "zero_width" else (lined if rule.name == "fake_boundary" else flat)
        )
        match = rule.pattern.search(target)
        if match is None:
            continue
        weight = rule.weight
        if rule.name not in {"zero_width", "fake_boundary"} and _in_descriptive_context(
            flat, match.start(), match.end()
        ):
            weight *= DAMPING_FACTOR
        hits.append((rule.name, round(weight, 2)))

    score = round(sum(weight for _, weight in hits), 2)
    return InjectionScan(
        score=score,
        rules=[name for name, _ in hits],
        flagged=score >= threshold,
    )


def _in_descriptive_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - DESCRIPTIVE_WINDOW) : end + DESCRIPTIVE_WINDOW]
    if any(marker in window for marker in DESCRIPTIVE_MARKERS):
        return True
    suffix = text[end : end + 2]
    return any(suffix.startswith(marker) for marker in SUFFIX_MARKERS)


def rules_as_text(rules: list[str]) -> str:
    """Storage form for the matched rule names."""
    return ",".join(rules)
