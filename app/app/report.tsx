import { LinearGradient } from 'expo-linear-gradient';
import * as MediaLibrary from 'expo-media-library';
import { router, useFocusEffect } from 'expo-router';
import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  LayoutChangeEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Animated, {
  Easing,
  interpolate,
  interpolateColor,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { captureRef } from 'react-native-view-shot';

import DownIcon from '@/assets/images/common/down.svg';
import PrevIcon from '@/assets/images/common/prev.svg';
import InformationIcon from '@/assets/images/onboarding/information.svg';
import { authColors } from '@/components/auth/colors';
import BottomSheet from '@/components/common/BottomSheet';
import { nutrientColorFor } from '@/components/common/nutrientColors';
import { NUTRIENT_ICONS, NutrientIconKey } from '@/components/common/nutrientIcons';
import { reportColors } from '@/components/report/colors';
import IntakeTrendChart from '@/components/report/IntakeTrendChart';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  getReport,
  getReportAiAnalysis,
  NutrientSummaryItem,
  ReportAiAnalysis,
  ReportAiSummary,
  ReportComparison,
  ReportPeriod,
  ReportResponse,
} from '@/lib/api-client';

const SCREEN_SUBTITLE = '카페인과 관심 성분을 하루·일주일 단위로 정리했어요';
const EMPTY_NUTRIENTS_TEXT = '마이페이지에서 관심 영양소를 선택하면 카페인과 함께 여기에 표시돼요.';

// 알약이 "미끄러진다"고 느껴지도록 기본값보다 여유 있는 시간과 ease-in-out을 쓴다.
// 라벨 색도 같은 진행값을 공유해서, 알약이 이동하는 동안 글자색만 먼저 바뀌지 않는다.
const TOGGLE_TIMING = { duration: 300, easing: Easing.inOut(Easing.cubic) };

// AI 분석 카드가 처음 펼쳐질 때(아직 응답이 없을 때) 잠깐 보여주는 로딩 줄의 높이.
// 실측이 아니라 고정값이다 — 스피너+한 줄짜리 문구라 내용이 바뀌지 않으므로
// food-entry-ocr-confirm.tsx의 "추정치로 먼저 펼치고 나중에 실측으로 정착" 방식에서
// 추정 단계와 같은 역할을 한다. 응답이 오면 실제 내용을 오프스크린으로 재서 이 값에서
// 실측값으로 다시 애니메이션한다.
const AI_ANALYSIS_LOADING_HEIGHT = 28;
const AI_ANALYSIS_DISCLAIMER =
  '안전도 판단은 앱의 규칙 엔진이 하고, AI는 그 결과를 바탕으로 설명만 제공해요.';

// 배너 일러스트(Figma "note 1")는 원본 440x440 캔버스 중 실제 그림(불투명 영역)이 가로는
// 거의 꽉 차지만(0.5%~97.7%) 세로는 가운데 67%(15%~82%)뿐이다. Figma가 쓰던 116%/-8%
// 확대·오프셋을 그대로 적용하면 세로 여백은 그대로 보여주면서 가로는 그림 가장자리를
// 잘라버려(약 7%씩) 결과적으로 잘린 그림이 나온다. 정사각 캔버스이므로 resizeMode
// "contain"이 곧 "cover"와 같아 확대·오프셋 계산 없이 원본 전체를 손실 없이 보여준다.
const NOTE_BOX = 112;
// 오른쪽 위 정보 아이콘(배너 안에 얹힌 앱 요소, Figma 프레임에는 없음)이 x=313~345에
// 있어, Figma 원래 위치(right:12, 110 폭)로는 26px가 겹친다. 겹침을 없애려고만 왼쪽으로
// 밀면 글자 블록의 실제 오른쪽 끝(x=199)에 거의 닿아버려서(0~4px), 폭도 100으로 줄여
// 아이콘 쪽 6px · 글자 쪽 8px의 여유를 함께 확보했다.
const NOTE_BOX_RIGHT_INSET = 36;

/** 일간 행과 주간 카드는 배치가 다르지만 숫자를 해석하는 규칙은 하나여야 한다 —
 *  특히 밴드 판정(지방·철분)의 null 처리는 두 벌로 존재하면 안 되는 로직이라
 *  계산만 여기로 모으고 화면 구성은 각 컴포넌트가 따로 한다. */
function resolveNutrientDisplay(item: NutrientSummaryItem) {
  // 색은 상태가 아니라 영양소 정체성에서 온다. 일간·주간 모두 같은 맵을 쓰므로 토글을
  // 눌러도 같은 영양소의 색이 바뀌지 않는다. 상태는 색이 아니라 숫자와 퍼센트로 읽는다.
  const colors = nutrientColorFor(item.key);
  const Icon = NUTRIENT_ICONS[item.key as NutrientIconKey] as
    | (typeof NUTRIENT_ICONS)[NutrientIconKey]
    | undefined;

  // 밴드 판정 영양소(지방·철분)는 limit/percent가 둘 다 null로 온다 — 기준 대비 비율이라는
  // 개념 자체가 없기 때문이다. 그래서 게이지와 퍼센트를 그리지 않고, 서버가 실제로 내린
  // 판정인 status_label을 오른쪽에 보여준다. 빈 게이지를 두면 0%로 읽히는데, 밴드 영양소는
  // 채워진 양이 0이어도 '위험'일 수 있어 사실과 어긋난다.
  const hasLimit = item.limit != null && item.percent != null;

  return {
    colors,
    Icon,
    hasLimit,
    // total이 null이면(무언가는 기록됐는데 이 영양소만 확인된 값이 없음) 0을 보여주지
    // 않고 정보없음으로 표시한다 (NULL ≠ 0 원칙, backend/intake_totals.py 참고).
    valueText: item.total == null ? '정보 없음' : String(item.total),
    // 게이지는 0~100으로 자르지만 글자는 실제 값을 쓴다 — 130%가 트랙을 넘어 그려지지
    // 않으면서도 130%라는 사실은 그대로 전달된다.
    fillPercent: hasLimit ? Math.min(Math.max(item.percent as number, 0), 100) : 0,
    percentText: hasLimit ? `${Math.round(item.percent as number)}%` : null,
    limitText: hasLimit ? ` / ${item.limit}${item.unit}` : ` ${item.unit}`,
    compareLabel: hasLimit ? '권장 기준 대비' : '섭취 상태',
    compareValue: hasLimit ? `${Math.round(item.percent as number)}%` : (item.status_label ?? '정보없음'),
  };
}

/** 지난주 대비를 가진 영양소는 카페인/당류/나트륨 셋뿐이다. 나머지(철분·지방 등)는
 *  서버가 아예 비교를 계산하지 않으므로 여기에 없고, 빈 자리("-")로 그린다. */
const COMPARISON_FIELDS: Partial<Record<string, keyof Omit<ReportComparison, 'previous_period'>>> = {
  caffeine: 'caffeine_vs_previous_pct',
  sugar: 'sugar_vs_previous_pct',
  sodium: 'sodium_vs_previous_pct',
};

/** 지난주 대비 증감 한 줄. 값의 단위는 퍼센트포인트(%p)다 — "기준 대비 몇 %"가 지난주보다
 *  얼마나 달라졌는지이지, 섭취량이 몇 % 늘었다는 뜻이 아니다. 그래서 Figma의 "▲ 13%"를
 *  그대로 쓰지 않고 %p로 적는다.
 *
 *  올라가면 빨강, 내려가면 파랑이라는 단순한 규칙이 성립하는 이유는 비교 대상 세 가지가
 *  모두 상한형(ceiling) 영양소라 많을수록 나쁘기 때문이다. 단백질처럼 하한형 영양소를
 *  비교 대상에 추가한다면 이 규칙은 뒤집어야 한다. */
function resolveComparisonDisplay(key: string, comparison: ReportComparison) {
  const field = COMPARISON_FIELDS[key];

  if (field === undefined) {
    // 서버가 이 영양소의 비교를 계산하지 않는다. "정보 없음"은 NULL ≠ 0이라는 뜻이라 쓸 수 없다.
    return { text: '-', color: authColors.gray, textStyle: styles.compareDelta };
  }

  const delta = comparison[field];

  if (delta == null) {
    // 비교 대상이지만 두 주 중 한쪽이라도 확인된 값이 없어 서버가 null을 준 경우.
    // 0으로 대신 그리면 "지난주와 같았다"는 없는 사실을 만들어내게 된다.
    return { text: '- 정보 없음', color: authColors.gray, textStyle: styles.compareMissing };
  }

  const rounded = Math.round(delta);
  if (rounded > 0) {
    return { text: `▲ ${rounded}%p`, color: reportColors.comparisonUp, textStyle: styles.compareDelta };
  }
  if (rounded < 0) {
    return {
      text: `▼ ${Math.abs(rounded)}%p`,
      color: reportColors.comparisonDown,
      textStyle: styles.compareDelta,
    };
  }
  // 0은 없는 값이 아니라 "표시 단위로는 달라지지 않았다"는 실제 값이라 정보 없음과 구분해
  // 적되, 방향이 없으므로 화살표와 색은 붙이지 않는다(0.4처럼 반올림해서 0이 되는 값 포함).
  return { text: '0%p', color: authColors.gray, textStyle: styles.compareDelta };
}

/** 일간(331:319): 공용 컨테이너 안의 63 높이 행. 자체 배경도, 테두리도, 구분선도 없다. */
function DailyNutrientRow({ item }: { item: NutrientSummaryItem }) {
  const d = resolveNutrientDisplay(item);

  return (
    <View style={styles.dailyRow}>
      <View style={styles.readout}>
        <View style={styles.labelRow}>
          {d.Icon ? <d.Icon width={17} height={17} color={d.colors.value} /> : null}
          <Text style={styles.nutrientLabel}>{item.label}</Text>
        </View>

        <Text style={styles.valueRow}>
          <Text style={[styles.value, { color: d.colors.value }]}>{d.valueText}</Text>
          <Text style={styles.limit}>{d.limitText}</Text>
        </Text>

        {d.hasLimit ? (
          <View style={styles.barRow}>
            <View style={[styles.barTrack, { backgroundColor: d.colors.track }]}>
              <View
                style={[
                  styles.barFill,
                  { width: `${d.fillPercent}%`, backgroundColor: d.colors.value },
                ]}
              />
            </View>
            <Text style={styles.barPercent}>{d.percentText}</Text>
          </View>
        ) : null}
      </View>

      <View style={[styles.compareRow, styles.dailyCompare]}>
        <Text style={styles.compareLabel}>{d.compareLabel}</Text>
        <Text style={[styles.compareValue, { color: d.colors.value }]}>{d.compareValue}</Text>
      </View>
    </View>
  );
}

/** 주간(46:461 / 46:444 / 46:426): 카드 하나가 영양소 하나. 상자가 둘이다 —
 *  분홍 바깥 상자(337:334) 위에 흰 패널(46:427)이 왼쪽에 얹혀서, 왼쪽 수치 영역과
 *  오른쪽 비교 영역이 배경색으로 갈린다. */
function WeeklyNutrientCard({
  item,
  comparison,
}: {
  item: NutrientSummaryItem;
  comparison: ReportComparison;
}) {
  const d = resolveNutrientDisplay(item);
  const c = resolveComparisonDisplay(item.key, comparison);

  return (
    <View style={styles.weeklyCard}>
      {/* 왼쪽 흰 패널. 내용이 아니라 배경이라 절대 위치로 깔아두고 그 위에 수치를 올린다. */}
      <View style={styles.weeklyReadoutPanel} />

      <View style={styles.readout}>
        <View style={styles.labelRow}>
          {d.Icon ? <d.Icon width={17} height={17} color={d.colors.value} /> : null}
          <Text style={styles.nutrientLabel}>{item.label}</Text>
        </View>

        <Text style={styles.valueRow}>
          <Text style={[styles.value, { color: d.colors.value }]}>{d.valueText}</Text>
          <Text style={styles.limit}>{d.limitText}</Text>
        </Text>

        {d.hasLimit ? (
          <View style={styles.barRow}>
            <View style={[styles.barTrack, { backgroundColor: d.colors.track }]}>
              <View
                style={[
                  styles.barFill,
                  { width: `${d.fillPercent}%`, backgroundColor: d.colors.value },
                ]}
              />
            </View>
            <Text style={styles.barPercent}>{d.percentText}</Text>
          </View>
        ) : null}
      </View>

      {/* 오른쪽 열(46:432 / 46:431 / 46:428): 권장 기준 대비 → 구분선 → 지난주 대비.
          구분선과 지난주 대비 행은 값이 없을 때도 그린다 — 카드 4장의 높이가 서로 달라지지
          않도록. */}
      <View style={styles.weeklyCompareColumn}>
        <View style={styles.compareRow}>
          <Text style={styles.compareLabel}>{d.compareLabel}</Text>
          <Text style={[styles.compareValue, { color: d.colors.value }]}>{d.compareValue}</Text>
        </View>

        <View style={styles.compareDivider} />

        <View style={[styles.compareRow, styles.compareDeltaRow]}>
          <Text style={styles.compareLabel}>지난주 대비</Text>
          <Text style={[c.textStyle, { color: c.color }]}>{c.text}</Text>
        </View>
      </View>
    </View>
  );
}

/** 일간/주간 토글(332:323). 알약은 translateX만 움직인다 — 폭이나 레이아웃을 애니메이션하면
 *  화면 다른 곳(카드 흐림 처리)과 겹쳐 흔들릴 수 있기 때문이다. */
function PeriodToggle({
  period,
  onChange,
}: {
  period: ReportPeriod;
  onChange: (next: ReportPeriod) => void;
}) {
  const [trackWidth, setTrackWidth] = useState(0);
  const progress = useSharedValue(period === 'daily' ? 0 : 1);
  // 트랙의 1px 테두리 안쪽을 반으로 나눈 값이 Figma의 알약 폭(349 → 347/2 ≈ 173)이다.
  const pillWidth = trackWidth > 0 ? (trackWidth - 2) / 2 : 0;

  useEffect(() => {
    progress.value = withTiming(period === 'daily' ? 0 : 1, TOGGLE_TIMING);
  }, [period, progress]);

  const pillStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: progress.value * pillWidth }],
  }));
  const dailyLabelStyle = useAnimatedStyle(() => ({
    color: interpolateColor(progress.value, [0, 1], [authColors.pink, authColors.gray]),
  }));
  const weeklyLabelStyle = useAnimatedStyle(() => ({
    color: interpolateColor(progress.value, [0, 1], [authColors.gray, authColors.pink]),
  }));

  const handleLayout = (event: LayoutChangeEvent) => setTrackWidth(event.nativeEvent.layout.width);

  return (
    <View style={styles.toggleTrack} onLayout={handleLayout}>
      {/* 폭을 재기 전에는 그리지 않는다 — 0폭 알약이 한 프레임 깜빡이는 것을 막는다. */}
      {pillWidth > 0 ? (
        <Animated.View style={[styles.togglePill, { width: pillWidth }, pillStyle]} />
      ) : null}
      <Pressable style={styles.toggleHalf} onPress={() => onChange('daily')}>
        <Animated.Text style={[styles.toggleLabel, dailyLabelStyle]}>일간</Animated.Text>
      </Pressable>
      <Pressable style={styles.toggleHalf} onPress={() => onChange('weekly')}>
        <Animated.Text style={[styles.toggleLabel, weeklyLabelStyle]}>주간</Animated.Text>
      </Pressable>
    </View>
  );
}

/** AI 분석 요약 카드가 펼쳐졌을 때 무엇을 보여줄지의 상태 기계.
 *  idle: 아직 펼친 적 없음(펼침 API를 호출하지 않았다) — period/date가 바뀌면
 *    gemini/rule_based에서 다시 idle로 되돌아간다(아래 useEffect 참고).
 *  loading: 첫 펼침 — 응답 대기 중, 고정 높이 로딩 줄만 보인다
 *  gemini: 2단계 AI 설명 성공 — text를 그대로 보여준다("\n"으로 구분된 포인트들,
 *    renderResolvedContent() 참고)
 *  rule_based: 무엇이 실패했든(쿼터 초과/네트워크 오류 등) 규칙 기반 문구로 대체 —
 *    카드가 이미 갖고 있던 extraMessages를 그대로 쓴다(서버 응답의 messages를 별도로
 *    쓰지 않는다 — 같은 규칙 엔진이 같은 순서로 만든, 사실상 동일한 목록이다).
 *  같은 period/date로 머무는 동안 gemini/rule_based에 한 번 정착하면 다시 펼쳐도
 *  재호출하지 않는다(요청 #10) — 실패도 재시도하지 않고 그대로 정착시킨다(재시도
 *  조건을 따로 두면 "펼칠 때마다 다시 부를 수도 있다"는 예외가 생겨 요구사항이
 *  흐려진다). period나 date 자체가 바뀌면 얘기가 다르다 — 아래 useEffect가 그
 *  경계를 담당한다.
 */
type AiAnalysisState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'gemini'; text: string }
  | { status: 'rule_based' };

/** AI 분석 요약(331:320 + 2단계 Gemini 설명). 접힘 기본값으로 첫 문구(서버가 이미
 *  심각도순으로 정렬해 보낸다)만 보여주고, 탭하면 펼쳐진다 — 처음 펼칠 때만 서버에
 *  AI 설명을 요청하고(로딩 표시), 이후 같은 period/date로 머무는 동안에는 이미 받은
 *  결과를 그대로 다시 쓴다.
 *
 *  이 컴포넌트는 일간/주간 토글 때마다 리마운트되지 않는다(부모가 key={period}를
 *  주지 않는다) — 리마운트하면 카드가 펼쳐진 채로 토글했을 때 접히는 애니메이션 없이
 *  그 프레임에 바로 닫힌 모습으로 다시 나타난다(state/shared value가 전부 초기화되며
 *  진행 중이던 접힘 애니메이션도 함께 사라진다). 대신 아래 useEffect가 period/date
 *  변화를 감지해 이미 있는 접힘 애니메이션(toggle()의 접기 분기와 동일한 코드)으로
 *  부드럽게 접고, analysisState만 idle로 되돌려 다음 펼침이 새 period/date로 다시
 *  fetch하게 만든다 — 예전에는 이 리셋이 없어 다른 기간의 문구가 그대로 남아있었다
 *  (일간/주간 텍스트가 동일하게 보이던 버그의 원인).
 *
 *  높이 애니메이션은 food-entry-ocr-confirm.tsx의 영양성분 테이블 펼침과 같은 방식
 *  (수동 shared value + withTiming + 완료 시 runOnJS로 auto 높이에 정착)을 쓴다 —
 *  Reanimated의 자동 layout/entering/exiting은 가변 높이 텍스트 행에서 튄다. 내용이
 *  두 단계(로딩 줄 → 실제 응답)로 바뀌므로 높이도 두 번 애니메이션한다: 먼저 고정
 *  로딩 높이(AI_ANALYSIS_LOADING_HEIGHT)로, 응답이 오면 food-diary/index.tsx의
 *  오프스크린 측정 트릭(투명하게 숨겨둔 실제 내용을 onLayout으로 재서 정확한 값을
 *  얻는다)으로 다시 실측값까지 — 한국어 문구는 줄바꿈 폭이 일정하지 않아 고정
 *  상수로 추정할 수 없기 때문이다.
 */
function AiSummaryCard({
  summary,
  userId,
  period,
  date,
}: {
  summary: ReportAiSummary;
  userId: number | undefined;
  period: ReportPeriod;
  date: string;
}) {
  const [headline, ...extraMessages] = summary.messages;

  const [expanded, setExpanded] = useState(false);
  const [heightSettled, setHeightSettled] = useState(false);
  const [analysisState, setAnalysisState] = useState<AiAnalysisState>({ status: 'idle' });
  const measuredHeightRef = useRef(0);
  const extraHeight = useSharedValue(0);
  const extraOpacity = useSharedValue(0);
  const chevronRotation = useSharedValue(0);
  // period/date가 바뀔 때마다 올라간다. 펼침 시점에 캡처해 두었다가 fetch가 돌아왔을
  // 때 그 사이 값이 바뀌었으면(=사용자가 응답을 기다리는 동안 토글을 눌렀으면) 결과를
  // 버린다 — ReportScreen.fetchReport()의 seqRef와 같은 패턴이다.
  const requestTokenRef = useRef(0);

  // 이 카드는 일간/주간 토글에도 리마운트되지 않으므로(위 컴포넌트 docstring 참고),
  // period/date가 바뀌었다는 사실을 직접 감지해 이전 기간의 analysisState를 버려야
  // 한다 — 그렇지 않으면 toggle()의 "이미 응답 받아둔 상태" 분기가 다른 기간의 문구를
  // 그대로 재사용한다(일간/주간 텍스트가 같아 보이던 버그의 근본 원인).
  useEffect(() => {
    requestTokenRef.current += 1;
    if (expanded) {
      // toggle()의 접기 분기와 완전히 동일한 애니메이션이다 — 새 애니메이션을
      // 만들지 않고 이미 있는 접힘 경로를 그대로 재사용한다.
      setHeightSettled(false);
      extraHeight.value = measuredHeightRef.current;
      chevronRotation.value = withTiming(0, TOGGLE_TIMING);
      extraHeight.value = withTiming(0, TOGGLE_TIMING);
      extraOpacity.value = withTiming(0, TOGGLE_TIMING, (finished) => {
        if (finished) runOnJS(setExpanded)(false);
      });
    }
    setAnalysisState({ status: 'idle' });
    measuredHeightRef.current = 0;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, date]);

  // 오프스크린 사본은 응답이 실제로 정착했을 때만(로딩 중엔 내용이 없으므로 잴 것도
  // 없다) 렌더되므로, onLayout이 새로 잡히면 "막 응답이 도착해 로딩 높이에서 실제
  // 높이로 넘어가야 하는 순간"이거나 "이미 펼쳐진 채 재측정된 순간" 둘 중 하나다.
  // 두 경우 다 펼쳐져 있으면 그 높이로 바로 애니메이션한다.
  const handleMeasure = (event: LayoutChangeEvent) => {
    const height = event.nativeEvent.layout.height;
    if (height <= 0) return;
    measuredHeightRef.current = height;
    if (expanded && (analysisState.status === 'gemini' || analysisState.status === 'rule_based')) {
      extraHeight.value = withTiming(height, TOGGLE_TIMING, (finished) => {
        if (finished) runOnJS(setHeightSettled)(true);
      });
    }
  };

  const toggle = () => {
    if (expanded) {
      // 접기 전, 정지 상태(auto)에서 실측한 높이로 shared value를 먼저 동기화한다 —
      // 그래야 추정치로 스냅되는 튐 없이 실제 지점부터 0으로 줄어든다.
      setHeightSettled(false);
      extraHeight.value = measuredHeightRef.current;
      chevronRotation.value = withTiming(0, TOGGLE_TIMING);
      extraHeight.value = withTiming(0, TOGGLE_TIMING);
      extraOpacity.value = withTiming(0, TOGGLE_TIMING, (finished) => {
        if (finished) runOnJS(setExpanded)(false);
      });
      return;
    }

    setExpanded(true);
    chevronRotation.value = withTiming(1, TOGGLE_TIMING);
    extraOpacity.value = withTiming(1, TOGGLE_TIMING);

    if (analysisState.status === 'idle') {
      // 첫 펼침 — 고정 로딩 높이로 먼저 열고, 응답이 오면 handleMeasure가 실제
      // 높이로 다시 애니메이션한다.
      setHeightSettled(false);
      setAnalysisState({ status: 'loading' });
      extraHeight.value = withTiming(AI_ANALYSIS_LOADING_HEIGHT, TOGGLE_TIMING);

      if (!userId) {
        // 이론상 도달하지 않는다(이 카드는 리포트가 이미 로드된 뒤에만 그려지고,
        // 그러려면 user_id가 있어야 한다) — 방어적으로 규칙 기반으로 바로 정착한다.
        setAnalysisState({ status: 'rule_based' });
        return;
      }

      // 이 요청이 도착했을 때도 여전히 같은 period/date인지 확인할 토큰 — 응답을
      // 기다리는 동안 사용자가 토글을 눌렀으면(위 useEffect가 토큰을 올려둔다) 이제
      // 다른 기간을 보고 있는 것이므로 이 결과는 버려야 한다.
      const requestToken = requestTokenRef.current;
      getReportAiAnalysis(userId, period, date)
        .then((res) => {
          if (requestTokenRef.current !== requestToken) return;
          // res.text만 보면 " "(공백뿐인 문자열)도 truthy라 통과한다 — 실제로는
          // 서버가 이제 빈/공백 응답을 실패로 처리해 rule_based를 내려주지만
          // (backend/ai_report_summary.py), 프론트 쪽에서도 같은 기준으로 방어한다.
          const trimmedText = res.text?.trim();
          setAnalysisState(
            res.source === 'gemini' && trimmedText
              ? { status: 'gemini', text: trimmedText }
              : { status: 'rule_based' }
          );
        })
        .catch(() => {
          if (requestTokenRef.current !== requestToken) return;
          setAnalysisState({ status: 'rule_based' });
        });
    } else if (analysisState.status === 'loading') {
      setHeightSettled(false);
      extraHeight.value = withTiming(AI_ANALYSIS_LOADING_HEIGHT, TOGGLE_TIMING);
    } else {
      // 이미 응답을 받아둔 상태 — 다시 호출하지 않고 실측 높이로 바로 편다.
      setHeightSettled(false);
      extraHeight.value = withTiming(measuredHeightRef.current, TOGGLE_TIMING, (finished) => {
        if (finished) runOnJS(setHeightSettled)(true);
      });
    }
  };

  const chevronStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${interpolate(chevronRotation.value, [0, 1], [0, 180])}deg` }],
  }));
  const extraStyle = useAnimatedStyle(() => ({
    height: heightSettled ? undefined : extraHeight.value,
    opacity: extraOpacity.value,
    overflow: 'hidden',
  }));

  // 로딩 중엔 실제 사본을 아직 잴 수 없으니 렌더하지 않는다 — 고정 높이만 쓴다.
  const renderResolvedContent = () => {
    if (analysisState.status === 'gemini') {
      // 계약: 이 "\n" split은 backend/ai_report_summary.py의
      // _generate_analysis_text()가 points를 "\n"으로 조인하는 것과 짝을 이룬다 —
      // 조인 문자를 바꾸면 여기도 같이 바꿔야 한다(그렇지 않으면 다시 포인트 구분
      // 없는 한 덩어리로 보인다). points 배열 자체는 이미 Gemini 응답 스키마로
      // 구조화되어 백엔드가 만들어 보낸 것이라, 여기서 하는 일은 그 구분자로 다시
      // 나누는 것뿐이다 — 정규식으로 문장/불릿 경계를 추측하는 게 아니다. "\r"은
      // 방어적으로만 제거한다("\r\n"이 섞여 와도 빈 줄로 보이지 않게).
      const points = analysisState.text
        .split('\n')
        .map((point) => point.split('\r').join('').trim())
        .filter((point) => point.length > 0);
      return (
        <>
          {points.map((point, index) => (
            <View key={index} style={styles.summaryMessageRow}>
              <Text style={styles.summaryBullet}>•</Text>
              <Text style={styles.summaryMessage}>{point}</Text>
            </View>
          ))}
          <Text style={styles.summaryDisclaimer}>{AI_ANALYSIS_DISCLAIMER}</Text>
        </>
      );
    }
    if (analysisState.status === 'rule_based') {
      return (
        <>
          {extraMessages.map((message, index) => (
            <View key={index} style={styles.summaryMessageRow}>
              <Text style={styles.summaryBullet}>•</Text>
              <Text style={styles.summaryMessage}>{message}</Text>
            </View>
          ))}
          <Text style={styles.summaryDisclaimer}>{AI_ANALYSIS_DISCLAIMER}</Text>
        </>
      );
    }
    return null;
  };

  const isResolved = analysisState.status === 'gemini' || analysisState.status === 'rule_based';

  return (
    <View style={styles.summaryCard}>
      <Pressable style={styles.summaryHeaderRow} onPress={toggle} hitSlop={8}>
        <Image
          source={require('@/assets/images/premium/spark.png')}
          style={styles.summarySpark}
        />
        <Text style={styles.summaryTitle}>{summary.title}</Text>
        <Animated.View style={[styles.summaryChevron, chevronStyle]}>
          <DownIcon width={21} height={21} />
        </Animated.View>
      </Pressable>

      <View style={styles.summaryBody}>
        <View style={styles.summaryMessageRow}>
          <Text style={styles.summaryBullet}>•</Text>
          <Text style={styles.summaryMessage}>{headline}</Text>
        </View>

        <Animated.View style={extraStyle}>
          <View>
            {analysisState.status === 'loading' ? (
              <View style={styles.summaryLoadingRow}>
                <ActivityIndicator size="small" color={authColors.pink} />
                <Text style={styles.summaryMessage}>AI가 분석하고 있어요...</Text>
              </View>
            ) : (
              renderResolvedContent()
            )}
          </View>
        </Animated.View>
      </View>

      {/* 오프스크린 측정용 사본 — 응답이 정착했을 때만 렌더된다(로딩 중엔 잴 내용이
          없다). 화면에는 보이지 않지만(opacity 0) 실제와 같은 폭으로 그려져
          onLayout이 정확한 펼침 높이를 알려준다. */}
      {isResolved ? (
        <View pointerEvents="none" style={styles.summaryMeasurement} onLayout={handleMeasure}>
          {renderResolvedContent()}
        </View>
      ) : null}
    </View>
  );
}

export default function ReportScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [period, setPeriod] = useState<ReportPeriod>('daily');
  const [data, setData] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [infoVisible, setInfoVisible] = useState(false);
  // 리포트 본문을 통째로 캡처하기 위한 래퍼 ref. 캡처는 즉시 끝나지 않으므로(긴 뷰)
  // saving 동안 버튼을 스피너로 바꾼다. 저장은 add-only(writeOnly) 권한이면 충분하다 —
  // saveToLibraryAsync는 앨범을 만들지 않고 사진 앱에 바로 저장하므로 읽기 권한이 없어도 된다.
  const reportRef = useRef<View>(null);
  const [saving, setSaving] = useState(false);
  const [mediaPermission, requestMediaPermission] = MediaLibrary.usePermissions({
    writeOnly: true,
  });
  // 일간↔주간을 빠르게 오가면 먼저 보낸 요청이 나중에 도착할 수 있다. 최신 요청 번호와
  // 다른 응답은 성공이든 실패든 버려서, 늦게 온 이전 기간의 값이 화면을 덮지 못하게 한다.
  const seqRef = useRef(0);

  const fetchReport = useCallback(() => {
    if (!user?.user_id) return;
    const seq = ++seqRef.current;
    setLoading(true);
    setErrorText(null);
    // data는 비우지 않는다 — 이미 그려진 값을 유지한 채 새 값으로 교체해야 기간 전환이나
    // 재진입 때 스피너가 정상 데이터 위를 덮지 않는다.
    getReport(user.user_id, period)
      .then((res) => {
        if (seq !== seqRef.current) return;
        setData(res);
      })
      .catch((err) => {
        if (seq !== seqRef.current) return;
        setErrorText(err instanceof ApiError ? err.message : (err as Error).message);
      })
      .finally(() => {
        if (seq !== seqRef.current) return;
        setLoading(false);
      });
  }, [user?.user_id, period]);

  // fetchReport의 정체성이 period에 따라 바뀌므로 이 useFocusEffect 하나가 두 가지를 다
  // 처리한다: 화면 재진입(관심 영양소를 바꾸고 돌아온 경우)과 기간 토글.
  useFocusEffect(
    useCallback(() => {
      fetchReport();
    }, [fetchReport])
  );

  // 화면에 남아 있는 값이 지금 선택된 기간의 것이 아닌 상태. 새로 눌린 토글 라벨 아래에
  // 다른 기간의 숫자가 그대로 보이는 구간이라 흐리게 처리하고 조작도 막는다. 전환 요청이
  // 실패해도 값이 맞을 때까지 흐린 상태가 유지된다 — 어긋난 숫자를 또렷하게 보여주는 것보다
  // 낫고, 실패 사유는 아래 errorText가 알려준다.
  const showingOtherPeriod = data != null && data.period !== period;
  const nutrients = data?.nutrient_items.nutrients ?? [];

  const handleSaveImage = async () => {
    if (saving || !reportRef.current) return;
    setSaving(true);
    try {
      // 권한 — OCR 카메라 흐름(food-entry-ocr-guide.tsx)과 같은 패턴: 이미 허용됐으면
      // 그대로, 아니면 요청하고, 그래도 거부면 안내 후 중단(조용히 실패하지 않는다).
      const permission = mediaPermission?.granted
        ? mediaPermission
        : await requestMediaPermission();
      if (!permission.granted) {
        Alert.alert('저장 권한 필요', '사진 앱에 저장하려면 권한이 필요해요');
        return;
      }

      // 스크롤로 가려진 부분까지 포함해 리포트 래퍼 전체를 PNG로 캡처한다.
      const uri = await captureRef(reportRef, { format: 'png', quality: 1 });
      await MediaLibrary.saveToLibraryAsync(uri);

      Alert.alert('저장 완료', '건강 리포트를 사진 앱에 저장했어요.');
    } catch {
      // 권한 외 실패(캡처/저장 오류)도 조용히 넘기지 않는다.
      Alert.alert('저장 실패', '이미지를 저장하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 7, paddingBottom: insets.bottom + 32 },
        ]}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
            <PrevIcon width={15} height={15} />
          </Pressable>
        </View>

        {/* 캡처 대상 래퍼 — 저장 이미지에 담길 리포트 본문 전체를 감싼다. 위 headerRow
            (뒤로가기 + 화면 타이틀)는 내비 크롬이라 이 래퍼 밖에 두어 PNG에 담기지
            않는다. 대신 이미지가 스스로 무엇인지 알 수 있도록 래퍼 맨 위에 제목과
            기간을 다시 적는다. 아래 자식들의 들여쓰기는 diff를 최소화하려 그대로 뒀다. */}
        <View ref={reportRef} collapsable={false} style={styles.captureArea}>
        {data ? (
          <View style={styles.captureHeader}>
            <Text style={styles.title}>건강 리포트</Text>
            <Text style={styles.captureMeta}>
              {`${data.period === 'daily' ? '일간' : '주간'} · ${data.summary_card.date_range}`}
            </Text>
          </View>
        ) : null}

        <Text style={styles.screenSubtitle}>{SCREEN_SUBTITLE}</Text>

        {data ? (
          <LinearGradient
            colors={[reportColors.bannerGradientFrom, reportColors.bannerGradientTo]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.bannerCard}>
            <View style={styles.bannerTexts}>
              <Text style={styles.bannerWeek} numberOfLines={1}>
                ♥ {data.summary_card.title}
              </Text>
              <Text style={styles.bannerSubtitle} numberOfLines={1}>
                {data.summary_card.subtitle}
              </Text>
              <Text style={styles.bannerDate} numberOfLines={1}>
                {data.summary_card.date_range}
              </Text>
            </View>
            <View style={styles.bannerNoteBox} pointerEvents="none">
              <Image
                source={require('@/assets/images/premium/premium.png')}
                style={styles.bannerNoteImage}
              />
            </View>

            {/* 흰 원판 없이 배너 배경 위에 바로 글리프만 그린다. 일러스트가 왼쪽으로
                비켜서 더 이상 이 자리와 겹치지 않는다. 누르는 영역은 32x32로 유지한다. */}
            <Pressable
              style={styles.bannerInfoButton}
              onPress={() => setInfoVisible(true)}
              accessibilityRole="button"
              accessibilityLabel="일간과 주간 기준 설명 보기">
              <InformationIcon width={16} height={16} color={authColors.pink} />
            </Pressable>
          </LinearGradient>
        ) : null}

        <PeriodToggle period={period} onChange={setPeriod} />

        {errorText ? <Text style={styles.errorText}>{errorText}</Text> : null}

        {loading && !data ? (
          <ActivityIndicator size="small" color={authColors.pink} style={styles.loading} />
        ) : null}

        {data ? (
          <View
            style={[styles.section, showingOtherPeriod && styles.sectionStale]}
            pointerEvents={showingOtherPeriod ? 'none' : 'auto'}>
            <IntakeTrendChart chart={data.chart} />

            {/* 배치는 period(선택된 탭)가 아니라 data.period(지금 그려진 값의 기간)로 고른다 —
                위의 흐림 구간에서 일간 숫자가 주간 배치로 튀지 않게 하려면 값과 배치가
                같이 움직여야 한다. */}
            {data.period === 'daily' ? (
              // 일간(331:245): 행 전체가 하나의 카드 안에 들어간다. Figma는 3행이지만
              // 카페인 + 선택 영양소만큼 늘어나므로 높이를 고정하지 않는다.
              <View style={styles.dailyContainer}>
                {/* 카페인 + 선택 영양소를 한 배열로 돌려서, 구분선을 "첫 행 위에는 없고
                    마지막 행 아래에도 없다"는 규칙 하나로 처리한다. */}
                {[data.nutrient_items.caffeine, ...nutrients].map((item, index) => (
                  <Fragment key={item.key}>
                    {index > 0 ? <View style={styles.dailyDivider} /> : null}
                    <DailyNutrientRow item={item} />
                  </Fragment>
                ))}
                {nutrients.length === 0 ? (
                  <>
                    <View style={styles.dailyDivider} />
                    <Text style={styles.emptyText}>{EMPTY_NUTRIENTS_TEXT}</Text>
                  </>
                ) : null}
              </View>
            ) : (
              <View style={styles.weeklyList}>
                <WeeklyNutrientCard
                  item={data.nutrient_items.caffeine}
                  comparison={data.comparison}
                />
                {nutrients.map((item) => (
                  <WeeklyNutrientCard key={item.key} item={item} comparison={data.comparison} />
                ))}
                {nutrients.length === 0 ? (
                  <Text style={styles.emptyText}>{EMPTY_NUTRIENTS_TEXT}</Text>
                ) : null}
              </View>
            )}

            <AiSummaryCard
              summary={data.ai_summary}
              userId={user?.user_id}
              period={data.period}
              date={data.period === 'daily' ? data.date : data.date_range.start}
            />
          </View>
        ) : null}
        </View>
      </ScrollView>

      {/* 저장 버튼 — 캡처 래퍼 밖(ScrollView 형제)이라 버튼/스피너 자체는 PNG에
          담기지 않는다. top은 headerRow와 같은 높이(insets.top + 7)로 맞춘다.
          리포트가 그려졌을 때만 노출한다. */}
      {data ? (
        <Pressable
          style={[styles.saveButton, { top: insets.top + 7 }]}
          onPress={handleSaveImage}
          disabled={saving}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel="건강 리포트를 이미지로 저장">
          {saving ? (
            <ActivityIndicator size="small" color={authColors.pink} />
          ) : (
            <Text style={styles.saveButtonText}>이미지로 저장</Text>
          )}
        </Pressable>
      ) : null}

      <BottomSheet visible={infoVisible} onClose={() => setInfoVisible(false)}>
        <View
          style={[
            styles.infoSheet,
            { paddingBottom: styles.infoSheet.paddingBottom + insets.bottom },
          ]}>
          <Text style={styles.infoSheetBody}>
            <Text style={styles.infoSheetHeading}>일간</Text>
            {'\n하루 동안 먹은 총량을 기준으로 보여줘요.\n\n'}
            <Text style={styles.infoSheetHeading}>주간</Text>
            {'\n기록한 날들의 '}
            <Text style={styles.infoSheetStrong}>하루 평균</Text>
            {'을 기준으로 보여줘요.\n7일 합계가 아니라서, 기준량도 하루 기준 그대로예요.\n그래프는 그날 하루 값을, 아래 카드는 그 평균값을 보여줘요.'}
          </Text>
          <Pressable onPress={() => setInfoVisible(false)}>
            <Text style={styles.infoSheetCloseText}>확인</Text>
          </Pressable>
        </View>
      </BottomSheet>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FEFAF9',
  },
  scroll: {
    flex: 1,
  },
  content: {
    // 좌우 여백(19)은 captureArea로 옮겼다 — 캡처 PNG가 카드를 화면 끝까지 붙이지
    // 않고 여백을 갖도록. 세로 여백(paddingTop/Bottom)은 contentContainerStyle 배열에
    // 인라인으로 붙는다.
  },

  // ── 이미지 저장 (캡처 래퍼 + 버튼) ─────────────────────
  // 화면 배경과 같은 색을 줘서 PNG 배경이 투명해지지 않게 한다(화면상 변화 없음).
  // paddingHorizontal은 content에서 옮겨온 값 — 화면상 카드 위치는 그대로면서 캡처
  // 이미지에는 좌우 여백이 생긴다.
  captureArea: {
    backgroundColor: '#FEFAF9',
    paddingHorizontal: 19,
  },
  // 저장 이미지 맨 위의 제목 블록. 내비 헤더는 캡처에 담기지 않으므로 이미지에는
  // 이 블록이 유일한 제목이다. 위 headerRow와 시각적으로 붙지 않도록 위 여백을 둔다.
  captureHeader: {
    marginTop: 16,
    marginBottom: 4,
  },
  captureMeta: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    letterSpacing: -0.12,
    color: authColors.grayDark,
    marginTop: 4,
  },
  saveButton: {
    position: 'absolute',
    right: 19,
    height: 36,
    minWidth: 96,
    paddingHorizontal: 14,
    borderRadius: 18,
    backgroundColor: authColors.pinkLight,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 13,
    color: authColors.pink,
  },

  // ── 헤더 ───────────────────────────────────────────────
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    // content에서 좌우 패딩을 걷어냈으므로 내비 헤더는 자체 패딩으로 원래 위치(x=19)를
    // 유지한다 — 캡처 래퍼 밖이라 captureArea 패딩의 영향을 받지 않는다.
    paddingHorizontal: 19,
  },
  prevButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: authColors.pinkLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 20,
    color: authColors.brown,
  },
  screenSubtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    letterSpacing: -0.12,
    color: authColors.grayDark,
    marginTop: 7,
  },

  // ── 배너(331:264) ──────────────────────────────────────
  bannerCard: {
    marginTop: 31,
    height: 119,
    borderRadius: 25,
    overflow: 'hidden',
  },
  bannerTexts: {
    paddingTop: 23,
    paddingLeft: 22,
    // 일러스트 왼쪽 끝(오른쪽에서 44+100=144)보다 더 안쪽에서 끊어지도록 여유를 둔다.
    // numberOfLines=1과 함께 쓰여서, 문구가 길어지면 줄바꿈으로 배너 높이를 밀지 않고
    // 말줄임된다.
    paddingRight: 150,
  },
  bannerWeek: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 22,
    lineHeight: 27,
    letterSpacing: -1.1,
    color: authColors.pink,
  },
  bannerSubtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 13,
    lineHeight: 16,
    letterSpacing: -0.13,
    color: authColors.gray,
    marginTop: 4,
  },
  bannerDate: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 13,
    lineHeight: 16,
    letterSpacing: -0.13,
    color: authColors.grayDark,
    marginTop: 14,
  },
  bannerNoteBox: {
    position: 'absolute',
    right: NOTE_BOX_RIGHT_INSET,
    top: 5,
    width: NOTE_BOX,
    height: NOTE_BOX,
    overflow: 'hidden',
  },
  bannerNoteImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'contain',
  },
  // 정보 버튼의 실제 누르는 영역은 32x32다. 원판이 없어진 뒤로는 글리프가 배경 위에
  // 바로 놓이므로 별도 보정 없이 가운데 정렬만 하면 된다.
  bannerInfoButton: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },

  // ── 일간/주간 토글(332:323) ────────────────────────────
  toggleTrack: {
    flexDirection: 'row',
    marginTop: 11,
    height: 36,
    borderRadius: 100,
    backgroundColor: reportColors.toggleTrack,
    borderWidth: 1,
    borderColor: authColors.border,
  },
  togglePill: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    borderRadius: 100,
    backgroundColor: authColors.pinkLight,
    borderWidth: 1,
    borderColor: reportColors.toggleActiveBorder,
  },
  toggleHalf: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  toggleLabel: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 13,
    letterSpacing: -0.13,
  },

  errorText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.pink,
    marginTop: 16,
  },
  loading: {
    marginTop: 32,
  },
  section: {
    marginTop: 16,
    gap: 17,
  },
  sectionStale: {
    opacity: 0.4,
  },

  // ── 일간: 공용 컨테이너 + 행 ───────────────────────────
  dailyContainer: {
    borderRadius: 15,
    borderWidth: 0.7,
    borderColor: authColors.border,
    backgroundColor: authColors.white,
    paddingHorizontal: 16,
    paddingVertical: 20,
    // 행 사이에 1px 구분선을 끼우므로 gap을 절반으로 나눈다: 10.5 + 1 + 10.5 = 22로
    // 프레임의 행 간격이 그대로 유지된다.
    gap: 10.5,
    overflow: 'hidden',
  },
  // 프레임에는 없는 선이다 — 실기기에서 행이 서로 붙어 읽혀서 넣었다. 컨테이너의
  // 자식이라 좌우 16 패딩 안쪽으로 저절로 맞춰진다.
  dailyDivider: {
    height: 1,
    backgroundColor: authColors.border,
  },
  dailyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    // 63은 Figma 치수 그대로다. height가 아니라 minHeight인 이유는 폰트 확대 설정이나
    // 유난히 긴 값이 들어와도 잘리지 않고 늘어나게 하기 위함이며, 값이 들어맞는
    // 정상 상황에서는 결과가 동일하다.
    minHeight: 63,
  },

  // ── 주간: 카드 하나가 영양소 하나 ──────────────────────
  weeklyList: {
    // Figma는 106 간격(89 카드 + 17)이지만 실기기에서 너무 성글게 읽혀 12로 좁힌다.
    // 프레임을 따라가지 않기로 한 의도적인 차이다.
    gap: 12,
  },
  weeklyCard: {
    flexDirection: 'row',
    // 왼쪽 덩어리를 가운데가 아니라 위에 붙여 아이콘이 Figma의 y=12(카드 세로 여백)에
    // 정확히 오게 한다. 오른쪽 열은 alignSelf: 'stretch'라 이 값의 영향을 받지 않는다.
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    minHeight: 89,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 15,
    borderWidth: 0.7,
    borderColor: authColors.border,
    backgroundColor: reportColors.weeklyCardBg,
  },
  weeklyReadoutPanel: {
    position: 'absolute',
    // -0.7은 바깥 상자의 테두리 두께다. 이만큼 밀어야 두 상자의 테두리가 Figma처럼 겹쳐
    // 그려지고, 왼쪽·위·아래에 분홍 실선이 비치지 않는다.
    left: -0.7,
    top: -0.7,
    bottom: -0.7,
    // Figma는 349 안에서 201(=57.6%)이다. 201을 그대로 고정하면 폭이 360인 기기에서
    // 분홍 영역이 121만 남아 오른쪽 비교 열(최소 128)과 겹친다. 비율로 두면 360에서도
    // 185가 남아 게이지(오른쪽 끝 161)와 비교 열이 모두 들어간다.
    width: '57.6%',
    borderRadius: 15,
    borderWidth: 0.7,
    borderColor: authColors.border,
    backgroundColor: authColors.white,
  },
  weeklyCompareColumn: {
    // 카드 세로 여백(12)에 5를 더해 compare1을 Figma의 y=17에 맞춘다.
    alignSelf: 'stretch',
    justifyContent: 'flex-start',
    // stretch라야 두 행이 같은 폭을 갖고, 그 안에서 라벨이 왼쪽 끝·값이 오른쪽 끝에
    // 정렬된다. flex-end로 두면 행마다 내용 폭이 달라 라벨 시작점이 어긋난다.
    alignItems: 'stretch',
    paddingTop: 5,
    // Figma 구분선 폭. 폭을 고정하지 않는 이유는 "- 정보 없음"이 "▲ 13%p"보다 넓어서
    // 고정하면 잘리기 때문이다 — 최소치만 잡고 내용에 따라 늘어나게 둔다.
    minWidth: 128,
    marginLeft: 12,
  },
  compareDivider: {
    alignSelf: 'stretch',
    height: 1,
    backgroundColor: authColors.border,
    marginTop: 9,
  },

  // ── 두 배치가 공유하는 내부 요소 ───────────────────────
  readout: {
    flex: 1,
  },
  labelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    // 아이콘 오른쪽 끝(16+17=33)에서 라벨 시작(36)까지 3.
    gap: 3,
  },
  // letterSpacing은 Figma의 tracking 값 그대로다(대략 -0.02em). 빠뜨리면 글자가
  // 전체적으로 벌어져 프레임과 다르게 읽힌다. 일간 행(331:319)과 주간 카드(46:461)의
  // tracking 값이 같아서 두 배치가 이 스타일들을 그대로 공유한다.
  nutrientLabel: {
    fontFamily: fonts.medium,
    fontSize: 13,
    letterSpacing: -0.25,
    color: authColors.brown,
  },
  valueRow: {
    marginTop: 5,
  },
  value: {
    fontFamily: fonts.semiBold,
    fontSize: 20,
    letterSpacing: -0.4,
  },
  limit: {
    fontFamily: fonts.medium,
    fontSize: 12,
    letterSpacing: -0.24,
    color: authColors.gray,
  },
  barRow: {
    flexDirection: 'row',
    alignItems: 'center',
    // 게이지 오른쪽 끝(16+145=161)에서 퍼센트 글자 시작(165)까지 4.
    gap: 4,
    marginTop: 6,
  },
  // 프레임은 145지만 실기기에서 너무 길게 읽혀 120으로 줄인다. 의도적인 차이이므로
  // 프레임과 맞추겠다고 145로 되돌리지 말 것. 옆의 퍼센트 글자는 같은 flex 행에 있어
  // 게이지가 짧아진 만큼 4pt 간격을 유지한 채 함께 왼쪽으로 붙는다.
  barTrack: {
    width: 120,
    height: 8,
    borderRadius: 100,
    overflow: 'hidden',
  },
  barFill: {
    height: 8,
    borderRadius: 100,
  },
  // 게이지 옆 작은 퍼센트만 영양소 색을 쓰지 않는다 — 세 프레임 모두 회색(#848484)이다.
  barPercent: {
    fontFamily: fonts.medium,
    fontSize: 10,
    letterSpacing: -0.2,
    color: authColors.gray,
  },
  // 라벨은 왼쪽 끝, 값은 오른쪽 끝. 프레임에서 두 줄의 라벨이 같은 x에서 시작하고
  // (주간 215, 일간 234) 값은 블록 오른쪽 끝으로 밀려 있다. gap은 space-between과 함께
  // 최소 간격으로 남겨둔다 — 값이 길어져도 라벨에 붙지 않는다.
  compareRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 9,
  },
  // 일간 행은 오른쪽 블록이 컨테이너 없이 바로 붙으므로 여기서 간격을 준다
  // (주간은 weeklyCompareColumn이 같은 역할을 한다). 118은 프레임의 compare1 폭이고,
  // 고정이 아니라 최소값인 이유는 "섭취 상태 정보없음"이 그보다 넓기 때문이다.
  dailyCompare: {
    minWidth: 118,
    marginLeft: 12,
  },
  compareDeltaRow: {
    marginTop: 7,
  },
  compareLabel: {
    fontFamily: fonts.medium,
    fontSize: 12,
    letterSpacing: -0.24,
    color: authColors.grayDark,
  },
  // 오른쪽 두 값은 크기가 다르다 — 권장 기준 대비 17, 지난주 대비 15(compareDelta).
  compareValue: {
    fontFamily: fonts.semiBold,
    fontSize: 17,
    letterSpacing: -0.34,
  },
  compareDelta: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    letterSpacing: -0.3,
  },
  // 숫자가 아닌 안내 문구라 숫자와 같은 무게로 그리지 않는다. 라벨과 같은 크기라
  // 폭도 Figma 구분선(128) 안에 들어간다.
  compareMissing: {
    fontFamily: fonts.medium,
    fontSize: 12,
    letterSpacing: -0.24,
  },
  emptyText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    lineHeight: 20,
  },

  // ── AI 분석 요약(331:320) ──────────────────────────────
  summaryCard: {
    backgroundColor: reportColors.aiCardBg,
    borderRadius: 10,
    borderWidth: 0.7,
    borderColor: authColors.border,
    paddingHorizontal: 10,
    paddingTop: 15,
    paddingBottom: 18,
  },
  summaryHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  summarySpark: {
    width: 20,
    height: 20,
  },
  summaryTitle: {
    flex: 1,
    fontFamily: fonts.medium,
    fontSize: 14,
    color: authColors.brown,
  },
  summaryChevron: {
    padding: 4,
  },
  // ── 일간/주간 기준 안내 시트 ───────────────────────────
  // OCR 확인 화면의 info 시트와 같은 형태를 쓴다(BottomSheet + 흰 시트 + 확인).
  infoSheet: {
    backgroundColor: authColors.white,
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    paddingTop: 36,
    paddingHorizontal: 19,
    paddingBottom: 40,
  },
  infoSheetBody: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 14,
    lineHeight: 21,
    color: authColors.grayDark,
  },
  infoSheetHeading: {
    fontFamily: nanumSquareRound.bold,
    color: authColors.brown,
  },
  infoSheetStrong: {
    fontFamily: nanumSquareRound.bold,
  },
  infoSheetCloseText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: authColors.pink,
    textAlign: 'center',
    marginTop: 24,
    textDecorationLine: 'underline',
  },

  summaryBody: {
    // Figma는 17이지만 제목과 본문이 한 덩어리로 읽히도록 절반으로 줄인다.
    marginTop: 8.5,
    paddingHorizontal: 16,
  },
  // 오프스크린 측정 사본 — summaryCard(paddingHorizontal:10) + summaryBody
  // (paddingHorizontal:16)와 같은 26px 인셋을 줘서 실제 펼침 블록과 같은 폭으로
  // 줄바꿈되게 한다. opacity 0이라 top 위치는 결과에 영향이 없다.
  summaryMeasurement: {
    position: 'absolute',
    left: 26,
    right: 26,
    top: 0,
    opacity: 0,
  },
  summaryMessageRow: {
    flexDirection: 'row',
    gap: 6,
  },
  summaryBullet: {
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 20,
    color: authColors.grayDark,
  },
  // flex:1은 flexDirection:'row' 컨테이너(summaryMessageRow) 안에서 불릿 옆 남은
  // 너비를 채우기 위한 것 — row로 감싸지 않은 column의 단독 자식으로 쓰면 그
  // flex:1이 세로축에 적용되어 높이가 0으로 붕괴한다(과거 이 카드의 AI 문단이
  // 화면에 보이지 않던 원인). 항상 summaryMessageRow와 짝지어 쓸 것.
  summaryMessage: {
    flex: 1,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 20,
    color: authColors.grayDark,
  },
  summaryLoadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    height: AI_ANALYSIS_LOADING_HEIGHT,
  },
  // 2단계 AI 설명 아래 저강조 안내 — infoSheetBody보다 한 단계 더 작고 옅게, 본문
  // 문구(summaryMessage)와 시각적으로 섞이지 않도록 둔다.
  summaryDisclaimer: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 10,
    lineHeight: 14,
    color: authColors.gray,
    marginTop: 8,
  },
});
