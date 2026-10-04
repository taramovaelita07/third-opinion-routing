"""Explicit demo routing rules.

These rules describe an organizational next step for the hackathon prototype.
They are not diagnostic guidelines and require clinical validation before any
production use.
"""

from dataclasses import dataclass

from app.models import Modality, RoutingPriority


@dataclass(frozen=True)
class RoutingRule:
    rule_id: str
    modality: Modality
    finding_code: str
    priority: RoutingPriority
    action: str
    specialty: str
    timeframe: str
    reason: str
    prerequisites: tuple[str, ...] = ()
    red_flags: tuple[str, ...] = ()


# Order is intentional: when several findings are present, the first matching
# rule represents the highest-priority draft route.
ROUTING_RULES: tuple[RoutingRule, ...] = (
    RoutingRule(
        rule_id="CT_PNEUMOTHORAX_URGENT_REVIEW",
        modality=Modality.CT_CHEST,
        finding_code="CT_PNEUMOTHORAX",
        priority=RoutingPriority.URGENT,
        action="Организовать срочную очную клиническую оценку",
        specialty="Дежурный врач / торакальный хирург",
        timeframe="В тот же день",
        reason=(
            "Во входном результате ИИ структурировано указание на свободный газ "
            "в плевральной полости"
        ),
        prerequisites=(
            "Проверить клиническое состояние пациента",
            "Подтвердить результат врачом до отправки пациенту",
        ),
        red_flags=("Возможный пневмоторакс",),
    ),
    RoutingRule(
        rule_id="MMG_SUSPICIOUS_PRIORITY_REVIEW",
        modality=Modality.MAMMOGRAPHY,
        finding_code="MMG_SUSPICIOUS_FINDING",
        priority=RoutingPriority.PRIORITY,
        action="Организовать консультацию для уточнения дальнейшей тактики",
        specialty="Маммолог / онколог-маммолог",
        timeframe="В течение 14 дней",
        reason=(
            "Структурированные данные ИИ содержат подозрительную находку или "
            "категорию BI-RADS 4–5"
        ),
        prerequisites=(
            "Проверить изображения и заключение врачом-рентгенологом",
            "Приложить предыдущее исследование при наличии",
        ),
    ),
    RoutingRule(
        rule_id="CT_LUNG_NODULE_SPECIALIST_REVIEW",
        modality=Modality.CT_CHEST,
        finding_code="CT_LUNG_NODULE",
        priority=RoutingPriority.PRIORITY,
        action="Организовать консультацию для определения дальнейшего наблюдения",
        specialty="Пульмонолог",
        timeframe="В течение 14 дней",
        reason="Во входном результате ИИ структурировано очаговое образование лёгкого",
        prerequisites=(
            "Врачебно подтвердить находку и её размеры",
            "Сопоставить с предыдущими исследованиями при наличии",
        ),
    ),
    RoutingRule(
        rule_id="MMG_BENIGN_ROUTINE_REVIEW",
        modality=Modality.MAMMOGRAPHY,
        finding_code="MMG_BENIGN_FINDING",
        priority=RoutingPriority.ROUTINE,
        action="Продолжить плановое наблюдение по решению лечащего врача",
        specialty="Маммолог / лечащий врач",
        timeframe="В плановом порядке",
        reason=(
            "Структурированные данные ИИ соответствуют доброкачественной "
            "категории BI-RADS 2"
        ),
        prerequisites=("Подтвердить категорию врачом-рентгенологом",),
    ),
)

