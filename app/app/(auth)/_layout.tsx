import { Stack } from 'expo-router';

export default function AuthLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" options={{ gestureEnabled: false }} />
      <Stack.Screen name="intro" />
      <Stack.Screen name="login" />
      <Stack.Screen name="register" />
      <Stack.Screen name="input" />
    </Stack>
  );
}
