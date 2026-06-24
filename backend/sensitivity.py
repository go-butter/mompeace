"""
사용자별 민감도(허용 기준) 자동 조정 모듈.

caution/avoid 판정에 대해 "도움 안 됨" 피드백이 반복되면 해당 영양소의
사용자별 기준을 소폭 완화한다. recommendation_model.py 와는 분리된 모듈로,
계산/저장 책임만 가진다.
"""
import sqlite3

ADJ_STEP = 0.05
ADJ_MIN = -0.15
ADJ_MAX = 0.15
LOOKBACK_N = 10          # 영양소별로 살펴볼 최근 관련 기록 개수
TRIGGER_RATIO = 0.6      # "도움 안 됨" 비율이 이 값 이상이면 조정
MIN_SAMPLES = 3          # 이보다 적으면 판단하지 않음

NUTRIENTS = ("caffeine", "sugar", "sodium")
_ADJ_COLUMN = {
    "caffeine": "caffeine_sensitivity_adj",
    "sugar": "sugar_sensitivity_adj",
    "sodium": "sodium_sensitivity_adj",
}


def get_user_adj(user_row: dict) -> dict:
    """users 행 dict에서 현재 민감도 조정값을 추출한다."""
    return {
        "caffeine": user_row.get("caffeine_sensitivity_adj") or 0,
        "sugar": user_row.get("sugar_sensitivity_adj") or 0,
        "sodium": user_row.get("sodium_sensitivity_adj") or 0,
    }


def recalculate_sensitivity(user_id: int, db: sqlite3.Connection) -> dict:
    """
    사용자의 최근 food_log 기록(영양소별)을 살펴보고, caution/avoid 판정에 대한
    "도움 안 됨" 비율이 TRIGGER_RATIO 이상이면 해당 영양소 기준을 ADJ_STEP만큼
    완화한다. 변경이 있을 때만 user_sensitivity_log에 기록하고 users 테이블을
    갱신한다. 최신 조정값 dict를 반환한다.
    """
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    if not user_row:
        raise ValueError(f"user_id={user_id} 사용자를 찾을 수 없습니다.")
    user_row = dict(user_row)

    current_adj = get_user_adj(user_row)

    for nutrient in NUTRIENTS:
        cursor.execute(
            """
            SELECT feedback, recommendation_status
            FROM food_log
            WHERE user_id = ? AND reason_nutrient = ? AND feedback != 0
            ORDER BY eaten_at DESC
            LIMIT ?
            """,
            (user_id, nutrient, LOOKBACK_N),
        )
        rows = [dict(r) for r in cursor.fetchall()]

        relevant = [r for r in rows if r["recommendation_status"] in ("caution", "avoid")]
        if len(relevant) < MIN_SAMPLES:
            continue

        not_helpful_ratio = sum(1 for r in relevant if r["feedback"] == -1) / len(relevant)

        # NOTE: adjustment only loosens (+ADJ_STEP) on repeated "not helpful" feedback.
        # We deliberately do not auto-tighten (-ADJ_STEP) even when helpful-feedback
        # ratio is high — intentional asymmetry to avoid over-fitting on thin data
        # during the competition timeframe. Revisit if/when more feedback volume exists.
        if not_helpful_ratio >= TRIGGER_RATIO:
            old_adj = current_adj[nutrient]
            new_adj = max(ADJ_MIN, min(ADJ_MAX, old_adj + ADJ_STEP))
            if new_adj != old_adj:
                cursor.execute(
                    f"UPDATE users SET {_ADJ_COLUMN[nutrient]} = ? WHERE user_id = ?",
                    (new_adj, user_id),
                )
                cursor.execute(
                    """
                    INSERT INTO user_sensitivity_log
                    (user_id, nutrient, old_adj, new_adj, trigger_reason)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        nutrient,
                        old_adj,
                        new_adj,
                        f"not_helpful_ratio={not_helpful_ratio:.2f} over last {len(relevant)} caution/avoid logs",
                    ),
                )
                current_adj[nutrient] = new_adj

    db.commit()
    return current_adj
