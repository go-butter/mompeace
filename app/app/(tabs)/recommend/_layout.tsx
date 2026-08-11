import { Stack } from 'expo-router';

export default function RecommendLayout() {
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#FEFAF9' } }}>
      <Stack.Screen name="index" />
    </Stack>
  );
}
