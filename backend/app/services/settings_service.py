from app.models.system_setting import SystemSetting
from sqlalchemy.orm import Session

DEFAULT_SETTINGS: dict[str, tuple[str, str]] = {
    "top_k": ("5", "RAG 检索召回片段数"),
    "score_threshold": ("0.0", "低相关度拒答阈值，0 表示不启用"),
    "qwen_model": ("qwen-plus", "默认调用的千问模型"),
    "temperature": ("0.2", "LLM 生成温度"),
}


def ensure_default_settings(db: Session) -> None:
    changed = False
    for key, (value, description) in DEFAULT_SETTINGS.items():
        if db.get(SystemSetting, key) is None:
            db.add(SystemSetting(key=key, value=value, description=description))
            changed = True
    if changed:
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
        "top_k": int(values["top_k"]),
        "score_threshold": float(values["score_threshold"]),
        "qwen_model": values["qwen_model"],
        "temperature": float(values["temperature"]),
    }
