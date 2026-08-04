import { CameraView, useCameraPermissions } from 'expo-camera';
import { router, useLocalSearchParams } from 'expo-router';
import { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { scanNutritionLabel } from '@/lib/api-client';

export default function FoodEntryOcrCaptureScreen() {
  const insets = useSafeAreaInsets();
  const { date } = useLocalSearchParams<{ date: string }>();
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const handleCapture = async () => {
    if (!cameraRef.current || analyzing) return;
    setAnalyzing(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({ base64: true, quality: 0.5 });
      if (!photo?.base64) throw new Error('사진을 처리하지 못했어요.');

      const result = await scanNutritionLabel({ image: photo.base64 });

      router.push({
        pathname: '/(tabs)/food-diary/food-entry-ocr-confirm',
        params: {
          date,
          product_name: result.product_name ?? '',
          sugar_g: result.sugar_g != null ? String(result.sugar_g) : '',
          sodium_mg: result.sodium_mg != null ? String(result.sodium_mg) : '',
          scale_method: result.scale_method,
          scale_factor_applied:
            result.scale_factor_applied != null ? String(result.scale_factor_applied) : '',
          basis_amount_value:
            result.basis_amount_value != null ? String(result.basis_amount_value) : '',
          needs_review: String(result.needs_review),
        },
      });
    } catch {
      router.replace({ pathname: '/(tabs)/food-diary/food-entry-ocr-failure', params: { date } });
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>영양성분표 촬영</Text>
      </View>

      <Text style={styles.subtitle}>
        영양정보 표에 맞춰 사각형 안에 담아 촬영해 주세요!
      </Text>

      <View style={styles.cameraWrap}>
        {!permission ? null : !permission.granted ? (
          <View style={styles.permissionPrompt}>
            {permission.canAskAgain ? (
              <>
                <Text style={styles.permissionText}>
                  영양성분표를 촬영하려면 카메라 접근 권한이 필요해요.
                </Text>
                <Pressable style={styles.permissionButton} onPress={requestPermission}>
                  <Text style={styles.permissionButtonText}>카메라 권한 허용하기</Text>
                </Pressable>
              </>
            ) : (
              <Text style={styles.permissionText}>
                카메라 접근이 거부되었어요.{'\n'}기기 설정에서 카메라 권한을 허용해 주세요.
              </Text>
            )}
          </View>
        ) : (
          <>
            <CameraView ref={cameraRef} style={styles.camera} facing="back" />
            <View pointerEvents="none" style={styles.frameOverlay}>
              <View style={styles.frameGuide} />
              <Text style={styles.frameCaption}>영양정보 표 전체가 보이도록 맞춰주세요</Text>
            </View>
            {analyzing && (
              <View style={styles.analyzingOverlay}>
                <ActivityIndicator size="large" color={authColors.white} />
                <Text style={styles.analyzingText}>영양성분표를 분석하고 있어요...</Text>
              </View>
            )}
          </>
        )}
      </View>

      {permission?.granted && (
        <Pressable
          style={[styles.shutterButton, analyzing && styles.shutterButtonDisabled]}
          onPress={handleCapture}
          disabled={analyzing}>
          <View style={styles.shutterInner} />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000000',
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
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 18,
    color: authColors.white,
  },
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    color: authColors.white,
    marginTop: 12,
    marginHorizontal: 19,
  },
  cameraWrap: {
    flex: 1,
    marginTop: 16,
    marginHorizontal: 19,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#1A1A1A',
  },
  camera: {
    flex: 1,
  },
  frameOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  frameGuide: {
    width: '90%',
    height: '55%',
    borderWidth: 2,
    borderColor: authColors.pink,
    borderRadius: 12,
    borderStyle: 'dashed',
  },
  frameCaption: {
    marginTop: 14,
    fontFamily: nanumSquareRound.bold,
    fontSize: 12,
    color: authColors.white,
    textAlign: 'center',
  },
  analyzingOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  analyzingText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 13,
    color: authColors.white,
  },
  permissionPrompt: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  permissionText: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.white,
    textAlign: 'center',
    lineHeight: 18,
  },
  permissionButton: {
    marginTop: 12,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  permissionButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 12,
    color: authColors.white,
  },
  shutterButton: {
    alignSelf: 'center',
    width: 74,
    height: 74,
    borderRadius: 37,
    borderWidth: 4,
    borderColor: authColors.white,
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: 24,
  },
  shutterButtonDisabled: {
    opacity: 0.5,
  },
  shutterInner: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: authColors.white,
  },
});
