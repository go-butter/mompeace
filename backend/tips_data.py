"""임신 트라이메스터별/공통 건강 정보 팁 (홈 화면 정보 라이브러리용, 정적 데이터).

단일 진실 공급원(single source of truth) 원칙 — 이 파일 외 다른 곳에 중복 데이터를
두지 않는다 (nutrition_constants.py, coffee_caffeine_data.py 패턴 참조).

TRIMESTER_TIPS의 키("early"/"middle"/"late")는 backend.intake_totals.get_trimester_limits()의
반환값과 정확히 일치해야 한다.

출처: 대한영양사협회 임상영양관리지침서(2008), 보건복지부·한국건강증진개발원
임신기 영양관리(2018), WHO Healthy Eating during Pregnancy and Breastfeeding(2001)
"""

TRIMESTER_TIPS: dict[str, list[dict]] = {
    "early": [
        {"category": "입덧 관리", "content": "하루 4~6번 조금씩 자주 드세요"},
        {"category": "입덧 관리", "content": "기름지지 않고 소화가 잘 되는 음식을 선택하세요"},
        {"category": "입덧 관리", "content": "찬 음식은 냄새가 덜해 입덧 완화에 도움이 돼요"},
        {"category": "입덧 관리", "content": "강한 향신료가 들어간 음식은 피하는 게 좋아요"},
        {"category": "입덧 관리", "content": "물은 식사 중보다 식사와 식사 사이에 마셔보세요"},
        {"category": "엽산", "content": "엽산은 착상 후 21~27일 사이 특히 중요해요, 임신 초기 보충제를 권장해요"},
    ],
    "middle": [
        {"category": "빈혈 예방", "content": "철분이 풍부한 육류, 조개류, 콩류, 녹색 채소를 챙기세요"},
        {"category": "빈혈 예방", "content": "철 흡수를 돕는 비타민C 식품(과일, 과일주스)을 함께 드세요"},
        {"category": "빈혈 예방", "content": "식사 후 커피·홍차·녹차는 철 흡수를 방해할 수 있어요"},
        {"category": "빈혈 예방", "content": "철결핍빈혈이 있다면 보충제 복용을 고려해보세요"},
        {"category": "칼슘", "content": "우유 3컵 정도로 칼슘을 챙기면 좋아요, 비타민D와 함께면 흡수율이 올라가요"},
    ],
    "late": [
        {"category": "변비 예방", "content": "하루 1~1.5L 정도 수분을 섭취하세요"},
        {"category": "변비 예방", "content": "잡곡·두유·과일·채소·해조류로 섬유소를 늘려보세요"},
        {"category": "변비 예방", "content": "규칙적인 운동이 변비 예방에 도움이 돼요"},
        {"category": "변비 예방", "content": "의사 처방 없이 변비약을 임의로 쓰지 마세요"},
        {"category": "단백질", "content": "임신 후기엔 단백질이 특히 중요해요, 하루 세 끼 결식 없이 챙기세요"},
        {"category": "당류 주의", "content": "간식은 소량씩 자주, 당류는 과하지 않게 드세요"},
    ],
}

COMMON_TIPS: list[dict] = [
    {"content": "익히지 않은 달걀·생선·고기·조개류·새싹채소는 식중독 위험이 있어 주의하세요"},
    {"content": "상어·황새치·냉동참치 등 메틸수은 함량이 높은 생선은 주 1회 이하로 드세요"},
    {"content": "술은 임신 중 절대 금지예요"},
    {"content": "짠 음식은 피하고 되도록 싱겁게 드세요"},
    {"content": "하루 세 번 규칙적으로 식사하세요"},
    {"content": "단백질·채소/과일·유제품을 매일 균형 있게 챙기세요"},
    {"content": "규칙적인 신체활동을 이어가세요"},
]
