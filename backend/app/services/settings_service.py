import logging
from collections.abc import Callable
from typing import Literal, TypedDict, TypeVar, cast

from app.models.system_setting import SystemSetting
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_SETTINGS: dict[str, tuple[str, str]] = {
    "top_k": ("5", "RAG 检索召回片段数"),
    "score_threshold": ("0.0", "低相关度拒答阈值，0 表示不启用"),
    "qwen_model": ("qwen-plus", "默认调用的千问模型"),
    "temperature": ("0.2", "LLM 生成温度"),
    "privacy_mode": ("hybrid", "资料处理模式：local、hybrid 或 cloud"),
    "glass_variant": ("balanced", "界面玻璃材质强度"),
    "retrieval_channels": ("hybrid", "检索通道：vector、lexical 或 hybrid"),
    "injection_filter_mode": ("downweight", "摄入侧注入筛查处置：off、downweight 或 exclude"),
    "injection_downweight": ("0.5", "命中注入标记块的降权系数，0 到 1"),
}


RETRIEVAL_CHANNELS = ("vector", "lexical", "hybrid")
INJECTION_FILTER_MODES = ("off", "downweight", "exclude")


def normalize_retrieval_channels(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in RETRIEVAL_CHANNELS else "hybrid"


def normalize_injection_filter_mode(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in INJECTION_FILTER_MODES else "downweight"


def ensure_default_settings(db: Session) -> None:
    values = [
        {"key": key, "value": value, "description": description}
        for key, (value, description) in DEFAULT_SETTINGS.items()
    ]
    statement = insert(SystemSetting).values(values).on_conflict_do_nothing(index_elements=["key"])
    db.execute(statement)
    db.commit()


def get_settings(db: Session) -> dict[str, str]:
    ensure_default_settings(db)
    rows = db.query(SystemSetting).all()
    values = {row.key: row.value for row in rows}
    for key, (value, _) in DEFAULT_SETTINGS.items():
        values.setdefault(key, value)
    return values


def update_settings(db: Session, payload: dict[str, object]) -> dict[str, str]:
    ensure_default_settings(db)
    for key, value in payload.items():
        if value is None or key not in DEFAULT_SETTINGS:
            continue
        if key == "retrieval_channels":
            value = normalize_retrieval_channels(value)
        if key == "injection_filter_mode":
            value = normalize_injection_filter_mode(value)
        setting = db.get(SystemSetting, key)
        if setting is None:
            setting = SystemSetting(
                key=key,
                value=str(value),
                description=DEFAULT_SETTINGS[key][1],
            )
            db.add(setting)
        else:
            setting.value = str(value)
    db.commit()
    return get_settings(db)


PrivacyMode = Literal["local", "hybrid", "cloud"]
GlassVariant = Literal["clear", "balanced", "contrast"]
RetrievalChannel = Literal["vector", "lexical", "hybrid"]
InjectionFilterMode = Literal["off", "downweight", "exclude"]


class TypedSettings(TypedDict):
    """Runtime-coerced settings, safe to pass straight into typed schemas."""

    top_k: int
    score_threshold: float
    qwen_model: str
    temperature: float
    privacy_mode: PrivacyMode
    glass_variant: GlassVariant
    retrieval_channels: RetrievalChannel
    injection_filter_mode: InjectionFilterMode
    injection_downweight: float


def typed_settings(db: Session) -> TypedSettings:
    values = get_settings(db)
    # The stored values can drift from the allowed literals only through manual
    # edits to the database; get_settings seeds every key with a valid default
    # and update_settings validates on write, so a cast here documents the
    # invariant instead of failing open.
    return {
        "top_k": _coerce_setting(values["top_k"], "top_k", int),
        "score_threshold": _coerce_setting(values["score_threshold"], "score_threshold", float),
        "qwen_model": values["qwen_model"],
        "temperature": _coerce_setting(values["temperature"], "temperature", float),
        "privacy_mode": cast(PrivacyMode, values["privacy_mode"]),
        "glass_variant": cast(GlassVariant, values["glass_variant"]),
        "retrieval_channels": cast(
            RetrievalChannel, normalize_retrieval_channels(values["retrieval_channels"])
        ),
        "injection_filter_mode": cast(
            InjectionFilterMode,
            normalize_injection_filter_mode(values["injection_filter_mode"]),
        ),
        "injection_downweight": _coerce_ratio(
            values["injection_downweight"], "injection_downweight"
        ),
    }


def _coerce_setting[T](raw: str, key: str, converter: Callable[[str], T]) -> T:
    """Convert a stored setting, falling back to its default when corrupted."""
    default = DEFAULT_SETTINGS[key][0]
    try:
        return converter(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Stored setting %s=%r is invalid; falling back to default %r",
            key,
            raw,
            default,
        )
        return converter(default)


def _coerce_ratio(raw: str, key: str) -> float:
    """Clamp a 0..1 ratio setting, falling back to its default when unusable."""
    value = _coerce_setting(raw, key, float)
    if not 0.0 <= value <= 1.0:
        default = float(DEFAULT_SETTINGS[key][0])
        logger.warning(
            "Stored setting %s=%r is outside 0..1; falling back to default %r",
            key,
            raw,
            default,
        )
        return default
    return value
