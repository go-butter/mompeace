import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import ReportIllustration from '@/assets/images/home/report.svg';
import CaffeineIcon from '@/assets/images/foodDiary/caffeine.svg';
import SodiumIcon from '@/assets/images/foodDiary/sodium.svg';
import SugarIcon from '@/assets/images/foodDiary/sugar.svg';
import { authColors } from '@/components/auth/colors';
import AiSummaryCard from '@/components/premium-report/AiSummaryCard';
import IntakeChart from '@/components/premium-report/IntakeChart';
import MetricCard from '@/components/premium-report/MetricCard';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  getPremiumReport,
  getPremiumStatus,
  PremiumReportResponse,
} from '@/lib/api-client';

type Period = 'daily' | 'weekly';

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function getCardData(report: PremiumReportResponse) {
  if (report.period === 'daily') {
    return {
      caffeine: { value: report.totals.caffeine_mg, limit: report.limits.caffeine_mg },
      sugar: { value: report.totals.sugar_g, limit: report.limits.sugar_g },
      sodium: { value: report.totals.sodium_mg, limit: report.limits.sodium_mg },
    };
  }
  return {
    caffeine: { value: report.daily_average.caffeine_mg, limit: report.limits.daily_caffeine_mg },
    sugar: { value: report.daily_average.sugar_g, limit: report.limits.daily_sugar_g },
    sodium: { value: report.daily_average.sodium_mg, limit: report.limits.daily_sodium_mg },
  };
}

export default function PremiumReportScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [isPremium, setIsPremium] = useState<boolean | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [period, setPeriod] = useState<Period>('daily');
  const [date] = useState(() => formatDate(new Date()));
  const [report, setReport] = useState<PremiumReportResponse | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.user_id) return;
    getPremiumStatus(user.user_id)
      .then((res) => setIsPremium(res.is_premium))
      .catch((err) => setStatusError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setStatusLoading(false));
  }, [user?.user_id]);

  useEffect(() => {
    if (!user?.user_id || isPremium !== true) return;
    setReportLoading(true);
    setReportError(null);
    getPremiumReport(user.user_id, period, date)
      .then(setReport)
      .catch((err) => setReportError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setReportLoading(false));
  }, [user?.user_id, isPremium, period, date]);

  const handleCtaPress = () => {
    Alert.alert('알림', '추후 제공될 기능입니다.');
  };

  const cardData = report ? getCardData(report) : null;
  const comparison = report && report.period === 'weekly' ? report.comparison : null;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7 }]}>
      <ScrollView
        style={styles.screenScroll}
        contentContainerStyle={[styles.screenContent, { paddingBottom: insets.bottom + 32 }]}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
            <PrevIcon width={15} height={15} />
          </Pressable>
          <Text style={styles.title}>프리미엄 리포트 👑</Text>
        </View>
        <Text style={styles.headerSubtitle}>카페인, 당류, 나트륨 섭취 패턴을 자세히 확인해 보세요</Text>

        {statusLoading ? (
          <ActivityIndicator size="small" color={authColors.pink} style={styles.centerSpinner} />
        ) : statusError ? (
          <Text style={styles.errorText}>{statusError}</Text>
        ) : !isPremium ? (
          <View style={styles.upsellCard}>
            <Text style={styles.upsellTitle}>프리미엄 회원 전용 기능이에요</Text>
            <Text style={styles.upsellBody}>
              일간·주간 섭취 흐름을 한눈에 보는{'\n'}프리미엄 리포트를 이용해 보세요.
            </Text>
          </View>
        ) : (
          <>
            {report && (
              <View style={styles.bannerCard}>
                <LinearGradient
                  colors={['#FEF6F6', '#FEEBEA']}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 0, y: 1 }}
                  style={StyleSheet.absoluteFillObject}
                />
                <View style={styles.bannerTextGroup}>
                  <Text style={styles.bannerWeek}>♥ {report.summary_card.title}</Text>
                  <Text style={styles.bannerSubtitle}>{report.summary_card.subtitle}</Text>
                  <Text style={styles.bannerDateRange}>{report.summary_card.date_range}</Text>
                </View>
                <ReportIllustration width={56} height={56} />
              </View>
            )}

            <View style={styles.toggleRow}>
              <Pressable
                style={[styles.toggleButton, period === 'daily' && styles.toggleButtonActive]}
                onPress={() => setPeriod('daily')}>
                <Text style={[styles.toggleText, period === 'daily' && styles.toggleTextActive]}>일간</Text>
              </Pressable>
              <Pressable
                style={[styles.toggleButton, period === 'weekly' && styles.toggleButtonActive]}
                onPress={() => setPeriod('weekly')}>
                <Text style={[styles.toggleText, period === 'weekly' && styles.toggleTextActive]}>주간</Text>
              </Pressable>
            </View>

            {reportLoading || !report || !cardData ? (
              <ActivityIndicator size="small" color={authColors.pink} style={styles.centerSpinner} />
            ) : reportError ? (
              <Text style={styles.errorText}>{reportError}</Text>
            ) : (
              <>
                <View style={styles.cardStack}>
                  <MetricCard
                    nutrient="caffeine"
                    label="카페인"
                    Icon={CaffeineIcon}
                    value={cardData.caffeine.value}
                    unit="mg"
                    limit={cardData.caffeine.limit}
                    pct={report.percentages.caffeine}
                    status={report.status.caffeine_status}
                    comparisonPct={comparison ? comparison.caffeine_vs_previous_pct : undefined}
                  />
                  <MetricCard
                    nutrient="sugar"
                    label="당류"
                    Icon={SugarIcon}
                    value={cardData.sugar.value}
                    unit="g"
                    limit={cardData.sugar.limit}
                    pct={report.percentages.sugar}
                    status={report.status.sugar_status}
                    comparisonPct={comparison ? comparison.sugar_vs_previous_pct : undefined}
                  />
                  <MetricCard
                    nutrient="sodium"
                    label="나트륨"
                    Icon={SodiumIcon}
                    value={cardData.sodium.value}
                    unit="mg"
                    limit={cardData.sodium.limit}
                    pct={report.percentages.sodium}
                    status={report.status.sodium_status}
                    comparisonPct={comparison ? comparison.sodium_vs_previous_pct : undefined}
                  />
                </View>

                <View style={styles.chartCard}>
                  <Text style={styles.chartTitle}>{report.chart.title}</Text>
                  <IntakeChart items={report.chart.items} />
                </View>

                <AiSummaryCard summary={report.ai_summary} />

                <Pressable style={styles.ctaButton} onPress={handleCtaPress}>
                  <Text style={styles.ctaButtonText}>{period === 'daily' ? '기록 저장' : '리포트 저장하기'}</Text>
                </Pressable>
              </>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FEFAF9',
  },
  screenScroll: {
    flex: 1,
  },
  screenContent: {
    paddingHorizontal: 19,
    gap: 14,
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
  headerSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
  },
  centerSpinner: {
    marginTop: 40,
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 24,
  },
  upsellCard: {
    backgroundColor: authColors.white,
    borderRadius: 25,
    padding: 24,
    marginTop: 8,
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 4,
    alignItems: 'center',
  },
  upsellTitle: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.brown,
    textAlign: 'center',
  },
  upsellBody: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 20,
  },
  bannerCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: 25,
    padding: 20,
    overflow: 'hidden',
  },
  bannerTextGroup: {
    flex: 1,
    gap: 4,
  },
  bannerWeek: {
    fontFamily: fonts.bold,
    fontSize: 18,
    color: authColors.pink,
  },
  bannerSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.brown,
  },
  bannerDateRange: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
    marginTop: 4,
  },
  toggleRow: {
    flexDirection: 'row',
    gap: 10,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'transparent',
    backgroundColor: '#F0F0F0',
    alignItems: 'center',
  },
  toggleButtonActive: {
    backgroundColor: authColors.white,
    borderColor: authColors.pink,
  },
  toggleText: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: authColors.gray,
  },
  toggleTextActive: {
    color: authColors.pink,
  },
  cardStack: {
    gap: 12,
  },
  chartCard: {
    backgroundColor: authColors.white,
    borderRadius: 20,
    padding: 18,
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 4,
  },
  chartTitle: {
    fontFamily: fonts.medium,
    fontSize: 15,
    color: '#000000',
  },
  ctaButton: {
    backgroundColor: authColors.pink,
    borderRadius: 30,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 4,
  },
  ctaButtonText: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.white,
  },
});
