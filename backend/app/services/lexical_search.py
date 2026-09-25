import re

ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
TOKEN_SCAN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def to_search_text(text: str) -> str:
    tokens: list[str] = []
    for match in TOKEN_SCAN_RE.finditer(text or ""):
        token = match.group(0)
        if ASCII_WORD_RE.fullmatch(token):
            tokens.append(token)
        else:
            chars = [char for char in token if _is_cjk(char)]
            tokens.extend(chars[index] + chars[index + 1] for index in range(len(chars) - 1))
    return " ".join(tokens)


def _build_search_text(content: str, section_path: str = "") -> str:
    return f"{to_search_text(content)} {to_search_text(section_path or '')}".strip()
