import logging

from app.models.system_setting import SystemSetting
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict[str, tuple[str, str]] = {
    "top_k": ("5", "RAG 检索召回片段数"),
    "score_threshold": ("0.0", "低相关度拒答阈值，0 表示不启用"),
    "qwen_model": ("qwen-plus", "默认调用的千问模型"),
    "temperature": ("0.2", "LLM 生成温度"),
    "privacy_mode": ("hybrid", "资料处理模式：local、hybrid 或 cloud"),
    "glass_variant": ("balanced", "界面玻璃材质强度"),
    "retrieval_channels": ("hybrid", "检索通道：vector、lexical 或 hybrid"),
}


RETRIEVAL_CHANNELS = ("vector", "lexical", "hybrid")


def normalize_retrieval_channels(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in RETRIEVAL_CHANNELS else "hybrid"


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


def typed_settings(db: Session) -> dict[str, object]:
    values = get_settings(db)
    return {
        "top_k": _coerce_setting(values["top_k"], "top_k", int),
        "score_threshold": _coerce_setting(values["score_threshold"], "score_threshold", float),
        "qwen_model": values["qwen_model"],
        "temperature": _coerce_setting(values["temperature"], "temperature", float),
        "privacy_mode": values["privacy_mode"],
        "glass_variant": values["glass_variant"],
        "retrieval_channels": normalize_retrieval_channels(values["retrieval_channels"]),
    }


def _coerce_setting(raw: object, key: str, converter: type) -> object:
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
