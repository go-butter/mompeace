import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, useFocusEffect } from 'expo-router';

import PrevIcon from '@/assets/images/common/prev.svg';
import InformationIcon from '@/assets/images/onboarding/information.svg';
import DashboardIcon from '@/assets/images/recommend/dashboard.svg';
import SafeCheckIcon from '@/assets/images/recommend/safe_check.svg';
import FilterIcon from '@/assets/images/recommend/filter.svg';
import { authColors } from '@/components/auth/colors';
import BottomSheet from '@/components/common/BottomSheet';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  getFoodCategories,
  getRecommendations,
  PanelNutrient,
  RecommendationItem,
  RecommendationNutrients,
  RecommendationResponse,
} from '@/lib/api-client';
import { formatNumber, formatNutrient } from '@/lib/format';

type RecommendationStatus = RecommendationItem['status'];

const REQUEST_LIMIT = 60;
const INITIAL_ROWS_SHOWN = 4;
const CHIP_HIT_SLOP = { top: 8, bottom: 8, left: 6, right: 6 };

// panel_nutrients 키 -> RecommendationNutrients 필드. backend routers/recommendation.py의
// PANEL_NUTRIENT_TO_FOOD_KEY와 이름을 맞춰서 유지한다 — 같은 매핑을 두 언어로 각자
// 만들면 언젠가 어긋난다.
const PANEL_NUTRIENT_TO_FOOD_KEY: Record<string, keyof RecommendationNutrients> = {
  caffeine: 'caffeine_mg',
  sugar: 'sugar_g',
  sodium: 'sodium_mg',
  carbohydrate: 'carbohydrate_g',
  protein: 'protein_g',
  fat: 'fat_g',
  iron: 'iron_mg',
  energy: 'calories_kcal',
};

// 표시 전용 — 실제 /recommendations 호출에는 항상 GET /categories가 돌려주는 원본 DB
// 문자열을 그대로 쓴다 (category = ? 정확 일치라 다른 문자열을 보내면 0건이 된다).
// 여기 없는 카테고리는 원본 문자열을 그대로 보여준다 — 새 카테고리가 생겨도 화면에서
// 사라지지 않는다. 8자 초과만 줄인다.
const CATEGORY_LABELS: Record<string, string> = {
  '유제품류 및 빙과류': '유제품/빙과류',
  '두류, 견과 및 종실류': '두류/견과류',
  '찌개 및 전골류': '찌개/전골류',
  '죽 및 스프류': '죽/스프류',
  '전·적 및 부침류': '전·적/부침류',
  '곡류, 서류 제품': '곡류/서류 제품',
};

// 당류 칩 정렬 시 디저트류를 먼저 보여주기 위한 카테고리 — CATEGORY_LABELS 바로 옆에
// 두어 두 목록이 서로 다른 문자열로 갈라지지 않도록 한다(둘 다 CATEGORY_LABELS의 키와
// 동일한 리터럴을 쓴다).
const DESSERT_CATEGORIES = new Set(['빵 및 과자류', '유제품류 및 빙과류']);

// Figma가 인라인으로 보여주는 9개 중 "전체"를 뺀 8개 실제 카테고리 — 나머지 카테고리는
// 전체 필터를 펼쳤을 때 GET /categories로 받은 값을 그대로 보여준다.
const INLINE_CATEGORY_VALUES = [
  '밥류',
  '과일류',
  '구이류',
  '국 및 탕류',
  '김치류',
  '빵 및 과자류',
  '음료 및 차류',
  '면 및 만두류',
];

// 정렬 힌트일 뿐이다 — 실제 카테고리 값과 목록은 항상 GET /categories에서 받는다.
// 여기 없는 카테고리(향후 DB에 새로 추가된 값)는 맨 뒤로 밀릴 뿐 사라지지 않는다.
// dish_db_download 기준 행 수 내림차순 스냅샷(시간이 지나면 실제 분포와 어긋날 수 있음).
const CATEGORY_ORDER_HINT = [
  '빵 및 과자류',
  '음료 및 차류',
  '유제품류 및 빙과류',
  '국 및 탕류',
  '생채·무침류',
  '볶음류',
  '튀김류',
  '밥류',
  '면 및 만두류',
  '찌개 및 전골류',
  '구이류',
  '나물·숙채류',
  '조림류',
  '전·적 및 부침류',
  '찜류',
  '죽 및 스프류',
  '김치류',
  '장류, 양념류',
  '장아찌·절임류',
  '젓갈류',
  '수·조·어·육류',
  '곡류, 서류 제품',
  '채소, 해조류',
  '두류, 견과 및 종실류',
  '과일류',
];

function sortByUsefulness(categories: string[]): string[] {
  const rank = new Map(CATEGORY_ORDER_HINT.map((c, i) => [c, i]));
  return [...categories].sort((a, b) => (rank.get(a) ?? Infinity) - (rank.get(b) ?? Infinity));
}

const FALLBACK_REASON: Record<RecommendationStatus, string> = {
  possible: '오늘 남은 섭취량 안에서 비교적 부담이 낮은 음식이에요.',
  caution: '영양성분 정보가 일부 없어 오늘 섭취량을 정확히 확인하기 어려운 음식이에요.',
  avoid: '오늘 기준을 넘길 수 있어 다른 음식을 선택하는 편이 좋아요.',
};

const STATUS_LABEL: Record<RecommendationStatus, string> = {
  possible: '섭취 가능',
  caution: '정보 부족',
  avoid: '피함',
};

function isRecommendationStatus(status: unknown): status is RecommendationStatus {
  return status === 'possible' || status === 'caution' || status === 'avoid';
}

function getStatusLabel(status: RecommendationStatus) {
  return STATUS_LABEL[status] ?? status;
}

function getReason(item: RecommendationItem) {
  const reason = typeof item.reason === 'string' ? item.reason.trim() : '';
  return reason || FALLBACK_REASON[item.status];
}

// panel_nutrients 항목 하나의 "값" 줄. type에 따라 어느 필드를 읽을지 갈라지지만,
// 어떤 영양소 키가 어떤 type인지는 절대 하드코딩하지 않는다 — API가 준 item.type을
// 그대로 따른다. null은 절대 0으로 렌더링하지 않고 항상 "정보 없음"으로 표시한다.
//
// 세 타입 모두 이 줄의 의미는 하나다 — "얼마나 남았는가"(limit - 소비량). ceiling은
// 상한까지, floor는 목표까지, band는 상한까지. 카드 제목("오늘 남은 허용량")과 (i)
// 아이콘 설명이 이미 그 의미를 말해주므로, 셀 자체에는 숫자+단위만 두고 "남음"/"더" 같은
// 설명 단어를 붙이지 않는다 — 세 타입이 전부 같은 형태(bare number+unit)로 보여야 한다.
//
// "정보 없음"은 항상 style(16px, marginTop 포함)로 렌더링한다 — unitStyle(12px, 마진
// 없음)로 렌더링하면 숫자가 있는 셀보다 작고 위로 붙어 보인다(정렬 안 맞는 문제의
// 원인이었다).
function PanelValueText({ item, style, unitStyle }: { item: PanelNutrient; style: object; unitStyle: object }) {
  if (item.type === 'ceiling') {
    if (item.remaining == null) return <Text style={style}>정보 없음</Text>;
    return (
      <Text style={style}>
        {formatNumber(item.remaining)}
        <Text style={unitStyle}>{item.unit}</Text>
      </Text>
    );
  }
  if (item.type === 'floor') {
    if (item.remaining == null) return <Text style={style}>정보 없음</Text>;
    return (
      <Text style={style}>
        {formatNumber(item.remaining)}
        <Text style={unitStyle}>{item.unit}</Text>
      </Text>
    );
  }
  // band: remaining은 계약상 항상 null이다 — API가 계산해 주지 않으므로 여기서 상한까지
  // 남은 양을 직접 계산한다(upper - total). ceiling의 remaining과 같은 개념(상한까지
  // 남은 여유)이므로 표현도 ceiling과 똑같이 숫자+단위만 쓴다. total이 lower 미만이어도
  // (하한을 아직 못 채웠어도) 이 숫자 자체는 "상한까지 얼마나 남았는가"로 여전히
  // 유효하다 — 하한 미달 여부는 이 숫자가 답하는 질문이 아니고, 보조 줄의 lower~upper
  // 범위가 그 판단 근거를 대신 보여준다. lower/upper는 오늘 로그가 아니라 고정
  // 기준값에서 오므로 계약상 항상 존재하지만, total은 오늘 데이터가 없으면 null일 수
  // 있다.
  if (item.total == null || item.upper == null) return <Text style={style}>정보 없음</Text>;
  const remainingToUpper = Math.max(0, item.upper - item.total);
  return (
    <Text style={style}>
      {formatNumber(remainingToUpper)}
      <Text style={unitStyle}>{item.unit}</Text>
    </Text>
  );
}

// 보조(회색) 줄 = 순수 기준값. 편집성 접두어(권장/목표 등) 없이 숫자만 — 이 값들은
// 전부 API가 준 limit/target/lower/upper에서만 온다. 프론트에서 새로 만든 임계값은
// 없다. 오늘 데이터(remaining/total)가 없어도 기준값 자체는 고정 상수라 항상 그대로
// 보여준다.
function panelSecondaryText(item: PanelNutrient): string {
  if (item.type === 'ceiling') {
    return item.limit != null ? `/ ${formatNumber(item.limit)}${item.unit}` : '정보 없음';
  }
  if (item.type === 'floor') {
    return item.target != null ? `${formatNumber(item.target)}${item.unit}` : '정보 없음';
  }
  return item.lower != null && item.upper != null
    ? `${formatNumber(item.lower)}~${formatNumber(item.upper)}${item.unit}`
    : '정보 없음';
}

// 한글 완성형(가~힣) 범위에서만 받침 유무를 판별한다 — 라벨은 전부 순한글(카페인/당류/
// 나트륨/탄수화물/단백질/에너지/지방/철분)이라 이 범위를 벗어날 일이 없다. 라틴 문자
// (mg/g/kcal 같은 단위)는 이 공식이 의미가 없으므로, 목적어 조사(을/를)는 아예 쓰지
// 않도록 문장 자체를 "이상/이하로" 표현으로 바꿔 피한다(아래 explainNutrient 참고).
function hasBatchim(text: string): boolean {
  const lastChar = text.trim().slice(-1);
  const code = lastChar.charCodeAt(0);
  if (code < 0xac00 || code > 0xd7a3) return false;
  return (code - 0xac00) % 28 !== 0;
}

function withTopicParticle(label: string): string {
  return `${label}${hasBatchim(label) ? '은' : '는'}`;
}

// (i) 아이콘 설명 문구. 8개 영양소를 하드코딩하지 않고 type 하나당 템플릿 하나만 쓴다.
// "이상/이하로"는 조사(을/를)가 없는 표현이라 단위가 라틴 문자(mg/g/kcal)여도 걸리지
// 않는다 — {label}에만 받침 기반 은/는을 적용한다.
function explainNutrient(item: PanelNutrient): string {
  const subject = withTopicParticle(item.label);
  if (item.type === 'ceiling') {
    return item.limit != null
      ? `${subject} 하루 ${formatNumber(item.limit)}${item.unit} 이하로 드세요.`
      : `${subject} 하루 권장 기준 정보가 없어요.`;
  }
  if (item.type === 'floor') {
    return item.target != null
      ? `${subject} 하루 ${formatNumber(item.target)}${item.unit} 이상 드세요.`
      : `${subject} 하루 권장 기준 정보가 없어요.`;
  }
  return item.lower != null && item.upper != null
    ? `${subject} 하루 ${formatNumber(item.lower)}${item.unit} 이상 ${formatNumber(item.upper)}${item.unit} 이하로 드세요.`
    : `${subject} 하루 권장 기준 정보가 없어요.`;
}

function Chip({
  label,
  selected,
  onPress,
  fixedWidth,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  fixedWidth?: boolean;
}) {
  return (
    <Pressable
      style={[
        styles.chip,
        fixedWidth ? styles.chipFixedWidth : styles.chipFluid,
        selected ? styles.chipSelected : styles.chipUnselected,
      ]}
      hitSlop={CHIP_HIT_SLOP}
      onPress={onPress}>
      <Text
        style={[styles.chipText, selected ? styles.chipTextSelected : styles.chipTextUnselected]}
        numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

const BADGE_STYLE_KEY: Record<RecommendationStatus, 'possible' | 'caution' | 'avoid'> = {
  possible: 'possible',
  caution: 'caution',
  avoid: 'avoid',
};

function FoodRow({
  item,
  isLast,
  panelNutrients,
}: {
  item: RecommendationItem;
  isLast: boolean;
  panelNutrients: PanelNutrient[];
}) {
  const reason = getReason(item);
  const categoryLabel = item.category != null ? (CATEGORY_LABELS[item.category] ?? item.category) : null;
  const isAvoid = item.status === 'avoid';
  const badgeKey = BADGE_STYLE_KEY[item.status];

  // 사용자가 고른 영양소(panel_nutrients와 동일한 소스, 카페인 우선 + 선택 최대 3개)를
  // 그대로 따른다 — 당류/나트륨을 하드코딩하지 않는다. 그래야 사용자가 단백질/철분/
  // 지방을 골랐을 때도 음식 행이 그 성분을 보여준다.
  const nutrientText = panelNutrients
    .map((p) => {
      const foodKey = PANEL_NUTRIENT_TO_FOOD_KEY[p.key];
      const value = foodKey ? item.nutrients[foodKey] : null;
      return `${p.label} ${formatNutrient(value, p.unit)}`;
    })
    .join(' · ');

  return (
    <View style={[styles.foodRow, !isLast && styles.foodRowDivider]}>
      <View style={styles.foodRowHeader}>
        <Text style={styles.foodRowName} numberOfLines={1}>
          {item.food_name}
        </Text>
        <View
          style={[
            styles.statusBadge,
            badgeKey === 'possible' && styles.possibleBadge,
            badgeKey === 'caution' && styles.cautionBadge,
            badgeKey === 'avoid' && styles.avoidBadge,
          ]}>
          <Text
            style={[
              styles.statusBadgeText,
              badgeKey === 'possible' && styles.possibleBadgeText,
              badgeKey === 'caution' && styles.cautionBadgeText,
              badgeKey === 'avoid' && styles.avoidBadgeText,
            ]}>
            {getStatusLabel(item.status)}
          </Text>
        </View>
      </View>
      {categoryLabel != null && <Text style={styles.foodRowCategory}>{categoryLabel}</Text>}
      <Text style={styles.foodRowReason}>{reason}</Text>
      {nutrientText.length > 0 && <Text style={styles.foodRowNutrients}>{nutrientText}</Text>}
      {/* 대체 제안은 avoid에만 붙인다. caution은 영양성분 값을 읽지 못했다는 뜻이라
          다른 음식으로 바꿀 근거가 없다. */}
      {isAvoid && item.alternative && (
        <View style={styles.alternativeBox}>
          <Text style={styles.alternativeLabel}>대신 이건 어때요?</Text>
          <Text style={styles.alternativeName}>{item.alternative.food_name}</Text>
        </View>
      )}
    </View>
  );
}

export default function RecommendScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();

  // 성분/카테고리 칩 하나만 "선택"될 수 있다. 밴드형(지방/철분)은 재요청 없이
  // 상단 카드의 해당 셀만 하이라이트한다(아래 handleChipPress 참고).
  const [selectedChip, setSelectedChip] = useState<{ key: string; isBand: boolean } | null>(null);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [infoVisible, setInfoVisible] = useState(false);

  const [categories, setCategories] = useState<string[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null);
  const [loadingRecommendations, setLoadingRecommendations] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [possibleExpanded, setPossibleExpanded] = useState(false);

  // 카테고리 목록은 세션 내내 고정된 참고 데이터라 포커스마다 다시 받을 필요가 없다.
  useEffect(() => {
    getFoodCategories()
      .then((res) => setCategories(res.categories))
      .catch(() => setCategories([]));
  }, []);

  const sortNutrientParam = selectedChip && !selectedChip.isBand ? selectedChip.key : null;

  const fetchRecommendations = useCallback(() => {
    if (!user?.user_id) {
      setRecommendations(null);
      setLoadingRecommendations(false);
      return;
    }
    setLoadingRecommendations(true);
    setError(null);
    getRecommendations({
      user_id: user.user_id,
      limit: REQUEST_LIMIT,
      category: selectedCategories,
      sort_nutrient: sortNutrientParam,
    })
      .then(setRecommendations)
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setLoadingRecommendations(false));
  }, [user?.user_id, selectedCategories, sortNutrientParam]);

  useFocusEffect(
    useCallback(() => {
      fetchRecommendations();
    }, [fetchRecommendations])
  );

  // 필터가 바뀌면 이전 목록 기준으로 펼쳐뒀던 상태를 새 목록에 그대로 들고 가지 않는다.
  useEffect(() => {
    setPossibleExpanded(false);
  }, [selectedCategories, sortNutrientParam]);

  function handleChipPress(item: PanelNutrient) {
    if (selectedChip?.key === item.key) {
      setSelectedChip(null);
      return;
    }
    setSelectedChip({ key: item.key, isBand: item.type === 'band' });
  }

  function toggleCategory(category: string) {
    setSelectedCategories((prev) =>
      prev.includes(category) ? prev.filter((c) => c !== category) : [...prev, category]
    );
  }

  function clearCategories() {
    setSelectedCategories([]);
  }

  const panelNutrients = recommendations?.panel_nutrients ?? [];
  const inlineCategories = INLINE_CATEGORY_VALUES.filter((c) => categories.includes(c));
  // 인라인 9개(전체 포함)를 뺀 나머지 — 전체 필터를 펼쳤을 때만 보여준다.
  const expandedCategories = sortByUsefulness(categories).filter(
    (c) => !INLINE_CATEGORY_VALUES.includes(c)
  );

  const allItems = Array.isArray(recommendations?.recommendations)
    ? recommendations!.recommendations.filter(
        (item): item is RecommendationItem => {
          const candidate = item as Partial<RecommendationItem> | null;
          return candidate != null && typeof candidate === 'object' && isRecommendationStatus(candidate.status);
        }
      )
    : [];

  const sortBySugarWithDessertFirst = (items: RecommendationItem[]) => {
    if (sortNutrientParam !== 'sugar') return items;
    const dessert = items.filter((item) => item.category != null && DESSERT_CATEGORIES.has(item.category));
    const other = items.filter((item) => !(item.category != null && DESSERT_CATEGORIES.has(item.category)));
    return [...dessert, ...other];
  };

  const possibleItems = sortBySugarWithDessertFirst(allItems.filter((item) => item.status === 'possible'));

  const visiblePossible = possibleExpanded ? possibleItems : possibleItems.slice(0, INITIAL_ROWS_SHOWN);

  const loading = loadingRecommendations;
  const emptyMessage = recommendations?.message || '지금 바로 먹을 수 있는 음식이 없어요.';
  const showEmptyMessage = !loading && !error && possibleItems.length === 0;

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + 7, paddingBottom: insets.bottom + 32 },
        ]}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
            <PrevIcon width={15} height={15} />
          </Pressable>
          <Text style={styles.title}>오늘의 음식 추천</Text>
        </View>
        <Text style={styles.subtitle}>오늘 남은 허용량 안에서 먹어도 되는 음식이에요 :)</Text>

        <View style={styles.allowanceCard}>
          <Pressable
            style={styles.allowanceInfoButton}
            onPress={() => setInfoVisible(true)}
            accessibilityRole="button"
            accessibilityLabel="영양소 기준 설명 보기">
            <InformationIcon width={16} height={16} color={authColors.pink} />
          </Pressable>
          <View style={styles.allowanceHeader}>
            <DashboardIcon width={19} height={19} />
            <Text style={styles.allowanceTitle}>오늘 남은 허용량</Text>
          </View>
          {loading && panelNutrients.length === 0 ? (
            <ActivityIndicator size="small" color={authColors.pink} style={{ marginVertical: 12 }} />
          ) : panelNutrients.length === 0 ? (
            <Text style={styles.allowanceUnavailable}>표시할 영양소가 없어요.</Text>
          ) : (
            <View style={styles.allowanceRow}>
              {panelNutrients.map((item, index) => {
                return (
                  <View key={item.key} style={styles.allowanceCellWrap}>
                    {index > 0 && <View style={styles.allowanceDivider} />}
                    <View style={styles.allowanceCell}>
                      <Text style={styles.allowanceCellLabel} numberOfLines={1}>
                        {item.label}
                      </Text>
                      <PanelValueText
                        item={item}
                        style={styles.allowanceCellValue}
                        unitStyle={styles.allowanceCellValueUnit}
                      />
                      <Text style={styles.allowanceCellSecondary} numberOfLines={1}>
                        {panelSecondaryText(item)}
                      </Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}
          {recommendations?.exceeded_label != null && (
            <Text style={styles.exceededBanner}>{recommendations.exceeded_label}</Text>
          )}
        </View>

        <View style={styles.chipsCard}>
          <Text style={styles.chipsSectionLabel}>성분</Text>
          <View style={styles.nutrientChipRow}>
            {panelNutrients.map((item) => (
              <Chip
                key={item.key}
                label={item.label}
                selected={selectedChip?.key === item.key}
                onPress={() => handleChipPress(item)}
                fixedWidth
              />
            ))}
          </View>

          <Text style={[styles.chipsSectionLabel, styles.categorySectionLabel]}>카테고리</Text>
          <View style={styles.categoryChipRow}>
            <Chip label="전체" selected={selectedCategories.length === 0} onPress={clearCategories} />
            {inlineCategories.map((cat) => (
              <Chip
                key={cat}
                label={CATEGORY_LABELS[cat] ?? cat}
                selected={selectedCategories.includes(cat)}
                onPress={() => toggleCategory(cat)}
              />
            ))}
          </View>

          {/* 팝업 대신 카드 안에서 그대로 펼친다 — 나머지 화면은 그만큼 아래로 밀린다. */}
          {filtersExpanded && expandedCategories.length > 0 && (
            <View style={[styles.categoryChipRow, styles.expandedCategoryRow]}>
              {expandedCategories.map((cat) => (
                <Chip
                  key={cat}
                  label={CATEGORY_LABELS[cat] ?? cat}
                  selected={selectedCategories.includes(cat)}
                  onPress={() => toggleCategory(cat)}
                />
              ))}
            </View>
          )}

          <Pressable
            style={styles.filterButton}
            onPress={() => setFiltersExpanded((v) => !v)}
            hitSlop={CHIP_HIT_SLOP}>
            <View style={filtersExpanded ? styles.filterIconExpanded : undefined}>
              <FilterIcon width={13} height={13} />
            </View>
            <Text style={styles.filterButtonText}>전체 필터</Text>
          </Pressable>
        </View>

        {loading ? (
          <ActivityIndicator size="small" color={authColors.pink} style={{ marginTop: 32 }} />
        ) : error ? (
          <Text style={styles.errorText}>{error}</Text>
        ) : (
          <>
            {showEmptyMessage && <Text style={styles.emptyMessage}>{emptyMessage}</Text>}

            {possibleItems.length > 0 && (
              <View style={styles.section}>
                <View style={styles.sectionHeaderRow}>
                  <SafeCheckIcon width={16} height={16} />
                  <Text style={styles.sectionHeaderText}>이건 괜찮아요!</Text>
                </View>
                <Text style={styles.sectionSubtitle}>
                  남은 허용량 내에서 안심하고 먹을 수 있어요 :)
                </Text>
                <View style={styles.sectionBox}>
                  {visiblePossible.map((item, index) => (
                    <FoodRow
                      key={item.food_id ?? `${item.food_name}-${index}`}
                      item={item}
                      isLast={index === visiblePossible.length - 1}
                      panelNutrients={panelNutrients}
                    />
                  ))}
                </View>
                {possibleItems.length > INITIAL_ROWS_SHOWN && (
                  <Pressable onPress={() => setPossibleExpanded((v) => !v)} style={styles.moreButton}>
                    <Text style={styles.moreButtonText}>{possibleExpanded ? '접기' : '더보기'}</Text>
                  </Pressable>
                )}
              </View>
            )}
          </>
        )}
      </ScrollView>

      <BottomSheet visible={infoVisible} onClose={() => setInfoVisible(false)}>
        <View style={[styles.infoSheet, { paddingBottom: styles.infoSheet.paddingBottom + insets.bottom }]}>
          <Text style={styles.infoSheetTitle}>영양소 기준 안내</Text>
          <View style={styles.infoSheetList}>
            {panelNutrients.map((item) => (
              <Text key={item.key} style={styles.infoSheetBody}>
                {explainNutrient(item)}
              </Text>
            ))}
          </View>
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
  scrollContent: {
    paddingHorizontal: 19,
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
    backgroundColor: authColors.pinkLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 20,
    color: authColors.brown,
  },
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    letterSpacing: -0.12,
    color: authColors.grayDark,
    marginTop: 7,
  },

  // ── 오늘 남은 허용량 카드 ────────────────────────────────────
  allowanceCard: {
    marginTop: 16,
    backgroundColor: authColors.white,
    borderRadius: 15,
    padding: 16,
    shadowColor: '#FFDBDB',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 2,
  },
  allowanceInfoButton: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  allowanceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  allowanceTitle: {
    fontFamily: fonts.semiBold,
    fontSize: 12,
    color: authColors.grayDark,
  },
  allowanceUnavailable: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
    textAlign: 'center',
    marginVertical: 8,
  },
  allowanceRow: {
    flexDirection: 'row',
    marginTop: 14,
  },
  allowanceCellWrap: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  allowanceDivider: {
    width: 0.7,
    backgroundColor: authColors.border,
    marginRight: 4,
  },
  allowanceCell: {
    flex: 1,
    alignItems: 'center',
    borderRadius: 8,
    paddingVertical: 4,
  },
  allowanceCellLabel: {
    fontFamily: fonts.light,
    fontSize: 11,
    color: authColors.grayDark,
  },
  allowanceCellValue: {
    fontFamily: fonts.bold,
    fontSize: 16,
    color: authColors.pink,
    marginTop: 6,
  },
  allowanceCellValueUnit: {
    fontFamily: fonts.bold,
    fontSize: 12,
    color: authColors.pink,
  },
  allowanceCellSecondary: {
    fontFamily: fonts.light,
    fontSize: 10,
    color: authColors.gray,
    marginTop: 6,
  },
  exceededBanner: {
    fontFamily: fonts.medium,
    fontSize: 11,
    color: authColors.pink,
    textAlign: 'center',
    marginTop: 10,
  },

  // ── 성분/카테고리 칩 카드 ────────────────────────────────────
  chipsCard: {
    marginTop: 12,
    backgroundColor: authColors.white,
    borderWidth: 0.5,
    borderColor: authColors.border,
    borderRadius: 15,
    padding: 16,
    shadowColor: '#FFDBDB',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 1,
  },
  chipsSectionLabel: {
    fontFamily: fonts.semiBold,
    fontSize: 12,
    color: authColors.grayDark,
  },
  categorySectionLabel: {
    marginTop: 14,
  },
  nutrientChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 8,
  },
  categoryChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 8,
  },
  expandedCategoryRow: {
    marginTop: 5,
  },
  chip: {
    height: 19,
    borderRadius: 100,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipFixedWidth: {
    width: 50,
  },
  chipFluid: {
    paddingHorizontal: 14,
  },
  chipSelected: {
    backgroundColor: authColors.pinkChipBg,
    borderColor: authColors.pinkChipBorder,
  },
  chipUnselected: {
    backgroundColor: '#FEFAF9',
    borderColor: authColors.border,
  },
  chipText: {
    fontFamily: fonts.medium,
    fontSize: 10,
  },
  chipTextSelected: {
    color: authColors.pink,
  },
  chipTextUnselected: {
    color: authColors.gray,
  },
  filterButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    height: 28,
    borderRadius: 8,
    borderWidth: 0.8,
    borderColor: authColors.border,
    backgroundColor: authColors.white,
    marginTop: 14,
  },
  filterIconExpanded: {
    transform: [{ rotate: '180deg' }],
  },
  filterButtonText: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.gray,
  },

  // ── 결과 목록 ────────────────────────────────────────────────
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 24,
  },
  emptyMessage: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 24,
    lineHeight: 20,
  },
  section: {
    marginTop: 24,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  sectionHeaderText: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.grayDark,
    letterSpacing: -0.15,
  },
  sectionSubtitle: {
    fontFamily: fonts.light,
    fontSize: 12,
    color: authColors.gray,
    marginTop: 4,
  },
  sectionBox: {
    marginTop: 12,
    backgroundColor: authColors.white,
    borderRadius: 16,
    borderWidth: 0.7,
    borderColor: authColors.border,
    overflow: 'hidden',
  },
  moreButton: {
    marginTop: 10,
    alignItems: 'center',
  },
  moreButtonText: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.gray,
    textDecorationLine: 'underline',
  },
  foodRow: {
    padding: 14,
  },
  foodRowDivider: {
    borderBottomWidth: 0.7,
    borderBottomColor: authColors.border,
  },
  foodRowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  foodRowName: {
    fontFamily: fonts.semiBold,
    fontSize: 14,
    color: authColors.brown,
    flex: 1,
  },
  foodRowCategory: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 2,
  },
  statusBadge: {
    borderRadius: 100,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  statusBadgeText: {
    fontFamily: fonts.medium,
    fontSize: 11,
  },
  possibleBadge: {
    backgroundColor: '#FFF5F3',
  },
  possibleBadgeText: {
    color: authColors.pink,
  },
  cautionBadge: {
    backgroundColor: '#EFEAE9',
  },
  cautionBadgeText: {
    color: authColors.gray,
  },
  avoidBadge: {
    backgroundColor: '#FFF0D6',
  },
  avoidBadgeText: {
    color: '#A86B00',
  },
  foodRowReason: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
    marginTop: 6,
    lineHeight: 18,
  },
  foodRowNutrients: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 8,
  },
  alternativeBox: {
    marginTop: 8,
    backgroundColor: '#FEFAF9',
    borderRadius: 10,
    padding: 10,
  },
  alternativeLabel: {
    fontFamily: fonts.regular,
    fontSize: 10,
    color: authColors.gray,
  },
  alternativeName: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.pink,
    marginTop: 2,
  },

  // ── 영양소 기준 설명 바텀시트 ──────────────────────────────────
  infoSheet: {
    backgroundColor: authColors.white,
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    paddingTop: 24,
    paddingHorizontal: 19,
    paddingBottom: 24,
  },
  infoSheetTitle: {
    fontFamily: fonts.semiBold,
    fontSize: 16,
    color: authColors.grayDark,
    marginBottom: 12,
  },
  infoSheetList: {
    gap: 8,
  },
  infoSheetBody: {
    fontFamily: fonts.regular,
    fontSize: 13,
    lineHeight: 20,
    color: authColors.grayDark,
  },
  infoSheetCloseText: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.pink,
    textAlign: 'center',
    marginTop: 20,
    textDecorationLine: 'underline',
  },
});
