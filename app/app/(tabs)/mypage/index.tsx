import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import NextIcon from '@/assets/images/common/next.svg';
import CrownIcon from '@/assets/images/mypage/crown.svg';
import MilkIcon from '@/assets/images/mypage/milk.svg';
import CalendarIcon from '@/assets/images/mypage/mypage_calendar.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { useIntake } from '@/context/intake-context';
import { getPremiumStatus } from '@/lib/api-client';

const CARD_GRADIENT_COLORS = ['#fef4f3', '#fff8f8', '#fff2f1'] as const;
const CARD_GRADIENT_LOCATIONS = [0, 0.68755, 1] as const;
const CARD_GRADIENT_START = { x: 1, y: 0 };
const CARD_GRADIENT_END = { x: 0, y: 0 };

function MenuRow({
  icon,
  title,
  subtitle,
  onPress,
  chevron = true,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  onPress: () => void;
  chevron?: boolean;
}) {
  return (
    <Pressable style={styles.menuRow} onPress={onPress}>
      <View style={styles.menuIconCircle}>{icon}</View>
      <View style={styles.menuTextArea}>
        <Text style={styles.menuTitle}>{title}</Text>
        {subtitle && <Text style={styles.menuSubtitle}>{subtitle}</Text>}
      </View>
      {chevron && <NextIcon width={16} height={16} />}
    </Pressable>
  );
}

export default function MyPageScreen() {
  const insets = useSafeAreaInsets();
  const { user, logout } = useAuth();
  const { intake, refresh } = useIntake();
  const [isPremium, setIsPremium] = useState(false);

  const loadPremiumStatus = useCallback(() => {
    if (!user?.user_id) return;
    getPremiumStatus(user.user_id)
      .then((res) => setIsPremium(res.is_premium))
      .catch((err) => console.warn('[mypage] failed to load premium status', err));
  }, [user?.user_id]);

  useEffect(() => {
    loadPremiumStatus();
  }, [loadPremiumStatus]);

  useFocusEffect(
    useCallback(() => {
      refresh();
      loadPremiumStatus();
    }, [refresh, loadPremiumStatus])
  );

  const handleLogout = () => {
    logout();
    router.replace('/(auth)/intro');
  };

  const allergyList = user?.allergy_info
    ? user.allergy_info
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    : [];

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 20 }]}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>마이 페이지</Text>
      </View>

      <LinearGradient
        colors={CARD_GRADIENT_COLORS}
        locations={CARD_GRADIENT_LOCATIONS}
        start={CARD_GRADIENT_START}
        end={CARD_GRADIENT_END}
        style={styles.banner}>
        <View style={styles.bannerGreetingRow}>
          <Text style={styles.bannerGreeting}>{user?.nickname}님👶🏻</Text>
          {isPremium && <CrownIcon width={18} height={18} style={styles.bannerCrown} />}
        </View>
        {intake && (
          <Text style={styles.bannerWeek}>
            {intake.pregnancy_week}주 {intake.pregnancy_day}일
            {intake.days_until_due != null ? ` · 예정일 D-${intake.days_until_due}` : ''}
          </Text>
        )}
      </LinearGradient>

      <Text style={styles.sectionLabel}>내 정보</Text>
      <View style={styles.card}>
        <MenuRow
          icon={<CalendarIcon width={24} height={24} />}
          title="정보 수정"
          subtitle="임신 주차 및 예정일 수정"
          onPress={() => router.push('/(tabs)/mypage/edit-profile')}
        />
        <View style={styles.menuDivider} />
        <MenuRow
          icon={<MilkIcon width={24} height={24} />}
          title="알레르기 정보"
          subtitle={allergyList.length > 0 ? allergyList.join(', ') : '설정된 알레르기 없음'}
          onPress={() => router.push('/(tabs)/mypage/edit-allergy')}
        />
      </View>

      <LinearGradient
        colors={CARD_GRADIENT_COLORS}
        locations={CARD_GRADIENT_LOCATIONS}
        start={CARD_GRADIENT_START}
        end={CARD_GRADIENT_END}
        style={styles.premiumCard}>
        <Image
          source={require('@/assets/images/premium/premium.png')}
          style={styles.premiumIllustration}
          resizeMode="contain"
        />
        <View style={styles.premiumTitleRow}>
          <Text style={styles.premiumTitle}>Premium</Text>
          <CrownIcon width={18} height={18} />
        </View>
        <View style={styles.premiumFeatures}>
          <View style={styles.premiumFeatureRow}>
            <View style={styles.premiumFeatureIcon}>
              <Ionicons name="sparkles-outline" size={14} color="#E8536B" />
            </View>
            <View>
              <Text style={styles.premiumFeatureTitle}>AI 성분 분석</Text>
              <Text style={styles.premiumFeatureSubtitle}>식품 성분을 분석해드려요</Text>
            </View>
          </View>
          <View style={styles.premiumFeatureRow}>
            <View style={styles.premiumFeatureIcon}>
              <Ionicons name="bar-chart-outline" size={14} color="#E8536B" />
            </View>
            <View>
              <Text style={styles.premiumFeatureTitle}>주간 리포트</Text>
              <Text style={styles.premiumFeatureSubtitle}>섭취 리포트를 제공해요</Text>
            </View>
          </View>
        </View>
        <Pressable
          style={styles.premiumCta}
          onPress={() => router.push('/(tabs)/mypage/premium-payment')}>
          <Text style={styles.premiumCtaText}>프리미엄 시작하기</Text>
          <Ionicons name="chevron-forward" size={13} color={authColors.pink} />
        </Pressable>
      </LinearGradient>

      <Text style={styles.sectionLabel}>기타</Text>
      <View style={styles.card}>
        <MenuRow
          icon={<Ionicons name="mail-outline" size={22} color={authColors.pink} />}
          title="문의하기"
          onPress={() => router.push('/(tabs)/mypage/contact')}
        />
        <View style={styles.menuDivider} />
        <MenuRow
          icon={<Ionicons name="document-text-outline" size={22} color={authColors.pink} />}
          title="개인정보 처리방침"
          onPress={() => Alert.alert('준비중입니다', '빠른 시일 내에 준비하겠습니다.')}
        />
        <View style={styles.menuDivider} />
        <MenuRow
          icon={<Ionicons name="log-out-outline" size={22} color={authColors.pink} />}
          title="로그아웃"
          onPress={handleLogout}
          chevron={false}
        />
      </View>
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
  header: {
    flexDirection: 'column',
    alignItems: 'flex-start',
  },
  headerTitle: {
    fontSize: 25,
    fontWeight: '500',
    color: '#000000',
  },
  sectionLabel: {
    fontFamily: fonts.regular,
    fontSize: 14,
    color: authColors.brown,
    marginTop: 20,
    marginBottom: 8,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 15,
    paddingHorizontal: 20,
    borderWidth: 1,
    borderColor: authColors.border,
  },
  banner: {
    borderRadius: 15,
    padding: 20,
    marginTop: 20,
    borderWidth: 1,
    borderColor: authColors.border,
  },
  bannerGreetingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  bannerGreeting: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 20,
    color: authColors.brown,
  },
  bannerCrown: {
    marginTop: -2,
  },
  bannerWeek: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 15,
    color: authColors.brown,
    marginTop: 6,
  },
  menuDivider: {
    height: 1,
    backgroundColor: authColors.border,
  },
  menuRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 18,
  },
  menuIconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  menuTextArea: {
    flex: 1,
  },
  menuTitle: {
    fontFamily: fonts.medium,
    fontSize: 16,
    color: authColors.brown,
  },
  menuSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    marginTop: 2,
  },
  premiumCard: {
    borderRadius: 15,
    marginTop: 20,
    padding: 20,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: authColors.border,
  },
  premiumIllustration: {
    position: 'absolute',
    right: 20,
    bottom: -6,
    width: 130,
    height: 130,
    opacity: 0.55,
  },
  premiumTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  premiumTitle: {
    fontWeight: 'bold',
    fontSize: 20,
    color: '#ff8f9b',
  },
  premiumFeatures: {
    marginTop: 12,
    maxWidth: '68%',
    gap: 10,
  },
  premiumFeatureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  premiumFeatureIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  premiumFeatureTitle: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: '#A88770',
  },
  premiumFeatureSubtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    color: '#848484',
    marginTop: 1,
  },
  premiumCta: {
    marginTop: 16,
    alignSelf: 'flex-start',
    width: 173,
    height: 27,
    backgroundColor: '#FFF0F0',
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 15,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  premiumCtaText: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 13,
    color: authColors.pink,
  },
});
