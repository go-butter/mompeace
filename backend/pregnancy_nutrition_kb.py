"""
docs/임신_시기별_영양소_섭취기준_최종.md, docs/임신_관련_정보.md 에서만 가져온 참고
자료 — ai_report_summary.py가 판정(rule_messages/nutrient_items)에 실천 조언을
붙이기 위해 Gemini 프롬프트에 얹는다.

숫자(기준치/상한/하한/횟수/용량)는 단 하나도 담지 않는다. 이유는 두 가지다.
1) 기준치는 nutrition_constants.py/intake_totals.py가 유일한 출처여야 한다 —
   이 파일이 숫자를 갖고 있으면 판정 엔진과 다른 숫자가 섞여 들어갈 위험이 생긴다.
   카페인이 대표 사례: 임신_관련_정보.md는 식약처 2011년 자료의 300mg을 쓰지만,
   이 앱은 ACOG/WHO 200mg을 쓰기로 이미 결정했다(nutrition_constants.py,
   docs/임신_시기별_영양소_섭취기준_최종.md 변경 이력 참고) — 이 파일에 300mg이
   들어가면 그 결정을 조용히 뒤집는 셈이 된다.
2) 하루 4~6회, 1~1.5L 같은 빈도/용량 수치도 뺐다 — 영양소 기준치는 아니지만,
   출처 문서 두 곳이 같은 내용을 서로 다른 단위(리터 vs 컵)로 적어 놓아 숫자를
   그대로 옮기면 두 문서 중 하나를 조용히 고르는 셈이 된다. "여러 번 나눠",
   "충분한 수분"처럼 정성적 표현으로만 남긴다.

get_ai_report_analysis()가 build_kb_excerpts()로 "이번 응답에 실제로 등장한
영양소 키 + 임신 시기"에 맞는 문단만 골라 프롬프트에 넣는다 — 등장하지 않은
영양소의 조언까지 보내면 모델이 판정되지 않은 영양소에 대해서도 조언을
만들어낼 여지가 생긴다.
"""
from __future__ import annotations

# ── 영양소별 급원식품 ──
# 판정 대상 8개 영양소 중 "무엇을 더 먹으면 좋은지"가 말이 되는 것만 담는다.
# 카페인/당류/나트륨/에너지는 "줄이거나 관리하는" 문제라 여기 없다 — 아래
# *_NOTE/SODIUM_REDUCTION_TIPS 쪽에 있다.
#
# calcium은 이 앱이 판정하는 8개 영양소(NUTRIENT_SUMMARY_FIELDS)에 없어
# build_kb_excerpts()가 절대 고르지 않는다 — 그래도 남겨 둔다. 두 출처 문서 모두
# 철분(중기 핵심 영양소)을 설명할 때 칼슘을 바로 옆에서 함께 다루고 있어(우유·
# 치즈·멸치·뱅어포·두부), 이 앱이 나중에 칼슘을 추적하게 되거나 철분 조언에
# 칼슘 급원을 곁들이기로 하면 바로 쓸 수 있는 상태로 두는 편이 다시 원문을
# 찾아 옮기는 것보다 싸다.
NUTRIENT_FOOD_SOURCES: dict[str, str] = {
    "iron": (
        "육류, 조개류(재첩·바지락·굴 등), 진한 녹색 채소, 콩류, 달걀에 풍부합니다. "
        "조개류·육류는 식중독 예방을 위해 완전히 익혀서 섭취합니다."
    ),
    "protein": (
        "육류, 가금류, 생선, 달걀, 우유 및 유제품(치즈·요구르트), 콩류 등에 풍부합니다."
    ),
    # 원문(두 출처 문서 모두)은 "오메가-3 EPA·DHA"라고 쓰지만, "오메가-3"의 숫자
    # 3은 지방산 분류명의 일부이지 영양 기준치가 아니다 — 그래도 "숫자를 단
    # 하나도 담지 않는다"는 요구를 문자 그대로 지키기 위해 EPA·DHA 명칭만으로
    # 충분히 식별되는 이 표현에서는 뺀다.
    "fat": (
        "필수 지방산인 EPA·DHA는 고등어, 멸치, 오징어, 꽁치, 달걀에 풍부합니다."
    ),
    "carbohydrate": (
        "곡류가 주요 급원이며, 포도당은 태아에게 가장 중요한 에너지원입니다."
    ),
    # NUTRIENT_SUMMARY_FIELDS에 없어 build_kb_excerpts()가 고르지 않는다(위 설명 참고).
    "calcium": (
        "우유, 요구르트 등 유제품과 멸치, 뱅어포, 두부 등에 풍부합니다."
    ),
}

# ── 흡수 상호작용 ──
IRON_ABSORPTION_NOTE = (
    "비타민 C가 풍부한 식품(과일, 과일주스 등)과 함께 먹으면 철 흡수가 촉진됩니다. "
    "탄닌 성분(커피·홍차·녹차)은 흡수를 방해하므로 식사 직후에는 피합니다."
)
CAFFEINE_ABSORPTION_NOTE = (
    "카페인은 칼슘·철분 등의 흡수를 방해하고, 이뇨 작용으로 수분 손실을 유발할 수 있습니다."
)
# calcium과 마찬가지로 build_kb_excerpts()가 지금은 고르지 않는다(칼슘 미판정).
CALCIUM_ABSORPTION_NOTE = "칼슘은 비타민 D와 함께 섭취하면 체내 흡수율이 높아집니다."

# ── 나트륨 관리 습관 (식품군이 아니라 "줄이는 습관" 자체가 핵심) ──
SODIUM_REDUCTION_TIPS = (
    "찌개, 젓갈, 가공식품(햄, 생선 통조림)처럼 염분이 높은 음식을 줄이고, "
    "조리할 때 소금·간장·된장 같은 양념도 평소보다 적게 씁니다."
)

# ── 임신 시기별 특이 증상과 대처 ──
# get_trimester_limits()가 쓰는 것과 같은 값(early/middle/late)을 키로 쓴다.
TRIMESTER_NOTES: dict[str, str] = {
    "early": (
        "임신 초기에는 입덧(메스꺼움·구토)이 흔합니다. 여러 번 나눠 소량씩 먹고, "
        "기름지거나 향이 강한 음식은 피하며, 물은 식사 중보다 식사 사이에 "
        "마시는 것이 도움이 됩니다."
    ),
    "middle": (
        "임신 중기에는 혈액량이 늘며 상대적으로 적혈구가 희석돼(혈액 희석 현상) "
        "철 결핍성 빈혈이 생기기 쉬운 시기입니다. 철이 풍부한 음식을 비타민 C와 "
        "함께 챙기는 것이 특히 중요합니다."
    ),
    "late": (
        "임신 후기에는 커진 자궁이 장을 눌러 변비가 흔합니다. 충분한 수분과 "
        "섬유소가 풍부한 잡곡·채소·과일·해조류, 규칙적인 신체 활동이 도움이 됩니다."
    ),
}


def build_kb_excerpts(nutrient_keys: list[str], trimester: str) -> list[str]:
    """이번 응답에 실제로 등장한 영양소 키(nutrient_items의 caffeine + nutrients
    순서)와 임신 시기에 맞는 문단만 골라 돌려준다. 순서는 입력 순서를 따르고,
    시기 특이사항은 항상 맨 뒤에 붙는다.
    """
    excerpts: list[str] = []
    for key in nutrient_keys:
        source = NUTRIENT_FOOD_SOURCES.get(key)
        if source:
            excerpts.append(f"[{key} 급원식품] {source}")
    if "iron" in nutrient_keys:
        excerpts.append(f"[철분 흡수] {IRON_ABSORPTION_NOTE}")
    if "caffeine" in nutrient_keys:
        excerpts.append(f"[카페인 주의] {CAFFEINE_ABSORPTION_NOTE}")
    if "sodium" in nutrient_keys:
        excerpts.append(f"[나트륨 줄이기] {SODIUM_REDUCTION_TIPS}")
    trimester_note = TRIMESTER_NOTES.get(trimester)
    if trimester_note:
        excerpts.append(f"[이 시기 특이사항] {trimester_note}")
    return excerpts
