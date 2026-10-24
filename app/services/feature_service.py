"""R3 特征计算：25 个特征（字段名固定，不得改名）。

用户维度 10 + 订单维度 10 + 地址维度 5。

性能约定（文档 4 节「禁止 N+1 查询」）：
`build_feature_snapshot` 先构造 FeatureContext，一次性批量预取
  - 上游订单/用户快照（单次 JSON 加载，进程内缓存）
  - risk_events 30 天聚合（1 条 SQL）
  - risk_cases 计数（1 条 SQL）
  - 生效中的黑名单全集（1 条 SQL）
此后 25 个 calc_* 函数全部读内存，恒定为 3 条 SQL 完成一次快照。

兼容性：每个 calc_* 保留文档要求的签名 (db, user_id, order_id)，
db 既可以是 FeatureContext（批量模式，推荐），也可以是 SQLAlchemy Session
（单特征直调模式，会为该函数单独构造上下文）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Blacklist, RiskCase, RiskEvent
from app.services import source_adapter as upstream

FEATURE_NAMES: list[str] = [
    # 用户维度（10）
    "user_order_count_30d",
    "user_refund_count_30d",
    "user_complaint_count_30d",
    "user_reg_days",
    "user_address_count",
    "user_risk_event_count_30d",
    "user_blacklist_hit",
    "user_avg_order_amount",
    "user_refund_rate",
    "user_case_count",
    # 订单维度（10）
    "order_amount",
    "order_category_risk_score",
    "order_pay_method",
    "order_hour",
    "order_is_weekend",
    "order_item_count",
    "order_discount_rate",
    "order_is_new_user",
    "order_device_risk",
    "order_ip_risk",
    # 地址维度（5）
    "address_change_count_90d",
    "address_user_count",
    "address_in_blacklist",
    "address_ip_consistency",
    "address_distance_from_history",
]

NEW_USER_DAYS = 7
REFUND_STATUSES = {"refunded", "refunding", "refund_apply"}


def _d(value: Any) -> Decimal:
    return Decimal(str(value if value is not None else 0))


class FeatureContext:
    """一次风险检查所需的全部特征原料，批量预取。"""

    def __init__(
        self,
        db: Session,
        user_id: str,
        order_id: str | None,
        exclude_event_id: str | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.order_id = order_id
        self.exclude_event_id = exclude_event_id
        self.now = datetime.now(timezone.utc)
        self.since_30d = self.now - timedelta(days=30)
        self.since_90d = self.now - timedelta(days=90)

        # ---- 上游快照 ----
        self.user: dict = upstream.get_user(user_id) or {}
        self.order: dict = upstream.get_order(order_id) or {}
        self.user_orders: list[dict] = upstream.list_user_orders(user_id)
        self.orders_30d: list[dict] = upstream.orders_within(self.user_orders, 30, self.now)
        self.orders_90d: list[dict] = upstream.orders_within(self.user_orders, 90, self.now)
        self.addresses: list[dict] = list(self.user.get("addresses", []))
        self.order_address = None
        if self.order:
            self.order_address = upstream.resolve_address(
                user_id, self.order.get("address_id") or self.order.get("address", {}).get("address_id")
            )

        # ---- SQL 聚合（固定 3 条）----
        stmt = select(func.count(RiskEvent.id)).where(
            RiskEvent.user_id == user_id, RiskEvent.created_at >= self.since_30d
        )
        if exclude_event_id:
            stmt = stmt.where(RiskEvent.id != exclude_event_id)
        self.risk_event_count_30d: int = int(db.execute(stmt).scalar() or 0)

        self.case_count: int = int(
            db.execute(
                select(func.count(RiskCase.id)).where(RiskCase.user_id == user_id)
            ).scalar()
            or 0
        )

        rows = db.execute(
            select(Blacklist.blacklist_type, Blacklist.blacklist_value).where(
                Blacklist.status == "active"
            )
        ).all()
        self.blacklist: dict[str, set[str]] = {}
        for btype, bvalue in rows:
            self.blacklist.setdefault(btype, set()).add(str(bvalue))

    # 供 calc_* 复用的派生量
    @property
    def refunded_30d(self) -> list[dict]:
        return [o for o in self.orders_30d if o.get("refund_status") in REFUND_STATUSES]

    @property
    def complained_30d(self) -> list[dict]:
        return [o for o in self.orders_30d if o.get("has_complaint")]

    def has_blacklist(self, btype: str, value: Any) -> bool:
        if value is None or value == "":
            return False
        return str(value) in self.blacklist.get(btype, set())


def _ctx(db: Session | FeatureContext, user_id: str, order_id: str | None) -> FeatureContext:
    if isinstance(db, FeatureContext):
        return db
    return FeatureContext(db, user_id, order_id)


# --------------------------------------------------------------------------
# 用户维度（10）
# --------------------------------------------------------------------------
def calc_user_order_count_30d(db, user_id: str, order_id: str | None) -> int:
    """近 30 天下单数（上游订单服务）。"""
    return len(_ctx(db, user_id, order_id).orders_30d)


def calc_user_refund_count_30d(db, user_id: str, order_id: str | None) -> int:
    """近 30 天退款/退款申请次数。"""
    return len(_ctx(db, user_id, order_id).refunded_30d)


def calc_user_complaint_count_30d(db, user_id: str, order_id: str | None) -> int:
    """近 30 天投诉次数（订单带 has_complaint 标记）。"""
    return len(_ctx(db, user_id, order_id).complained_30d)


def calc_user_reg_days(db, user_id: str, order_id: str | None) -> int | None:
    """账号注册天数；无注册时间返回 None。"""
    ctx = _ctx(db, user_id, order_id)
    reg = ctx.user.get("register_at_dt")
    if not reg:
        return None
    return max(0, (ctx.now - reg).days)


def calc_user_address_count(db, user_id: str, order_id: str | None) -> int:
    """账号历史收货地址数。"""
    return len(_ctx(db, user_id, order_id).addresses)


def calc_user_risk_event_count_30d(db, user_id: str, order_id: str | None) -> int:
    """近 30 天该用户触发的风控事件数（不含本次事件）。"""
    return _ctx(db, user_id, order_id).risk_event_count_30d


def calc_user_blacklist_hit(db, user_id: str, order_id: str | None) -> bool:
    """用户是否命中用户类黑名单。"""
    ctx = _ctx(db, user_id, order_id)
    return ctx.has_blacklist("user", user_id)


def calc_user_avg_order_amount(db, user_id: str, order_id: str | None) -> Decimal | None:
    """历史平均订单金额；无订单返回 None。"""
    ctx = _ctx(db, user_id, order_id)
    if not ctx.user_orders:
        return None
    total = sum((_d(o["amount"]) for o in ctx.user_orders), Decimal("0"))
    return (total / Decimal(len(ctx.user_orders))).quantize(Decimal("0.01"))


def calc_user_refund_rate(db, user_id: str, order_id: str | None) -> Decimal | None:
    """历史退款率 = 退款单数 / 总订单数。"""
    ctx = _ctx(db, user_id, order_id)
    total = len(ctx.user_orders)
    if total == 0:
        return None
    refunded = len([o for o in ctx.user_orders if o.get("refund_status") in REFUND_STATUSES])
    return (Decimal(refunded) / Decimal(total)).quantize(Decimal("0.0001"))


def calc_user_case_count(db, user_id: str, order_id: str | None) -> int:
    """该用户历史风控案件数。"""
    return _ctx(db, user_id, order_id).case_count


# --------------------------------------------------------------------------
# 订单维度（10）
# --------------------------------------------------------------------------
def calc_order_amount(db, user_id: str, order_id: str | None) -> Decimal | None:
    """订单金额（元）。"""
    order = _ctx(db, user_id, order_id).order
    return _d(order["amount"]) if order else None


def calc_order_category_risk_score(db, user_id: str, order_id: str | None) -> int | None:
    """品类风险分 0-100（虚拟卡/贵金属等高风险品类偏高）。"""
    order = _ctx(db, user_id, order_id).order
    if not order:
        return None
    value = order.get("category_risk_score")
    return int(value) if value is not None else None


def calc_order_pay_method(db, user_id: str, order_id: str | None) -> str | None:
    """支付方式。"""
    order = _ctx(db, user_id, order_id).order
    return order.get("pay_method") if order else None


def calc_order_hour(db, user_id: str, order_id: str | None) -> int | None:
    """下单小时（按订单时区偏移后的北京时间小时）。"""
    order = _ctx(db, user_id, order_id).order
    if not order or not order.get("created_at_dt"):
        return None
    dt: datetime = order["created_at_dt"]
    tz_offset = int(order.get("tz_offset_hours", 8))
    return (dt.astimezone(timezone.utc) + timedelta(hours=tz_offset)).hour


def calc_order_is_weekend(db, user_id: str, order_id: str | None) -> bool | None:
    """是否周末下单（按北京时间）。"""
    hour_ctx = _ctx(db, user_id, order_id)
    order = hour_ctx.order
    if not order or not order.get("created_at_dt"):
        return None
    tz_offset = int(order.get("tz_offset_hours", 8))
    local = order["created_at_dt"].astimezone(timezone.utc) + timedelta(hours=tz_offset)
    return local.weekday() >= 5


def calc_order_item_count(db, user_id: str, order_id: str | None) -> int | None:
    """订单商品件数。"""
    order = _ctx(db, user_id, order_id).order
    return int(order.get("item_count")) if order and order.get("item_count") is not None else None


def calc_order_discount_rate(db, user_id: str, order_id: str | None) -> Decimal | None:
    """订单折扣率 0-1。"""
    order = _ctx(db, user_id, order_id).order
    return _d(order["discount_rate"]) if order else None


def calc_order_is_new_user(db, user_id: str, order_id: str | None) -> bool | None:
    """是否新用户（注册 <= 7 天）。"""
    reg_days = calc_user_reg_days(db, user_id, order_id)
    if reg_days is None:
        return None
    return reg_days <= NEW_USER_DAYS


def calc_order_device_risk(db, user_id: str, order_id: str | None) -> int | None:
    """设备风险分 0-100（设备指纹服务）。"""
    ctx = _ctx(db, user_id, order_id)
    value = ctx.order.get("device_risk", ctx.user.get("default_device_risk"))
    return int(value) if value is not None else None


def calc_order_ip_risk(db, user_id: str, order_id: str | None) -> int | None:
    """IP 风险分 0-100（IP 情报服务）。"""
    ctx = _ctx(db, user_id, order_id)
    value = ctx.order.get("ip_risk", ctx.user.get("default_ip_risk"))
    return int(value) if value is not None else None


# --------------------------------------------------------------------------
# 地址维度（5）
# --------------------------------------------------------------------------
def calc_address_change_count_90d(db, user_id: str, order_id: str | None) -> int:
    """近 90 天收货地址变更次数（去重地址数 - 1，最小 0）。"""
    ctx = _ctx(db, user_id, order_id)
    recent = {
        a.get("address_id") for a in ctx.addresses if a.get("used_at_dt") and a["used_at_dt"] >= ctx.since_90d
    }
    for o in ctx.orders_90d:
        aid = o.get("address_id")
        if aid:
            recent.add(aid)
    return max(0, len(recent) - 1)


def calc_address_user_count(db, user_id: str, order_id: str | None) -> int | None:
    """该收货地址关联的用户数（地址共用度）。"""
    ctx = _ctx(db, user_id, order_id)
    addr = ctx.order_address
    if not addr:
        return None
    value = addr.get("shared_user_count")
    return int(value) if value is not None else 1


def calc_address_in_blacklist(db, user_id: str, order_id: str | None) -> bool:
    """收货地址是否命中地址黑名单。"""
    ctx = _ctx(db, user_id, order_id)
    addr_id = (ctx.order or {}).get("address_id")
    if not addr_id and ctx.order_address:
        addr_id = ctx.order_address.get("address_id")
    if not addr_id:
        return False
    return ctx.has_blacklist("address", addr_id)


def calc_address_ip_consistency(db, user_id: str, order_id: str | None) -> int | None:
    """地址与 IP 归属地是否一致：1 一致 / 0 不一致。"""
    ctx = _ctx(db, user_id, order_id)
    if not ctx.order or not ctx.order_address:
        return None
    ip_city = ctx.order.get("ip_city")
    addr_city = ctx.order_address.get("city")
    if not ip_city or not addr_city:
        return None
    return 1 if str(ip_city) == str(addr_city) else 0


def calc_address_distance_from_history(db, user_id: str, order_id: str | None) -> float | None:
    """本次收货地址与历史常用地址（首次登记地址）的直线距离，单位 km。"""
    ctx = _ctx(db, user_id, order_id)
    if not ctx.order_address or len(ctx.addresses) < 2:
        return None
    current_id = ctx.order_address.get("address_id")
    others = [a for a in ctx.addresses if a.get("address_id") != current_id]
    if not others:
        return None
    base = others[0]
    return upstream.haversine_km(ctx.order_address, base)


# --------------------------------------------------------------------------
# 快照构建
# --------------------------------------------------------------------------
CALCULATORS = {
    "user_order_count_30d": calc_user_order_count_30d,
    "user_refund_count_30d": calc_user_refund_count_30d,
    "user_complaint_count_30d": calc_user_complaint_count_30d,
    "user_reg_days": calc_user_reg_days,
    "user_address_count": calc_user_address_count,
    "user_risk_event_count_30d": calc_user_risk_event_count_30d,
    "user_blacklist_hit": calc_user_blacklist_hit,
    "user_avg_order_amount": calc_user_avg_order_amount,
    "user_refund_rate": calc_user_refund_rate,
    "user_case_count": calc_user_case_count,
    "order_amount": calc_order_amount,
    "order_category_risk_score": calc_order_category_risk_score,
    "order_pay_method": calc_order_pay_method,
    "order_hour": calc_order_hour,
    "order_is_weekend": calc_order_is_weekend,
    "order_item_count": calc_order_item_count,
    "order_discount_rate": calc_order_discount_rate,
    "order_is_new_user": calc_order_is_new_user,
    "order_device_risk": calc_order_device_risk,
    "order_ip_risk": calc_order_ip_risk,
    "address_change_count_90d": calc_address_change_count_90d,
    "address_user_count": calc_address_user_count,
    "address_in_blacklist": calc_address_in_blacklist,
    "address_ip_consistency": calc_address_ip_consistency,
    "address_distance_from_history": calc_address_distance_from_history,
}


def jsonable(value: Any) -> Any:
    """Decimal → str，datetime → ISO8601，保证可写入 JSONB。"""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value != value.to_integral_value() else str(value.quantize(Decimal("1")))
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def build_feature_snapshot(
    db: Session, user_id: str, order_id: str | None, exclude_event_id: str | None = None
) -> dict[str, Any]:
    """返回 25 个特征键值；批量预取，恒为 3 条 SQL。"""
    ctx = FeatureContext(db, user_id, order_id, exclude_event_id=exclude_event_id)
    features: dict[str, Any] = {}
    for name in FEATURE_NAMES:
        try:
            features[name] = CALCULATORS[name](ctx, user_id, order_id)
        except Exception:  # noqa: BLE001 —— 单特征失败降级为 None（规则侧视为不命中）
            features[name] = None
    return features


def snapshot_for_json(features: dict[str, Any]) -> dict[str, Any]:
    return {k: jsonable(v) for k, v in features.items()}
