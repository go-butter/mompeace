import { useNavigation } from '@react-navigation/native';
import { Stack, useSegments } from 'expo-router';
import { useEffect } from 'react';
import { LayoutAnimation, Platform, UIManager } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const VISIBLE_TAB_BAR_STYLE = {
  backgroundColor: '#fff',
  borderTopLeftRadius: 15,
  borderTopRightRadius: 15,
  shadowColor: '#000',
  shadowOffset: { width: 0, height: 0 },
  shadowOpacity: 0.25,
  shadowRadius: 4,
  elevation: 4,
} as const;

const CONTENT_HEIGHT = 80; // mirrors (tabs)/_layout.tsx's CONTENT_HEIGHT
const HIDDEN_TAB_BAR_ROUTES = new Set([
  'edit-profile',
  'edit-allergy',
  'contact',
]);

export default function MyPageLayout() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation();
  const segments = useSegments();
  const currentLeaf = segments[segments.length - 1];
  const shouldHideTabBar = HIDDEN_TAB_BAR_ROUTES.has(currentLeaf);

  useEffect(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    navigation.setOptions({
      tabBarStyle: shouldHideTabBar
        ? { display: 'none' }
        : { ...VISIBLE_TAB_BAR_STYLE, height: CONTENT_HEIGHT + insets.bottom },
    });
  }, [navigation, shouldHideTabBar, insets.bottom]);

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="edit-profile" />
      <Stack.Screen name="edit-allergy" />
      <Stack.Screen name="contact" />
    </Stack>
  );
}
