import { Stack } from 'expo-router';

export default function HomeLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="scan-result" />
      <Stack.Screen name="food-diary-list" />
      <Stack.Screen name="food-diary" />
      <Stack.Screen name="food-entry-search" />
      <Stack.Screen name="food-entry-manual" />
      <Stack.Screen name="premium-report" />
    </Stack>
  );
}
