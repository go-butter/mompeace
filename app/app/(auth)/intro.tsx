import { router } from 'expo-router';
import { useEffect } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
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
    title: '영양성분표 스캔',
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

// Splash hands off here at full opacity, centered; expo-router replaces the
// route with `animation: 'none'` (see (auth)/_layout.tsx) so there's no nav
// transition to hide a mismatch. The logo starts exactly where the splash's
// centered logo sat and rises from there, computed from window height so it
// lines up on any device.
const LOGO_SIZE = 161;
const CONTENT_PADDING_TOP = 60;
const LOGO_RISE_DURATION = 1300;
const TEXT_FADE_DURATION = 900;
const SUBTITLE_DELAY = 150;
const CARD_FADE_DURATION = 700;
const CARD_STAGGER = 350;
const TEXT_RISE_OFFSET = 16;
const FADE_EASING = Easing.inOut(Easing.cubic);

export default function IntroScreen() {
  const { height: windowHeight } = useWindowDimensions();
  // Splash centers the logo at (windowHeight - LOGO_SIZE) / 2; intro's resting
  // position (post-animation) is CONTENT_PADDING_TOP. The gap between them is
  // the initial translateY offset the logo rises through.
  const logoStartOffset = (windowHeight - LOGO_SIZE) / 2 - CONTENT_PADDING_TOP;

  const logoTranslateY = useSharedValue(logoStartOffset);
  const logoOpacity = useSharedValue(1);

  const titleOpacity = useSharedValue(0);
  const titleTranslateY = useSharedValue(TEXT_RISE_OFFSET);
  const subtitleOpacity = useSharedValue(0);
  const subtitleTranslateY = useSharedValue(TEXT_RISE_OFFSET);

  const card0Opacity = useSharedValue(0);
  const card0TranslateY = useSharedValue(TEXT_RISE_OFFSET);
  const card1Opacity = useSharedValue(0);
  const card1TranslateY = useSharedValue(TEXT_RISE_OFFSET);
  const card2Opacity = useSharedValue(0);
  const card2TranslateY = useSharedValue(TEXT_RISE_OFFSET);

  useEffect(() => {
    // Chain each stage off the previous one's actual `finished` callback rather
    // than hardcoded absolute delays, so the text can never appear before the
    // logo has genuinely settled.
    logoTranslateY.value = withTiming(
      0,
      { duration: LOGO_RISE_DURATION, easing: FADE_EASING },
      (finished) => {
        'worklet';
        if (!finished) return;

        titleOpacity.value = withTiming(
          1,
          { duration: TEXT_FADE_DURATION, easing: FADE_EASING },
          (titleFinished) => {
            'worklet';
            if (!titleFinished) return;

            card0Opacity.value = withTiming(1, { duration: CARD_FADE_DURATION, easing: FADE_EASING });
            card0TranslateY.value = withTiming(0, { duration: CARD_FADE_DURATION, easing: FADE_EASING });
            card1Opacity.value = withDelay(
              CARD_STAGGER,
              withTiming(1, { duration: CARD_FADE_DURATION, easing: FADE_EASING }),
            );
            card1TranslateY.value = withDelay(
              CARD_STAGGER,
              withTiming(0, { duration: CARD_FADE_DURATION, easing: FADE_EASING }),
            );
            card2Opacity.value = withDelay(
              CARD_STAGGER * 2,
              withTiming(1, { duration: CARD_FADE_DURATION, easing: FADE_EASING }),
            );
            card2TranslateY.value = withDelay(
              CARD_STAGGER * 2,
              withTiming(0, { duration: CARD_FADE_DURATION, easing: FADE_EASING }),
            );
          },
        );
        titleTranslateY.value = withTiming(0, { duration: TEXT_FADE_DURATION, easing: FADE_EASING });

        subtitleOpacity.value = withDelay(
          SUBTITLE_DELAY,
          withTiming(1, { duration: TEXT_FADE_DURATION, easing: FADE_EASING }),
        );
        subtitleTranslateY.value = withDelay(
          SUBTITLE_DELAY,
          withTiming(0, { duration: TEXT_FADE_DURATION, easing: FADE_EASING }),
        );
      },
    );
    logoOpacity.value = withTiming(0.4, { duration: LOGO_RISE_DURATION, easing: FADE_EASING });
  }, [
    logoTranslateY,
    logoOpacity,
    titleOpacity,
    titleTranslateY,
    subtitleOpacity,
    subtitleTranslateY,
    card0Opacity,
    card0TranslateY,
    card1Opacity,
    card1TranslateY,
    card2Opacity,
    card2TranslateY,
  ]);

  const logoAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: logoTranslateY.value }],
    opacity: logoOpacity.value,
  }));
  const titleAnimatedStyle = useAnimatedStyle(() => ({
    opacity: titleOpacity.value,
    transform: [{ translateY: titleTranslateY.value }],
  }));
  const subtitleAnimatedStyle = useAnimatedStyle(() => ({
    opacity: subtitleOpacity.value,
    transform: [{ translateY: subtitleTranslateY.value }],
  }));
  const card0AnimatedStyle = useAnimatedStyle(() => ({
    opacity: card0Opacity.value,
    transform: [{ translateY: card0TranslateY.value }],
  }));
  const card1AnimatedStyle = useAnimatedStyle(() => ({
    opacity: card1Opacity.value,
    transform: [{ translateY: card1TranslateY.value }],
  }));
  const card2AnimatedStyle = useAnimatedStyle(() => ({
    opacity: card2Opacity.value,
    transform: [{ translateY: card2TranslateY.value }],
  }));
  const cardAnimatedStyles = [card0AnimatedStyle, card1AnimatedStyle, card2AnimatedStyle];

  return (
    <View style={styles.container}>
      <GradientBackground />
      <ScrollView contentContainerStyle={styles.content}>
        <Animated.Image
          source={require('@/assets/images/common/logo_default.png')}
          style={[styles.logo, logoAnimatedStyle]}
          resizeMode="contain"
        />

        <Animated.View style={titleAnimatedStyle}>
          <Text style={styles.title}>
            <Text style={{ color: authColors.brown }}>안전한 선택을, </Text>
            <Text style={{ color: authColors.pink }}>맘편하게</Text>
          </Text>
        </Animated.View>
        <Animated.View style={subtitleAnimatedStyle}>
          <Text style={styles.subtitle}>
            임신 중 먹거리 걱정을{'\n'}맘편하게가 함께 해결해 드려요
          </Text>
        </Animated.View>

        <View style={styles.cards}>
          {FEATURES.map(({ key, iconBg, Icon, title, subtitle }, index) => (
            <Animated.View
              key={key}
              style={[styles.card, cardAnimatedStyles[index]]}>
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
    paddingTop: CONTENT_PADDING_TOP,
    paddingHorizontal: 24,
  },
  logo: {
    width: LOGO_SIZE,
    height: LOGO_SIZE,
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
