"""风险核心接口：检查 / 评估 / 规则 / 案件 / 黑名单 / 画像 / 看板。

权限（文档 2.3.2 三类角色）：
  - 数据查看人 viewer：仅 GET（画像、历史风险记录、命中统计）
  - 风控审核员 reviewer：GET + 风险检查 + 案件审核/归档
  - 风控管理员 admin：全部（规则与黑名单维护仅管理员）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import BizError, CurrentOperator, get_current_operator, get_db, ok, require_roles
from app.schemas.risk import (
    BlacklistCreateRequest,
    BlacklistDeleteRequest,
    BlacklistImportRequest,
    CaseResolveRequest,
    CaseReviewRequest,
    RiskCheckRequest,
    RuleCreateRequest,
    RuleDeleteRequest,
    RuleStatusRequest,
    RuleUpdateRequest,
)
from app.services import (
    blacklist_service,
    case_service,
    dashboard_service,
    profile_service,
    risk_service,
    rule_service,
)

router = APIRouter(prefix="/api/risk", tags=["risk"])

# 角色依赖
_any_role = get_current_operator
_operator_role = require_roles("reviewer")  # 审核员 + 管理员
_admin_role = require_roles()  # 仅管理员


# --------------------------------------------------------------------------
# 检查与评估
# --------------------------------------------------------------------------
@router.post("/check")
async def risk_check(
    payload: RiskCheckRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_operator_role),
):
    """发起风险检查：写事件 → 算特征 → 跑规则 → 出决策 → 必要时自动建案。"""
    try:
        data = await risk_service.check_risk(
            db,
            event_type=payload.event_type,
            source_id=payload.source_id,
            user_id=payload.user_id,
            order_id=payload.order_id,
            operator_id=operator.operator_id,
        )
    except risk_service.RiskValidationError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


@router.get("/assessments/{assessment_id}")
def get_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_any_role),
):
    data = risk_service.get_assessment_detail(db, assessment_id)
    if not data:
        raise BizError(f"评估不存在: {assessment_id}", 404)
    return ok(data)


# --------------------------------------------------------------------------
# 规则
# --------------------------------------------------------------------------
@router.get("/rules")
def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    rule_status: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_any_role),
):
    return ok(rule_service.list_rules(db, page, page_size, rule_status, keyword))


@router.post("/rules")
def create_rule(
    payload: RuleCreateRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_admin_role),
):
    try:
        data = rule_service.create_rule(db, payload.model_dump())
    except rule_service.RuleError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


@router.post("/rules/update")
def update_rule(
    payload: RuleUpdateRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_admin_role),
):
    try:
        data = rule_service.update_rule(db, payload.model_dump(exclude_none=False))
    except rule_service.RuleError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


@router.post("/rules/status")
def set_rule_status(
    payload: RuleStatusRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_admin_role),
):
    try:
        data = rule_service.set_status(db, payload.rule_id, payload.target_status)
    except rule_service.RuleError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


@router.post("/rules/delete")
def delete_rule(
    payload: RuleDeleteRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_admin_role),
):
    try:
        data = rule_service.delete_rule(db, payload.rule_id)
    except rule_service.RuleError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


# --------------------------------------------------------------------------
# 案件
# --------------------------------------------------------------------------
@router.get("/cases")
def list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    case_status: str | None = None,
    user_id: str | None = None,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_any_role),
):
    return ok(case_service.list_cases(db, page, page_size, case_status, user_id))


@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_any_role),
):
    try:
        data = case_service.get_case(db, case_id)
    except case_service.CaseError as exc:
        raise BizError(str(exc), 404) from exc
    return ok(data)


@router.post("/cases/review")
def review_case(
    payload: CaseReviewRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_operator_role),
):
    """审核案件：operator_id 从 JWT 取，写 review_logs 并更新案件状态。"""
    try:
        data = case_service.review_case(
            db,
            case_id=payload.case_id,
            review_result=payload.review_result,
            review_remark=payload.review_remark,
            operator_id=operator.operator_id,
        )
    except case_service.CaseError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


@router.post("/cases/resolve")
def resolve_case(
    payload: CaseResolveRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_operator_role),
):
    """标记案件处理完成（approved/rejected → resolved），同样写入 review_logs。"""
    try:
        data = case_service.resolve_case(
            db,
            case_id=payload.case_id,
            resolve_remark=payload.resolve_remark,
            operator_id=operator.operator_id,
        )
    except case_service.CaseError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


# --------------------------------------------------------------------------
# 黑名单
# --------------------------------------------------------------------------
@router.get("/blacklists")
def list_blacklists(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    blacklist_type: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_any_role),
):
    return ok(blacklist_service.list_blacklists(db, page, page_size, blacklist_type, keyword))


@router.post("/blacklists")
def add_blacklist(
    payload: BlacklistCreateRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_admin_role),
):
    try:
        data = blacklist_service.add_blacklist(db, payload.model_dump())
    except blacklist_service.BlacklistError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


@router.post("/blacklists/import")
def import_blacklists(
    payload: BlacklistImportRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_admin_role),
):
    """批量导入黑名单：items 数组或 text 文本二选一（文档 2.3.3）。"""
    items: list[dict] = []
    if payload.items:
        items = [i.model_dump() for i in payload.items]
    elif payload.text:
        items = blacklist_service.parse_import_text(payload.text)
    if not items:
        raise BizError("没有可导入的数据：请提供 items 数组或按「类型,名单值,备注」逐行填写 text", 400)
    return ok(blacklist_service.import_blacklists(db, items))


@router.post("/blacklists/delete")
def delete_blacklist(
    payload: BlacklistDeleteRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_admin_role),
):
    try:
        data = blacklist_service.delete_blacklist(db, payload.blacklist_id)
    except blacklist_service.BlacklistError as exc:
        raise BizError(str(exc), 400) from exc
    return ok(data)


# --------------------------------------------------------------------------
# 画像与看板
# --------------------------------------------------------------------------
@router.get("/users/{user_id}/profile")
def user_profile(
    user_id: str,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_any_role),
):
    return ok(profile_service.get_user_profile(db, user_id))


@router.get("/dashboard")
def dashboard(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(_any_role),
):
    return ok(dashboard_service.get_dashboard(db, days))
