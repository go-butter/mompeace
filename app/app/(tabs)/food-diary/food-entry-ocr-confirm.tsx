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
import SearchIcon from '@/assets/images/scan/search.svg';
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
  OcrNutrientStatus,
  OcrScaleMethod,
  OcrScanResponse,
  updateNutrientPreferences,
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
// 7행 영양성분 테이블의 펼침 애니메이션 목표 높이 — 실제 콘텐츠 높이의 근사치일 뿐이다.
// 애니메이션이 끝나면 height를 undefined(auto)로 전환해 실제 높이에 맞추므로, 이 값이
// 다소 넉넉해도(잘림보다 여백이 나는 쪽이 안전) 정지 상태의 표시에는 영향이 없다.
const NUTRIENT_TABLE_HEIGHT = 400;
// 기준량 배지에 쓸 파란색 — 팔레트에 채도 있는 파란색 토큰이 없어 새로 추가한다.
// waterColors.waveFront(#C2E1F5) 계열 색상군과 어울리도록 고른 값.
const BASIS_BADGE_BLUE = '#5B9BD1';
const BASIS_BADGE_BLUE_BG = '#EAF3FA';

const NUTRIENT_ICONS: Record<SelectableNutrientKey, ReactNode> = {
  carbohydrate: <CarbohydrateIcon width={17} height={17} />,
  sugar: <SugarIcon width={17} height={17} />,
  energy: <CaloriesIcon width={17} height={17} />,
  fat: <FatIcon width={17} height={17} />,
  iron: <IronIcon width={17} height={17} />,
  protein: <ProteinIcon width={17} height={17} />,
  sodium: <SodiumIcon width={18} height={18} />,
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
    body: '스캔한 식품의 영양성분을 임신 중 하루 권장 섭취 기준과 비교해서, 오늘 이 음식이 안전한 수준인지 알려드려요. 색상과 게이지는 가장 주의가 필요한 성분 하나를 기준으로 계산돼요.',
  },
  nutrientStatus: {
    title: '영양소 섭취 분석이란?',
    body: '카페인, 나트륨, 당류 등 임신 중 주의가 필요한 영양소가 하루 권장 섭취 기준 대비 어느 정도인지 배지로 분석해드려요. 배지 색상이 진할수록 섭취량이 기준에 가깝거나 초과했다는 뜻이에요.',
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

type Tier = 'avoid' | 'caution' | 'safe' | 'unknown';
const TIER_ORDER: Tier[] = ['avoid', 'caution', 'safe', 'unknown'];

// 'low'(band 타입 하한 미달, 예: 철분 부족)는 summaryColors.ts의 부족/안전 동색 처리와
// 같은 이유로 caution과 같은 심각도로 묶는다.
function tierOf(status: string): Tier {
  if (status === 'avoid') return 'avoid';
  if (status === 'caution' || status === 'low') return 'caution';
  if (status === 'safe') return 'safe';
  return 'unknown';
}

function pickRandomFrom<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

// 관심성분(사용자가 선택한 최대 3개) 우선 배지 선택 로직 — 위험→주의→안전→정보없음
// 순서로, 각 단계에서 관심성분 먼저, 없으면 그 외 영양소 중에서 고른다(동률이면 랜덤).
// backend가 이미 계산한 status 중에서 고르는 것뿐이라 새 판정 로직을 들여오지 않는다.
function pickHeadlineNutrient(
  statuses: OcrNutrientStatus[],
  preferredKeys: SelectableNutrientKey[],
  pickRandom: <T>(arr: T[]) => T
): OcrNutrientStatus {
  const preferredSet = new Set(preferredKeys);
  for (const tier of TIER_ORDER) {
    const atTier = statuses.filter((s) => tierOf(s.status) === tier);
    if (atTier.length === 0) continue;
    const preferred = atTier.filter((s) => preferredSet.has(s.key as SelectableNutrientKey));
    return pickRandom(preferred.length > 0 ? preferred : atTier);
  }
  return statuses[0]; // unreachable — tierOf는 항상 TIER_ORDER 중 하나를 반환한다
}

// 헤드라인 문장 — mockup의 "지방은 주의가 필요해요"처럼 자연스러운 구어체를 쓴다.
// 배지의 원문 그대로("위험")를 문장에 넣지 않는다 — 부드러운 표현이 목적이라
// 굳이 같은 단어를 반복할 필요가 없다. 정보없음은 특정 성분 이름을 넣지 않는다
// (판단 근거가 없다는 뜻이라 "이 성분이 문제"라는 느낌을 주면 오해의 소지가 있다).
function buildHeadlineText(tier: Tier, nutrientLabel: string): string {
  switch (tier) {
    case 'avoid':
      return `${attachEunNeun(nutrientLabel)} 주의가 필요해요`;
    case 'caution':
      return `${attachEunNeun(nutrientLabel)} 오늘 허용량에 가까워지고 있어요`;
    case 'safe':
      return `${attachEunNeun(nutrientLabel)} 여유있게 드실 수 있어요`;
    case 'unknown':
      return '라벨에서 확인 가능한 정보가 부족해요';
  }
}

// 헤드라인 아래 2줄 설명 — 특정 성분이 아니라 단계 전체를 설명하는 문구라
// 이전 라운드에 이미 승인된 카피(OVERALL_TIER_HEADLINE)를 그대로 재사용한다.
const TIER_DESCRIPTION: Record<Tier, string> = {
  avoid: '오늘 허용량을 넘길 수 있어요, 다른 메뉴도 고려해보세요',
  caution: '오늘 허용량에 거의 다 찼어요, 적당히 조절해주세요',
  safe: '오늘 허용량 안에서 여유있게 드실 수 있어요',
  unknown: '라벨에서 확인 가능한 정보가 부족해요, 직접 수치를 확인해주세요',
};

// 판정(배지/게이지/헤드라인)이 현재 입력값과 어긋났을 때 쓰는 문구.
// nutrient_statuses는 스캔 시점 스냅샷이라 사용자가 수치를 고쳐도 다시 계산되지
// 않는다 — 흐리게만 처리하면 "지방은 주의가 필요해요" 같은 확정적인 문장을 그대로
// 읽게 되므로, 문장 자체를 중립적인 안내로 교체한다.
const STALE_VERDICT_HEADLINE = '수정한 내용이 아직 판정에 반영되지 않았어요';
const STALE_VERDICT_DESCRIPTION =
  '아래 배지와 게이지는 스캔 직후 수치 기준이에요. 다시 계산되기 전까지는 참고하지 말아주세요.';
const STALE_VERDICT_CAPTION = '※ 판정만 이전 기준이고, 저장되는 수치는 수정한 값 그대로예요';
const STALE_GAUGE_BAND_LABEL = '재계산 필요';

// 원형 게이지 퍼센트 — 7개 중 상태를 아는 영양소만으로 계산하는 종합 점수.
// 개별 성분의 실제 한도 대비 비율(옵션 a)은 이 화면에 한도 원값이 없어(백엔드가
// 3단계 status만 내려줌) 새 백엔드 필드 없이는 계산 불가능하므로 채택하지 않았다.
// unknown은 computeSafetyPercent()가 평균 계산 전에 걸러내므로 실제로 읽히지
// 않지만, Record<Tier, number>가 4개 키 전부를 요구해 자리만 채워둔다.
const TIER_SCORE: Record<Tier, number> = { safe: 100, caution: 55, avoid: 10, unknown: 0 };

function computeSafetyPercent(statuses: OcrNutrientStatus[]): number | null {
  const known = statuses.filter((s) => tierOf(s.status) !== 'unknown');
  if (known.length === 0) return null;
  const total = known.reduce((sum, s) => sum + TIER_SCORE[tierOf(s.status)], 0);
  return Math.round(total / known.length);
}

function safetyBandLabel(percent: number | null): string {
  if (percent == null) return '정보없음';
  if (percent >= 70) return '양호해요';
  if (percent >= 40) return '보통이에요';
  return '주의가 필요해요';
}

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
  // 오늘 섭취 안전도 헤드라인이 가리키는 성분과 같은 행일 때만 true — item B의
  // headlineNutrient를 그대로 재사용해서 계산되고, 이 컴포넌트 안에서 새로
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
          placeholder="-"
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
  percent,
  bandLabel,
  size = 96,
  // 표시 중인 판정이 낡았을 때(verdictFreshness==='stale') 링을 비우고 퍼센트를
  // 감춘다. percent==null("정보없음" — 라벨에 값 자체가 없음)과는 의미가 달라
  // 별도 플래그로 받는다. 둘을 같은 표현으로 합치면 "값이 없다"와 "다시 계산해야
  // 한다"를 구분할 수 없다.
  stale = false,
}: {
  percent: number | null;
  bandLabel: string;
  size?: number;
  stale?: boolean;
}) {
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clampedPercent = stale || percent == null ? 0 : Math.max(0, Math.min(100, percent));
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withTiming(clampedPercent, { duration: 600 });
  }, [clampedPercent, progress]);

  const animatedProps = useAnimatedProps(() => ({
    strokeDashoffset: circumference * (1 - progress.value / 100),
  }));

  const ringColor =
    stale || percent == null
      ? authColors.border
      : percent >= 70
        ? summaryStatusColors['여유'].value
        : percent >= 40
          ? summaryStatusColors['안전'].value
          : summaryStatusColors['위험'].value;

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
        <Text style={[styles.gaugePercentText, stale && styles.gaugePercentTextStale]}>
          {stale ? '–' : percent == null ? '-' : `${percent}%`}
        </Text>
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
  // 화면에 보이는 판정(nutrient_statuses 배지 + 안전도 게이지 + 헤드라인)이 지금
  // 입력값과 일치하는지. 이 값들은 스캔 시점 스냅샷이고 편집으로 다시 계산되지
  // 않으므로, 어긋난 순간 'stale'로 바꿔 화면에 드러낸다 — 저장되는 수치는 편집
  // 결과를 그대로 따라가는데 판정만 예전 것을 보여주면 사용자가 잘못된 근거로
  // 저장하게 된다.
  //
  // T8에서 /ocr/recompute 응답이 도착하면 setVerdictFreshness('fresh')로 되돌리고
  // 이 유니온에 'pending'/'error'를 추가한다 — 표시 분기(isVerdictStale)와 스타일은
  // 그대로 재사용할 수 있도록 상태 하나로 모아둔다.
  const [verdictFreshness, setVerdictFreshness] = useState<'fresh' | 'stale'>('fresh');
  const isVerdictStale = verdictFreshness === 'stale';

  // 판정에 입력되는 값이 바뀌었음을 표시한다. 판정에 관여하지 않는 필드(상품명/
  // 카페인/섭취시간/추가 성분)를 고칠 때는 호출하지 않는다 — 그때까지 판정을
  // 가리면 근거 없이 정보를 숨기는 셈이 된다.
  const markVerdictStale = () => setVerdictFreshness('stale');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alternatives, setAlternatives] = useState<OcrAlternativesResponse | null>(null);
  // 관심성분(사용자가 마이페이지에서 고른 최대 3개) — null이면 아직 로딩 전.
  // updateNutrientPreferences(userId, null)은 값을 바꾸지 않고 현재 선택을 그대로
  // 조회하는 기존 read-as-write-null 패턴(마이페이지 화면과 동일)이다.
  const [preferredNutrients, setPreferredNutrients] = useState<SelectableNutrientKey[] | null>(null);
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

  useEffect(() => {
    if (!user?.user_id) return;
    updateNutrientPreferences(user.user_id, null)
      .then((res) => setPreferredNutrients(res.selected_nutrients as SelectableNutrientKey[]))
      .catch(() => setPreferredNutrients([]));
  }, [user?.user_id]);

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
    setNutrientFields((prev) => ({ ...prev, [key]: sanitized }));
    markVerdictStale();
  };

  const updateTotalContentAmount = (text: string) => {
    setTotalContentAmount(sanitizeNonNegativeDecimal(text));
    markVerdictStale();
  };

  const updateBasisAmountValue = (text: string) => {
    setBasisAmountValueText(sanitizeNonNegativeDecimal(text));
    markVerdictStale();
  };

  // 섭취량/단위도 판정 입력이다 — 지금은 배지가 1회 제공량 기준이라 화면상 즉시
  // 달라지지 않지만, T8에서 판정 기준이 "실제 섭취량"으로 바뀌면 이 두 값이 직접
  // 판정을 움직인다. 그때 빠뜨리지 않도록 지금부터 같은 경로로 묶어둔다.
  const updateAmount = (text: string) => {
    setAmount(text);
    markVerdictStale();
  };

  const updateUnit = (nextUnit: string) => {
    setUnit(nextUnit);
    markVerdictStale();
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

  const handleSave = () => {
    if (!isFormValid || !user?.user_id || !params.date || saving) return;

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

  // 오늘 섭취 안전도 헤드라인 — nutrient_statuses 스냅샷(스캔 시점 고정) + 관심성분
  // 목록으로 한 번만 고른다. deps가 [scanResult, preferredNutrients]뿐이라 다른
  // 필드 편집으로는 재계산되지 않는다 — 관심성분 로딩이 끝나 preferredNutrients가
  // null→배열로 바뀔 때 한 번 더 계산되는 것은 의도된 "업그레이드"다.
  const headlineNutrient = useMemo(
    () => pickHeadlineNutrient(scanResult?.nutrient_statuses ?? [], preferredNutrients ?? [], pickRandomFrom),
    [scanResult, preferredNutrients]
  );
  const headlineTier = tierOf(headlineNutrient?.status ?? 'unknown');
  const safetyPercent = useMemo(
    () => computeSafetyPercent(scanResult?.nutrient_statuses ?? []),
    [scanResult]
  );

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
                onChangeAmount={updateAmount}
                onChangeUnit={updateUnit}
              />

              <View style={styles.cardDivider} />

              <Text style={styles.fieldLabel}>섭취시간</Text>
              <Pressable style={styles.timeInput} onPress={toggleTimePicker}>
                <ClockIcon width={15} height={15} style={styles.timeInputClock} />
                <Text style={styles.timeInputText}>{formatTimeLabel(time)}</Text>
                <Animated.View style={[styles.timeInputChevron, timeChevronAnimatedStyle]}>
                  <ChevronDownIcon width={12} height={8} />
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
            end={{ x: 0, y: 1 }}
            style={StyleSheet.absoluteFillObject}
          />
          <Pressable
            style={styles.safetyInfoButton}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            onPress={() => setActiveInfo('safety')}>
            <InformationIcon width={18} height={18} />
          </Pressable>
          <View style={styles.safetyRow}>
            <View style={styles.safetyTextGroup}>
              <Text
                style={[
                  styles.safetyHeadline,
                  isVerdictStale
                    ? styles.safetyHeadlineStale
                    : { color: (summaryStatusColors[headlineNutrient.status_label] ?? DEFAULT_SUMMARY_STATUS_COLORS).label },
                ]}>
                {isVerdictStale
                  ? STALE_VERDICT_HEADLINE
                  : buildHeadlineText(headlineTier, headlineNutrient.label)}
              </Text>
              <Text style={styles.safetyDescription}>
                {isVerdictStale ? STALE_VERDICT_DESCRIPTION : TIER_DESCRIPTION[headlineTier]}
              </Text>
            </View>
            <SafetyGauge
              percent={safetyPercent}
              bandLabel={isVerdictStale ? STALE_GAUGE_BAND_LABEL : safetyBandLabel(safetyPercent)}
              stale={isVerdictStale}
            />
          </View>
          <Text style={styles.statusCaption}>
            {isVerdictStale ? STALE_VERDICT_CAPTION : '※ 스캔한 라벨 기준 상태예요'}
          </Text>
        </View>

        {/* 3. 성분별 상태 — 7개 배지 그리드, 이전 라운드와 동일 */}
        <View style={styles.card}>
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.fieldLabel}>영양소 섭취 분석</Text>
            <Pressable
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              onPress={() => setActiveInfo('nutrientStatus')}>
              <InformationIcon width={18} height={18} />
            </Pressable>
          </View>
          <View style={styles.statusGrid}>
            {scanResult.nutrient_statuses.map((item) => (
              <StatusChip
                key={item.key}
                label={item.label}
                value={item.status_label}
                colors={summaryStatusColors[item.status_label] ?? DEFAULT_SUMMARY_STATUS_COLORS}
                style={[styles.statusChipItem, isVerdictStale && styles.statusChipItemStale]}
              />
            ))}
          </View>
          {/* 배지 그리드는 안전도 카드와 별도 카드라, 흐려진 이유를 여기서도 한 번 밝힌다
              — 스크롤 위치에 따라 안전도 카드의 안내를 못 볼 수 있다. */}
          {isVerdictStale && <Text style={styles.statusCaption}>{STALE_VERDICT_CAPTION}</Text>}
        </View>

        {/* 4. 영양성분 상세 (100g당 / 총섭취량(N인분)) */}
        <View style={styles.card}>
          <View style={styles.sectionHeaderRow}>
            <Pressable
              style={styles.sectionHeaderToggle}
              onPress={toggleNutrientTable}
              hitSlop={{ top: 8, bottom: 8 }}>
              <Text style={styles.fieldLabel}>영양성분 상세</Text>
              <Animated.View style={tableChevronAnimatedStyle}>
                <ChevronDownIcon width={12} height={8} />
              </Animated.View>
            </Pressable>
            <Pressable
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              onPress={() => setActiveInfo('nutrientDetail')}>
              <InformationIcon width={18} height={18} />
            </Pressable>
          </View>

          {/* 총내용량/기준량 카드 — 기본은 읽기 전용 배지 표시, 연필 버튼으로 기존
              입력 행(총내용량/기준량 TextInput)을 그대로 드러낸다. kcal 필드는
              헤더에서 파생되는 참고용 숫자로 저장 값과 무관하다. */}
          <View style={styles.amountCard}>
            <View style={styles.amountCardHeaderRow}>
              <Pressable
                style={styles.amountCardEditButton}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                onPress={() => setIsEditingAmountCard((v) => !v)}>
                <PencilIcon />
              </Pressable>
            </View>
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
                  <View style={[styles.amountCardIconCircle, styles.amountCardIconCircleGreen]}>
                    <PackageGlyph color={homeColors.sugar.value} />
                  </View>
                  <Text style={styles.amountCardItemLabel}>총 내용량</Text>
                  <Text style={styles.amountCardItemValue}>
                    {totalContentAmount || '-'} {scanResult.total_content_unit}
                  </Text>
                  {headerKcal != null && (
                    <Text style={styles.amountCardKcalSubtext}>{headerKcal} kcal</Text>
                  )}
                </View>
                <View style={styles.amountCardDivider} />
                <View style={styles.amountCardItem}>
                  <View style={[styles.amountCardIconCircle, styles.amountCardIconCircleBlue]}>
                    <BalanceGlyph color={BASIS_BADGE_BLUE} />
                  </View>
                  <Text style={styles.amountCardItemLabel}>기준량</Text>
                  <Text style={styles.amountCardItemValue}>
                    {basisAmountValueText || '-'} {scanResult.basis_amount_unit}
                  </Text>
                </View>
              </View>
            )}
          </View>

          <Text style={styles.transparencyText}>※ {totalConsumedCaption}</Text>

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
                      highlighted={!isVerdictStale && key === headlineNutrient.key}
                    />
                  );
                })}
              </View>
            </Animated.View>
          )}

          <View style={styles.cardDivider} />
          <View style={styles.nutrientInputRow}>
            <View style={styles.nutrientLabelGroup}>
              <CaffeineIcon width={17} height={17} />
              <Text style={styles.nutrientLabel}>카페인(mg)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={caffeineMg}
              onChangeText={(text) => setCaffeineMg(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 65"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>
        </View>

        {/* 5. 추가 성분 입력 */}
        <View style={styles.card}>
          <View style={styles.nutrientHeaderRow}>
            <View>
              <Text style={styles.fieldLabel}>추가 성분</Text>
            </View>
            <Pressable style={styles.addNutrientPill} onPress={addDraftRow}>
              <Text style={styles.addNutrientPillText}>+ 성분 추가</Text>
            </Pressable>
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
          style={[styles.saveButton, (!isFormValid || saving) && styles.saveButtonDisabled]}
          onPress={handleSave}
          disabled={!isFormValid || saving}>
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
  sectionHeaderToggle: {
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
  transparencyText: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 8,
  },
  nutrientInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 12,
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
  safetyHeadlineStale: {
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
  gaugePercentTextStale: {
    color: authColors.gray,
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
  statusGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: 10,
    marginTop: 12,
  },
  statusChipItem: {
    flex: 0,
    width: '31%',
  },
  // 낡은 판정 배지 — 지우지 않고 흐리게 남긴다. 아예 비우면 화면이 크게 흔들리고,
  // "값이 없다"(정보없음 배지)와도 헷갈린다.
  statusChipItemStale: {
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
  amountCard: {
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 12,
    padding: 14,
    marginTop: 10,
  },
  amountCardHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginBottom: 4,
  },
  amountCardEditButton: {
    width: 26,
    height: 26,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: authColors.pink,
    backgroundColor: authColors.white,
    alignItems: 'center',
    justifyContent: 'center',
  },
  amountCardEditRow: {},
  amountCardDisplayRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  amountCardItem: {
    flex: 1,
  },
  amountCardDivider: {
    width: 1,
    alignSelf: 'stretch',
    backgroundColor: authColors.border,
    marginHorizontal: 14,
  },
  amountCardIconCircle: {
    width: 28,
    height: 28,
    borderRadius: 14,
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
    marginTop: 8,
  },
  amountCardItemValue: {
    fontFamily: fonts.bold,
    fontSize: 18,
    color: '#000000',
    marginTop: 2,
  },
  amountCardKcalSubtext: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: homeColors.sugar.value,
    marginTop: 2,
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
