import DateTimePicker from '@react-native-community/datetimepicker';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import Animated, {
  Easing,
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import ChevronDownIcon from '@/assets/images/common/chevron_down_plain.svg';
import InformationIcon from '@/assets/images/onboarding/information.svg';
import ClockIcon from '@/assets/images/common/clock.svg';
import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  CoffeeCaffeineEntry,
  CoffeeOptionsResponse,
  HomeCoffeePreset,
  createFoodLog,
  getCoffeeOptions,
} from '@/lib/api-client';

const EXPAND_SPRING_CONFIG = { damping: 16, stiffness: 100, mass: 1 };
const TIME_PICKER_HEIGHT = 216;

function formatTimeLabel(time: Date) {
  const hours = time.getHours();
  const minutes = time.getMinutes();
  const period = hours < 12 ? '오전' : '오후';
  const displayHour = hours % 12 === 0 ? 12 : hours % 12;
  return `${period} ${displayHour}:${String(minutes).padStart(2, '0')}`;
}

function toEatenAt(date: string, time: Date) {
  const hh = String(time.getHours()).padStart(2, '0');
  const min = String(time.getMinutes()).padStart(2, '0');
  const ss = String(time.getSeconds()).padStart(2, '0');
  return `${date} ${hh}:${min}:${ss}`;
}

function variantLabel(variant: CoffeeCaffeineEntry) {
  const sizeText = variant.size ?? '용량 미공개';
  const volumeText = variant.volume_ml != null ? ` (${variant.volume_ml}ml)` : '';
  const tempText = variant.hot_or_ice === 'hot' ? 'HOT' : 'ICE';
  return `${sizeText}${volumeText} · ${tempText}`;
}

export default function FoodEntryCoffeeScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { date } = useLocalSearchParams<{ date: string }>();

  const [options, setOptions] = useState<CoffeeOptionsResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [mode, setMode] = useState<'franchise' | 'home'>('franchise');

  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const [selectedMenu, setSelectedMenu] = useState<string | null>(null);
  const [selectedVariant, setSelectedVariant] = useState<CoffeeCaffeineEntry | null>(null);
  const [selectedHomePreset, setSelectedHomePreset] = useState<HomeCoffeePreset | null>(null);

  const [time, setTime] = useState(new Date());
  const [showTimePicker, setShowTimePicker] = useState(false);
  const chevronRotation = useSharedValue(0);
  const timePickerHeight = useSharedValue(0);
  const timePickerOpacity = useSharedValue(0);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const loadOptions = () => {
    setLoadError(null);
    getCoffeeOptions()
      .then(setOptions)
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : (err as Error).message;
        setLoadError(message || '데이터를 불러오지 못했어요. 다시 시도해주세요.');
      });
  };

  useEffect(() => {
    loadOptions();
  }, []);

  const brands = useMemo(() => {
    if (!options) return [];
    return Array.from(new Set(options.brands.map((e) => e.brand)));
  }, [options]);

  const menusForBrand = useMemo(() => {
    if (!options || !selectedBrand) return [];
    return Array.from(
      new Set(options.brands.filter((e) => e.brand === selectedBrand).map((e) => e.menu))
    );
  }, [options, selectedBrand]);

  const variantsForMenu = useMemo(() => {
    if (!options || !selectedBrand || !selectedMenu) return [];
    return options.brands.filter((e) => e.brand === selectedBrand && e.menu === selectedMenu);
  }, [options, selectedBrand, selectedMenu]);

  const selection = useMemo(() => {
    if (mode === 'franchise' && selectedVariant) {
      const sizePart = selectedVariant.size ? ` ${selectedVariant.size}` : '';
      const tempText = selectedVariant.hot_or_ice === 'hot' ? 'HOT' : 'ICE';
      const food_name = `${selectedVariant.brand} ${selectedVariant.menu}${sizePart} (${tempText})`;
      return { food_name, caffeine_mg: selectedVariant.caffeine_mg };
    }
    if (mode === 'home' && selectedHomePreset) {
      return {
        food_name: `집에서 만든 커피 - ${selectedHomePreset.menu}`,
        caffeine_mg: selectedHomePreset.caffeine_mg,
      };
    }
    return null;
  }, [mode, selectedVariant, selectedHomePreset]);

  const timeChevronAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${interpolate(chevronRotation.value, [0, 1], [0, 180])}deg` }],
  }));

  const timePickerAnimatedStyle = useAnimatedStyle(() => ({
    height: timePickerHeight.value,
    opacity: timePickerOpacity.value,
    overflow: 'hidden',
  }));

  const openTimePicker = () => {
    setShowTimePicker(true);
    chevronRotation.value = withSpring(1, EXPAND_SPRING_CONFIG);
    timePickerHeight.value = withTiming(TIME_PICKER_HEIGHT, {
      duration: 400,
      easing: Easing.out(Easing.cubic),
    });
    timePickerOpacity.value = withTiming(1, { duration: 400 });
  };

  const closeTimePicker = () => {
    chevronRotation.value = withSpring(0, EXPAND_SPRING_CONFIG);
    timePickerHeight.value = withTiming(0, {
      duration: 400,
      easing: Easing.out(Easing.cubic),
    });
    timePickerOpacity.value = withTiming(0, { duration: 300 }, (finished) => {
      if (finished) runOnJS(setShowTimePicker)(false);
    });
  };

  const toggleTimePicker = () => {
    if (showTimePicker) {
      closeTimePicker();
    } else {
      openTimePicker();
    }
  };

  const handleSave = () => {
    if (!selection || !user?.user_id || !date || saving) return;

    setSaving(true);
    setSaveError(null);

    createFoodLog({
      user_id: user.user_id,
      food_name: selection.food_name,
      input_type: 'coffee_calculator',
      caffeine_mg: selection.caffeine_mg,
      sugar_g: null,
      sodium_mg: null,
      eaten_at: toEatenAt(date, time),
      amount: 1,
      unit: '잔',
    })
      .then(() => {
        router.replace('/(tabs)/food-diary');
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : (err as Error).message;
        setSaveError(message || '저장에 실패했어요. 다시 시도해주세요.');
      })
      .finally(() => setSaving(false));
  };

  const renderFranchiseFlow = () => {
    if (!options) return null;

    if (!selectedBrand) {
      return (
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>브랜드 선택</Text>
          {brands.map((brand) => (
            <Pressable
              key={brand}
              style={styles.listRow}
              onPress={() => setSelectedBrand(brand)}>
              <Text style={styles.listRowText}>{brand}</Text>
            </Pressable>
          ))}
        </View>
      );
    }

    if (!selectedMenu) {
      return (
        <View style={styles.card}>
          {renderBreadcrumb()}
          <Text style={styles.fieldLabel}>메뉴 선택</Text>
          {menusForBrand.map((menu) => (
            <Pressable key={menu} style={styles.listRow} onPress={() => setSelectedMenu(menu)}>
              <Text style={styles.listRowText}>{menu}</Text>
            </Pressable>
          ))}
        </View>
      );
    }

    if (!selectedVariant) {
      return (
        <View style={styles.card}>
          {renderBreadcrumb()}
          <Text style={styles.fieldLabel}>사이즈 · 온도 선택</Text>
          {variantsForMenu.map((variant, index) => (
            <Pressable
              key={`${variant.size ?? 'none'}-${variant.hot_or_ice}-${index}`}
              style={styles.listRow}
              onPress={() => setSelectedVariant(variant)}>
              <Text style={styles.listRowText}>{variantLabel(variant)}</Text>
              <Text style={styles.listRowSubtext}>{variant.caffeine_mg}mg</Text>
            </Pressable>
          ))}
        </View>
      );
    }

    return (
      <View style={styles.card}>
        {renderBreadcrumb()}
        <Pressable onPress={() => setSelectedVariant(null)}>
          <Text style={styles.changeSelectionText}>다른 사이즈 선택</Text>
        </Pressable>
      </View>
    );
  };

  const renderBreadcrumb = () => (
    <View style={styles.breadcrumbRow}>
      <Pressable
        onPress={() => {
          setSelectedBrand(null);
          setSelectedMenu(null);
          setSelectedVariant(null);
        }}>
        <Text style={styles.breadcrumbText}>{selectedBrand}</Text>
      </Pressable>
      {selectedMenu && (
        <>
          <Text style={styles.breadcrumbSep}>›</Text>
          <Pressable
            onPress={() => {
              setSelectedMenu(null);
              setSelectedVariant(null);
            }}>
            <Text style={styles.breadcrumbText}>{selectedMenu}</Text>
          </Pressable>
        </>
      )}
      {selectedVariant && (
        <>
          <Text style={styles.breadcrumbSep}>›</Text>
          <Text style={[styles.breadcrumbText, styles.breadcrumbTextActive]}>
            {variantLabel(selectedVariant)}
          </Text>
        </>
      )}
    </View>
  );

  const renderHomeFlow = () => {
    if (!options) return null;

    if (!selectedHomePreset) {
      return (
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>집에서 만든 커피</Text>
          {options.home_presets.map((preset, index) => (
            <Pressable
              key={`${preset.menu}-${index}`}
              style={styles.listRow}
              onPress={() => setSelectedHomePreset(preset)}>
              <Text style={styles.listRowText}>
                {preset.menu} ({preset.serving})
              </Text>
              <Text style={styles.listRowSubtext}>{preset.caffeine_mg}mg</Text>
            </Pressable>
          ))}
        </View>
      );
    }

    return (
      <View style={styles.card}>
        <Text style={styles.breadcrumbText}>{selectedHomePreset.menu}</Text>
        <Pressable onPress={() => setSelectedHomePreset(null)}>
          <Text style={styles.changeSelectionText}>다른 메뉴 선택</Text>
        </Pressable>
      </View>
    );
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + 7, paddingBottom: insets.bottom + 40 },
      ]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>커피 계산</Text>
      </View>

      <View style={styles.modeToggleRow}>
        <Pressable
          style={[styles.modePill, mode === 'franchise' && styles.modePillSelected]}
          onPress={() => setMode('franchise')}>
          <Text style={[styles.modePillText, mode === 'franchise' && styles.modePillTextSelected]}>
            프랜차이즈
          </Text>
        </Pressable>
        <Pressable
          style={[styles.modePill, mode === 'home' && styles.modePillSelected]}
          onPress={() => setMode('home')}>
          <Text style={[styles.modePillText, mode === 'home' && styles.modePillTextSelected]}>
            집에서 만든 커피
          </Text>
        </Pressable>
      </View>

      {!options && !loadError && (
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={authColors.pink} />
        </View>
      )}

      {loadError && (
        <View style={styles.card}>
          <Text style={styles.errorText}>{loadError}</Text>
          <Pressable onPress={loadOptions}>
            <Text style={styles.changeSelectionText}>다시 시도</Text>
          </Pressable>
        </View>
      )}

      {options && (mode === 'franchise' ? renderFranchiseFlow() : renderHomeFlow())}

      {selection && (
        <View style={styles.card}>
          <Text style={styles.resultLabel}>예상 카페인 함량</Text>
          <View style={styles.resultValueRow}>
            <Text style={styles.resultValue}>{selection.caffeine_mg}</Text>
            <Text style={styles.resultUnit}>mg</Text>
          </View>
          <Text style={styles.resultSubtitle}>{selection.food_name}</Text>
          <View style={styles.infoBanner}>
            <InformationIcon width={16} height={16} />
            <Text style={styles.infoBannerText}>
              실제 카페인 함량은 매장·추출 조건에 따라 다를 수 있어요
            </Text>
          </View>
        </View>
      )}

      {selection && (
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>섭취시간</Text>
          <Pressable style={styles.timeInput} onPress={toggleTimePicker}>
            <ClockIcon width={15} height={15} style={styles.timeInputClock} />
            <Text style={styles.timeInputText}>{formatTimeLabel(time)}</Text>
            <Animated.View style={[styles.timeInputChevron, timeChevronAnimatedStyle]}>
              <ChevronDownIcon width={12} height={8} color="#848484" />
            </Animated.View>
          </Pressable>
          {showTimePicker && (
            <Animated.View
              style={[
                Platform.OS === 'ios' ? styles.timePickerContainer : undefined,
                timePickerAnimatedStyle,
              ]}>
              <DateTimePicker
                value={time}
                mode="time"
                display={Platform.OS === 'ios' ? 'spinner' : 'default'}
                themeVariant="light"
                onChange={(_, selected) => {
                  const nextVisible = Platform.OS === 'ios';
                  if (!nextVisible) closeTimePicker();
                  if (selected) setTime(selected);
                }}
              />
            </Animated.View>
          )}
        </View>
      )}

      {saveError && <Text style={styles.errorText}>{saveError}</Text>}

      <Pressable
        style={[styles.saveButton, (!selection || saving) && styles.saveButtonDisabled]}
        onPress={handleSave}
        disabled={!selection || saving}>
        <Text style={styles.saveButtonText}>{saving ? '저장 중...' : '기록 저장'}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: authColors.white,
  },
  content: {
    paddingHorizontal: 17,
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
  modeToggleRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 16,
  },
  modePill: {
    flex: 1,
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 100,
    paddingVertical: 10,
    alignItems: 'center',
  },
  modePillSelected: {
    borderColor: authColors.pink,
    backgroundColor: '#FFF5F3',
  },
  modePillText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 13,
    color: authColors.gray,
  },
  modePillTextSelected: {
    color: authColors.pink,
  },
  loadingWrap: {
    marginTop: 24,
    alignItems: 'center',
  },
  card: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: '#FFEDEE',
    borderRadius: 15,
    padding: 19,
    marginTop: 16,
    shadowColor: '#F47E8A',
    shadowOpacity: 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    elevation: 3,
  },
  fieldLabel: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: '#000000',
    marginBottom: 8,
  },
  breadcrumbRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    marginBottom: 12,
  },
  breadcrumbText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 13,
    color: authColors.gray,
  },
  breadcrumbTextActive: {
    color: authColors.pink,
  },
  breadcrumbSep: {
    marginHorizontal: 6,
    color: authColors.gray,
    fontSize: 13,
  },
  listRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginTop: 8,
  },
  listRowText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: '#000000',
  },
  listRowSubtext: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 12,
    color: authColors.pink,
  },
  changeSelectionText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 13,
    color: authColors.pink,
    textDecorationLine: 'underline',
    marginTop: 8,
  },
  resultLabel: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: '#000000',
  },
  resultValueRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginTop: 8,
  },
  resultValue: {
    fontFamily: fonts.semiBold,
    fontSize: 36,
    color: authColors.pink,
  },
  resultUnit: {
    fontFamily: fonts.medium,
    fontSize: 16,
    color: authColors.pink,
    marginLeft: 4,
    marginBottom: 6,
  },
  resultSubtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 13,
    color: authColors.gray,
    marginTop: 4,
  },
  infoBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#FFF5F3',
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
  },
  infoBannerText: {
    fontSize: 11,
    fontFamily: fonts.regular,
    color: authColors.gray,
    flex: 1,
  },
  timeInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 32,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  timeInputClock: {
    marginRight: 6,
  },
  timeInputText: {
    flex: 1,
    fontSize: 12,
    color: '#4A4A4A',
  },
  timeInputChevron: {
    marginLeft: 4,
  },
  timePickerContainer: {
    height: 216,
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    marginTop: 10,
    overflow: 'hidden',
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 12,
    textAlign: 'center',
    marginTop: 16,
  },
  saveButton: {
    marginTop: 20,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveButtonDisabled: {
    opacity: 0.6,
  },
  saveButtonText: {
    fontFamily: fonts.semiBold,
    fontSize: 19,
    color: authColors.white,
  },
});
