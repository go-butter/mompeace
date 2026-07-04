import { LinearGradient } from 'expo-linear-gradient';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import CrownIcon from '@/assets/images/mypage/crown.svg';
import MilkIcon from '@/assets/images/mypage/milk.svg';
import CalendarIcon from '@/assets/images/mypage/mypage_calendar.svg';
import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
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
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  onPress: () => void;
}) {
  return (
    <Pressable style={styles.menuRow} onPress={onPress}>
      <View style={styles.menuIconCircle}>{icon}</View>
      <View style={styles.menuTextArea}>
        <Text style={styles.menuTitle}>{title}</Text>
        <Text style={styles.menuSubtitle}>{subtitle}</Text>
      </View>
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
      .catch(() => {});
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
        <Image
          source={require('@/assets/images/common/logo_nottext.png')}
          style={styles.logo}
          resizeMode="contain"
        />
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
          {isPremium && <CrownIcon width={16} height={16} style={styles.bannerCrown} />}
        </View>
        {intake && (
          <Text style={styles.bannerWeek}>
            {intake.pregnancy_week}주 {intake.pregnancy_day}일
            {intake.days_until_due != null ? ` · 예정일 D-${intake.days_until_due}` : ''}
          </Text>
        )}
      </LinearGradient>

      <View style={styles.menuCard}>
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
        <View style={styles.premiumTitleRow}>
          <Text style={styles.premiumBadge}>Premium</Text>
          {isPremium && <CrownIcon width={18} height={18} />}
        </View>
        <Text style={styles.premiumBody}>
          AI가 분석한 일간·주간 섭취 리포트를{'\n'}프리미엄에서 확인해 보세요.
        </Text>
        <Pressable
          style={styles.premiumCta}
          onPress={() => router.push('/(tabs)/mypage/premium-payment')}>
          <Text style={styles.premiumCtaText}>프리미엄 구독하기</Text>
        </Pressable>
      </LinearGradient>

      <Pressable onPress={handleLogout} style={styles.logoutLink}>
        <Text style={styles.logoutText}>로그아웃 하기</Text>
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
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  logo: {
    width: 28,
    height: 28,
  },
  headerTitle: {
    fontFamily: fonts.bold,
    fontSize: 20,
    color: authColors.brown,
  },
  banner: {
    borderRadius: 20,
    padding: 20,
    marginTop: 20,
  },
  bannerGreetingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  bannerGreeting: {
    fontFamily: fonts.semiBold,
    fontSize: 17,
    color: authColors.brown,
  },
  bannerCrown: {
    marginTop: -2,
  },
  bannerWeek: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: authColors.brown,
    marginTop: 6,
  },
  menuCard: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    marginTop: 20,
    paddingHorizontal: 20,
    shadowColor: authColors.pink,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 6,
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
  menuDivider: {
    height: 1,
    backgroundColor: authColors.border,
  },
  premiumCard: {
    borderRadius: 15,
    marginTop: 20,
    padding: 20,
  },
  premiumTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  premiumBadge: {
    fontFamily: fonts.bold,
    fontSize: 20,
    color: '#ff8f9b',
  },
  premiumBody: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: '#848484',
    marginTop: 12,
    lineHeight: 18,
  },
  premiumCta: {
    marginTop: 16,
    backgroundColor: '#FFF0F0',
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: 'center',
  },
  premiumCtaText: {
    fontFamily: fonts.bold,
    fontSize: 15,
    color: authColors.pink,
  },
  logoutLink: {
    alignItems: 'center',
    marginTop: 24,
  },
  logoutText: {
    fontFamily: fonts.regular,
    fontSize: 14,
    color: authColors.gray,
    textDecorationLine: 'underline',
  },
});
