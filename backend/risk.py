from datetime import date, datetime
from typing import Optional

MAX_PREGNANCY_WEEK = 42


def calculate_current_pregnancy_age(
    entered_week: Optional[int],
    entered_day: Optional[int],
    entered_at_str: Optional[str],
    today: Optional[date] = None,
) -> dict:
    """
    entered_at_str(앵커 날짜)부터 today까지의 경과일을 entered_week/entered_day에
    더해 "오늘" 기준 임신 주차/일을 계산한다. 앵커가 없으면 더할 기준이 없으므로
    입력값을 그대로 반환한다.
    """
    if entered_week is None or entered_at_str is None:
        return {"week": entered_week or 0, "day": entered_day or 0}

    today = today or date.today()
    entered_at = datetime.strptime(entered_at_str, "%Y-%m-%d").date()
    elapsed_days = (today - entered_at).days
    total_days = entered_week * 7 + (entered_day or 0) + elapsed_days
    week = min(total_days // 7, MAX_PREGNANCY_WEEK)
    day = total_days % 7
    return {"week": max(week, 0), "day": day}


def calculate_days_until_due(due_date_str: Optional[str], today: Optional[date] = None) -> Optional[int]:
    """출산 예정일까지 남은 일수. due_date_str이 없으면 None."""
    if due_date_str is None:
        return None
    today = today or date.today()
    due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
    return (due - today).days


def get_trimester(week: int):
    """
    임신 주차를 초기/중기/후기로 변환
    """
    if week <= 12:
        return "early"
    elif week <= 27:
        return "middle"
    else:
        return "late"
