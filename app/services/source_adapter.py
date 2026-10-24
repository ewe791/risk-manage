"""上游业务数据适配层（Mock 订单/用户服务）。

风控系统本身不落订单库，订单/用户属性由上游业务系统提供。生产环境将本模块
替换为对订单服务、用户服务的 RPC 调用（接口签名保持不变）；本地演示读取
seed/demo_orders.json 与 seed/demo_users.json。

设计要点：
- 数据只在进程内加载一次并缓存（mtime 变更自动重载），特征计算层零额外 IO
- 返回只读视图，风控侧不得修改上游数据
- 订单金额使用 Decimal，禁止 float 参与金额计算
"""

from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from app.config import settings

_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"key": None, "users": {}, "orders": {}, "orders_by_user": {}}


def _data_dir() -> Path:
    p = Path(settings.UPSTREAM_DATA_DIR)
    if not p.is_absolute():
        p = (Path(__file__).resolve().parents[2] / p).resolve()
    return p


def _parse_dt(value: str | None) -> datetime | None:
    """解析时间；支持相对写法 T-3d / T-12h / T-30m（相对当前时间回溯）。

    演示数据用相对时间，保证任何日期执行 seed 都能复现 30/90 天窗口内的链路。
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.upper().startswith("T-"):
        token = text[2:].lower()
        hour: int | None = None
        if "@" in token:
            token, hour_text = token.split("@", 1)
            try:
                hour = int(hour_text)
            except ValueError:
                hour = None
        try:
            num = float(token[:-1])
            unit = token[-1]
        except (ValueError, IndexError):
            return None
        delta_map = {"d": timedelta(days=num), "h": timedelta(hours=num), "m": timedelta(minutes=num)}
        delta = delta_map.get(unit)
        if not delta:
            return None
        dt = datetime.now(timezone.utc) - delta
        if hour is not None:
            # 固定为北京时间 hour:00，并把周末回退到最近的周五，
            # 保证 30 天窗口/周末/时段类规则在任何日期执行结果一致
            beijing = dt.astimezone(timezone(timedelta(hours=8))).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            while beijing.weekday() >= 5:
                beijing -= timedelta(days=1)
            dt = beijing.astimezone(timezone.utc)
        return dt
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load() -> None:
    """加载上游数据快照（单次 IO，全量缓存）。"""
    data_dir = _data_dir()
    users_file = data_dir / "demo_users.json"
    orders_file = data_dir / "demo_orders.json"
    key = (
        str(users_file),
        users_file.stat().st_mtime if users_file.exists() else 0,
        str(orders_file),
        orders_file.stat().st_mtime if orders_file.exists() else 0,
    )
    if _CACHE["key"] == key:
        return

    users_raw: list[dict] = json.loads(users_file.read_text(encoding="utf-8")) if users_file.exists() else []
    orders_raw: list[dict] = json.loads(orders_file.read_text(encoding="utf-8")) if orders_file.exists() else []

    users: dict[str, dict] = {}
    for u in users_raw:
        u = dict(u)
        u["register_at_dt"] = _parse_dt(u.get("register_at"))
        addresses = []
        for addr in u.get("addresses", []):
            addr = dict(addr)
            addr["used_at_dt"] = _parse_dt(addr.get("used_at"))
            addresses.append(addr)
        u["addresses"] = addresses
        users[u["user_id"]] = u

    orders: dict[str, dict] = {}
    orders_by_user: dict[str, list[dict]] = {}
    for o in orders_raw:
        o = dict(o)
        o["amount"] = Decimal(str(o.get("amount", "0")))
        o["discount_rate"] = Decimal(str(o.get("discount_rate", "0")))
        o["created_at_dt"] = _parse_dt(o.get("created_at"))
        orders[o["order_id"]] = o
        orders_by_user.setdefault(o["user_id"], []).append(o)
    for items in orders_by_user.values():
        items.sort(key=lambda x: x["created_at_dt"] or datetime.min.replace(tzinfo=timezone.utc))

    _CACHE.update(key=key, users=users, orders=orders, orders_by_user=orders_by_user)


def reload() -> None:
    with _LOCK:
        _CACHE["key"] = None
        _load()


def get_user(user_id: str) -> dict | None:
    _load()
    return _CACHE["users"].get(user_id)


def get_order(order_id: str | None) -> dict | None:
    if not order_id:
        return None
    _load()
    return _CACHE["orders"].get(order_id)


def list_user_orders(user_id: str) -> list[dict]:
    _load()
    return list(_CACHE["orders_by_user"].get(user_id, []))


def find_user_by_address(address_id: str) -> str | None:
    _load()
    for u in _CACHE["users"].values():
        for a in u.get("addresses", []):
            if a.get("address_id") == address_id:
                return u["user_id"]
    return None


def resolve_address(user_id: str, address_id: str | None) -> dict | None:
    """取地址明细（坐标、城市、共用人数）。"""
    if not address_id:
        return None
    user = get_user(user_id)
    if user:
        for a in user.get("addresses", []):
            if a.get("address_id") == address_id:
                return a
    return None


def orders_within(orders: Iterable[dict], days: int, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    out = []
    for o in orders:
        dt = o.get("created_at_dt")
        if dt is None or dt >= since:
            out.append(o)
    return out


def haversine_km(a: dict | None, b: dict | None) -> float | None:
    """两地址球面距离（km），缺坐标返回 None。"""
    if not a or not b:
        return None
    try:
        lat1, lon1 = float(a["lat"]), float(a["lng"])
        lat2, lon2 = float(b["lat"]), float(b["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)), 3)
