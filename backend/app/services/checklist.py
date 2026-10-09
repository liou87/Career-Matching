"""提升清单写入：接口层和 AI 助手的 add_to_checklist 工具共用。"""
from sqlalchemy.orm import Session

from app.db import models


def add_items(db: Session, items: list[dict]) -> list[models.Checklist]:
    """items 每项包含 content，可选 importance、suggestion、category（gap / action）。"""
    rows = [
        models.Checklist(
            content=i["content"],
            importance=i.get("importance"),
            suggestion=i.get("suggestion"),
            category=i.get("category") or "gap",
        )
        for i in items
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows
