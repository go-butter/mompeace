"""backend/caffeine_relevance.py 의 3단계 카페인 관련성 판정 테스트.

두 종류의 테스트가 들어 있다:

1. 순수 함수 테스트 — DB 없이 classify_caffeine_relevance()의 분기만 검증한다.
2. 실제 mompeace.db 대조 테스트 — 하드코딩된 subcategory 목록이 실제 데이터와
   여전히 맞는지 확인한다. import_dish_db.py가 엑셀을 다시 임포트하면서 subcategory
   이름이 바뀌거나 사라지면 이 테스트가 시끄럽게 깨져야 한다.

2번이 필요한 이유는 이 저장소에 이미 전례가 있기 때문이다: pregnancy_limits 테이블은
DB에 3행이 남아 있지만 어떤 코드도 참조하지 않고, 값도 낡은 채(당류 30/40g, 나트륨
2000/1800mg — 현재 기준은 50g/1500mg) 아무 경고 없이 방치돼 있었다. 참조도 검증도
없으면 조용히 썩는다.

DB 파일이 없는 환경(CI 등)에서는 2번을 건너뛴다. 다만 파일이 있으면 반드시 돈다 —
"없으면 통과"가 아니라 "없으면 실행 안 함"이어야 로컬에서 드리프트를 잡을 수 있다.
"""
import sqlite3
from pathlib import Path

import pytest

from backend.caffeine_relevance import (
    CAFFEINE_FREE_SUBCATEGORIES,
    CAFFEINE_POSSIBLE_SUBCATEGORIES,
    FULLY_FREE_CATEGORIES,
    MEASURED_CATEGORIES,
    TIER_CAFFEINE_FREE,
    TIER_CAFFEINE_POSSIBLE,
    TIER_NOT_MEASURED,
    classify_caffeine_relevance,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / "mompeace.db"
_ALLOWED_SOURCE = "dish_db_download"

requires_real_db = pytest.mark.skipif(
    not _DB_PATH.exists(),
    reason=f"실제 DB({_DB_PATH})가 없는 환경에서는 데이터 대조 테스트를 건너뛴다",
)

# 측정 대상 카테고리 안에서 명시 목록에 없어 기본값(POSSIBLE)으로 떨어지는
# subcategory 개수. 실측 근거가 0건이라 티어를 근거로 정할 수 없는 것들이며,
# 재임포트로 새 subcategory가 생기면 이 숫자가 움직여 눈에 띄어야 한다.
# 빵 및 과자류는 FULLY_FREE_CATEGORIES라 목록 자체를 보지 않으므로 여기서 제외된다.
EXPECTED_DEFAULTED_SUBCATEGORY_COUNT = 15

# 실제 DB의 25개 카테고리에서 측정 대상 3개를 뺀 나머지 전부.
UNMEASURED_CATEGORIES = (
    "국 및 탕류", "생채·무침류", "볶음류", "튀김류", "밥류", "면 및 만두류",
    "찌개 및 전골류", "구이류", "나물·숙채류", "조림류", "전·적 및 부침류",
    "찜류", "죽 및 스프류", "김치류", "장류, 양념류", "장아찌·절임류",
    "젓갈류", "수·조·어·육류", "곡류, 서류 제품", "과일류",
    "두류, 견과 및 종실류", "채소, 해조류",
)


@pytest.fixture(scope="module")
def real_db():
    conn = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ── 순수 함수: 티어 분기 ──────────────────────────────────

class TestNotMeasured:
    @pytest.mark.parametrize("category", UNMEASURED_CATEGORIES)
    def test_unmeasured_categories(self, category):
        assert classify_caffeine_relevance(category, "아무거나") == TIER_NOT_MEASURED

    def test_unmeasured_category_count_is_22(self):
        # 실제 DB의 25개 카테고리 중 측정 대상 3개를 뺀 나머지.
        assert len(UNMEASURED_CATEGORIES) == 22
        assert not (set(UNMEASURED_CATEGORIES) & MEASURED_CATEGORIES)

    def test_none_category_is_not_measured(self):
        # 분류를 모르는 입력에 대해 근거 없는 카페인 경고를 만들지 않는다.
        assert classify_caffeine_relevance(None, None) == TIER_NOT_MEASURED

    def test_unknown_category_is_not_measured(self):
        assert classify_caffeine_relevance("존재하지 않는 분류", "커피") == TIER_NOT_MEASURED

    def test_subcategory_is_ignored_when_category_is_unmeasured(self):
        # subcategory 단독으로는 키가 될 수 없다 — 카테고리가 먼저다.
        assert classify_caffeine_relevance("국 및 탕류", "커피") == TIER_NOT_MEASURED


class TestFullyFreeCategory:
    @pytest.mark.parametrize("subcategory", ["케이크", "마카롱", "피자", "초콜릿", "모카빵", None])
    def test_bakery_is_free_regardless_of_subcategory(self, subcategory):
        assert classify_caffeine_relevance("빵 및 과자류", subcategory) == TIER_CAFFEINE_FREE


class TestBeverageSubcategories:
    @pytest.mark.parametrize("subcategory", sorted(CAFFEINE_FREE_SUBCATEGORIES["음료 및 차류"]))
    def test_listed_free_subcategories(self, subcategory):
        assert classify_caffeine_relevance("음료 및 차류", subcategory) == TIER_CAFFEINE_FREE

    @pytest.mark.parametrize("subcategory", sorted(CAFFEINE_POSSIBLE_SUBCATEGORIES["음료 및 차류"]))
    def test_listed_possible_subcategories(self, subcategory):
        assert classify_caffeine_relevance("음료 및 차류", subcategory) == TIER_CAFFEINE_POSSIBLE

    def test_herbal_tea_is_possible_not_free(self):
        # 실측 95행 중 14행이 0 초과(최대 117mg)이고, 자스민티(녹차)·얼그레이(홍차)가
        # 이 분류에 묶여 있다. 이름만 보고 FREE로 두면 안 되는 대표 사례.
        assert classify_caffeine_relevance("음료 및 차류", "허브차") == TIER_CAFFEINE_POSSIBLE

    def test_mate_tea_is_possible_despite_all_zero_samples(self):
        # 실측 4행이 전부 0.0이지만 표본이 너무 얇아 안전한 쪽을 택했다.
        assert classify_caffeine_relevance("음료 및 차류", "마테차") == TIER_CAFFEINE_POSSIBLE

    @pytest.mark.parametrize("subcategory", [
        "액상커피", "커피(타먹는커피)", "카페라떼", "아이스 카페라떼",
        "두유 카페라떼", "카페모카", "아이스 카페모카", "밀크티",
    ])
    def test_unlisted_but_obviously_caffeinated_defaults_to_possible(self, subcategory):
        # 실측 0건이라 목록에 없지만, 기본값이 POSSIBLE이라 조용히 0으로 처리되지 않는다.
        assert classify_caffeine_relevance("음료 및 차류", subcategory) == TIER_CAFFEINE_POSSIBLE

    def test_unknown_subcategory_defaults_to_possible(self):
        assert classify_caffeine_relevance("음료 및 차류", "한번도 본 적 없는 분류") == TIER_CAFFEINE_POSSIBLE

    def test_none_subcategory_in_measured_category_defaults_to_possible(self):
        assert classify_caffeine_relevance("음료 및 차류", None) == TIER_CAFFEINE_POSSIBLE

    def test_near_duplicate_names_resolve_independently(self):
        # 정확 일치로만 조회하므로 근사 중복은 서로 다른 항목으로 취급된다.
        # 미숫가루는 실측 6행 전부 0이라 FREE, 미숫가루(선식)음료는 실측 0건이라 기본값.
        assert classify_caffeine_relevance("음료 및 차류", "미숫가루") == TIER_CAFFEINE_FREE
        assert classify_caffeine_relevance("음료 및 차류", "미숫가루(선식)음료") == TIER_CAFFEINE_POSSIBLE

    def test_substring_does_not_leak_between_subcategories(self):
        # "커피"가 "액상커피"의 부분문자열이지만 부분문자열 매칭을 쓰지 않는다.
        # 둘 다 POSSIBLE이므로 결과가 아니라 경로로 확인한다.
        assert "액상커피" not in CAFFEINE_POSSIBLE_SUBCATEGORIES["음료 및 차류"]
        assert classify_caffeine_relevance("음료 및 차류", "액상커피") == TIER_CAFFEINE_POSSIBLE


class TestDairySubcategories:
    @pytest.mark.parametrize("subcategory", sorted(CAFFEINE_FREE_SUBCATEGORIES["유제품류 및 빙과류"]))
    def test_listed_free_subcategories(self, subcategory):
        assert classify_caffeine_relevance("유제품류 및 빙과류", subcategory) == TIER_CAFFEINE_FREE

    @pytest.mark.parametrize("subcategory", sorted(CAFFEINE_POSSIBLE_SUBCATEGORIES["유제품류 및 빙과류"]))
    def test_listed_possible_subcategories(self, subcategory):
        assert classify_caffeine_relevance("유제품류 및 빙과류", subcategory) == TIER_CAFFEINE_POSSIBLE

    def test_ice_cream_is_possible(self):
        # 아포가토 120mg — 1일 기준 200mg의 60%. 디저트라고 무시할 수 없다.
        assert classify_caffeine_relevance("유제품류 및 빙과류", "아이스크림") == TIER_CAFFEINE_POSSIBLE


class TestTableConsistency:
    def test_free_and_possible_lists_do_not_overlap(self):
        for category in set(CAFFEINE_FREE_SUBCATEGORIES) | set(CAFFEINE_POSSIBLE_SUBCATEGORIES):
            free = CAFFEINE_FREE_SUBCATEGORIES.get(category, frozenset())
            possible = CAFFEINE_POSSIBLE_SUBCATEGORIES.get(category, frozenset())
            assert not (free & possible), f"{category}에서 중복 분류: {free & possible}"

    def test_listed_categories_are_all_measured(self):
        for category in set(CAFFEINE_FREE_SUBCATEGORIES) | set(CAFFEINE_POSSIBLE_SUBCATEGORIES):
            assert category in MEASURED_CATEGORIES

    def test_fully_free_categories_have_no_subcategory_lists(self):
        # FULLY_FREE는 목록을 보지 않고 반환하므로, 목록을 두면 죽은 데이터가 된다.
        for category in FULLY_FREE_CATEGORIES:
            assert category not in CAFFEINE_FREE_SUBCATEGORIES
            assert category not in CAFFEINE_POSSIBLE_SUBCATEGORIES


# ── 실제 DB 대조: 드리프트 감지 ────────────────────────────

@requires_real_db
class TestAgainstRealData:
    def test_no_caffeine_value_outside_measured_categories(self, real_db):
        """TIER_NOT_MEASURED 규칙의 근거 자체를 검증한다.

        측정 대상 3개 카테고리 밖에 카페인 값이 하나라도 생기면, "이 종류는 잰 적이
        없다"는 전제가 깨진 것이므로 티어 테이블을 다시 그려야 한다.
        """
        placeholders = ", ".join("?" for _ in MEASURED_CATEGORIES)
        rows = real_db.execute(
            f"SELECT food_name, category, subcategory, caffeine_mg FROM food_items "
            f"WHERE caffeine_mg IS NOT NULL AND category NOT IN ({placeholders})",
            tuple(MEASURED_CATEGORIES),
        ).fetchall()
        assert rows == [], (
            "측정 대상 밖 카테고리에 카페인 값이 생겼다 — TIER_NOT_MEASURED 전제가 깨졌다: "
            + ", ".join(f"{r['category']}/{r['subcategory']} {r['food_name']}={r['caffeine_mg']}" for r in rows[:10])
        )

    def test_measured_categories_still_exist(self, real_db):
        actual = {r["category"] for r in real_db.execute(
            "SELECT DISTINCT category FROM food_items WHERE data_source = ?", (_ALLOWED_SOURCE,)
        )}
        missing = MEASURED_CATEGORIES - actual
        assert not missing, f"food_items에서 사라진 카테고리: {missing}"

    def test_category_universe_is_fully_accounted_for(self, real_db):
        """실제 카테고리 25개가 측정 대상 3개 + 미측정 22개로 정확히 나뉘는지 확인한다.

        재임포트로 새 카테고리가 생기면 그것도 NOT_MEASURED로 처리되는데, 그게 맞는지는
        사람이 봐야 한다 (새 카테고리에 카페인 값이 있을 수도 있다).
        """
        actual = {r["category"] for r in real_db.execute(
            "SELECT DISTINCT category FROM food_items WHERE data_source = ?", (_ALLOWED_SOURCE,)
        )}
        known = MEASURED_CATEGORIES | set(UNMEASURED_CATEGORIES)
        assert actual == known, (
            f"카테고리 목록이 달라졌다. 새로 생김: {sorted(actual - known)} / "
            f"사라짐: {sorted(known - actual)}"
        )

    @pytest.mark.parametrize("category,subcategory", sorted(
        [(c, s) for c, subs in CAFFEINE_FREE_SUBCATEGORIES.items() for s in subs]
        + [(c, s) for c, subs in CAFFEINE_POSSIBLE_SUBCATEGORIES.items() for s in subs]
    ))
    def test_every_listed_subcategory_still_exists(self, real_db, category, subcategory):
        """하드코딩한 subcategory 키가 실제 데이터에 여전히 존재하는지 확인한다.

        재임포트로 이름이 바뀌면(예: "밀크티/버블티" → "밀크티") 그 항목은 조용히
        기본값으로 떨어져 아무도 모르게 분류가 달라진다. 여기서 먼저 깨뜨린다.
        """
        count = real_db.execute(
            "SELECT COUNT(*) FROM food_items WHERE category = ? AND subcategory = ?",
            (category, subcategory),
        ).fetchone()[0]
        assert count > 0, (
            f"티어 테이블의 ({category}, {subcategory})가 food_items에 없다 — "
            f"재임포트로 이름이 바뀌었거나 사라졌다"
        )

    def test_defaulted_subcategory_count_is_pinned(self, real_db):
        """명시 목록에 없어 기본값으로 떨어지는 subcategory 개수를 고정한다.

        기본값 자체는 의도된 설계지만(실측 0건이라 근거로 티어를 못 정함), 그 집합이
        조용히 커지는 것은 다른 문제다. 재임포트로 새 subcategory가 생기면 여기서
        걸려서 사람이 한 번 보고 목록에 넣을지 결정하게 한다.
        """
        defaulted = []
        for category in sorted(MEASURED_CATEGORIES - FULLY_FREE_CATEGORIES):
            listed = (
                CAFFEINE_FREE_SUBCATEGORIES.get(category, frozenset())
                | CAFFEINE_POSSIBLE_SUBCATEGORIES.get(category, frozenset())
            )
            actual = {r["subcategory"] for r in real_db.execute(
                "SELECT DISTINCT subcategory FROM food_items "
                "WHERE category = ? AND data_source = ?",
                (category, _ALLOWED_SOURCE),
            )}
            defaulted.extend(sorted(actual - listed))

        assert len(defaulted) == EXPECTED_DEFAULTED_SUBCATEGORY_COUNT, (
            f"기본값(POSSIBLE)으로 떨어지는 subcategory 개수가 "
            f"{EXPECTED_DEFAULTED_SUBCATEGORY_COUNT}에서 {len(defaulted)}로 바뀌었다. "
            f"현재 목록: {defaulted}"
        )

    def test_all_real_subcategories_classify_without_error(self, real_db):
        # 실제 데이터 전 행을 한 번씩 통과시켜 예외가 나지 않는지 확인한다.
        rows = real_db.execute(
            "SELECT DISTINCT category, subcategory FROM food_items"
        ).fetchall()
        tiers = {classify_caffeine_relevance(r["category"], r["subcategory"]) for r in rows}
        assert tiers <= {TIER_NOT_MEASURED, TIER_CAFFEINE_FREE, TIER_CAFFEINE_POSSIBLE}
