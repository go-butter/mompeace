import { Stack } from 'expo-router';

export default function FoodDiaryLayout() {
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#FEFAF9' } }}>
      <Stack.Screen name="index" />
    </Stack>
  );
}
