import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import NextIcon from '@/assets/images/common/next.svg';
import CalendarIcon from '@/assets/images/mypage/mypage_calendar.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { useIntake } from '@/context/intake-context';
import { deleteAccount } from '@/lib/api-client';

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
  danger = false,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  onPress: () => void;
  chevron?: boolean;
  danger?: boolean;
}) {
  return (
    <Pressable style={styles.menuRow} onPress={onPress}>
      <View style={styles.menuIconCircle}>{icon}</View>
      <View style={styles.menuTextArea}>
        <Text style={[styles.menuTitle, danger && styles.menuTitleDanger]}>{title}</Text>
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
  const [deletingAccount, setDeletingAccount] = useState(false);

  useFocusEffect(
    useCallback(() => {
      refresh();
    }, [refresh])
  );

  const handleLogout = () => {
    logout();
    router.replace('/(auth)/intro');
  };

  const handleDeleteAccount = () => {
    if (!user?.user_id) return;

    Alert.alert('정말 탈퇴하시겠어요?', '탈퇴하면 모든 기록이 삭제되며 복구할 수 없어요.', [
      { text: '취소', style: 'cancel' },
      {
        text: '탈퇴하기',
        style: 'destructive',
        onPress: async () => {
          setDeletingAccount(true);
          try {
            await deleteAccount(user.user_id);
            logout();
            router.replace('/(auth)/intro');
          } catch (err) {
            Alert.alert('오류', '탈퇴 처리 중 문제가 발생했어요. 다시 시도해 주세요.');
          } finally {
            setDeletingAccount(false);
          }
        },
      },
    ]);
  };

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
          icon={<Ionicons name="nutrition-outline" size={22} color={authColors.pink} />}
          title="영양성분 선택하기"
          subtitle="홈 화면에 표시할 영양소 수정"
          onPress={() => router.push('/(tabs)/mypage/nutrient-preferences')}
        />
      </View>

      <Text style={styles.sectionLabel}>기타</Text>
      <View style={styles.card}>
        <MenuRow
          icon={<Ionicons name="nutrition-outline" size={22} color={authColors.pink} />}
          title="초/중/후기별 제한사항"
          subtitle="현재 시기 기준 1일 영양 기준값"
          onPress={() => router.push('/(tabs)/mypage/nutrition-limits')}
        />
        <View style={styles.menuDivider} />
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
        <View style={styles.menuDivider} />
        <MenuRow
          icon={<Ionicons name="person-remove-outline" size={22} color="#DC2626" />}
          title={deletingAccount ? '탈퇴 처리 중...' : '회원탈퇴'}
          onPress={handleDeleteAccount}
          chevron={false}
          danger
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
  menuTitleDanger: {
    color: '#DC2626',
  },
  menuSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    marginTop: 2,
  },
});
