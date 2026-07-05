"""임산부 1일 영양소 섭취 절대 기준값 (트라이메스터 불변, 앱 내부 보수적 기준).
- 카페인 200mg/day: ACOG/WHO
- 당류 50g/day: WHO (2000kcal 기준 10% 미만)
- 나트륨 2300mg/day: KDRI 만성질환위험감소섭취량(CDRR)

트라이메스터는 caution 민감도(early 카페인 60%, late 나트륨 80%, apply_safety_guard())에만
영향을 주며, 아래 절대 기준값 자체는 트라이메스터와 무관하게 항상 동일하다.
"""
DAILY_CAFFEINE_LIMIT_MG = 200.0
DAILY_SUGAR_LIMIT_G = 50.0
DAILY_SODIUM_LIMIT_MG = 2300.0

TRIMESTER_NOTES = {
    "early": "임신 초기에는 카페인 섭취량과 알레르기 유발 성분을 특히 꼼꼼히 확인해 주세요.",
    "middle": "임신 중기에는 당류 섭취가 누적되지 않도록 확인하고, 카페인 섭취량도 함께 관리해 주세요.",
    "late": "임신 후기에는 나트륨과 당류 섭취가 과도하게 누적되지 않도록 주의해 주세요.",
}
