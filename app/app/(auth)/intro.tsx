import { router } from 'expo-router';
import { useEffect } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import Animated, {
  FadeInDown,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import BulbIcon from '@/assets/images/onboarding/bulb.svg';
import GraphIcon from '@/assets/images/onboarding/graph.svg';
import HeartIcon from '@/assets/images/onboarding/heart.svg';
import { authColors } from '@/components/auth/colors';
import { GradientBackground } from '@/components/auth/gradient-background';
import { fonts } from '@/constants/fonts';

const FEATURES = [
  {
    key: 'scan',
    iconBg: '#FFF0F0',
    Icon: BulbIcon,
    title: '바코드 스캔',
    subtitle: '식품 안전을 간편하게 확인',
  },
  {
    key: 'risk',
    iconBg: '#F3E7F6',
    Icon: GraphIcon,
    title: '성분 위험도',
    subtitle: 'AI가 분석한 성분 위험도 확인',
  },
  {
    key: 'recommend',
    iconBg: '#FEF0E7',
    Icon: HeartIcon,
    title: '대체 음식 추천',
    subtitle: '오늘 먹은 음식을 기반으로 음식 추천',
  },
] as const;

// Splash hands off here at full opacity, centered; Reanimated has no cross-route
// shared-element transition in v4, so we fake the "settle into place" continuity
// by starting the logo lower/opaque and animating it up + fading it on mount.
const LOGO_START_OFFSET = 160;

export default function IntroScreen() {
  const logoTranslateY = useSharedValue(LOGO_START_OFFSET);
  const logoOpacity = useSharedValue(1);

  useEffect(() => {
    logoTranslateY.value = withTiming(0, { duration: 1300 });
    logoOpacity.value = withTiming(0.4, { duration: 1300 });
  }, [logoOpacity, logoTranslateY]);

  const logoAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: logoTranslateY.value }],
    opacity: logoOpacity.value,
  }));

  return (
    <View style={styles.container}>
      <GradientBackground />
      <ScrollView contentContainerStyle={styles.content}>
        <Animated.Image
          source={require('@/assets/images/common/logo_default.png')}
          style={[styles.logo, logoAnimatedStyle]}
          resizeMode="contain"
        />

        <Animated.View entering={FadeInDown.delay(0).duration(900)}>
          <Text style={styles.title}>
            <Text style={{ color: authColors.brown }}>안전한 선택을, </Text>
            <Text style={{ color: authColors.pink }}>맘편하게</Text>
          </Text>
        </Animated.View>
        <Animated.View entering={FadeInDown.delay(350).duration(900)}>
          <Text style={styles.subtitle}>
            임신 중 먹거리 걱정을{'\n'}맘편하게가 함께 해결해 드려요
          </Text>
        </Animated.View>

        <View style={styles.cards}>
          {FEATURES.map(({ key, iconBg, Icon, title, subtitle }, index) => (
            <Animated.View
              key={key}
              entering={FadeInDown.delay(700 + index * 350).duration(900)}
              style={styles.card}>
              <View style={[styles.iconCircle, { backgroundColor: iconBg }]}>
                <Icon width={28} height={28} />
              </View>
              <View style={styles.cardText}>
                <Text style={styles.cardTitle}>{title}</Text>
                <Text style={styles.cardSubtitle}>{subtitle}</Text>
              </View>
            </Animated.View>
          ))}
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <Pressable style={styles.startButton} onPress={() => router.push('/(auth)/register')}>
          <Text style={styles.startButtonText}>시작하기</Text>
        </Pressable>
        <Pressable onPress={() => router.push('/(auth)/login')}>
          <Text style={styles.loginLink}>이미 계정이 있어요</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    alignItems: 'center',
    paddingTop: 60,
    paddingHorizontal: 24,
  },
  logo: {
    width: 161,
    height: 161,
  },
  title: {
    fontSize: 29,
    fontFamily: fonts.bold,
    textAlign: 'center',
    marginTop: 16,
  },
  subtitle: {
    fontSize: 17,
    fontFamily: fonts.regular,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 12,
    lineHeight: 24,
  },
  cards: {
    width: '100%',
    marginTop: 32,
    gap: 12,
  },
  card: {
    width: 331,
    height: 98,
    alignSelf: 'center',
    backgroundColor: authColors.white,
    borderRadius: 24,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    gap: 16,
  },
  iconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardText: {
    flex: 1,
  },
  cardTitle: {
    fontSize: 16,
    fontFamily: fonts.medium,
    color: authColors.brown,
  },
  cardSubtitle: {
    fontSize: 13,
    fontFamily: fonts.regular,
    color: authColors.gray,
    marginTop: 4,
  },
  footer: {
    paddingHorizontal: 24,
    paddingBottom: 32,
    alignItems: 'center',
  },
  startButton: {
    width: '100%',
    backgroundColor: authColors.pink,
    borderRadius: 999,
    paddingVertical: 16,
    alignItems: 'center',
  },
  startButtonText: {
    color: authColors.white,
    fontSize: 17,
    fontFamily: fonts.bold,
  },
  loginLink: {
    color: authColors.gray,
    fontSize: 14,
    fontFamily: fonts.regular,
    marginTop: 16,
    textDecorationLine: 'underline',
  },
});
