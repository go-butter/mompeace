import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import CrownIcon from '@/assets/images/mypage/crown.svg';
import { authColors } from '@/components/auth/colors';
import { PremiumToggle } from '@/components/mypage/premium-toggle';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, cancelPremium, getPremiumStatus, upgradeToPremium } from '@/lib/api-client';

export default function PremiumPaymentScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [isPremium, setIsPremium] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.user_id) return;
    getPremiumStatus(user.user_id)
      .then((res) => setIsPremium(res.is_premium))
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setStatusLoading(false));
  }, [user?.user_id]);

  const performChange = async (next: boolean) => {
    if (!user?.user_id || actionLoading) return;
    setError(null);
    setIsPremium(next);
    setActionLoading(true);
    try {
      if (next) {
        await upgradeToPremium(user.user_id);
      } else {
        await cancelPremium(user.user_id);
      }
    } catch (err) {
      setIsPremium(!next);
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>프리미엄 결제</Text>
      </View>

      <View style={styles.content}>
        <View style={styles.card}>
          <View style={styles.badgeRow}>
            <Text style={styles.badge}>Premium</Text>
            {isPremium && <CrownIcon width={18} height={18} />}
          </View>
          <Text style={styles.body}>
            AI가 분석한 성분 리포트로 더 꼼꼼하게 관리해보세요.{'\n'}일별/주간별 섭취 현황을 한눈에
            확인할 수 있어요.
          </Text>

          {statusLoading ? (
            <ActivityIndicator size="small" color={authColors.pink} style={styles.loader} />
          ) : (
            <View style={styles.toggleRow}>
              <Text style={styles.toggleLabel}>{isPremium ? '구독 중' : '구독하기'}</Text>
              <PremiumToggle value={isPremium} onToggle={() => performChange(!isPremium)} />
            </View>
          )}

          {error && <Text style={styles.errorText}>{error}</Text>}
        </View>

        {isPremium && (
          <Pressable
            onPress={() => performChange(false)}
            style={styles.cancelLink}
            disabled={actionLoading}>
            <Text style={styles.cancelText}>구독 해제</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FEFAF9',
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 19,
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
  content: {
    paddingHorizontal: 24,
    paddingTop: 20,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 20,
    shadowColor: authColors.pink,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.12,
    shadowRadius: 20,
    elevation: 4,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  badge: {
    fontFamily: fonts.bold,
    fontSize: 20,
    color: '#ff8f9b',
  },
  body: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: '#848484',
    marginTop: 12,
    lineHeight: 18,
  },
  loader: {
    marginTop: 20,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 20,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: authColors.border,
  },
  toggleLabel: {
    fontFamily: fonts.medium,
    fontSize: 15,
    color: authColors.brown,
  },
  errorText: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.pink,
    marginTop: 12,
  },
  cancelLink: {
    alignItems: 'center',
    marginTop: 20,
  },
  cancelText: {
    fontFamily: fonts.regular,
    fontSize: 14,
    color: authColors.gray,
    textDecorationLine: 'underline',
  },
});
