import { useIsFocused } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import CautionIcon from '@/assets/images/scan/caution.svg';
import SunIcon from '@/assets/images/scan/sun.svg'; // ⚠️ 아직 없는 에셋 — 파일 추가 전까지 번들 실패
import OcrScanIcon from '@/assets/images/common/ocr_scan.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { scanNutritionLabel } from '@/lib/api-client';

// #FFF5F3: 팔레트 토큰이 없는 Figma 원본값(가장 가까운 authColors.pinkLight #FFF0F0과는
// 다른 색). 디자인에서 승인된 정확한 값이라 로컬 상수로 둔다.
const CAUTION_BOX_BG = '#FFF5F3';

export default function FoodEntryOcrGuideScreen() {
  const insets = useSafeAreaInsets();
  const { width: windowWidth } = useWindowDimensions();
  const isFocused = useIsFocused();
  const { user } = useAuth();
  const { date } = useLocalSearchParams<{ date: string }>();
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const [scanning, setScanning] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const exampleImageWidth = Math.min(Math.max(windowWidth - 102, 0), 456);
  const exampleImageHeight = exampleImageWidth * (1086 / 1448);
  const cameraHeight = exampleImageWidth * (4 / 3);
  const animatedCameraHeight = useSharedValue(exampleImageHeight);
  const animatedShutterHeight = useSharedValue(0);

  const cameraAnimatedStyle = useAnimatedStyle(() => ({
    height: animatedCameraHeight.value,
  }));
  const shutterAnimatedStyle = useAnimatedStyle(() => ({
    height: animatedShutterHeight.value,
    opacity: animatedShutterHeight.value / 76,
  }));

  useEffect(() => {
    const timing = { duration: 450, easing: Easing.inOut(Easing.ease) };
    animatedCameraHeight.value = withTiming(
      scanning ? cameraHeight : exampleImageHeight,
      timing,
    );
    animatedShutterHeight.value = withTiming(scanning ? 76 : 0, timing);
  }, [animatedCameraHeight, animatedShutterHeight, cameraHeight, exampleImageHeight, scanning]);

  const startScanning = async () => {
    if (scanning) return;

    const nextPermission = permission?.granted ? permission : await requestPermission();
    if (!nextPermission.granted) return;

    setScanning(true);
  };

  const handleCapture = async () => {
    if (!cameraRef.current || analyzing || !user?.user_id) return;

    setAnalyzing(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({ base64: true, quality: 0.5 });
      if (!photo?.base64) throw new Error('사진을 처리하지 못했어요.');

      const result = await scanNutritionLabel({ image: photo.base64, user_id: user.user_id });
      router.push({
        pathname: '/food-entry-ocr-confirm',
        params: { date, scan_result: JSON.stringify(result) },
      });
    } catch {
      router.replace({ pathname: '/food-entry-ocr-failure', params: { date } });
    } finally {
      setAnalyzing(false);
    }
  };

  const goToManual = () => {
    router.push({ pathname: '/food-entry-manual', params: { date } });
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + 7, paddingBottom: insets.bottom + 40 },
      ]}>
      {/* 헤더: food-entry-search.tsx의 라이트 테마 헤더 패턴(뒤로가기 + 타이틀)을 그대로 재사용.
          서브타이틀은 두 참조 화면 중 유일하게 서브타이틀이 있는 capture 화면의 스타일을
          라이트 배경에 맞게 색만 바꿔 가져왔다. */}
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>OCR 스캔</Text>
      </View>

      <Text style={styles.subtitle}>
        영양성분표를 비추면 임신 주차를 기준으로 안전 정보를 확인해 드려요!
      </Text>

      {/* 흰색 라운드 박스: 예시 이미지 + 그 아래 "스캔 시작하기 >" 링크 */}
      <View style={styles.exampleBox}>
        {scanning ? (
          <Animated.View
            style={[
              styles.cameraPreview,
              { width: exampleImageWidth },
              cameraAnimatedStyle,
            ]}>
            {isFocused && permission?.granted && (
              <CameraView ref={cameraRef} style={StyleSheet.absoluteFillObject} facing="back" />
            )}
            {analyzing && (
              <View style={styles.analyzingOverlay}>
                <ActivityIndicator size="large" color={authColors.white} />
              </View>
            )}
          </Animated.View>
        ) : (
          <Image
            source={require('@/assets/images/scan/ocr_example.png')}
            style={[
              styles.exampleImage,
              { width: exampleImageWidth, height: exampleImageHeight },
            ]}
            resizeMode="contain"
          />
        )}

        {scanning ? (
          <Animated.View style={[styles.shutterArea, shutterAnimatedStyle]}>
            <Pressable
              style={[styles.shutterButton, analyzing && styles.shutterButtonDisabled]}
              onPress={handleCapture}
              disabled={analyzing}
              accessibilityLabel="영양성분표 촬영하기">
              <View style={styles.shutterInner} />
            </Pressable>
          </Animated.View>
        ) : (
          <Pressable onPress={startScanning} hitSlop={8}>
            <Text style={styles.scanStartLink}>스캔 시작하기 {'>'}</Text>
          </Pressable>
        )}
      </View>

      {/* 주의 박스 */}
      <View style={styles.cautionBox}>
        <View style={styles.cautionHeaderRow}>
          <CautionIcon width={16} height={16} />
          <Text style={styles.cautionTitle}>실제 성분표가 있는 상품만 스캔 가능해요!</Text>
        </View>
        <Text style={styles.cautionBody}>
          수제 음식, 성분표가 없는 제품, 흐리거나 손상된 성분표는 인식이 어려울 수 있어요!
        </Text>
      </View>

      {/* 팁 박스 2개 나란히 — 아이콘(좌) + 텍스트(우) 가로 배치, 높이 58 */}
      <View style={styles.tipRow}>
        <View style={styles.tipBox}>
          <SunIcon width={24} height={24} />
          <Text style={[styles.tipText, styles.tipTextSingle]}>밝은 곳에서 촬영해 주세요!</Text>
        </View>
        <View style={styles.tipBox}>
          <OcrScanIcon width={24} height={24} color={authColors.pink} />
          <Text style={[styles.tipText, styles.tipTextMulti]}>성분표가 잘 보이게 찍어주세요!</Text>
        </View>
      </View>

      <Pressable onPress={goToManual} hitSlop={8} style={styles.manualLinkWrap}>
        <Text style={styles.manualLink}>영양성분 직접 입력하기</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  // container/headerRow/prevButton/title: food-entry-search.tsx 헤더 스타일 그대로.
  // (headerRow의 paddingHorizontal:19는 content가 이미 19를 주므로 이중 패딩을 피하려 생략.)
  container: {
    flex: 1,
    backgroundColor: '#FEFAF9',
  },
  content: {
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
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 20,
    color: authColors.brown,
  },
  // capture 화면 서브타이틀 스타일(nanumSquareRound.regular 12) — 라이트 배경이라 색만 변경.
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    color: authColors.grayDark,
    marginTop: 12,
    lineHeight: 18,
  },
  exampleBox: {
    backgroundColor: authColors.white,
    borderWidth: 1,
    borderColor: authColors.border, // #ECDEDD
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingTop: 28,
    paddingBottom: 20,
    marginTop: 16,
    alignItems: 'center',
    overflow: 'hidden',
  },
  exampleImage: {
    borderRadius: 12,
  },
  cameraPreview: {
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#1A1A1A',
  },
  analyzingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  scanStartLink: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    color: authColors.pink,
    textDecorationLine: 'underline',
    textAlign: 'center',
    marginTop: 14,
  },
  shutterArea: {
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterButton: {
    width: 64,
    height: 64,
    borderRadius: 32,
    borderWidth: 4,
    borderColor: authColors.pink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterButtonDisabled: {
    opacity: 0.5,
  },
  shutterInner: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: authColors.pink,
  },
  cautionBox: {
    backgroundColor: CAUTION_BOX_BG, // #FFF5F3 (팔레트 외 값)
    borderWidth: 1,
    borderColor: authColors.border, // #ECDEDD
    borderRadius: 15,
    padding: 14,
    marginTop: 16,
  },
  cautionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  cautionTitle: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    color: authColors.pink,
    flex: 1,
  },
  cautionBody: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    color: authColors.grayDark, // #4A4A4A
    marginTop: 8,
    lineHeight: 18,
  },
  tipRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 12,
  },
  tipBox: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    height: 58,
    backgroundColor: authColors.white,
    borderWidth: 1,
    borderColor: authColors.border, // #ECDEDD
    borderRadius: 11,
    paddingHorizontal: 12,
  },
  // Inter는 이 프로젝트에 토큰화되어 있지 않아 fonts.regular(Pretendard-Regular)로 대체.
  tipText: {
    flex: 1,
    fontFamily: fonts.regular,
    color: authColors.grayDark, // #4A4A4A
  },
  tipTextSingle: {
    fontSize: 10,
  },
  tipTextMulti: {
    fontSize: 9.5,
  },
  manualLinkWrap: {
    marginTop: 24,
    alignItems: 'center',
  },
  manualLink: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    color: authColors.pink,
    textDecorationLine: 'underline',
    textAlign: 'center',
  },
});
