"""
리포트 카드의 AI 분석(2단계). 규칙 엔진(intake_totals.py)이 이미 내린 판정
(nutrient_items, rule_messages)을 Gemini에게 "설명"만 맡긴다 — 안전 판정이나
기준치를 다시 내리거나 새로 만들어내지 않는다 (design doc §13, 원칙 ①: 규칙
엔진이 판정하고 LLM은 그 결과를 설명만 한다).

gemini_vision.py(OCR 추출 경로)와는 완전히 분리된 모듈이다 — 그 파일은 이미지에서
구조화된 필드를 뽑는 별개 관심사라 여기 때문에 수정하지 않는다. 호출 쿼터·mock
플래그·예외 클래스도 전부 독립적으로 둔다(ocr_category_classifier.py가 OCR 추출과
분류 호출을 분리한 것과 같은 이유 — 이 기능이 OCR 쿼터를 먹거나, 반대로 OCR이
이 기능의 쿼터를 먹어서는 안 된다).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field

from backend.intake_totals import NUTRIENT_SUMMARY_FIELDS
from backend.pregnancy_nutrition_kb import build_kb_excerpts

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# gemini-2.5-flash는 신규 API 키에 더 이상 제공되지 않는다(운영 로그에서 확인된
# 404: "This model models/gemini-2.5-flash is no longer available to new
# users"). gemini_vision.py가 이미 실제로 성공시키고 있는 모델로 맞춘다 — 그
# 모듈은 이미지+텍스트, 이 모듈은 텍스트 전용이라 호출 모양은 다르지만, 둘 다
# GenerateContentConfig에 response_mime_type/response_schema만 쓰고
# temperature/top_p/top_k/thinking_budget 같은 2.5 전용 파라미터는 쓰지 않으므로
# 모델명만 바꾸면 된다.
GEMINI_MODEL_NAME = "gemini-3.6-flash"

# gemini_vision.py/ocr_category_classifier.py와 같은 패턴 — 프로세스 메모리 카운터,
# 재시작하면 초기화된다. 이 기능 전용 하루 호출 상한이라 OCR 추출/분류 쿼터와
# 서로 잠식하지 않는다.
GEMINI_REPORT_DAILY_CALL_LIMIT = int(os.getenv("GEMINI_REPORT_DAILY_CALL_LIMIT", "30"))
_call_count_by_day: dict[str, int] = {}

# 오프라인 개발/테스트용. 기본 false(실제 호출) — routers/ocr.py의 OCR_USE_MOCK_GEMINI와
# 같은 이유로 상수가 아니라 환경변수(실제 키가 확인되면 코드 수정 없이 되돌릴 수 있어야
# 켜둔 채로 잊혀도 덜 위험하다).
REPORT_AI_USE_MOCK_GEMINI = os.getenv("REPORT_AI_USE_MOCK_GEMINI", "false").lower() == "true"
# import 시점 값을 한 번 찍어 둔다 — 이 플래그는 모듈 레벨에서 한 번만 읽히므로
# (get_ai_report_analysis 안에서 매 요청마다 다시 읽지 않는다), .env를 고쳐도
# 프로세스를 재시작하지 않으면 반영되지 않는다. 기동 로그에 실제 반영된 값이
# 보이면 "고쳤는데 왜 그대로지" 상태를 바로 구분할 수 있다.
print(f"[ai_report_summary] REPORT_AI_USE_MOCK_GEMINI={REPORT_AI_USE_MOCK_GEMINI} (재시작 전까지 고정)")


class AiReportSummaryDailyLimitExceededError(Exception):
    """하루 리포트 AI 설명 호출 상한을 초과한 경우.

    gemini_vision.py의 GeminiDailyLimitExceededError를 재사용하지 않는다 — 그 예외의
    의미는 "OCR 인식 횟수 초과"에 고정되어 있어, 이 기능(리포트 설명)에 그대로 쓰면
    로그/디버깅 시 원인을 잘못 짚게 된다. 이 예외는 라우터까지 올라가지 않는다 —
    get_ai_report_analysis()가 여기서 잡아 rule_based로 내려간다(카드는 절대 에러
    상태를 보여주지 않는다는 원칙, routers/report.py는 별도 try/except가 필요 없다).
    """


def _under_daily_limit() -> bool:
    today = date.today().isoformat()
    return _call_count_by_day.get(today, 0) < GEMINI_REPORT_DAILY_CALL_LIMIT


def _record_call() -> None:
    today = date.today().isoformat()
    _call_count_by_day[today] = _call_count_by_day.get(today, 0) + 1


# system_instruction으로 전달한다(gemini_vision.py/ocr_category_classifier.py는
# 이미지가 있거나 응답이 단일 enum이라 지시문을 contents에 얹는 방식을 썼지만,
# 여기서는 순수 행동 제약이라 SDK가 지원하는 전용 채널을 쓰는 편이 더 명확하다).
_SYSTEM_INSTRUCTION = """\
당신은 임신부를 위한 영양 리포트를 설명하는 도우미입니다. 아래 규칙을 반드시 지키세요.
- 안전 여부(안전/주의/위험 등급)는 이미 판정이 끝났습니다. 그 판정을 다시 내리거나 바꾸지 마세요.
- 주어지지 않은 기준치나 숫자를 새로 만들어내지 마세요. 입력에 있는 값만 언급하세요.
- 의학적 진단이나 처방을 하지 마세요.
- 반드시 한국어 존댓말, "~해요" 어체로 답하세요.
- period가 "weekly"이면 입력의 모든 수치는 하루 평균입니다 — "오늘 ~했어요"가 아니라
  "이번 주 하루 평균 ~예요"처럼 표현하세요. period가 "daily"이면 오늘 하루 값입니다.
- status_label이 "부족"인 항목은 경고가 아닙니다. 다그치거나 걱정하는 어조로 쓰지 마세요.
- 효능·기준치·수치를 언급할 때는 반드시 입력의 "reference_notes"에 있는 내용만 쓰세요.
  거기 없는 효능·수치는 만들어내지 마세요. (아래 음식 제안 규칙은 이 제한과 별개입니다.)
- 주어진 영양소를 전부 다루지 말고, 가장 실천할 만한 영양소 중심으로 최대 두 개까지만
  골라 집중해서 설명하세요. 두 개를 고를 때는 서로 무관한 것보다, reference_notes에
  상호작용이 나와 있는 조합(예: 카페인이 철분 흡수를 방해한다는 점)을 우선하세요 —
  그런 조합이 없으면 가장 상태가 좋지 않은 영양소 하나만 다뤄도 됩니다.
- 음식 제안: 부족한(하한 미달) 영양소는 그 영양소가 풍부한 일상 음식 2~3개를, 초과한
  (상한 초과·주의) 영양소는 줄이면 좋을 흔한 음식 2~3개를 대화체 문장 안에 자연스럽게
  녹여 언급하세요. 목록을 나열하듯 쓰지 마세요. 이 음식 제안은 reference_notes에 없어도
  당신이 알고 있는 일반적인 음식 지식을 써도 됩니다 — 다만 효능·수치·기준 자체는 여전히
  reference_notes에 있는 내용만 써야 합니다(위 규칙과 동일).
- 아래 목록의 음식은 영양학적으로 맞아 보여도 절대 제안하지 마세요:
  - 간, 레버 등 내장육 (비타민A 과잉 위험)
  - 회, 육회, 생선회, 날달걀, 비살균 유제품·연성치즈 (리스테리아·살모넬라 위험)
  - 참치, 상어, 황새치 등 대형 어류 (수은 축적 위험)
  - 한약재, 건강기능식품, 영양제(브랜드 불문)
  - 카페인이 든 음료 (카페인은 이미 별도로 판정되는 항목입니다)
  보충제·영양제·용량(예: "OOmg 섭취하세요")·브랜드명도 언급하지 마세요 — 반드시 일반적인
  자연식품만 제안하세요.
- 음식을 제안할 때 "안전해요"/"위험해요"처럼 안전 여부를 판단하는 말을 쓰지 마세요. 그
  판단은 이미 규칙 엔진이 내렸습니다. 대신 "~에 풍부해요", "~이 많이 들어있는 편이에요"처럼
  영양 성분에 대한 사실만 말하세요.
- 입력의 nutrients 항목에는 "remaining"(상한형 여유분, 초과 시 음수) 또는 "gap"(하한형
  부족분, 0 이상)이 들어 있습니다. remaining이 음수이면 기준을 그 절댓값만큼 초과했다는
  뜻입니다 — 음수를 그대로 말하지 마세요(예: "-1500mg 남았어요"는 금지). 초과를 언급할
  때도 다그치지 않는 부드러운 어조를 유지하세요.
- period가 "daily"이면 remaining/gap을 참고해 오늘 남은 식사에서 어떻게 조절하면 좋을지
  관점에서 제안하세요. period가 "weekly"이면 하루 평균과, 주어진 경우 weekday_pattern을
  참고해 이번 주 전체 흐름 관점에서 제안하세요.
- weekday_pattern이 주어지면, 그 안에서 유독 두드러지는(눈에 띄게 높거나 낮은) 요일이 있을
  때만 짚어 언급하세요(예: "월요일에 나트륨이 특히 높았어요"). 요일별 값이 서로 비슷하면
  요일을 억지로 언급하지 마세요. 항목의 logged가 false인 요일은 완전히 건너뛰고 그 요일에
  대해 어떤 말도 하지 마세요 — 기록이 없다는 뜻이지 그날 적게 먹었다는 뜻이 아닙니다.
- 입력에 trimester가 주어집니다. reference_notes 안에 지금 시기(초기/중기/후기)와 관련된
  근거가 있을 때만 그 영양소의 중요성을 시기와 연결해 말하세요. reference_notes에 시기별
  근거가 없으면 시기를 언급하지 말고 일반적으로만 설명하세요.
- 응답은 points 배열로 주세요. 보통 2~3개입니다: (1) 현재 상태를 요약하는 포인트 하나,
  (2) 그와 관련해 실천할 수 있는 구체적 제안(음식 제안 포함) 포인트 하나, (3) 해당하면
  지금 임신 시기와 관련된 조언 포인트 하나(해당 없으면 생략). 각 포인트는 그 자체로
  완결된 한국어 문장 1~2개로 쓰세요. 포인트 앞에 번호나 기호(1., -, • 등)를 직접 붙이지
  마세요 — 화면이 표시합니다.
"""


class _AiAnalysisPoints(BaseModel):
    # min_length=1은 "빈 배열"만 걸러낸다 — 원소가 공백뿐인 문자열이어도(" ", "\n")
    # 배열 길이 자체는 0이 아니라서 여기를 통과한다. 그 경우는
    # _generate_analysis_text()가 각 원소를 strip()해 걸러낸다. 스키마와 strip() 둘
    # 다 필요한 이유가 이것이다(과거 _AiAnalysisText.text의 min_length=1과 같은 이유).
    points: list[str] = Field(min_length=1, max_length=3)


def _serialize_nutrient_items(nutrient_items: dict) -> list[dict]:
    """Gemini에게 보낼 판정 요약 — build_nutrient_summary_item()이 이미 계산해 둔
    값만 추린다(라벨/수치/기준/퍼센트/상태라벨). 새 판정을 만들지 않는다(원칙 ①).

    remaining/gap도 여기서 순수 산술로 미리 계산해 넣는다 — "기준 - 총량"을 Gemini에게
    직접 시키면 LLM이 뺄셈을 틀릴 수 있고, 그러면 "숫자는 전부 규칙 엔진에서 온다"는
    원칙이 깨진다. 판정(상태/등급)을 새로 내리는 게 아니라 이미 판정에 쓰인 두 숫자를
    그대로 빼는 것뿐이므로 원칙 ①과 충돌하지 않는다.
    - ceiling형(카페인/당류/나트륨): remaining = limit - total. 초과했으면 음수 그대로
      둔다 — 음수를 어떻게 말로 옮길지는 시스템 지시문의 어조 규칙이 담당한다.
    - floor형(탄수화물/단백질/에너지): gap = limit - total, 단 이미 채웠으면(음수) 0으로
      내린다 — "얼마나 부족한지"만 의미가 있고 "얼마나 초과했는지"는 floor형에 없는
      개념이다(get_floor_status()도 이진 판정뿐).
    - band형(지방/철분): limit 자체가 항상 None이라(build_nutrient_summary_item 참고,
      단일 상한 개념이 없음) 아래 total/limit 가드에서 자동으로 둘 다 None이 된다 —
      band는 remaining/gap 계산 대상이 아니다.
    - total이 None(정보 없음)이면 둘 다 None — NULL ≠ 0 원칙을 여기서도 지킨다.
    """
    items = [nutrient_items["caffeine"], *nutrient_items["nutrients"]]
    serialized = []
    for item in items:
        entry = {
            "label": item["label"],
            "total": item["total"],
            "unit": item["unit"],
            "limit": item["limit"],
            "percent": item["percent"],
            "status_label": item["status_label"],
        }
        if item["total"] is None or item["limit"] is None:
            entry["remaining"] = None
            entry["gap"] = None
        elif NUTRIENT_SUMMARY_FIELDS[item["key"]]["type"] == "floor":
            gap = round(item["limit"] - item["total"], 2)
            entry["remaining"] = None
            entry["gap"] = gap if gap > 0 else 0
        else:
            entry["remaining"] = round(item["limit"] - item["total"], 2)
            entry["gap"] = None
        serialized.append(entry)
    return serialized


def _nutrient_keys_present(nutrient_items: dict) -> list[str]:
    """nutrient_items에 실제로 등장한 키를 chart_keys와 같은 순서로 뽑는다
    (카페인 먼저, 그다음 사용자가 선택한 순서) — build_kb_excerpts()가 이 순서를
    그대로 참고 자료 순서로 쓴다."""
    items = [nutrient_items["caffeine"], *nutrient_items["nutrients"]]
    return [item["key"] for item in items]


def _build_prompt_payload(
    period: str,
    nutrient_items: dict,
    rule_messages: list[str],
    trimester: str,
    weekday_pattern: dict | None = None,
) -> dict:
    payload = {
        "period": period,
        "nutrients": _serialize_nutrient_items(nutrient_items),
        "already_generated_messages": rule_messages,
        "trimester": trimester,
        # 음식/습관 조언의 유일한 출처 — 프롬프트가 여기 없는 내용은 쓰지 말라고
        # 명시한다(원칙 ①: 이 파일도, KB도 새 판정을 만들지 않는다. KB는 "무엇을
        # 먹으면 좋은가"만 말하지 "얼마나/기준을 넘었는가"는 말하지 않는다).
        "reference_notes": build_kb_excerpts(_nutrient_keys_present(nutrient_items), trimester),
    }
    # weekly이고 눈에 띄는(deficient/exceeded) 영양소가 있을 때만 routers/report.py가
    # 채워 보낸다 — daily는 항상 None이고, weekly라도 챙길 만한 영양소가 없으면 None이라
    # 페이로드에 아예 실리지 않는다(빈 값을 굳이 보내 프롬프트를 늘리지 않는다).
    if weekday_pattern:
        payload["weekday_pattern"] = weekday_pattern
    return payload


def fingerprint_analysis_inputs(
    nutrient_items: dict,
    pregnancy_week: int,
    trimester: str,
    weekday_pattern: dict | None = None,
) -> str:
    """캐시 키에 넣는 지문. Gemini에게 보내는 것과 같은 판정 데이터(nutrients)에
    pregnancy_week/trimester까지 포함해 해시한다.

    nutrients만으로는 부족한 이유: reference_notes(KB 문단)는 nutrient 키 +
    trimester로부터 결정론적으로 정해지므로 trimester가 바뀌면 프롬프트도 바뀐다.
    또한 trimester가 그대로여도 pregnancy_week는 계속 앞으로 간다(같은 "중기" 안에서
    15주 -> 16주) — 모델이 "임신 O주차인 지금은..." 처럼 주차를 직접 언급할 수 있는데,
    지문에 주차가 없으면 오래된 주차를 말하는 캐시된 문장이 그대로 남는다.
    KB 원문 자체(pregnancy_nutrition_kb.py)는 지문에 넣지 않는다 — 정적 파일이라
    바뀌려면 배포(=프로세스 재시작)가 필요하고, 이 캐시는 어차피 프로세스 메모리라
    재시작하면 통째로 비워진다(gemini_vision.py의 호출 카운터와 같은 수명 가정).

    weekday_pattern도 넣는 이유: nutrient_items(주간 하루 평균)가 그대로여도 그 평균을
    구성하는 요일별 분포는 바뀔 수 있다(예: 화요일 기록을 지우고 같은 양을 수요일에
    다시 기록하면 평균은 같지만 패턴은 달라진다) — 패턴만 바뀌었는데 캐시가 그대로
    히트하면 이제는 틀린 요일을 언급하는 문장이 남는다.
    """
    payload = {
        "nutrients": _serialize_nutrient_items(nutrient_items),
        "pregnancy_week": pregnancy_week,
        "trimester": trimester,
    }
    if weekday_pattern:
        payload["weekday_pattern"] = weekday_pattern
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


# 재시도 전 대기 시간. genai SDK 자체의 기본 백오프(초기 1.0초, 지수적으로 증가)보다
# 살짝 여유를 둔 정도 — 여기서는 "잠깐 기다렸다 한 번만 더" 이상을 하지 않는다
# (여러 번 재시도하는 정교한 백오프는 SDK의 HttpRetryOptions가 이미 제공하며, 이
# 모듈은 기본 설정을 그대로 쓰고 있어 SDK 차원의 자동 재시도는 꺼져 있다).
_TRANSIENT_RETRY_BACKOFF_SECONDS = 2.0


def _is_transient_gemini_error(exc: BaseException) -> bool:
    """다시 시도하면 성공할 수 있는 오류만 True.

    google-genai SDK는 HTTP 상태코드로 예외를 이미 나눠준다(_api_client.py의
    raise_error): 4xx -> ClientError, 5xx -> ServerError. 404(모델을 찾을 수
    없음)/401·403(인증 실패)/429(쿼터 초과)는 전부 ClientError라 재시도해도 똑같이
    실패한다 — 여기 포함하지 않는다(재시도하면 시간과 쿼터만 태운다). 503
    UNAVAILABLE 같은 서버 과부하(ServerError, 5xx)와 네트워크 타임아웃만 일시적
    오류로 본다. 실제로 라이브 검증 중 503을 만났고 재시도로 성공했다.
    """
    return isinstance(exc, genai_errors.ServerError) or isinstance(exc, httpx.TimeoutException)


def _call_gemini(
    period: str,
    nutrient_items: dict,
    rule_messages: list[str],
    trimester: str,
    weekday_pattern: dict | None = None,
) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")
    if not _under_daily_limit():
        raise AiReportSummaryDailyLimitExceededError(
            f"하루 리포트 AI 설명 호출 상한({GEMINI_REPORT_DAILY_CALL_LIMIT}회)을 초과했습니다."
        )

    payload = _build_prompt_payload(period, nutrient_items, rule_messages, trimester, weekday_pattern)
    client = genai.Client(api_key=GEMINI_API_KEY)
    # 재시도 여부와 무관하게 한 번만 기록한다 — 쿼터는 "이 함수가 몇 번 불렸는가"를
    # 세는 것이지 "네트워크 요청이 몇 번 나갔는가"를 세는 게 아니다. 아래에서 실제
    # 요청을 최대 두 번(최초 시도 + 재시도 1회) 보내더라도 _record_call()은 이
    # 한 줄에서만 호출된다.
    _record_call()

    try:
        return _generate_analysis_text(client, payload)
    except Exception as exc:
        if not _is_transient_gemini_error(exc):
            raise
        print(
            f"[ai_report_summary] 일시적 오류로 1회 재시도합니다 "
            f"({type(exc).__name__}: {exc})"
        )
        time.sleep(_TRANSIENT_RETRY_BACKOFF_SECONDS)
        # 재시도는 딱 한 번뿐이다 — 이 두 번째 시도가 또 실패하면(같은 일시적
        # 오류든 다른 오류든) 그대로 위로 올라가 get_ai_report_analysis()의
        # except Exception이 rule_based로 내려보낸다.
        return _generate_analysis_text(client, payload)


def _generate_analysis_text(client: genai.Client, payload: dict) -> str:
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=json.dumps(payload, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_AiAnalysisPoints,
        ),
    )
    parsed = _AiAnalysisPoints.model_validate_json(response.text)
    # 스키마의 min_length=1(배열)은 빈 배열만 막는다 — 원소가 " "/"\n" 같은 공백뿐이어도
    # 배열 길이는 0이 아니라서 그대로 통과한다. 여기서 각 원소를 strip()해 빈 것만 골라낸다.
    points = [p.strip() for p in parsed.points if p.strip()]
    # 전부 공백이었다면(스키마는 통과했지만 실질적으로 내용이 없는 경우) 카드가 빈
    # 문단을 그대로 보여준다(성공으로 취급돼 except에 걸리지 않으므로 rule_based로도
    # 안 내려간다). ValueError를 던져 _call_gemini()의 except Exception으로 흘려보낸다 —
    # get_ai_report_analysis()가 이미 "무엇이 실패하든 rule_based"로 처리하므로 별도
    # 분기가 필요 없다. 이 경로는 _is_transient_gemini_error()가 아니므로 재시도 없이
    # 곧장 실패로 처리된다(빈 응답은 네트워크 문제가 아니라 모델이 실제로 낸 값이라
    # 재시도 대상이 아니다).
    if not points:
        raise ValueError("Gemini가 빈 포인트만 반환했습니다(배열은 있었지만 전부 공백).")
    # 계약: 이 "\n" 조인은 app/app/report.tsx의 AiSummaryCard.renderResolvedContent()
    # (gemini 분기)의 text.split("\n")과 짝을 이룬다 — 구분자를 여기서 바꾸면 그쪽도
    # 같이 바꿔야 한다(그렇지 않으면 화면이 다시 포인트 구분 없이 한 덩어리로 보인다).
    # points 배열 자체는 이미 Gemini 응답 스키마로 구조화되어 있으므로, 프론트가 하는
    # 일은 이 구분자로 다시 나누는 것뿐이지 자유 문장을 정규식으로 추측해 자르는 게
    # 아니다.
    return "\n".join(points)


def _mock_text(period: str) -> str:
    """REPORT_AI_USE_MOCK_GEMINI=true일 때 쓰는 고정 문구. 실제 응답과 같은 모양
    (points 2~3개를 "\\n"으로 조인한 문자열, ~해요 어체)을 유지해 이후 경로를 그대로
    통과시킨다 — _generate_analysis_text()의 "\\n" 조인 계약과 같은 모양이라야, 이
    mock 경로로도 프론트(report.tsx)의 포인트별 렌더링을 그대로 검증할 수 있다."""
    if period == "weekly":
        points = [
            "이번 주 하루 평균 섭취 흐름을 보면 전반적으로 기준 안에서 관리되고 있어요.",
            "지금처럼 세 끼를 규칙적으로 챙기면서, 부족한 항목이 있다면 관련 식품을 조금씩 늘려보는 정도면 충분해요.",
            "지금 시기에 중요한 영양소가 있다면 특히 신경 써서 챙겨보세요.",
        ]
    else:
        points = [
            "오늘 섭취 흐름을 보면 대체로 기준 안에서 잘 유지하고 있어요.",
            "부족한 항목이 있다면 다음 식사에서 관련 식품으로 조금씩 채워보는 것을 추천해요.",
            "지금 시기에 중요한 영양소가 있다면 특히 신경 써서 챙겨보세요.",
        ]
    return "\n".join(points)


# (user_id, period, date_key, fingerprint) -> Gemini 응답 텍스트. 성공한 응답만
# 캐시한다(get_ai_report_analysis 참고) — 실패를 캐시하면 그날 남은 시간 동안
# Gemini가 복구돼도 계속 rule_based만 보여주게 된다.
_analysis_cache: dict[tuple[int, str, str, str], str] = {}


def get_ai_report_analysis(
    user_id: int,
    period: str,
    date_key: str,
    nutrient_items: dict,
    rule_messages: list[str],
    pregnancy_week: int,
    trimester: str,
    weekday_pattern: dict | None = None,
) -> dict:
    """리포트 카드가 펼쳐질 때 호출된다.

    성공: {"source": "gemini", "text": str} — text는 여러 포인트를 "\\n"으로 조인한
    문자열이다(_generate_analysis_text() 참고). app/app/report.tsx가 이 "\\n"을 다시
    나눠 포인트별로 렌더링하므로, 이 응답 모양(하나의 문자열)과 그 안의 "\\n" 구분자는
    api-client.ts의 ReportAiAnalysis 타입과 별개로 지켜야 하는 계약이다.
    실패(쿼터 초과/키 없음/네트워크 오류/스키마 불일치 등 무엇이든): 절대 예외를
    올리지 않고 {"source": "rule_based", "messages": rule_messages} — 카드는 이미
    갖고 있던 규칙 기반 문구를 그대로 보여주면 되므로 에러 상태가 없다
    (routers/report.py의 새 엔드포인트가 이 함수를 try/except로 감싸지 않는 이유이기도
    하다 — 이 함수 자체가 실패를 밖으로 내보내지 않는다). 쿼터 초과도 이 경로를 그대로
    타므로("무엇이 실패하든"), AiReportSummaryDailyLimitExceededError가 별도 처리 없이
    바로 rule_based로 내려간다.

    weekday_pattern: weekly이고 눈에 띄는 영양소가 있을 때만 routers/report.py가 채워
    보낸다(daily는 항상 None) — routers/report.py의 _build_weekday_pattern() 참고.
    """
    fingerprint = fingerprint_analysis_inputs(nutrient_items, pregnancy_week, trimester, weekday_pattern)
    cache_key = (user_id, period, date_key, fingerprint)

    # 이 요청이 캐시/mock/실제 호출 중 어느 경로로 응답됐는지 매번 한 줄로 남긴다 —
    # "Gemini가 정말 호출되고 있는가"가 지금까지 눈에 보이지 않았던 것이 이 파일을
    # 건드리게 된 이유다.
    if cache_key in _analysis_cache:
        print(f"[ai_report_summary] cache hit (user_id={user_id}, period={period}, date={date_key})")
        return {"source": "gemini", "text": _analysis_cache[cache_key]}

    if REPORT_AI_USE_MOCK_GEMINI:
        print(f"[ai_report_summary] mock 응답 사용 (user_id={user_id}, period={period}, date={date_key})")
        text = _mock_text(period)
        _analysis_cache[cache_key] = text
        return {"source": "gemini", "text": text}

    print(f"[ai_report_summary] Gemini 실제 호출 (user_id={user_id}, period={period}, date={date_key})")
    try:
        text = _call_gemini(period, nutrient_items, rule_messages, trimester, weekday_pattern)
    except Exception:
        # 무엇이 실패했든 카드에는 절대 노출하지 않지만, 서버 로그에는 남긴다
        # (routers/ocr.py의 502 처리와 같은 방식 — traceback.print_exc()).
        print(f"[ai_report_summary] Gemini 호출 실패 -> rule_based로 대체 (user_id={user_id}, period={period}, date={date_key})")
        import traceback
        traceback.print_exc()
        return {"source": "rule_based", "messages": rule_messages}

    preview = text[:40]
    print(
        f"[ai_report_summary] Gemini 응답 성공 (user_id={user_id}, period={period}, "
        f"date={date_key}, length={len(text)}, preview={preview!r})"
    )

    _analysis_cache[cache_key] = text
    return {"source": "gemini", "text": text}
