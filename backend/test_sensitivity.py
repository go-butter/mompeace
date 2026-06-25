"""
backend/sensitivity.py 의 recalculate_sensitivity() 테스트.

핵심 검증 대상:
- MIN_SAMPLES 미달이면 조정하지 않는다
- TRIGGER_RATIO 이상의 "도움 안 됨" 비율이면 ADJ_STEP만큼 완화하고 로그를 남긴다
- ADJ_MAX 를 넘어서 계속 완화되지 않는다 (클램핑)
- 조정은 완화(+) 방향만 일어난다 — "도움 됨" 비율이 높아도 자동으로 강화(-)하지 않는
  의도된 비대칭성 (코드 주석에 명시된 설계 결정)
- caution/avoid 가 아닌 기록, 또는 다른 영양소(reason_nutrient) 기록은 영향을 주지 않는다
"""
import pytest

from backend.sensitivity import (
    ADJ_MAX,
    ADJ_STEP,
    MIN_SAMPLES,
    TRIGGER_RATIO,
    recalculate_sensitivity,
)

from .conftest import make_food_log, make_user


def _log_many(db, user_id, n, feedback, recommendation_status="caution", reason_nutrient="sodium"):
    for _ in range(n):
        make_food_log(
            db, user_id,
            feedback=feedback,
            recommendation_status=recommendation_status,
            reason_nutrient=reason_nutrient,
        )


class TestRecalculateSensitivity:
    def test_no_user_raises(self, db):
        with pytest.raises(ValueError):
            recalculate_sensitivity(user_id=9999, db=db)

    def test_below_min_samples_does_not_adjust(self, db):
        user_id = make_user(db)
        # MIN_SAMPLES보다 적은 "도움 안 됨" caution 기록만 있음
        _log_many(db, user_id, n=MIN_SAMPLES - 1, feedback=-1)

        result = recalculate_sensitivity(user_id, db)

        assert result["sodium"] == 0

    def test_high_not_helpful_ratio_loosens_by_one_step(self, db):
        user_id = make_user(db)
        # TRIGGER_RATIO 이상의 "도움 안 됨" 비율, 샘플 수는 충분
        _log_many(db, user_id, n=MIN_SAMPLES, feedback=-1)

        result = recalculate_sensitivity(user_id, db)

        assert result["sodium"] == pytest.approx(ADJ_STEP)

    def test_low_not_helpful_ratio_does_not_adjust(self, db):
        user_id = make_user(db)
        # "도움 됨" 피드백이 대부분이면 (TRIGGER_RATIO 미달) 조정 없음
        _log_many(db, user_id, n=MIN_SAMPLES, feedback=1)

        result = recalculate_sensitivity(user_id, db)

        assert result["sodium"] == 0

    def test_adjustment_clamped_at_adj_max(self, db):
        # 이미 최대치 근처에 있는 사용자가 다시 트리거되어도 ADJ_MAX를 넘지 않는다
        user_id = make_user(db, sodium_sensitivity_adj=ADJ_MAX)
        _log_many(db, user_id, n=MIN_SAMPLES, feedback=-1)

        result = recalculate_sensitivity(user_id, db)

        assert result["sodium"] == ADJ_MAX

    def test_never_auto_tightens_on_high_helpful_ratio(self, db):
        # 설계상 의도된 비대칭성: "도움 됨" 비율이 100%여도 음수(강화) 방향으로는
        # 절대 자동 조정되지 않는다. 사용자가 이미 음수 조정값을 가진 상태에서도
        # 그 값이 더 내려가지 않아야 한다.
        user_id = make_user(db, sodium_sensitivity_adj=-0.1)
        _log_many(db, user_id, n=MIN_SAMPLES, feedback=1)  # 전부 "도움 됨"

        result = recalculate_sensitivity(user_id, db)

        assert result["sodium"] == -0.1  # 변화 없음, 강화 방향 조정이 없어야 함

    def test_only_caution_or_avoid_status_counts(self, db):
        # recommendation_status가 possible인 기록은 trigger 판단에서 제외되어야 한다
        user_id = make_user(db)
        _log_many(db, user_id, n=MIN_SAMPLES, feedback=-1, recommendation_status="possible")

        result = recalculate_sensitivity(user_id, db)

        assert result["sodium"] == 0

    def test_nutrients_are_independent(self, db):
        # sodium만 트리거되고 caffeine/sugar는 영향받지 않아야 한다
        user_id = make_user(db)
        _log_many(db, user_id, n=MIN_SAMPLES, feedback=-1, reason_nutrient="sodium")

        result = recalculate_sensitivity(user_id, db)

        assert result["sodium"] == pytest.approx(ADJ_STEP)
        assert result["caffeine"] == 0
        assert result["sugar"] == 0

    def test_adjustment_is_logged(self, db):
        user_id = make_user(db)
        _log_many(db, user_id, n=MIN_SAMPLES, feedback=-1)

        recalculate_sensitivity(user_id, db)

        cursor = db.cursor()
        cursor.execute(
            "SELECT * FROM user_sensitivity_log WHERE user_id = ? AND nutrient = 'sodium'",
            (user_id,),
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["old_adj"] == 0
        assert rows[0]["new_adj"] == pytest.approx(ADJ_STEP)

    def test_no_log_entry_when_no_adjustment_happens(self, db):
        user_id = make_user(db)
        _log_many(db, user_id, n=MIN_SAMPLES, feedback=1)  # 트리거 안 됨

        recalculate_sensitivity(user_id, db)

        cursor = db.cursor()
        cursor.execute(
            "SELECT * FROM user_sensitivity_log WHERE user_id = ?", (user_id,)
        )
        assert cursor.fetchall() == []

    def test_exact_trigger_ratio_boundary(self, db):
        # not_helpful_ratio가 정확히 TRIGGER_RATIO와 같을 때도 트리거되어야 한다 (>=)
        user_id = make_user(db)
        n = 10
        not_helpful = int(n * TRIGGER_RATIO)
        helpful = n - not_helpful
        _log_many(db, user_id, n=not_helpful, feedback=-1)
        _log_many(db, user_id, n=helpful, feedback=1)

        result = recalculate_sensitivity(user_id, db)

        assert result["sodium"] == pytest.approx(ADJ_STEP)
