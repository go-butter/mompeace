import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import CoffeeIcon from '@/assets/images/common/coffee.svg';
import SugarIcon from '@/assets/images/common/sugar.svg';
import SaltIcon from '@/assets/images/common/salt.svg';
import ShieldIcon from '@/assets/images/scan/shield.svg';
import { authColors } from '@/components/auth/colors';
import {
  allergyToVisualStatus,
  scanBannerColors,
  scanBannerLabel,
  scanStatusColors,
  toVisualStatus,
  VisualStatus,
} from '@/components/scan/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  BarcodeFoodResponse,
  createFoodLog,
  getFoodByBarcode,
} from '@/lib/api-client';

const STATUS_BADGE: Record<VisualStatus, number> = {
  safe: require('@/assets/images/scan/safe.png'),
  caution: require('@/assets/images/scan/warn.png'),
  avoid: require('@/assets/images/scan/danger.png'),
};

const STATUS_DESCRIPTION: Record<VisualStatus, string> = {
  safe: '해당 제품은 임신 중 섭취에 적합한 제품이에요.',
  caution: '해당 제품은 임신 중 섭취에 주의해야 하는 제품이에요.',
  avoid: '해당 제품은 임산부에게 위험해요',
};

function formatScannedAt(date: Date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const hh = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  return `${yyyy}.${mm}.${dd}. ${hh}:${min}`;
}

function DetailChip({
  icon,
  label,
  value,
  status,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  status: VisualStatus;
}) {
  return (
    <View style={styles.detailChip}>
      {icon}
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
      <Text style={[styles.detailStatus, { color: scanStatusColors[status] }]}>
        {status === 'safe' ? '안전' : status === 'caution' ? '주의' : '확인 필요'}
      </Text>
    </View>
  );
}

export default function BarcodeScanResultScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { barcode } = useLocalSearchParams<{ barcode: string }>();

  const [result, setResult] = useState<BarcodeFoodResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scannedAt] = useState(() => new Date());
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    if (!barcode) return;
    let isMounted = true;
    setLoading(true);
    setError(null);

    getFoodByBarcode(barcode, user?.pregnancy_week ?? 20)
      .then((res) => {
        if (!isMounted) return;
        setResult(res);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [barcode, user?.pregnancy_week]);

  const handleAddToFoodDiary = () => {
    if (!result || !user?.user_id || adding || added) return;
    setAdding(true);
    createFoodLog({
      user_id: user.user_id,
      food_name: result.data.food_name,
      input_type: 'barcode',
      food_id: result.food_id,
      amount: 1,
      unit: '개',
      caffeine_mg: result.risk.details.caffeine.value,
      sugar_g: result.risk.details.sugar.value ?? 0,
      sodium_mg: result.risk.details.sodium.value ?? 0,
      calories_kcal: result.data.calories_kcal ?? 0,
    })
      .then(() => setAdded(true))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      })
      .finally(() => setAdding(false));
  };

  if (loading) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={authColors.pink} />
      </View>
    );
  }

  if (error || !result) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <Text style={styles.errorText}>{error || '결과를 불러오지 못했습니다.'}</Text>
        <Pressable
          style={styles.retryButton}
          onPress={() => router.replace('/(tabs)/scan/scanning')}>
          <Text style={styles.retryButtonText}>다시 스캔하기</Text>
        </Pressable>
      </View>
    );
  }

  const { risk, data } = result;
  const visualStatus = risk.overall_status as VisualStatus;
  const banner = scanBannerColors[visualStatus];
  const caffeineStatus = toVisualStatus(risk.details.caffeine.status);
  const sugarStatus = toVisualStatus(risk.details.sugar.status);
  const sodiumStatus = toVisualStatus(risk.details.sodium.status);
  const allergyStatus = allergyToVisualStatus(risk.details.allergy.status);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 7 }]}>
      <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
        <PrevIcon width={15} height={15} />
      </Pressable>

      <View style={styles.top}>
        <Text style={styles.title}>스캔 결과</Text>
        <Text style={styles.subtitle}>바코드 인식이 완료 되었어요!</Text>
      </View>

      <View style={styles.foodCard}>
        <Text style={styles.foodName}>{data.food_name}</Text>
        <View style={styles.foodMetaRow}>
          <Text style={styles.foodMetaLabel}>스캔 시간</Text>
          <Text style={styles.foodMetaValue}>{formatScannedAt(scannedAt)}</Text>
        </View>
        <View style={styles.foodMetaRow}>
          <Text style={styles.foodMetaLabel}>바코트 번호</Text>
          <Text style={styles.foodMetaValue}>{barcode}</Text>
        </View>
      </View>

      <View
        style={[styles.bannerCard, { backgroundColor: banner.bg, borderColor: banner.border }]}>
        <Image source={STATUS_BADGE[visualStatus]} style={styles.bannerBadge} resizeMode="contain" />
        <Text style={[styles.bannerLabel, { color: banner.title }]}>
          {scanBannerLabel[visualStatus]}
        </Text>
        <View style={styles.bannerDivider} />
        <View style={styles.bannerTextArea}>
          <Text style={styles.bannerTrimester}>{risk.trimester_label} 기준</Text>
          <Text style={[styles.bannerTitle, { color: banner.title }]}>{risk.title}</Text>
          <Text style={styles.bannerSubtitle}>
            {risk.messages[0] || STATUS_DESCRIPTION[visualStatus]}
          </Text>
        </View>
      </View>

      <View style={styles.nutritionCard}>
        <View style={styles.nutritionHeaderRow}>
          <Text style={styles.nutritionTitle}>주요 영양 정보</Text>
          <Text style={styles.nutritionSubtitle}>(1회 제공량 기준)</Text>
        </View>
        <View style={styles.detailRow}>
          <DetailChip
            icon={<CoffeeIcon width={29} height={29} />}
            label="카페인"
            value={
              risk.details.caffeine.value != null
                ? `${risk.details.caffeine.value}${risk.details.caffeine.unit}`
                : '정보 없음'
            }
            status={caffeineStatus}
          />
          <DetailChip
            icon={<SugarIcon width={28} height={28} />}
            label="당류"
            value={`${risk.details.sugar.value}${risk.details.sugar.unit}`}
            status={sugarStatus}
          />
          <DetailChip
            icon={<SaltIcon width={29} height={29} />}
            label="나트륨"
            value={`${risk.details.sodium.value}${risk.details.sodium.unit}`}
            status={sodiumStatus}
          />
          <DetailChip
            icon={<ShieldIcon width={26} height={26} />}
            label="알레르기"
            value={risk.details.allergy.allergens.length > 0 ? risk.details.allergy.allergens.join(', ') + ' 포함' : '없음'}
            status={allergyStatus}
          />
        </View>
      </View>

      <Pressable
        style={[styles.addButton, (adding || added) && styles.addButtonDisabled]}
        onPress={handleAddToFoodDiary}
        disabled={adding || added}>
        <Text style={styles.addButtonText}>{added ? '추가됨' : 'Food Diary에 추가'}</Text>
      </Pressable>

      <Pressable onPress={() => router.replace('/(tabs)/scan/scanning')}>
        <Text style={styles.rescanText}>다시 스캔하기</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FEFAF9',
  },
  content: {
    paddingHorizontal: 19,
    paddingBottom: 40,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FEFAF9',
    paddingHorizontal: 24,
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 14,
    textAlign: 'center',
  },
  retryButton: {
    marginTop: 16,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  retryButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    color: authColors.white,
  },
  prevButton: {
    width: 30,
    height: 29,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 5,
  },
  top: {
    marginTop: 14,
    marginHorizontal: 5,
  },
  title: {
    fontFamily: fonts.medium,
    fontSize: 29,
    color: '#000000',
  },
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 11,
    color: '#4A4A4A',
    marginTop: 8,
    letterSpacing: -0.11,
  },
  foodCard: {
    marginTop: 19,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: authColors.border,
    backgroundColor: '#FFF0F0',
    padding: 18,
  },
  foodName: {
    fontFamily: fonts.bold,
    fontSize: 20,
    color: authColors.pink,
  },
  foodMetaRow: {
    flexDirection: 'row',
    marginTop: 10,
    gap: 14,
  },
  foodMetaLabel: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    color: '#4A4A4A',
    width: 64,
  },
  foodMetaValue: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    color: '#4A4A4A',
  },
  bannerCard: {
    marginTop: 14,
    borderRadius: 17,
    borderWidth: 0.5,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
  },
  bannerBadge: {
    width: 50,
    height: 50,
  },
  bannerLabel: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    width: 50,
    textAlign: 'center',
    marginTop: 4,
  },
  bannerDivider: {
    width: 1,
    height: 60,
    backgroundColor: authColors.border,
    marginHorizontal: 12,
  },
  bannerTextArea: {
    flex: 1,
  },
  bannerTrimester: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: '#4A4A4A',
  },
  bannerTitle: {
    fontFamily: fonts.medium,
    fontSize: 17,
    marginTop: 6,
  },
  bannerSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 9.5,
    color: '#848484',
    marginTop: 6,
  },
  nutritionCard: {
    marginTop: 14,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: authColors.border,
    backgroundColor: authColors.white,
    padding: 16,
  },
  nutritionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  nutritionTitle: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: '#000000',
  },
  nutritionSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 9.5,
    color: '#848484',
  },
  detailRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  detailChip: {
    flex: 1,
    borderWidth: 0.5,
    borderColor: authColors.border,
    backgroundColor: '#FEFAF9',
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    gap: 4,
  },
  detailLabel: {
    fontFamily: fonts.medium,
    fontSize: 11,
    color: '#000000',
    marginTop: 4,
  },
  detailValue: {
    fontFamily: fonts.regular,
    fontSize: 10,
    color: '#000000',
  },
  detailStatus: {
    fontFamily: fonts.semiBold,
    fontSize: 10,
  },
  addButton: {
    marginTop: 18,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addButtonDisabled: {
    opacity: 0.6,
  },
  addButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 16,
    color: authColors.white,
  },
  rescanText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: authColors.pink,
    textAlign: 'center',
    marginTop: 14,
    textDecorationLine: 'underline',
  },
});
