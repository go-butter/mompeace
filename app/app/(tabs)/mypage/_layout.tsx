import { Stack } from 'expo-router';

export default function MyPageLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="edit-profile" />
    </Stack>
  );
}
