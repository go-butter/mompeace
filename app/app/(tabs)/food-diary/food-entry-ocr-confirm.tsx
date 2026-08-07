import DateTimePicker from '@react-native-community/datetimepicker';
import { router, useLocalSearchParams } from 'expo-router';
import { ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import Animated, {
  Easing,
  interpolate,
  runOnJS,
  useAnimatedProps,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import {
  KeyboardAvoidingView,
  LayoutChangeEvent,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Circle, Path, Svg } from 'react-native-svg';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';

import ChevronDownIcon from '@/assets/images/common/chevron_down_plain.svg';
import CautionIcon from '@/assets/images/scan/caution.svg';
import ClockIcon from '@/assets/images/common/clock.svg';
import PrevIcon from '@/assets/images/common/prev.svg';
import ScaleIcon from '@/assets/images/scan/scale.svg';
import SearchIcon from '@/assets/images/scan/search.svg';
import StandardScaleIcon from '@/assets/images/scan/standard_scales.svg';
import InformationIcon from '@/assets/images/onboarding/information.svg';
import CaffeineIcon from '@/assets/images/foodDiary/caffeine.svg';
import SodiumIcon from '@/assets/images/foodDiary/sodium.svg';
import SugarIcon from '@/assets/images/foodDiary/sugar.svg';
import CaloriesIcon from '@/assets/images/foodDiary/calories.svg';
import CarbohydrateIcon from '@/assets/images/foodDiary/carbohydrate.svg';
import FatIcon from '@/assets/images/foodDiary/fat.svg';
import IronIcon from '@/assets/images/foodDiary/iron.svg';
import ProteinIcon from '@/assets/images/foodDiary/protein.svg';
import { authColors } from '@/components/auth/colors';
import BottomSheet from '@/components/common/BottomSheet';
import StatusChip from '@/components/common/StatusChip';
import AmountUnitPicker, { WEIGHT_UNITS } from '@/components/food-diary/AmountUnitPicker';
import { homeColors } from '@/components/home/colors';
import { summaryStatusColors, DEFAULT_SUMMARY_STATUS_COLORS } from '@/components/home/summaryColors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { NUTRIENT_LABELS_KO, SELECTABLE_NUTRIENT_KEYS, SelectableNutrientKey } from '@/constants/nutrients';
import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  createFoodLog,
  getOcrAlternatives,
  OcrAlternativesResponse,
  OcrHeadline,
  OcrNutrientStatus,
  OcrProjectionNutrientKey,
  OcrRecomputeNutrientInput,
  OcrScaleMethod,
  OcrScanResponse,
  OcrStatusTier,
  recomputeOcrStatuses,
} from '@/lib/api-client';

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

const EXPAND_SPRING_CONFIG = { damping: 16, stiffness: 100, mass: 1 };
const DRAFT_ROW_HEIGHT = 42;
const TIME_PICKER_HEIGHT = 216;
// /ocr/alternatives는 제품명 분류를 위해 Gemini를 최대 2회 호출한다
// (backend/ocr_category_classifier.py). 그 호출은 GEMINI_CLASSIFY_DAILY_CALL_LIMIT
// (기본 30회/일)을 소모하므로, 실제 Gemini를 켠 뒤에는 이 화면에서 몇 번만 재호출해도
// 하루치 분류 예산이 조용히 바닥난다 — 그래서 디바운스를 넉넉히 잡는다.
const ALTERNATIVES_DEBOUNCE_MS = 1500;
// /ocr/recompute는 Gemini를 부르지 않고 DB 조회 + 산술뿐이라(backend/routers/ocr.py)
// 대체 메뉴 호출처럼 예산을 태우지 않는다. 타이핑 한 글자마다 보내지 않을 만큼만 짧게 잡는다.
const RECOMPUTE_DEBOUNCE_MS = 300;
// 7행 영양성분 테이블의 펼침 애니메이션 목표 높이 — 실제 콘텐츠 높이의 근사치일 뿐이다.
// 애니메이션이 끝나면 height를 undefined(auto)로 전환해 실제 높이에 맞추므로, 이 값이
// 다소 넉넉해도(잘림보다 여백이 나는 쪽이 안전) 정지 상태의 표시에는 영향이 없다.
const NUTRIENT_TABLE_HEIGHT = 400;
// 기준량 배지에 쓸 파란색 — 팔레트에 채도 있는 파란색 토큰이 없어 새로 추가한다.
// waterColors.waveFront(#C2E1F5) 계열 색상군과 어울리도록 고른 값.
const BASIS_BADGE_BLUE = '#5B9BD1';
const BASIS_BADGE_BLUE_BG = '#EAF3FA';

const NUTRIENT_ICONS: Record<SelectableNutrientKey, ReactNode> = {
  carbohydrate: <CarbohydrateIcon width={17} height={17} color="#F47E8A" />,
  sugar: <SugarIcon width={17} height={17} color="#F47E8A" />,
  energy: <CaloriesIcon width={17} height={17} color="#F47E8A" />,
  fat: <FatIcon width={17} height={17} color="#F47E8A" />,
  iron: <IronIcon width={17} height={17} color="#F47E8A" />,
  protein: <ProteinIcon width={17} height={17} color="#F47E8A" />,
  sodium: <SodiumIcon width={18} height={18} color="#F47E8A" />,
};

const NUTRIENT_UNITS: Record<SelectableNutrientKey, string> = {
  carbohydrate: 'g',
  sugar: 'g',
  energy: 'kcal',
  fat: 'g',
  iron: 'mg',
  protein: 'g',
  sodium: 'mg',
};

type InfoKey = 'safety' | 'nutrientStatus' | 'nutrientDetail';

const INFO_CONTENT: Record<InfoKey, { title: string; body: string; note?: string }> = {
  safety: {
    title: '오늘 섭취 안전도란?',
    body: '오늘 기록한 음식에 이 음식을 더했을 때, 임신 중 하루 권장 섭취 기준과 비교해 안전한 수준인지 알려드려요. 게이지의 %는 가장 주의가 필요한 성분 하나가 하루 기준 대비 얼마나 되는지를 나타내요.',
  },
  nutrientStatus: {
    title: '영양소 섭취 분석이란?',
    body: '이 음식만의 영양성분이 아니라, 오늘 푸드 다이어리에 기록한 음식까지 모두 더한 결과예요. 위험·주의는 하루 기준을 초과했다는 뜻이고, 부족은 아직 권장량에 못 미쳤다는 뜻이에요.',
  },
  nutrientDetail: {
    title: '영양성분 상세란?',
    body: '라벨에 표시된 기준량당 영양성분과, 실제로 섭취한 양(총섭취량) 기준 영양성분을 함께 보여드려요. 총섭취량 값은 기준량당 값에 섭취량을 곱해 자동으로 계산돼요.',
    note: '※ 카페인 함량은 제품 라벨의 원재료명 또는 영양정보 표시 앞부분에 별도로 표기되는 경우가 많아요. 라벨에서 바로 안 보이면 앞쪽을 확인해보세요.',
  },
};

function sanitizeNonNegativeDecimal(text: string) {
  const digitsAndDot = text.replace(/[^0-9.]/g, '');
  const firstDotIndex = digitsAndDot.indexOf('.');
  if (firstDotIndex === -1) return digitsAndDot;
  return (
    digitsAndDot.slice(0, firstDotIndex + 1) +
    digitsAndDot.slice(firstDotIndex + 1).replace(/\./g, '')
  );
}

function formatTimeLabel(time: Date) {
  const hours = time.getHours();
  const minutes = time.getMinutes();
  const period = hours < 12 ? '오전' : '오후';
  const displayHour = hours % 12 === 0 ? 12 : hours % 12;
  return `${period} ${displayHour}:${String(minutes).padStart(2, '0')}`;
}

function toEatenAt(date: string, time: Date) {
  const hh = String(time.getHours()).padStart(2, '0');
  const min = String(time.getMinutes()).padStart(2, '0');
  const ss = String(time.getSeconds()).padStart(2, '0');
  return `${date} ${hh}:${min}:${ss}`;
}

// backend의 truncate_to_places(value, 2)와 동일하게 0 방향으로 절사한다 (반올림 아님).
function truncate2(value: number) {
  return Math.trunc(value * 100) / 100;
}

// 한글 명사에 붙는 "은/는" 조사 — 마지막 글자에 받침이 있으면 "은", 없으면 "는".
// 7개 영양소 이름 전부(탄수화물/당류/에너지/지방/철분/단백질/나트륨)에 대해
// 문법적으로 맞는 헤드라인 문장을 만들기 위해 하드코딩 대신 규칙으로 계산한다.
function attachEunNeun(word: string): string {
  const lastChar = word.charCodeAt(word.length - 1);
  const hasBatchim = lastChar >= 0xac00 && lastChar <= 0xd7a3 && (lastChar - 0xac00) % 28 !== 0;
  return `${word}${hasBatchim ? '은' : '는'}`;
}

// 헤드라인 문장 — mockup의 "지방은 주의가 필요해요"처럼 자연스러운 구어체를 쓴다.
// 배지의 원문 그대로("위험")를 문장에 넣지 않는다 — 부드러운 표현이 목적이라
// 굳이 같은 단어를 반복할 필요가 없다. 정보없음은 특정 성분 이름을 넣지 않는다
// (판단 근거가 없다는 뜻이라 "이 성분이 문제"라는 느낌을 주면 오해의 소지가 있다).
// neutral(하한 미달)은 경고가 아니라 사실 진술이다 — 아침에 스캔하면 하루 목표에
// 못 미치는 것이 당연하므로 결핍처럼 읽히면 안 된다(api-client.ts의 OcrStatusTier 주석).
// 서버는 neutral/unknown을 헤드라인 후보에서 제외하지만(backend/intake_totals.py의
// _HEADLINE_TIERS), tier는 API 계약이므로 다섯 값 전부를 여기서 직접 분기한다.
function buildHeadlineText(tier: OcrStatusTier, nutrientLabel: string): string {
  switch (tier) {
    case 'avoid':
      return `${attachEunNeun(nutrientLabel)} 오늘 초과예요`;
    case 'caution':
      return `${attachEunNeun(nutrientLabel)} 오늘 허용량에 가까워지고 있어요`;
    case 'safe':
      return `${attachEunNeun(nutrientLabel)} 여유있게 드실 수 있어요`;
    case 'neutral':
      return '아직 채우는 중이에요';
    case 'unknown':
      return '라벨에서 확인 가능한 정보가 부족해요';
  }
}

// 헤드라인 아래 2줄 설명 — 특정 성분이 아니라 단계 전체를 설명하는 문구라
// 이전 라운드에 이미 승인된 카피(OVERALL_TIER_HEADLINE)를 그대로 재사용한다.
const TIER_DESCRIPTION: Record<OcrStatusTier, string> = {
  avoid: '다른 메뉴를 고려하거나, 남은 하루는 이 성분을 줄여보세요',
  caution: '오늘 허용량에 거의 다 찼어요, 적당히 조절해주세요',
  safe: '오늘 허용량 안에서 여유있게 드실 수 있어요',
  neutral: '하루 권장량에 아직 못 미쳤어요.',
  unknown: '라벨에서 확인 가능한 정보가 부족해요, 직접 수치를 확인해주세요',
};

// tier별 표시 규칙을 한곳에 모은다 — 헤드라인 문장 색, 게이지 밴드 문구, 게이지 호 비율.
// statusLabel은 배지 그리드가 이미 쓰는 기존 상태 문구(여유/안전/위험/정보없음)이면서
// summaryColors.ts의 색 키이기도 해서, 문구와 색이 항상 같은 값에서 함께 나온다.
//
// neutral은 safe와 같은 취급이다 — 의미가 같은 라벨인 "부족"은 "안전"과 색을 공유하는
// 중간 경고 색이라(summaryColors.ts 주석: 안전/부족은 같은 "중간 경고" 의미) 그대로
// 쓰면 경고로 읽힌다. neutral은 문제가 아니라 사실 진술이므로 경고 취급을 하지 않는다.
//
// arcPercent는 링을 얼마나 채울지만 정하는 표시용 기하값이다 — 무엇과도 비교되지 않고
// 심각도를 판정하지도 않는다(심각도는 서버가 보낸 tier에서 이미 확정됐다).
//
// 방향은 "심각도" 기준이다: 링이 많이 찰수록 더 심각하다(avoid가 가득, safe가 가장 적게).
// 예전 종합점수(높을수록 안전)를 그대로 옮겨 쓰던 때는 avoid가 가장 빈 링이라, 배지의
// 위험 표시·헤드라인 문구와 게이지가 서로 반대로 읽혔다.
//
// safe가 10이 아니라 15인 이유: 0인 neutral/unknown의 빈 링과 눈으로 구분되어야 한다
// (그 둘은 회색이라 색으로도 구분되지만, 형태로도 구분되는 편이 안전하다).
const TIER_DISPLAY: Record<OcrStatusTier, { statusLabel: string; arcPercent: number }> = {
  avoid: { statusLabel: '위험', arcPercent: 100 },
  caution: { statusLabel: '안전', arcPercent: 55 },
  safe: { statusLabel: '여유', arcPercent: 15 },
  neutral: { statusLabel: '여유', arcPercent: 0 },
  unknown: { statusLabel: '정보없음', arcPercent: 0 },
};

function tierColors(tier: OcrStatusTier) {
  return summaryStatusColors[TIER_DISPLAY[tier].statusLabel] ?? DEFAULT_SUMMARY_STATUS_COLORS;
}

// 화면에 떠 있는 판정이 지금 입력값의 판정이라고 말할 수 없는 두 상태의 문구.
// 흐리게만 처리하면 "지방은 주의가 필요해요" 같은 확정적인 문장을 그대로 읽게 되므로,
// 문장 자체를 상태에 맞는 안내로 교체한다. 두 상태는 서로 다른 문구를 쓴다 —
// "다시 계산 중"과 "계산에 실패함"은 사용자가 할 일이 다르기 때문이다(기다리기 vs 다시 누르기).
// pending에는 description이 없다 — 300ms 남짓 머무는 상태라 사용자가 끝까지 읽을 수
// 없는 문장은 소음일 뿐이다. 그래서 description은 선택 필드다.
const VERDICT_COPY: Record<
  'pending' | 'error',
  { headline: string; description?: string; gaugeLabel: string }
> = {
  pending: {
    headline: '판정을 다시 계산하고 있어요',
    gaugeLabel: '계산 중',
  },
  error: {
    headline: '판정을 계산하지 못했어요',
    description: '잠시 후 다시 시도해주세요.',
    gaugeLabel: '확인 불가',
  },
};

const RETRY_LABEL = '다시 시도';

// 영양성분 상세 테이블의 "100g당" 열 헤더 — 라벨의 실제 기준(reference_amount_
// display_method)에 따라 기준량이 100g가 아닐 수 있어(예: 총내용량당/1회
// 제공량당 라벨) scale_method + basis_amount_value로 동적으로 결정한다.
// needs_review가 아니라 scale_method만으로 분기한다 — per_basis_with_total인데
// serving_size_value만 없는 경우(needs_review=true)에도 기준량 자체는 알고 있으므로
// (예: "100g당") 정확한 라벨을 보여줄 수 있다.
// basisUnit은 scanResult.basis_amount_unit을 그대로 받는다 — 200ml 우유팩처럼
// 기준량이 ml인 라벨을 "200g당"으로 잘못 표시하지 않기 위해서다.
function getBasisLabel(
  scaleMethod: OcrScaleMethod,
  basisAmountValue: number | null,
  basisUnit: string
): string {
  switch (scaleMethod) {
    case 'per_basis_with_total':
      return basisAmountValue != null ? `${basisAmountValue}${basisUnit}당` : '기준량당';
    case 'total_content':
      return basisAmountValue != null ? `총 내용량당 (${basisAmountValue}${basisUnit})` : '총 내용량당';
    case 'per_serving_with_count':
      return basisAmountValue != null ? `1회 제공량당 (${basisAmountValue}${basisUnit})` : '1회 제공량당';
    case 'unknown':
    default:
      return '기준량 확인 필요';
  }
}

type DraftRowProps = {
  row: { id: string; name: string; value: string };
  onRemove: (id: string) => void;
  onUpdate: (id: string, field: 'name' | 'value', text: string) => void;
};

function DraftRow({ row, onRemove, onUpdate }: DraftRowProps) {
  const height = useSharedValue(0);
  const opacity = useSharedValue(0);

  useEffect(() => {
    height.value = withTiming(DRAFT_ROW_HEIGHT, { duration: 400, easing: Easing.out(Easing.cubic) });
    opacity.value = withTiming(1, { duration: 400 });
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    height: height.value,
    opacity: opacity.value,
    overflow: 'hidden',
  }));

  const handleRemove = () => {
    height.value = withTiming(0, { duration: 400, easing: Easing.out(Easing.cubic) });
    opacity.value = withTiming(0, { duration: 300 }, (finished) => {
      if (finished) runOnJS(onRemove)(row.id);
    });
  };

  return (
    <Animated.View style={animatedStyle}>
      <View style={styles.extraInputRow}>
        <TextInput
          style={styles.extraNameInput}
          placeholder="성분명"
          placeholderTextColor={authColors.gray}
          value={row.name}
          onChangeText={(text) => onUpdate(row.id, 'name', text)}
        />
        <TextInput
          style={styles.extraValueInput}
          placeholder="수치"
          placeholderTextColor={authColors.gray}
          value={row.value}
          onChangeText={(text) => onUpdate(row.id, 'value', text)}
          returnKeyType="done"
        />
        <Pressable hitSlop={8} onPress={handleRemove} style={styles.draftRemoveButton}>
          <Text style={styles.draftRemoveText}>×</Text>
        </Pressable>
      </View>
    </Animated.View>
  );
}

function PairedNutrientField({
  icon,
  label,
  unit,
  basisValue,
  detailValue,
  onChangeBasis,
  highlighted,
}: {
  icon: ReactNode;
  label: string;
  unit: string;
  basisValue: string;
  detailValue: string;
  onChangeBasis: (text: string) => void;
  // 오늘 섭취 안전도 헤드라인이 가리키는 성분과 같은 행일 때만 true — 서버가 고른
  // verdict.headline.key를 그대로 비교한 결과이고, 이 컴포넌트 안에서 새로
  // 무언가를 판정하지 않는다.
  highlighted?: boolean;
}) {
  // "100g당"/"총섭취량(...)" 라벨은 테이블 헤더 행(카드 상단, 핑크 배경)에서
  // 한 번만 보여준다 — 여기서 행마다 반복하면 중복이라 카드가 불필요하게
  // 길어진다. 이 행은 값만 보여준다.
  return (
    <View style={[styles.pairedRow, highlighted && styles.pairedRowHighlighted]}>
      <View style={styles.pairedLabelGroup}>
        {icon}
        <Text
          style={[styles.nutrientLabel, highlighted && styles.nutrientLabelHighlighted]}
          numberOfLines={1}>
          {label}({unit})
        </Text>
      </View>
      <View style={styles.columnDivider} />
      <View style={styles.pairedInputCol}>
        <TextInput
          style={styles.pairedInput}
          value={basisValue}
          onChangeText={onChangeBasis}
          placeholder="입력"
          placeholderTextColor={authColors.gray}
          keyboardType="decimal-pad"
        />
      </View>
      <View style={styles.columnDivider} />
      <View style={styles.pairedInputCol}>
        <Text
          style={[styles.pairedReadOnlyValue, highlighted && styles.pairedReadOnlyValueHighlighted]}>
          {detailValue}
        </Text>
      </View>
    </View>
  );
}

function SafetyGauge({
  tier,
  bandLabel,
  size = 96,
  // 판정을 그대로 보여줄 수 없는 상태(재계산이 필요하거나 진행 중)에는 링을 비우고
  // 회색으로 둔다. tier==='unknown'(판정할 값 자체가 없음)과는 의미가 달라 별도
  // 플래그로 받는다 — 둘을 합치면 "값이 없다"와 "다시 계산해야 한다"를 구분할 수 없다.
  muted = false,
  // undefined=지금 표시할 값이 없는 상태(pending/error) — 줄 자체를 그리지 않는다.
  // null=fresh인데 계산 불가(정보 없음, NULL≠0) — "-"를 보여준다.
  // number=fresh이고 값이 있음 — "N%"를 보여준다.
  percent,
}: {
  tier: OcrStatusTier;
  bandLabel: string;
  size?: number;
  muted?: boolean;
  percent?: number | null;
}) {
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const arcPercent = muted ? 0 : TIER_DISPLAY[tier].arcPercent;
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withTiming(arcPercent, { duration: 600 });
  }, [arcPercent, progress]);

  const animatedProps = useAnimatedProps(() => ({
    strokeDashoffset: circumference * (1 - progress.value / 100),
  }));

  const ringColor = muted ? authColors.border : tierColors(tier).value;

  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={authColors.border}
          strokeWidth={strokeWidth}
          fill="none"
        />
        <AnimatedCircle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={ringColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${circumference} ${circumference}`}
          fill="none"
          animatedProps={animatedProps}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      <View style={styles.gaugeLabelOverlay} pointerEvents="none">
        {percent !== undefined && (
          <Text
            style={[
              styles.gaugePercentText,
              (percent == null ? '-' : `${percent}%`).replace(/[.%]/g, '').length >= 4 &&
                styles.gaugePercentTextLong,
            ]}
            numberOfLines={1}>
            {percent == null ? '-' : `${percent}%`}
          </Text>
        )}
        <Text style={styles.gaugeBandText} numberOfLines={1}>
          {bandLabel}
        </Text>
      </View>
    </View>
  );
}

// 앱 내에 연필/편집 아이콘 에셋이 없어 인라인 SVG로 직접 그린다 — 총내용량/기준량
// 카드의 편집 토글 버튼 전용.
function PencilIcon({ size = 12, color = authColors.pink }: { size?: number; color?: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d="M12 20h9" stroke={color} strokeWidth={2} strokeLinecap="round" />
      <Path
        d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5Z"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </Svg>
  );
}

// 총내용량 배지 아이콘 — 상자(택배박스) 모양의 최소 선화. 마찬가지로 에셋이 없어
// react-native-svg Path로 직접 그린다.
function PackageGlyph({ size = 14, color = '#FFFFFF' }: { size?: number; color?: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3Z" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
      <Path d="M4 7.5 12 12l8-4.5" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
      <Path d="M12 12v9" stroke={color} strokeWidth={1.8} />
    </Svg>
  );
}

// 기준량 배지 아이콘 — 저울(balance) 모양의 최소 선화.
function BalanceGlyph({ size = 14, color = '#FFFFFF' }: { size?: number; color?: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 3v18M7 7h10M4 7l3-4 3 4-3 5-3-5Zm10 0 3-4 3 4-3 5-3-5Z"
        stroke={color}
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </Svg>
  );
}

export default function FoodEntryOcrConfirmScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const params = useLocalSearchParams<{ date: string; scan_result?: string }>();

  const scanResult = useMemo<OcrScanResponse | null>(() => {
    if (!params.scan_result) return null;
    try {
      return JSON.parse(params.scan_result) as OcrScanResponse;
    } catch {
      return null;
    }
  }, [params.scan_result]);

  useEffect(() => {
    if (!scanResult) {
      router.replace({ pathname: '/(tabs)/food-diary/food-entry-ocr-failure', params: { date: params.date } });
    }
    // scanResult가 없으면(잘못된 딥링크 등) 캡처 화면의 기존 실패 흐름을 그대로 재사용한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanResult]);

  const needsReview = scanResult?.needs_review ?? false;
  const scaleFactor = scanResult?.scale_factor_applied ?? null;
  // 기준량(basis_amount_value)은 스캔 결과에서 온 초기값이지만, Gemini가 라벨을
  // 잘못 읽었을 때(예: "100g당"을 "1000g당"으로 오독) 사용자가 고칠 수 있도록
  // 편집 가능한 상태로 승격한다. 아래 basisAmountValue는 매 렌더마다 다시 계산되는
  // 파생값이라 getBasisLabel/servingMultiplier 등 기존 소비처가 자동으로 최신값을 읽는다.
  const [basisAmountValueText, setBasisAmountValueText] = useState(
    scanResult?.basis_amount_value != null ? String(scanResult.basis_amount_value) : ''
  );
  const trimmedBasisAmountText = basisAmountValueText.trim();
  const parsedBasisAmountValue = Number(trimmedBasisAmountText);
  const basisAmountValue =
    trimmedBasisAmountText === '' || Number.isNaN(parsedBasisAmountValue) ? null : parsedBasisAmountValue;

  // 라벨에서 1회 제공량을 확정하지 못했지만(needs_review) 기준량(예: 100g)은 알 때 —
  // 인분수를 가정할 수 없으니 실제 섭취량(g)을 직접 입력받도록 유도한다. 그 외에는
  // 가장 흔한 단위인 인분/1을 기본값으로 시작한다.
  const [foodName, setFoodName] = useState(scanResult?.product_name ?? '');
  const [amount, setAmount] = useState(needsReview && basisAmountValue != null ? '' : '1');
  const [unit, setUnit] = useState(
    needsReview && basisAmountValue != null ? (scanResult?.basis_amount_unit ?? 'g') : '인분'
  );
  const [time, setTime] = useState(new Date());
  const [showTimePicker, setShowTimePicker] = useState(false);
  // 병합 카드(상품명/섭취량/섭취시간)의 표시 모드 — "스캔 결과 확인"이 핵심 목적이라
  // 도착 즉시 바로 검토/수정할 수 있도록 편집 모드로 시작한다(요약 모드는 검토가
  // 끝난 뒤 접어두는 용도).
  const [isEditingTopCard, setIsEditingTopCard] = useState(true);
  // 총내용량/기준량 카드 — 기본은 읽기 전용 배지 표시, 연필 버튼으로 기존 입력 행을 드러낸다.
  const [isEditingAmountCard, setIsEditingAmountCard] = useState(false);
  const [activeInfo, setActiveInfo] = useState<InfoKey | null>(null);
  const [caffeineMg, setCaffeineMg] = useState('');
  const [draftRows, setDraftRows] = useState<{ id: string; name: string; value: string }[]>([]);
  // 총내용량(g) — 라벨 헤더처럼 편집 가능. basis_amount_value(기준량, 100g)는
  // 이 화면에서 편집하지 않는 고정값 그대로 유지하고, 이 값만 상태로 승격한다.
  const [totalContentAmount, setTotalContentAmount] = useState(
    scanResult?.total_content_value != null ? String(scanResult.total_content_value) : ''
  );
  // 100g당 값만 저장한다 — 총내용량 열은 더 이상 편집 상태가 아니라 매 렌더마다
  // basis에서 계산되는 값이라 별도로 들고 있지 않는다.
  const [nutrientFields, setNutrientFields] = useState<Record<SelectableNutrientKey, string>>(() => {
    const initial = {} as Record<SelectableNutrientKey, string>;
    for (const key of SELECTABLE_NUTRIENT_KEYS) {
      const nv = scanResult?.nutrients?.[key];
      initial[key] = nv?.basis_value != null ? String(nv.basis_value) : '';
    }
    return initial;
  });
  // 화면에 보이는 판정(배지 그리드 + 안전도 게이지 + 헤드라인)의 단일 출처.
  // scanResult.nutrient_statuses는 "스캔 시점의 첫 판정"일 뿐이라 초기값으로만 쓰고,
  // 이후에는 사용자가 값을 고칠 때마다 /ocr/recompute 응답이 이 state를 통째로
  // 교체한다. 화면은 scanResult가 아니라 항상 이 값만 읽는다 — 표시되는 판정과
  // 저장되는 수치가 갈라지지 않게 하는 것이 이 state의 존재 이유다.
  const [verdict, setVerdict] = useState<{
    nutrient_statuses: OcrNutrientStatus[];
    headline: OcrHeadline | null;
  }>(() => ({
    nutrient_statuses: scanResult?.nutrient_statuses ?? [],
    headline: scanResult?.headline ?? null,
  }));

  // 판정 상태. 'fresh'=지금 입력값으로 계산된 판정을 보여주는 중,
  // 'pending'=재계산 요청이 진행 중, 'error'=재계산 실패(저장을 막는다).
  // 마운트 직후는 'fresh'다 — /ocr/scan이 이미 같은 조립기(build_ocr_status_view)로
  // 오늘 누적분까지 반영한 판정을 내려주므로, 다시 계산할 것이 없다.
  const [verdictState, setVerdictState] = useState<'fresh' | 'pending' | 'error'>('fresh');
  // 화면의 판정이 "지금 입력값의 판정"이라고 말할 수 없는 상태(pending/error).
  // 배지·게이지·헤드라인을 확정적으로 읽히지 않게 처리하는 기준이 된다.
  const isVerdictUnconfirmed = verdictState !== 'fresh';
  // fresh면 null, 아니면 그 상태의 문구 묶음. 이 값 하나로 세 상태의 표시가 갈린다.
  const verdictCopy = verdictState === 'fresh' ? null : VERDICT_COPY[verdictState];

  // 재계산이 실제로 필요할 때만 판정을 가린다. 입력 핸들러가 직접 부르면 결과가
  // 달라지지 않는 편집(예: "5" 입력 후 삭제, "5" → "5.")에서도 판정이 잠깐 가려졌다
  // 돌아오는 깜빡임이 생기므로, 요청을 실제로 보내는 두 곳(디바운스 이펙트, 다시 시도)
  // 에서만 호출한다.
  const markVerdictPending = () => setVerdictState('pending');

  // 사용자가 직접 고친 영양소 칸 — 요청의 source('ocr' | 'manual')를 정한다. 판정에는
  // 전혀 쓰이지 않고(backend/routers/ocr.py의 OcrRecomputeNutrientInput 참고) 이후
  // 라벨 스냅샷 저장에서 둘을 구분하기 위한 값이라, 렌더를 유발할 필요가 없어 ref로 둔다.
  // 값을 바꾸는 시점이 곧 setNutrientFields 시점이라 리렌더는 어차피 함께 일어난다.
  const touchedNutrientKeysRef = useRef<Set<SelectableNutrientKey>>(new Set());
  // 재계산 요청 순번 — 늦게 도착한 응답이 최신 응답을 덮어쓰지 않도록, 응답을 반영하기
  // 전에 자기 seq가 아직 최신인지 확인한다.
  const recomputeSeqRef = useRef(0);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alternatives, setAlternatives] = useState<OcrAlternativesResponse | null>(null);
  const chevronRotation = useSharedValue(0);
  const timePickerHeight = useSharedValue(0);
  const timePickerOpacity = useSharedValue(0);
  // 7행 영양성분 테이블 펼침/접힘 — 기본은 접힘. NUTRIENT_TABLE_HEIGHT는 전환 중에만
  // 쓰는 근사 목표값이고, 펼침 애니메이션이 끝나면 tableHeightSettled를 true로 바꿔
  // 실제 콘텐츠 높이(undefined/auto)로 전환한다 — 추정치가 부정확해도 정지 상태에서는
  // 잘리거나 여백이 남지 않는다. measuredTableHeightRef는 그 실측 높이를 담아두었다가
  // 접을 때 애니메이션 시작점으로 써서(추정치로 스냅되는 시각적 튐 없이) 정확히
  // 그 지점부터 0으로 줄어들게 한다.
  const [tableExpanded, setTableExpanded] = useState(false);
  const [tableHeightSettled, setTableHeightSettled] = useState(false);
  const tableChevronRotation = useSharedValue(0);
  const tableBodyHeight = useSharedValue(0);
  const tableBodyOpacity = useSharedValue(0);
  const measuredTableHeightRef = useRef(NUTRIENT_TABLE_HEIGHT);

  const handleTableBodyLayout = (e: LayoutChangeEvent) => {
    const height = e.nativeEvent.layout.height;
    if (height > 0) measuredTableHeightRef.current = height;
  };

  const trimmedName = foodName.trim();
  // 인분(servings) 단위는 부분 인분 로깅을 지원하지 않음 — 소수/0 이하는 그램
  // 입력 모드를 쓰도록 유도한다 (앱 전체에서 "0.5인분" 같은 값은 저장하지 않음).
  const isServingsUnit = unit === '인분';
  const parsedAmount = Number(amount);
  const isAmountValid =
    amount.trim() !== '' &&
    !Number.isNaN(parsedAmount) &&
    (isServingsUnit ? Number.isInteger(parsedAmount) && parsedAmount >= 1 : parsedAmount > 0);
  const isFormValid = trimmedName.length > 0 && isAmountValid;

  // g/ml은 라벨 기준량(예: 100g) 대비 비율로 계산해야 하는 "무게형" 단위 — 그 외
  // (인분/개/접시/컵)는 "선택한 개수 그대로가 배율"인 "개수형" 단위다. AmountUnitPicker가
  // 제공하는 단위 목록과 어긋나지 않도록 WEIGHT_UNITS를 그 컴포넌트에서 그대로 가져온다.
  const isWeightUnit = WEIGHT_UNITS.includes(unit);

  // 서버가 각 영양소 값에 곱할 배율이자, 영양성분 상세의 총섭취량 열도 이 값을
  // 그대로 재사용한다(handleSave에서 다시 계산하지 않음).
  // - 개수형 단위(인분/개/접시/컵): 선택한 개수 그대로.
  // - 무게형 단위(g/ml): 실제 섭취량 ÷ 라벨 기준량(예: 100g) — 기준량을 모르면 배율 없음.
  const servingMultiplier: number | undefined = isWeightUnit
    ? basisAmountValue != null && basisAmountValue > 0
      ? parsedAmount / basisAmountValue
      : undefined
    : parsedAmount;

  const timeChevronAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${interpolate(chevronRotation.value, [0, 1], [0, 180])}deg` }],
  }));

  const timePickerAnimatedStyle = useAnimatedStyle(() => ({
    height: timePickerHeight.value,
    opacity: timePickerOpacity.value,
    overflow: 'hidden',
  }));

  const tableChevronAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${interpolate(tableChevronRotation.value, [0, 1], [0, 180])}deg` }],
  }));

  const tableBodyAnimatedStyle = useAnimatedStyle(() => ({
    height: tableHeightSettled ? undefined : tableBodyHeight.value,
    opacity: tableBodyOpacity.value,
    overflow: 'hidden',
  }));

  const openTimePicker = () => {
    setShowTimePicker(true);
    chevronRotation.value = withSpring(1, EXPAND_SPRING_CONFIG);
    timePickerHeight.value = withTiming(TIME_PICKER_HEIGHT, {
      duration: 400,
      easing: Easing.out(Easing.cubic),
    });
    timePickerOpacity.value = withTiming(1, { duration: 400 });
  };

  const closeTimePicker = () => {
    chevronRotation.value = withSpring(0, EXPAND_SPRING_CONFIG);
    timePickerHeight.value = withTiming(0, {
      duration: 400,
      easing: Easing.out(Easing.cubic),
    });
    timePickerOpacity.value = withTiming(0, { duration: 300 }, (finished) => {
      if (finished) runOnJS(setShowTimePicker)(false);
    });
  };

  const toggleTimePicker = () => {
    if (showTimePicker) {
      closeTimePicker();
    } else {
      openTimePicker();
    }
  };

  const openNutrientTable = () => {
    setTableExpanded(true);
    setTableHeightSettled(false);
    tableChevronRotation.value = withSpring(1, EXPAND_SPRING_CONFIG);
    tableBodyHeight.value = withTiming(
      NUTRIENT_TABLE_HEIGHT,
      { duration: 400, easing: Easing.out(Easing.cubic) },
      (finished) => {
        if (finished) runOnJS(setTableHeightSettled)(true);
      }
    );
    tableBodyOpacity.value = withTiming(1, { duration: 400 });
  };

  const closeNutrientTable = () => {
    setTableHeightSettled(false);
    // 정지 상태(auto)에서 실측한 높이로 먼저 동기화한 뒤 0으로 줄인다 — 추정치로
    // 순간 스냅되는 시각적 튐 없이 실제 위치에서부터 자연스럽게 접힌다.
    tableBodyHeight.value = measuredTableHeightRef.current;
    tableChevronRotation.value = withSpring(0, EXPAND_SPRING_CONFIG);
    tableBodyHeight.value = withTiming(0, {
      duration: 400,
      easing: Easing.out(Easing.cubic),
    });
    tableBodyOpacity.value = withTiming(0, { duration: 300 }, (finished) => {
      if (finished) runOnJS(setTableExpanded)(false);
    });
  };

  const toggleNutrientTable = () => {
    if (tableExpanded) {
      closeNutrientTable();
    } else {
      openNutrientTable();
    }
  };

  const addDraftRow = () => {
    setDraftRows((prev) => [
      ...prev,
      { id: String(Date.now()) + Math.random(), name: '', value: '' },
    ]);
  };

  const updateDraftRow = (id: string, field: 'name' | 'value', text: string) => {
    setDraftRows((prev) => prev.map((r) => (r.id === id ? { ...r, [field]: text } : r)));
  };

  const removeDraftRow = (id: string) => {
    setDraftRows((prev) => prev.filter((r) => r.id !== id));
  };

  const updateNutrientBasis = (key: SelectableNutrientKey, text: string) => {
    const sanitized = sanitizeNonNegativeDecimal(text);
    touchedNutrientKeysRef.current.add(key);
    setNutrientFields((prev) => ({ ...prev, [key]: sanitized }));
  };

  // 카페인은 라벨 OCR로 얻을 수 없어 항상 사용자가 직접 입력하는 값이고(source는 늘
  // 'manual'), 앱에서 기준이 가장 엄격한 판정 대상이라 재계산 입력에 반드시 포함된다.
  const updateCaffeineMg = (text: string) => {
    setCaffeineMg(sanitizeNonNegativeDecimal(text));
  };

  // 총내용량은 판정 입력이 아니다 — headerKcal(참고용 kcal 표시)에만 쓰이고
  // consumptionBasisValue/servingMultiplier/detailColumnValue 어디에도 관여하지 않아
  // 재계산 요청의 내용을 바꾸지 못한다. 재계산 이펙트가 payload를 비교해 요청 여부를
  // 결정하므로, 이 필드를 고쳐도 자연히 아무 요청도 나가지 않는다.
  const updateTotalContentAmount = (text: string) => {
    setTotalContentAmount(sanitizeNonNegativeDecimal(text));
  };

  const updateBasisAmountValue = (text: string) => {
    setBasisAmountValueText(sanitizeNonNegativeDecimal(text));
  };

  // 실제로 /food-log에 저장되는 값 — basis_value(사용자가 고친 라벨 값)에 스캔 시점의
  // (편집 불가) scale_factor를 다시 적용한다. backend의 scale_value()와 동일한 공식.
  // needs_review 모드에서는 scale_factor가 애초에 없어 basis 값 그대로 통과한다.
  const submittedValue = (key: SelectableNutrientKey): number | null => {
    const raw = nutrientFields[key].trim();
    if (raw === '') return null;
    const basisNum = Number(raw);
    if (Number.isNaN(basisNum)) return null;
    return scaleFactor != null ? truncate2(basisNum * scaleFactor) : basisNum;
  };

  // 무게형 단위(g/ml)일 때는 scale_factor(1회 제공량 스케일)를 건너뛰고 원본
  // 기준량당 값(basisNum)을 그대로 쓴다 — scale_factor를 거치면 이미 1회
  // 제공량으로 환산된 값에 그램 비율을 다시 곱해 이중 스케일링되는 버그가 있었다
  // (per_basis_with_total 라벨에서 scale_factor가 1.0이 아닐 때만 드러남, 예:
  // 100g당 기준 + 1회 제공량 30g인 라벨에서 실제 섭취량을 g으로 직접 입력하는 경우).
  // 개수형 단위(인분/개/접시/컵)는 submittedValue(scale_factor 적용값) 그대로 쓴다
  // — 그 경우 scale_factor가 기준량→1회 제공량 변환을 정당하게 담당한다.
  const consumptionBasisValue = (key: SelectableNutrientKey): number | null => {
    if (isWeightUnit) {
      const raw = nutrientFields[key].trim();
      if (raw === '') return null;
      const basisNum = Number(raw);
      return Number.isNaN(basisNum) ? null : basisNum;
    }
    return submittedValue(key);
  };

  // 영양성분 상세의 읽기 전용 "총섭취량" 열 — consumptionBasisValue에
  // servingMultiplier를 곱한다. 총내용량(g)은 여기 관여하지 않는다 — 총내용량 kcal와
  // 마찬가지로 순수 참고용 필드다(예전에는 totalScale까지 곱해 이중 계산되던 버그가
  // 있었다). 저장된 state가 아니라 매 렌더마다 새로 계산되므로 재계산 걱정이 없다.
  const detailColumnValue = (key: SelectableNutrientKey): number | null => {
    const basis = consumptionBasisValue(key);
    if (basis == null || servingMultiplier == null || Number.isNaN(servingMultiplier)) {
      return null;
    }
    return truncate2(basis * servingMultiplier);
  };

  // 헤더의 kcal 필드 — "총 내용물을 다 먹으면 총 몇 kcal인지" 보여주는 순수 참고용
  // 값이다. energy의 기준량당 값에 (총내용량 ÷ 기준량) 비율을 곱하는 하나의 공식으로
  // scale_method 전부(total_content/per_serving_with_count/per_basis_with_total)를
  // 커버한다 — 저장되는 값(handleSave의 calories_kcal)과는 무관하다.
  const headerKcal: number | null = (() => {
    const totalNum = Number(totalContentAmount);
    const energyBasisNum = Number(nutrientFields.energy);
    if (
      totalContentAmount.trim() === '' ||
      Number.isNaN(totalNum) ||
      nutrientFields.energy.trim() === '' ||
      Number.isNaN(energyBasisNum) ||
      basisAmountValue == null ||
      basisAmountValue <= 0
    ) {
      return null;
    }
    return truncate2(energyBasisNum * (totalNum / basisAmountValue));
  })();

  // 카페인의 "실제 섭취량" — 저장 시 backend가 caffeine_mg에도 serving_multiplier를
  // 곱하므로(routers/food_log.py의 _multiply), 판정에 보내는 값도 같은 곱을 거친 값이어야
  // 화면의 판정과 저장되는 수치가 같은 양을 가리킨다. 배율을 계산할 수 없으면(무게 단위인데
  // 기준량이 비어 있는 경우) 다른 7개 칸과 같은 규칙으로 null(정보 없음)을 보낸다.
  const consumedCaffeineMg: number | null = (() => {
    const raw = caffeineMg.trim();
    if (raw === '') return null;
    const num = Number(raw);
    if (Number.isNaN(num)) return null;
    if (servingMultiplier == null || Number.isNaN(servingMultiplier)) return null;
    return truncate2(num * servingMultiplier);
  })();

  // /ocr/recompute에 보낼 8칸. 값은 전부 "실제로 저장될 양"(detailColumnValue =
  // consumptionBasisValue × servingMultiplier)이다 — 기준량당 값이나 1회 제공량 값을
  // 보내면 서버가 저장될 양과 다른 양을 판정하게 되어, 이 작업이 없애려는 괴리를
  // 그대로 재현한다. 비어 있는 칸은 null로 보내야 서버에서 unknown으로 남는다(0 아님).
  const buildRecomputePayload = (): Record<OcrProjectionNutrientKey, OcrRecomputeNutrientInput> => {
    const nutrients = {} as Record<OcrProjectionNutrientKey, OcrRecomputeNutrientInput>;
    for (const key of SELECTABLE_NUTRIENT_KEYS) {
      nutrients[key] = {
        value: detailColumnValue(key),
        source: touchedNutrientKeysRef.current.has(key) ? 'manual' : 'ocr',
      };
    }
    nutrients.caffeine = { value: consumedCaffeineMg, source: 'manual' };
    return nutrients;
  };

  const recomputePayload = buildRecomputePayload();
  // 요청 내용의 동일성 판정 키. 화면에 떠 있는 판정이 어떤 입력으로 계산된 것인지를
  // 이 문자열로 기억해두고, 지금 입력이 그것과 같으면 요청을 보내지 않는다 —
  // 한 글자 쳤다 지우면 값이 원래대로 돌아오므로, 그때 재계산은 순수한 낭비다.
  const recomputePayloadKey = JSON.stringify(recomputePayload);
  const displayedPayloadKeyRef = useRef(recomputePayloadKey);

  // 재계산 요청 한 번. 언제 보낼지(디바운스 대기 / 즉시)는 호출부가 정하고, 여기서는
  // 순번 관리와 응답 반영만 한다. 늦게 도착한 응답은 seq 비교에서 걸러지므로 성공이든
  // 실패든 최신 요청의 결과만 화면에 반영된다 — 폐기된 응답이 error 상태를 만들 수 없다.
  const sendRecompute = (
    userId: number,
    payload: Record<OcrProjectionNutrientKey, OcrRecomputeNutrientInput>,
    payloadKey: string,
    seq: number
  ) => {
    recomputeOcrStatuses({ user_id: userId, nutrients: payload })
      .then((res) => {
        if (seq !== recomputeSeqRef.current) return;
        setVerdict({ nutrient_statuses: res.nutrient_statuses, headline: res.headline });
        displayedPayloadKeyRef.current = payloadKey;
        setVerdictState('fresh');
      })
      .catch(() => {
        if (seq !== recomputeSeqRef.current) return;
        setVerdictState('error');
      });
  };

  // "다시 시도" — 사용자가 명시적으로 누른 것이므로 디바운스를 거치지 않고 곧바로 보낸다.
  // 실패하면 이 요청이 최신 seq이므로 catch가 그대로 통과해 다시 error로 돌아오고,
  // 버튼도 계속 보이므로 몇 번이든 다시 누를 수 있다.
  const handleRetryRecompute = () => {
    if (!user?.user_id) return;
    markVerdictPending();
    const seq = (recomputeSeqRef.current += 1);
    sendRecompute(user.user_id, recomputePayload, recomputePayloadKey, seq);
  };

  // 값이 바뀔 때마다 판정을 다시 계산한다. 마운트 시점에는 보내지 않는다 —
  // /ocr/scan이 이미 같은 조립기(build_ocr_status_view)로 오늘 누적분까지 반영한
  // 판정을 내려줬으므로, 첫 렌더의 payload는 곧 화면에 떠 있는 판정의 입력이다.
  useEffect(() => {
    if (!user?.user_id) return;

    if (recomputePayloadKey === displayedPayloadKeyRef.current) {
      // 되돌린 편집(입력했다 지움 등) — 화면의 판정이 이미 이 입력의 판정이다.
      // 새 요청을 보내지 않고, 진행 중이던 요청은 seq를 올려 폐기한다(그 응답은
      // 지금 화면에 없는 입력의 판정이라 반영되면 오히려 어긋난다).
      recomputeSeqRef.current += 1;
      setVerdictState('fresh');
      return;
    }

    // 여기서부터는 요청이 실제로 나간다 — 결과가 달라질 수 있는 편집이라는 뜻이므로
    // 이 시점에 판정을 가린다. 되돌린 편집은 위 분기에서 이미 걸러졌다.
    markVerdictPending();

    // 편집이 일어난 순간 이전 요청은 무효다 — 응답이 돌아와도 이 seq 비교에서 걸러진다.
    const seq = (recomputeSeqRef.current += 1);
    const userId = user.user_id;
    const payload = recomputePayload;
    const payloadKey = recomputePayloadKey;

    const handle = setTimeout(() => sendRecompute(userId, payload, payloadKey, seq), RECOMPUTE_DEBOUNCE_MS);

    return () => clearTimeout(handle);
    // recomputePayload/payloadKey는 매 렌더 새로 만들어지므로 의존성은 내용 동일성을
    // 나타내는 문자열 하나로만 잡는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id, recomputePayloadKey]);

  const hasServingMultiplier = servingMultiplier != null && !Number.isNaN(servingMultiplier);
  const detailColumnHeader = hasServingMultiplier
    ? isWeightUnit
      ? `총섭취량(${amount || 0}${unit} 기준)`
      : `총섭취량(${parsedAmount || 0}${unit})`
    : '총섭취량';

  const totalConsumedCaption = hasServingMultiplier
    ? isWeightUnit
      ? `총 섭취량(${amount || 0}${unit}) 기준`
      : `총 섭취량(${parsedAmount || 0}${unit}) 기준`
    : '총 섭취량을 계산할 수 없어요';

  // /ocr/alternatives는 마운트 시 한 번, 이후 "상품명이 바뀔 때만" 디바운스로
  // 재호출한다 — 실패는 항상 available:false로 조용히 수렴하도록 설계된 부가
  // 기능이라(backend/routers/ocr.py), 저장 흐름을 막지 않는다.
  //
  // 영양소 편집값은 의존성에서 뺐다. 분류(category/subcategory)는 상품명만으로
  // 결정되는데, 값이 바뀔 때마다 재호출하면 분류 예산(최대 2회/호출)만 태우기
  // 때문이다. 대신 알려진 한계가 하나 생긴다: 상품명을 그대로 둔 채 수치만 고쳐
  // avoid가 된 경우(예: 나트륨 178 -> 3000) "대체 메뉴 보기" 버튼이 나타나지 않는다.
  // 지금은 판정 자체가 스캔 시점 스냅샷이라 어차피 갱신되지 않으므로 새로 생긴
  // 격차는 아니고, 판정이 실제로 다시 계산되는 시점(recompute 도입)에 그 결과에
  // 맞춰 다시 호출하도록 묶는 것이 맞는 자리다.
  //
  // 호출 시점에 보내는 nutrients 값 자체는 여전히 최신이다 — 이펙트 본문이 실행될
  // 때 현재 nutrientFields를 읽기 때문에, 의존성에서 뺀 것은 "언제 다시 부를지"뿐이다.
  useEffect(() => {
    if (!user?.user_id || !trimmedName) {
      setAlternatives(null);
      return;
    }
    const handle = setTimeout(() => {
      const nutrients: Partial<Record<SelectableNutrientKey, number | null>> = {};
      for (const key of SELECTABLE_NUTRIENT_KEYS) {
        nutrients[key] = submittedValue(key);
      }
      getOcrAlternatives({ user_id: user.user_id, product_name: trimmedName, nutrients })
        .then((res) => setAlternatives(res))
        .catch(() => setAlternatives(null));
    }, ALTERNATIVES_DEBOUNCE_MS);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id, trimmedName]);

  // 판정을 확인하지 못한 상태(error)에서는 저장을 막는다 — 수치는 정확히 저장되겠지만,
  // 이 화면의 목적은 "판정을 보고 저장 여부를 결정하는 것"이라 판정 없이 저장하면
  // 화면이 존재할 이유가 없어진다. pending은 막지 않는다(곧 결과가 온다).
  const isSaveBlocked = !isFormValid || saving || verdictState === 'error';

  const handleSave = () => {
    if (isSaveBlocked || !user?.user_id || !params.date) return;

    const caffeine = caffeineMg.trim() === '' ? null : Number(caffeineMg);
    const eatenAt = toEatenAt(params.date, time);

    setSaving(true);
    setError(null);

    createFoodLog({
      user_id: user.user_id,
      food_name: trimmedName,
      input_type: 'ocr',
      amount: parsedAmount || 1,
      unit,
      caffeine_mg: caffeine,
      sugar_g: consumptionBasisValue('sugar'),
      sodium_mg: consumptionBasisValue('sodium'),
      carbohydrate_g: consumptionBasisValue('carbohydrate'),
      protein_g: consumptionBasisValue('protein'),
      fat_g: consumptionBasisValue('fat'),
      iron_mg: consumptionBasisValue('iron'),
      // calories_kcal도 다른 영양소와 동일하게 null 허용(정보없음 ≠ 0) — 값이 있으면
      // 항상 실제 값을 보낸다. 헤더의 kcal 필드(headerKcal)와는 무관 — 저장되는 값은
      // 항상 에너지 행의 100g당(basis)에서 계산한다.
      calories_kcal: consumptionBasisValue('energy'),
      needs_review: needsReview,
      serving_multiplier: servingMultiplier,
      eaten_at: eatenAt,
      extra_nutrients: draftRows
        .filter((r) => r.name.trim() && r.value.trim())
        .map((r) => ({ name: r.name.trim(), value: r.value.trim() })),
    })
      .then(() => {
        router.replace('/(tabs)/food-diary');
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : (err as Error).message;
        setError(message || '저장에 실패했어요. 다시 시도해주세요.');
      })
      .finally(() => setSaving(false));
  };

  // 오늘 섭취 안전도 헤드라인 — 서버가 고른 성분을 그대로 읽는다. 클라이언트는 더 이상
  // 후보를 고르지 않는다(선택은 backend/intake_totals.py의 select_headline_nutrient가
  // 결정론적으로 수행하므로, 타이핑할 때마다 헤드라인이 다른 성분으로 튀지 않는다).
  // headline이 null이면 판정 가능한 상한형 성분이 하나도 없다는 뜻이라 기존 unknown 카피를 쓴다.
  const headline = verdict.headline;
  const headlineTier: OcrStatusTier = headline?.tier ?? 'unknown';
  // unknown/neutral 문구는 성분 이름을 쓰지 않으므로 headline이 null이어도 라벨이 필요 없다.
  const headlineText = buildHeadlineText(headlineTier, headline?.label ?? '');
  // 게이지 안의 숫자 퍼센트 — headline이 가리키는 영양소와 같은 key의 항목을
  // nutrient_statuses에서 찾는다(OcrHeadline 자체에는 percent가 없다). fresh 상태가
  // 아니면(verdictCopy가 있으면) undefined를 넘겨 SafetyGauge가 그 줄 자체를 그리지
  // 않게 한다 — 낡은 퍼센트를 숫자로 보여주면 안 된다는 정책과 같은 이유다.
  const headlinePercent: number | null | undefined = verdictCopy
    ? undefined
    : (verdict.nutrient_statuses.find((s) => s.key === headline?.key)?.percent ?? null);

  if (!scanResult) {
    return null;
  }

  return (
    <KeyboardAvoidingView
      style={styles.keyboardAvoidingView}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={0}>
      <ScrollView
        style={styles.container}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 7, paddingBottom: insets.bottom + 40 },
        ]}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
            <PrevIcon width={15} height={15} />
          </Pressable>
          <Text style={styles.title}>스캔 결과 확인</Text>
        </View>

        {needsReview && (
          <View style={styles.warningBanner}>
            <CautionIcon width={16} height={16} />
            <Text style={styles.warningBannerText}>
              라벨 환산 방식을 정확히 파악하지 못했어요. 섭취량과 각 영양성분 수치를 직접 확인해 입력해주세요.
            </Text>
          </View>
        )}

        {/* 1. 음식명 + 섭취량 + 섭취시간 (병합 카드) — 기본은 편집 모드로 시작한다.
             "스캔 결과 확인"이 이 화면의 핵심 목적이라 도착하자마자 바로 검토/수정할
             수 있어야 하고, 요약 모드는 검토가 끝난 뒤 다시 접어두는 용도다. */}
        <View style={styles.card}>
          {isEditingTopCard ? (
            <>
              <View style={styles.nutrientHeaderRow}>
                <Text style={styles.fieldLabel}>상품명</Text>
                <Pressable
                  style={styles.editTogglePill}
                  onPress={() => setIsEditingTopCard((v) => !v)}>
                  <Text style={styles.editTogglePillText}>완료</Text>
                </Pressable>
              </View>
              <View style={styles.nameEditRow}>
                <View style={[styles.nameInputRow, styles.flexOne]}>
                  <SearchIcon width={16} height={16} color={authColors.gray} />
                  <TextInput
                    style={styles.nameTextInput}
                    value={foodName}
                    onChangeText={setFoodName}
                    placeholder="예: 감자깡"
                    placeholderTextColor={authColors.gray}
                  />
                </View>
              </View>

              <View style={styles.cardDivider} />

              <Text style={styles.fieldLabel}>
                {isWeightUnit ? `실제 섭취량 (${unit})` : '섭취량'}
              </Text>
              <AmountUnitPicker
                amount={amount}
                unit={unit}
                onChangeAmount={setAmount}
                onChangeUnit={setUnit}
              />

              <View style={styles.cardDivider} />

              <Text style={styles.fieldLabel}>섭취시간</Text>
              <Pressable style={styles.timeInput} onPress={toggleTimePicker}>
                <ClockIcon width={15} height={15} style={styles.timeInputClock} />
                <Text style={styles.timeInputText}>{formatTimeLabel(time)}</Text>
                <Animated.View style={[styles.timeInputChevron, timeChevronAnimatedStyle]}>
                  <ChevronDownIcon width={12} height={8} color="#848484" />
                </Animated.View>
              </Pressable>
              {showTimePicker && (
                <Animated.View
                  style={[
                    Platform.OS === 'ios' ? styles.timePickerContainer : undefined,
                    timePickerAnimatedStyle,
                  ]}>
                  <DateTimePicker
                    value={time}
                    mode="time"
                    display={Platform.OS === 'ios' ? 'spinner' : 'default'}
                    themeVariant="light"
                    onChange={(_, selected) => {
                      const nextVisible = Platform.OS === 'ios';
                      if (!nextVisible) closeTimePicker();
                      if (selected) setTime(selected);
                    }}
                  />
                </Animated.View>
              )}
            </>
          ) : (
            <>
              <View style={styles.summaryHeaderRow}>
                <Text style={[styles.summaryProductName, styles.flexOne]}>
                  {trimmedName || '음식명을 입력해주세요'}
                </Text>
                <Pressable
                  style={styles.editTogglePill}
                  onPress={() => setIsEditingTopCard((v) => !v)}>
                  <Text style={styles.editTogglePillText}>수정</Text>
                </Pressable>
              </View>
              <View style={styles.summaryPillRow}>
                <View style={styles.summaryPill}>
                  <Text style={styles.summaryPillText}>
                    섭취량 {isAmountValid ? `${amount}${unit}` : '입력 필요'}
                  </Text>
                </View>
                <View style={styles.summaryPill}>
                  <ClockIcon width={13} height={13} />
                  <Text style={styles.summaryPillText}>섭취시간 {formatTimeLabel(time)}</Text>
                </View>
              </View>
            </>
          )}
        </View>

        {/* 2. 오늘 섭취 안전도 — 단일 성분 헤드라인 + 원형 게이지 */}
        <View style={styles.safetyCard}>
          <LinearGradient
            colors={['#FEF6F6', '#FEEBEA']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={StyleSheet.absoluteFillObject}
          />
          <Pressable
            style={styles.safetyInfoButton}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            onPress={() => setActiveInfo('safety')}>
            <InformationIcon width={18} height={18} color={authColors.gray} opacity={0.5} />
          </Pressable>
          <View style={styles.safetyRow}>
            <View style={styles.safetyTextGroup}>
              <Text
                style={[
                  styles.safetyHeadline,
                  verdictCopy
                    ? styles.safetyHeadlineMuted
                    : { color: tierColors(headlineTier).label },
                ]}>
                {verdictCopy ? verdictCopy.headline : headlineText}
              </Text>
              <Text style={styles.safetyDescription}>
                {verdictCopy ? verdictCopy.description : TIER_DESCRIPTION[headlineTier]}
              </Text>
            </View>
            <SafetyGauge
              tier={headlineTier}
              bandLabel={verdictCopy ? verdictCopy.gaugeLabel : TIER_DISPLAY[headlineTier].statusLabel}
              muted={isVerdictUnconfirmed}
              percent={headlinePercent}
            />
          </View>
          {/* 캡션 자리 — error일 때만 "다시 시도"가 캡션 옆에 함께 놓인다. */}
          <View style={styles.statusCaptionRow}>
            {!verdictCopy && <Text style={styles.statusCaption}>※ 스캔한 라벨 기준 상태예요</Text>}
            {verdictState === 'error' && (
              <Pressable
                style={styles.retryButton}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                onPress={handleRetryRecompute}>
                <Text style={styles.retryButtonText}>{RETRY_LABEL}</Text>
              </Pressable>
            )}
          </View>
        </View>

        {/* 3. 성분별 상태 — 7개 배지 그리드, 이전 라운드와 동일 */}
        <View style={[styles.card, styles.badgeGridCard]}>
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.fieldLabel}>영양소 섭취 분석</Text>
            <Pressable
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              onPress={() => setActiveInfo('nutrientStatus')}>
              <InformationIcon width={18} height={18} color={authColors.gray} opacity={0.5} />
            </Pressable>
          </View>
          <View style={styles.statusGrid}>
            {verdict.nutrient_statuses.map((item) => (
              <StatusChip
                key={item.key}
                label={item.label}
                value={item.status_label}
                colors={summaryStatusColors[item.status_label] ?? DEFAULT_SUMMARY_STATUS_COLORS}
                style={[styles.statusChipItem, isVerdictUnconfirmed && styles.statusChipItemMuted]}
              />
            ))}
          </View>
          {/* 배지 그리드는 안전도 카드와 별도 카드라, 흐려진 이유를 여기서도 한 번 밝힌다
              — 스크롤 위치에 따라 안전도 카드의 안내를 못 볼 수 있다. 문구가 있는 상태는
              error뿐이지만, 세 상태에서 카드 높이가 흔들리지 않도록 자리는 항상 차지한다. */}
          <Text style={[styles.statusCaption, styles.captionSlot]}>{verdictCopy?.description}</Text>
        </View>

        {/* 4. 영양성분 상세 (100g당 / 총섭취량(N인분)) */}
        <View style={styles.card}>
          <View style={styles.sectionHeaderRow}>
            <View style={styles.sectionHeaderTitleGroup}>
              <Text style={styles.fieldLabel}>영양성분 상세</Text>
              <Text style={styles.transparencyText}>※ {totalConsumedCaption}</Text>
            </View>
            <Pressable
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              onPress={() => setActiveInfo('nutrientDetail')}>
              <InformationIcon width={18} height={18} color={authColors.gray} opacity={0.5} />
            </Pressable>
          </View>

          {/* 총내용량/기준량 카드 — 기본은 읽기 전용 배지 표시, 연필 버튼으로 기존
              입력 행(총내용량/기준량 TextInput)을 그대로 드러낸다. kcal 필드는
              헤더에서 파생되는 참고용 숫자로 저장 값과 무관하다. */}
          <View style={styles.amountCard}>
            {/* 펼침 버튼 — 카드 오른쪽 위 모서리에 절대 위치로 얹는다. 테두리 없는 순수
                갈매기표만 남긴다(원형 배경/링 제거). 제목 행의 기존 토글 로직
                (toggleNutrientTable)과 애니메이션(tableChevronAnimatedStyle)을 그대로
                재사용한다 — 위치만 옮겼을 뿐 상태·로직은 새로 만들지 않는다. */}
            <Pressable
              style={styles.amountCardExpandButton}
              onPress={toggleNutrientTable}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Animated.View style={tableChevronAnimatedStyle}>
                <ChevronDownIcon width={16} height={11} color={authColors.gray} opacity={0.5} />
              </Animated.View>
            </Pressable>
            {isEditingAmountCard ? (
              <View style={styles.amountCardEditRow}>
                <View style={styles.totalHeaderRow}>
                  <Text style={styles.totalHeaderLabel}>총 내용량</Text>
                  <TextInput
                    style={styles.totalHeaderInput}
                    value={totalContentAmount}
                    onChangeText={updateTotalContentAmount}
                    placeholder="-"
                    placeholderTextColor={authColors.gray}
                    keyboardType="decimal-pad"
                  />
                  <Text style={styles.totalHeaderUnit}>{scanResult.total_content_unit}</Text>
                  <Text style={styles.totalHeaderSeparator}>·</Text>
                  <View style={[styles.totalHeaderInput, styles.totalHeaderReadOnly]}>
                    <Text style={styles.totalHeaderReadOnlyText}>
                      {headerKcal != null ? String(headerKcal) : '-'}
                    </Text>
                  </View>
                  <Text style={styles.totalHeaderUnit}>kcal</Text>
                </View>

                <View style={styles.basisHeaderRow}>
                  <Text style={styles.totalHeaderLabel}>기준량</Text>
                  <TextInput
                    style={styles.totalHeaderInput}
                    value={basisAmountValueText}
                    onChangeText={updateBasisAmountValue}
                    placeholder="-"
                    placeholderTextColor={authColors.gray}
                    keyboardType="decimal-pad"
                  />
                  <Text style={styles.totalHeaderUnit}>{scanResult.basis_amount_unit}</Text>
                </View>
                {scanResult.scale_method === 'per_basis_with_total' && !isWeightUnit && (
                  <Text style={styles.basisLimitationCaption}>
                    기준량 수정은 {scanResult.basis_amount_unit} 단위 입력에만 반영돼요
                  </Text>
                )}
              </View>
            ) : (
              <View style={styles.amountCardDisplayRow}>
                <View style={styles.amountCardItem}>
                  <View style={styles.amountCardItemMainRow}>
                    <View style={[styles.amountCardIconCircle, styles.amountCardIconCircleGreen]}>
                      <StandardScaleIcon width={28} height={28} color={homeColors.sugar.value} />
                    </View>
                    <View style={styles.amountCardItemTextGroup}>
                      <Text style={styles.amountCardItemLabel}>총 내용량</Text>
                      <Text style={styles.amountCardItemValue}>
                        {totalContentAmount || '-'}
                        <Text style={styles.amountCardItemUnit}> {scanResult.total_content_unit}</Text>
                      </Text>
                    </View>
                  </View>
                  {headerKcal != null && (
                    <Text style={styles.amountCardKcalSubtext}>{headerKcal} kcal</Text>
                  )}
                </View>
                <View style={styles.amountCardDivider} />
                <View style={styles.amountCardItem}>
                  <View style={styles.amountCardItemMainRow}>
                    <View style={[styles.amountCardIconCircle, styles.amountCardIconCircleBlue]}>
                      <ScaleIcon width={28} height={28} color={BASIS_BADGE_BLUE} />
                    </View>
                    <View style={styles.amountCardItemTextGroup}>
                      <Text style={styles.amountCardItemLabel}>기준량</Text>
                      <Text style={styles.amountCardItemValue}>
                        {basisAmountValueText || '-'}
                        <Text style={styles.amountCardItemUnit}> {scanResult.basis_amount_unit}</Text>
                      </Text>
                    </View>
                  </View>
                </View>
              </View>
            )}
          </View>

          {/* 편집 링크 — 예전 원형 편집 버튼을 대신한다. 펼침 버튼과 같은 tableExpanded
              조건을 써서, 상세 섹션이 접혀 있을 때는 자리도 차지하지 않는다(조건부
              렌더링 — opacity:0 아님). */}
          {tableExpanded && (
            <Pressable
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              onPress={() => setIsEditingAmountCard((v) => !v)}>
              <Text style={styles.amountCardEditLink}>총 내용량, 기준량 수정하기</Text>
            </Pressable>
          )}

          {tableExpanded && (
            <Animated.View style={tableBodyAnimatedStyle}>
              <View style={styles.tableContainer} onLayout={handleTableBodyLayout}>
                <View style={styles.tableHeaderRow}>
                  <View style={styles.pairedLabelGroup}>
                    <Text style={styles.tableHeaderCell}>영양성분</Text>
                  </View>
                  <View style={styles.columnDivider} />
                  <View style={styles.pairedInputCol}>
                    <Text style={[styles.tableHeaderCell, styles.tableHeaderValueCell]}>
                      {getBasisLabel(scanResult.scale_method, basisAmountValue, scanResult.basis_amount_unit)}
                    </Text>
                  </View>
                  <View style={styles.columnDivider} />
                  <View style={styles.pairedInputCol}>
                    <Text style={[styles.tableHeaderCell, styles.tableHeaderValueCell]}>
                      {detailColumnHeader}
                    </Text>
                  </View>
                </View>
                {SELECTABLE_NUTRIENT_KEYS.map((key) => {
                  const detail = detailColumnValue(key);
                  return (
                    <PairedNutrientField
                      key={key}
                      icon={NUTRIENT_ICONS[key]}
                      label={NUTRIENT_LABELS_KO[key]}
                      unit={NUTRIENT_UNITS[key]}
                      basisValue={nutrientFields[key]}
                      detailValue={detail != null ? String(detail) : '-'}
                      onChangeBasis={(text) => updateNutrientBasis(key, text)}
                      // 안전도 헤드라인이 가리키는 성분을 표에서 짚어주는 강조다 —
                      // 판정이 낡아 헤드라인에서 성분 이름을 감춘 동안에는 가리킬
                      // 대상이 없으므로 함께 끈다.
                      highlighted={!isVerdictUnconfirmed && key === headline?.key}
                    />
                  );
                })}
              </View>
            </Animated.View>
          )}

        </View>

        {/* 5. 추가 성분 입력 — 카페인 입력을 첫 행으로 둔다. 카페인은 draftRows가
            아니다: 전용 state(caffeineMg)와 전용 payload 키(recompute의 nutrients.caffeine,
            저장의 caffeine_mg)를 그대로 쓴다. 시각적 위치만 옮긴 것이라 삭제 버튼이
            없다 — draftRows 항목이 아니므로 지울 수 없다. */}
        <View style={styles.card}>
          <View style={styles.nutrientHeaderRow}>
            <View>
              <Text style={styles.fieldLabel}>추가 성분</Text>
            </View>
            <Pressable style={styles.addNutrientPill} onPress={addDraftRow}>
              <Text style={styles.addNutrientPillText}>+ 성분 추가</Text>
            </Pressable>
          </View>

          <View style={styles.nutrientInputRow}>
            <View style={styles.nutrientLabelGroup}>
              <CaffeineIcon width={17} height={17} color="#F47E8A" />
              <Text style={styles.nutrientLabel}>카페인(mg)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={caffeineMg}
              onChangeText={updateCaffeineMg}
              placeholder="예: 65"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>

          <View>
            {draftRows.map((row) => (
              <DraftRow
                key={row.id}
                row={row}
                onRemove={removeDraftRow}
                onUpdate={updateDraftRow}
              />
            ))}
          </View>
        </View>

        {error && <Text style={styles.errorText}>{error}</Text>}

        {/* 6. 대체 메뉴 보기 — avoid 상태 영양소가 있고 같은 subcategory 대체 후보가 있을 때만 */}
        {alternatives?.available && (
          <Pressable
            style={styles.alternativesButton}
            onPress={() =>
              router.push({
                pathname: '/food-alternatives',
                params: {
                  trigger_nutrient: alternatives.trigger_nutrient ?? '',
                  category: alternatives.category ?? '',
                  subcategory: alternatives.subcategory ?? '',
                  product_name: trimmedName,
                  alternatives: JSON.stringify(alternatives.alternatives),
                },
              })
            }>
            <Text style={styles.alternativesButtonText}>대체 메뉴 보기</Text>
          </Pressable>
        )}

        <Pressable
          style={[styles.saveButton, isSaveBlocked && styles.saveButtonDisabled]}
          onPress={handleSave}
          disabled={isSaveBlocked}>
          <Text style={styles.saveButtonText}>{saving ? '저장 중...' : '기록 저장'}</Text>
        </Pressable>
      </ScrollView>

      <BottomSheet visible={activeInfo !== null} onClose={() => setActiveInfo(null)}>
        <View style={[styles.infoSheet, { paddingBottom: styles.infoSheet.paddingBottom + insets.bottom }]}>
          {activeInfo && (
            <>
              <Text style={styles.infoSheetTitle}>{INFO_CONTENT[activeInfo].title}</Text>
              <Text style={styles.infoSheetBody}>{INFO_CONTENT[activeInfo].body}</Text>
              {INFO_CONTENT[activeInfo].note && (
                <Text style={styles.infoSheetNote}>{INFO_CONTENT[activeInfo].note}</Text>
              )}
            </>
          )}
          <Pressable onPress={() => setActiveInfo(null)}>
            <Text style={styles.infoSheetCloseText}>확인</Text>
          </Pressable>
        </View>
      </BottomSheet>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  keyboardAvoidingView: {
    flex: 1,
  },
  container: {
    flex: 1,
    backgroundColor: authColors.white,
  },
  content: {
    paddingHorizontal: 17,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  prevButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 20,
    color: authColors.brown,
  },
  warningBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: '#FFF0F0',
    borderWidth: 1,
    borderColor: authColors.pink,
    borderRadius: 12,
    padding: 14,
    marginTop: 16,
  },
  warningBannerText: {
    flex: 1,
    fontFamily: fonts.regular,
    fontSize: 11.5,
    color: authColors.pink,
    lineHeight: 17,
  },
  card: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: '#FFEDEE',
    borderRadius: 15,
    padding: 19,
    marginTop: 16,
    shadowColor: '#F47E8A',
    shadowOpacity: 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    elevation: 3,
  },
  // 영양소 섭취 분석(배지 그리드) 카드 전용 — 마지막 배지 줄 아래 남는 여백을 줄인다.
  // 가로 패딩은 공용 card(19)를 그대로 쓰고 아래쪽만 좁힌다.
  badgeGridCard: {
    paddingBottom: 14,
  },
  safetyCard: {
    overflow: 'hidden',
    borderWidth: 0.7,
    borderColor: '#FFEDEE',
    borderRadius: 15,
    paddingVertical: 13,
    paddingHorizontal: 19,
    marginTop: 12,
    shadowColor: '#F47E8A',
    shadowOpacity: 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    elevation: 3,
  },
  safetyInfoButton: {
    position: 'absolute',
    top: 14,
    right: 14,
    zIndex: 1,
  },
  cardDivider: {
    height: 1,
    backgroundColor: authColors.border,
    marginVertical: 16,
  },
  fieldLabel: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: '#000000',
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  // 제목 + 캡션(총 섭취량 기준)을 한 줄에 묶는 그룹. 더 이상 Pressable이 아니다 —
  // 펼침/접힘 트리거는 amountCardExpandButton(카드 우상단의 갈매기표)으로 옮겨갔다.
  sectionHeaderTitleGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  nameInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    paddingHorizontal: 12,
    height: 42,
  },
  nameEditRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 10,
  },
  flexOne: {
    flex: 1,
  },
  nameTextInput: {
    flex: 1,
    fontSize: 13,
    color: '#000000',
  },
  editTogglePill: {
    flexShrink: 0,
    borderWidth: 1,
    borderColor: authColors.pink,
    borderRadius: 100,
    paddingHorizontal: 12,
    paddingVertical: 5,
  },
  editTogglePillText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 11,
    color: authColors.pink,
  },
  summaryHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  summaryProductName: {
    fontFamily: fonts.bold,
    fontSize: 16,
    color: '#000000',
  },
  summaryPillRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
  },
  summaryPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#FFF5F3',
    borderRadius: 100,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  summaryPillText: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.grayDark,
  },
  timeInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 32,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  timeInputClock: {
    marginRight: 6,
  },
  timeInputText: {
    flex: 1,
    fontSize: 12,
    color: '#4A4A4A',
  },
  timeInputChevron: {
    marginLeft: 4,
  },
  timePickerContainer: {
    height: 216,
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    marginTop: 10,
    overflow: 'hidden',
  },
  nutrientHeaderRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  addNutrientPill: {
    borderWidth: 1,
    borderColor: authColors.pink,
    borderRadius: 100,
    paddingHorizontal: 12,
    paddingVertical: 5,
  },
  addNutrientPillText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 11,
    color: authColors.pink,
  },
  // marginTop 없음 — 예전엔 amountCard 아래 단독 줄이라 위쪽 여백이 필요했지만,
  // 지금은 제목 옆 한 줄(sectionHeaderTitleGroup)에 나란히 놓이므로 세로 여백을
  // 넣으면 제목 기준선에서 아래로 밀려 보인다.
  transparencyText: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
  },
  // paddingRight: 32 — DraftRow(extraInputRow)의 값 입력칸은 삭제 버튼(20) +
  // 여백(marginRight 8 + paddingRight 4 = 12)만큼 오른쪽이 비어 있다. 카페인 행은
  // 삭제 버튼이 없지만, 같은 만큼 오른쪽을 비워 입력칸 오른쪽 끝이 DraftRow의
  // 입력칸과 같은 세로선에 맞도록 한다.
  nutrientInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 12,
    paddingRight: 32,
  },
  nutrientLabelGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  nutrientLabel: {
    fontSize: 12,
    color: '#000000',
  },
  nutrientLabelHighlighted: {
    fontFamily: nanumSquareRound.bold,
    color: authColors.pink,
  },
  nutrientInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 27,
    width: 118,
    paddingHorizontal: 10,
    fontSize: 12,
    color: '#000000',
  },
  safetyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    marginTop: 8,
  },
  safetyTextGroup: {
    flex: 1,
  },
  safetyHeadline: {
    fontFamily: fonts.bold,
    fontSize: 18,
  },
  // 판정이 낡은 동안의 헤드라인 — 상태색(위험/안전/여유)을 쓰지 않는다. 색이 남아
  // 있으면 문구를 중립으로 바꿔도 색만으로 판정을 읽게 된다.
  safetyHeadlineMuted: {
    color: authColors.grayDark,
  },
  safetyDescription: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.grayDark,
    lineHeight: 18,
    marginTop: 6,
  },
  gaugeLabelOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  gaugePercentText: {
    fontFamily: fonts.bold,
    fontSize: 20,
    color: authColors.brown,
  },
  // 4자리 이상("1000%" 등 — 카페인 오타나 하루 누적 나트륨이 크게 초과된 경우)일 때
  // 링 안쪽 폭에 맞춰 글자 크기를 줄인다.
  gaugePercentTextLong: {
    fontSize: 16,
  },
  gaugeBandText: {
    fontFamily: fonts.regular,
    fontSize: 10,
    color: authColors.gray,
    marginTop: 2,
  },
  statusCaption: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 8,
  },
  // 캡션과 "다시 시도"를 한 줄에 놓기 위한 행. 두 자식 모두 marginTop 8을 갖고 있어
  // 캡션만 있을 때와 세로 위치가 같다 — 기존 간격을 그대로 유지하기 위한 구성이다.
  //
  // minHeight는 지터 방지용이다 — fresh(캡션)/error(다시 시도)/pending(빈 행) 세 상태에서
  // 이 행이 차지하는 높이가 달라지면 카드가 매 편집마다 위아래로 튄다. 한 줄(marginTop 8 +
  // 11pt 한 줄) 자리를 항상 확보해 세 상태의 높이를 같게 만든다.
  statusCaptionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: 26,
  },
  // 배지 그리드 아래 설명 자리 — 문구가 없는 상태(fresh/pending)에서도 같은 높이를 차지한다.
  captionSlot: {
    minHeight: 18,
  },
  retryButton: {
    marginTop: 8,
  },
  retryButtonText: {
    fontFamily: fonts.medium,
    fontSize: 11,
    color: authColors.pink,
    textDecorationLine: 'underline',
  },
  statusGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: 10,
    marginTop: 12,
  },
  statusChipItem: {
    flex: 0,
    width: '23%',
  },
  // 낡은 판정 배지 — 지우지 않고 흐리게 남긴다. 아예 비우면 화면이 크게 흔들리고,
  // "값이 없다"(정보없음 배지)와도 헷갈린다.
  statusChipItemMuted: {
    opacity: 0.35,
  },
  totalHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 10,
  },
  totalHeaderLabel: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: '#000000',
    marginRight: 4,
  },
  totalHeaderInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 27,
    width: 70,
    paddingHorizontal: 8,
    fontSize: 12,
    color: '#000000',
    textAlign: 'center',
  },
  totalHeaderUnit: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 11,
    color: authColors.gray,
  },
  totalHeaderSeparator: {
    fontSize: 12,
    color: authColors.gray,
    marginHorizontal: 2,
  },
  basisHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 8,
  },
  totalHeaderReadOnly: {
    backgroundColor: '#F7F7F7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  totalHeaderReadOnlyText: {
    fontSize: 12,
    color: authColors.grayDark,
  },
  basisLimitationCaption: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 6,
  },
  // 테두리 없음 — 총내용량/기준량 콘텐츠가 상위 card(영양성분 상세)의 흰 배경 위에
  // 바로 놓인다. padding은 그대로 유지해 콘텐츠가 상위 card의 가장자리에 닿지 않게 한다.
  // paddingHorizontal: 0 — 바깥 카드(styles.card)가 이미 19px 좌우 패딩을 갖고
  // 있어서, 여기 추가로 가로 패딩을 얹으면 amountCard의 콘텐츠만 형제 요소들
  // (제목 행, 편집 링크, 상세 테이블)보다 더 안쪽으로 들어가 보였다. 세로 패딩(14)은
  // 그대로 둔다 — 펼침 버튼의 top:0/bottom:0 중앙 정렬 기준과 편집행/표시행 사이
  // 세로 리듬은 이 변경과 무관하다.
  amountCard: {
    paddingVertical: 14,
    paddingHorizontal: 0,
    marginTop: 10,
    // 버튼 스택을 절대 위치로 카드 모서리에 얹기 위한 배치 기준점.
    position: 'relative',
  },
  // 펼침 버튼 — 카드 오른쪽에 절대 위치로 얹되, 카드 위쪽 모서리가 아니라 총내용량/
  // 기준량 콘텐츠의 세로 중앙에 맞춘다. top:0/bottom:0으로 버튼 자신을 amountCard와
  // 같은 높이로 늘린 뒤 justifyContent:center로 그 안의 갈매기표를 세로 가운데에
  // 둔다 — 콘텐츠 높이가 얼마든(편집모드/읽기전용 모드로 달라져도) 항상 중앙에 온다.
  // 원형 배경/테두리 없이 갈매기표 아이콘만 놓인 자리라, 크기는 hitSlop이 담당한다.
  amountCardExpandButton: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    right: 2,
    zIndex: 10,
    justifyContent: 'center',
  },
  // 편집 링크 — 원형 편집 버튼을 대신한다. amountCard 아래, 예전 캡션(※ 총 섭취량...)이
  // 있던 자리에 놓인다(그 캡션은 제목 행으로 옮겨갔다). 편집 버튼이 쓰던 pink 토큰을
  // 그대로 재사용하고, 밑줄로 탭 가능함을 표시한다.
  amountCardEditLink: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.pink,
    textDecorationLine: 'underline',
    marginTop: 8,
  },
  amountCardEditRow: {},
  // 두 항목(총내용량/기준량)만 담는 행. alignItems를 flex-start로 둬서, 총내용량
  // 쪽에만 있는 kcal 줄이 그 항목의 높이를 늘려도 두 항목의 라벨 줄·값 줄이 서로
  // 같은 높이에서 시작한다(center였다면 짧은 쪽이 세로로 다시 가운데 정렬되며 밀렸다).
  amountCardDisplayRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  // flex: 1 — 두 항목이 행의 정확히 절반씩을 차지하는 고정 2열이라, 기준량(2열)의
  // 시작 x좌표가 총내용량(1열)의 콘텐츠 폭에 좌우되지 않고 항상 카드 폭의 50%
  // 지점으로 고정된다(justifyContent:space-between이던 이전 방식은 두 항목이
  // auto-width라 1열 콘텐츠가 짧으면 2열이 왼쪽으로 끌려왔다).
  // 세로 방향은 열(column)이다 — kcal 줄을 아이콘+라벨/값 행(amountCardItemMainRow)
  // 밖으로 뺐기 때문에, kcal 유무가 아이콘 정렬 기준 높이에 영향을 주지 않는다.
  // paddingHorizontal 없음 — 좌우 여백은 amountCard의 padding(바깥쪽)과
  // amountCardDivider의 marginHorizontal(안쪽)이 이미 담당한다. 이 위에 또
  // paddingHorizontal을 얹으면 콘텐츠가 카드 가장자리/구분선에서 불필요하게
  // 더 안쪽으로 밀려, 두 열이 카드 중앙 쪽으로 뭉쳐 보이는 원인이 된다.
  amountCardItem: {
    flex: 1,
  },
  // 아이콘 + [라벨, 값]만 담는 행. 두 열 모두 라벨+값 두 줄로 높이가 항상 같아서
  // (kcal은 이 행 밖에 있다), alignItems:center로 각 아이콘을 자기 텍스트 블록에
  // 맞춰 세로 중앙 정렬해도 두 열의 아이콘이 서로 같은 y좌표에 놓인다. kcal이 있는
  // 열도 이 행 자체의 높이/정렬에는 영향을 주지 않는다.
  amountCardItemMainRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  amountCardItemTextGroup: {},
  // marginHorizontal: 19 — amountCard.paddingHorizontal이 0이 됐으니, 왼쪽 열의
  // "카드 왼쪽 끝 → 초록 아이콘" 간격(바깥 card.padding 19)과 오른쪽 열의
  // "구분선 → 파란 아이콘" 간격이 같은 19px가 되도록 맞춘 값이다. 좌우를 대칭으로
  // 유지해야 구분선이 행의 정확한 가로 중앙에서 벗어나지 않는다.
  amountCardDivider: {
    width: 1,
    alignSelf: 'stretch',
    backgroundColor: authColors.border,
    marginHorizontal: 19,
  },
  amountCardIconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  amountCardIconCircleGreen: {
    backgroundColor: homeColors.sugar.bg,
  },
  amountCardIconCircleBlue: {
    backgroundColor: BASIS_BADGE_BLUE_BG,
  },
  amountCardItemLabel: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.grayDark,
  },
  amountCardItemValue: {
    fontFamily: fonts.bold,
    fontSize: 18,
    color: '#000000',
    marginTop: 2,
  },
  amountCardItemUnit: {
    fontSize: 13,
  },
  // marginLeft: amountCardItemMainRow 밖으로 빠졌으니, 아이콘 폭(44) + 그 행의
  // gap(8)만큼(=52) 들여써서 시각적으로는 여전히 라벨/값 텍스트 아래에 붙는다
  // (아이콘 아래가 아니라). amountCardIconCircle/amountCardItemMainRow 값이
  // 바뀌면 이 숫자도 함께 맞춰야 한다.
  amountCardKcalSubtext: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: homeColors.sugar.value,
    marginTop: 2,
    marginLeft: 52,
  },
  // 헤더 행 + 데이터 행을 하나의 테두리 박스 안에 담아 실제 표처럼 보이게 한다 —
  // overflow:hidden이 안의 모서리를 컨테이너의 둥근 모서리에 맞춰 잘라준다.
  tableContainer: {
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 10,
    overflow: 'hidden',
    marginTop: 12,
  },
  tableHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFF0F0',
    paddingVertical: 6,
    paddingHorizontal: 10,
    // 데이터 행과의 경계를 살짝 더 진하게 — authColors.pink도 이미 앱에서
    // 쓰이는 기존 토큰이라 새 색을 들여오지 않는다.
    borderBottomWidth: 1.5,
    borderBottomColor: authColors.pink,
  },
  tableHeaderCell: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 11,
    color: authColors.pink,
    textAlign: 'center',
  },
  tableHeaderValueCell: {
    textAlign: 'center',
  },
  // 열 사이 세로 구분선 — 성분명/100g당/총섭취량 세 칸 사이에 공통으로 쓴다
  // (헤더 행과 데이터 행이 완전히 같은 자리에 넣어 정렬이 항상 맞는다).
  columnDivider: {
    width: 1,
    alignSelf: 'stretch',
    backgroundColor: authColors.border,
    marginHorizontal: 8,
  },
  pairedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 10,
    borderBottomWidth: 1,
    borderBottomColor: authColors.border,
  },
  pairedRowHighlighted: {
    backgroundColor: '#FFF0F0',
  },
  pairedLabelGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flex: 1,
    minWidth: 0,
  },
  pairedInputCol: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 84,
    height: 27,
  },
  pairedInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 27,
    width: 76,
    paddingHorizontal: 8,
    // Android TextInput은 기본 내부 padding이 있어 height를 맞춰도 옆의 Text와
    // 세로 중심이 어긋난다 — paddingVertical:0 + textAlignVertical로 맞춘다.
    paddingVertical: 0,
    fontSize: 12,
    color: '#000000',
    textAlign: 'center',
    textAlignVertical: 'center',
  },
  pairedReadOnlyValue: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.grayDark,
    alignSelf: 'stretch',
    textAlign: 'center',
    textAlignVertical: 'center',
  },
  pairedReadOnlyValueHighlighted: {
    fontFamily: nanumSquareRound.bold,
    color: authColors.pink,
  },
  extraInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 12,
    width: '100%',
    paddingRight: 4,
  },
  extraNameInput: {
    flex: 4.5,
    minWidth: 0,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 30,
    paddingHorizontal: 8,
    fontSize: 12,
    color: '#000000',
  },
  extraValueInput: {
    flex: 4,
    minWidth: 0,
    marginRight: 8,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 30,
    paddingHorizontal: 8,
    fontSize: 12,
    color: '#000000',
  },
  draftRemoveButton: {
    flex: 0,
    flexShrink: 0,
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  draftRemoveText: {
    fontSize: 18,
    color: authColors.gray,
    lineHeight: 20,
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 12,
    textAlign: 'center',
    marginTop: 16,
  },
  alternativesButton: {
    marginTop: 20,
    borderWidth: 1,
    borderColor: authColors.pink,
    borderRadius: 100,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  alternativesButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: authColors.pink,
  },
  saveButton: {
    marginTop: 12,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveButtonDisabled: {
    opacity: 0.6,
  },
  saveButtonText: {
    fontFamily: fonts.semiBold,
    fontSize: 19,
    color: authColors.white,
  },
  infoSheet: {
    backgroundColor: authColors.white,
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    paddingTop: 36,
    paddingHorizontal: 19,
    paddingBottom: 40,
  },
  infoSheetTitle: {
    fontFamily: fonts.medium,
    fontSize: 19,
    color: '#000000',
  },
  infoSheetBody: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 14,
    lineHeight: 21,
    color: authColors.grayDark,
    marginTop: 12,
  },
  infoSheetNote: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    lineHeight: 18,
    color: authColors.gray,
    marginTop: 12,
  },
  infoSheetCloseText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: authColors.pink,
    textAlign: 'center',
    marginTop: 24,
    textDecorationLine: 'underline',
  },
});
