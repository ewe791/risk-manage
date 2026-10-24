"""黑名单服务：查询 / 新增 / 删除。"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Blacklist, gen_id

BLACKLIST_TYPES = {"user", "address", "ip", "device"}


class BlacklistError(ValueError):
    pass


def serialize(item: Blacklist) -> dict:
    return {
        "blacklist_id": item.id,
        "blacklist_type": item.blacklist_type,
        "blacklist_value": item.blacklist_value,
        "remark": item.remark,
        "status": item.status,
        "created_at": item.created_at,
    }


def list_blacklists(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    blacklist_type: str | None = None,
    keyword: str | None = None,
) -> dict:
    stmt = select(Blacklist)
    count_stmt = select(func.count(Blacklist.id))
    conds = []
    if blacklist_type:
        conds.append(Blacklist.blacklist_type == blacklist_type)
    if keyword:
        conds.append(Blacklist.blacklist_value.like(f"%{keyword}%"))
    if conds:
        stmt = stmt.where(*conds)
        count_stmt = count_stmt.where(*conds)
    total = int(db.execute(count_stmt).scalar() or 0)
    rows = db.execute(
        stmt.order_by(Blacklist.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {"items": [serialize(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def add_blacklist(db: Session, payload: dict) -> dict:
    btype = payload.get("blacklist_type")
    value = (payload.get("blacklist_value") or "").strip()
    if btype not in BLACKLIST_TYPES:
        raise BlacklistError(f"blacklist_type 仅支持 {sorted(BLACKLIST_TYPES)}")
    if not value:
        raise BlacklistError("blacklist_value 必填")
    exists = db.execute(
        select(Blacklist).where(
            Blacklist.blacklist_type == btype, Blacklist.blacklist_value == value
        )
    ).scalars().first()
    if exists:
        raise BlacklistError(f"该记录已存在（{btype}:{value}）")
    item = Blacklist(
        id=gen_id("BL"),
        blacklist_type=btype,
        blacklist_value=value,
        remark=payload.get("remark"),
        status=payload.get("status") or "active",
        created_at=datetime.now(timezone.utc),
    )
    db.add(item)
    db.commit()
    return serialize(item)


def parse_import_text(text: str) -> list[dict]:
    """解析批量导入文本：每行 `类型,名单值,备注`，支持逗号/制表符/竖线分隔。

    兼容表头行与 # 注释行；类型支持中文（用户/地址/IP/设备）与英文。
    """
    alias = {
        "user": "user", "用户": "user", "用户id": "user", "用户ID": "user",
        "address": "address", "地址": "address", "收货地址": "address",
        "ip": "ip", "IP": "ip", "ip地址": "ip", "IP地址": "ip",
        "device": "device", "设备": "device", "设备指纹": "device",
    }
    items: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"[,，\t|｜]", line) if p.strip()]
        if len(parts) < 2:
            continue
        if parts[0] in ("类型", "type", "blacklist_type"):
            continue  # 表头
        items.append(
            {
                "blacklist_type": alias.get(parts[0], parts[0].lower()),
                "blacklist_value": parts[1],
                "remark": parts[2] if len(parts) > 2 else None,
            }
        )
    return items


def import_blacklists(db: Session, items: list[dict]) -> dict:
    """批量导入：逐条校验，重复与非法条目计入 skipped/failed，返回明细。"""
    created = skipped = failed = 0
    errors: list[dict] = []
    rows: list[dict] = []
    for index, item in enumerate(items, start=1):
        btype = (item.get("blacklist_type") or "").strip()
        value = (item.get("blacklist_value") or "").strip()
        if btype not in BLACKLIST_TYPES:
            failed += 1
            errors.append({"row": index, "value": value, "reason": f"类型非法: {btype}"})
            continue
        if not value:
            failed += 1
            errors.append({"row": index, "reason": "名单值为空"})
            continue
        exists = db.execute(
            select(Blacklist).where(
                Blacklist.blacklist_type == btype, Blacklist.blacklist_value == value
            )
        ).scalars().first()
        if exists:
            skipped += 1
            errors.append({"row": index, "value": value, "reason": "已存在，跳过"})
            continue
        entity = Blacklist(
            id=gen_id("BL"),
            blacklist_type=btype,
            blacklist_value=value,
            remark=item.get("remark"),
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        db.add(entity)
        db.flush()
        rows.append(serialize(entity))
        created += 1
    db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "total": len(items),
        "items": rows,
        "details": errors,
    }


def delete_blacklist(db: Session, blacklist_id: str | None = None, payload: dict | None = None) -> dict:
    item = None
    if blacklist_id:
        item = db.get(Blacklist, blacklist_id)
    elif payload:
        item = db.execute(
            select(Blacklist).where(
                Blacklist.blacklist_type == payload.get("blacklist_type"),
                Blacklist.blacklist_value == payload.get("blacklist_value"),
            )
        ).scalars().first()
    if not item:
        raise BlacklistError("黑名单记录不存在")
    deleted = serialize(item)
    db.delete(item)
    db.commit()
    return {"deleted": deleted}
