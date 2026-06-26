import { router } from 'expo-router';
import { useEffect } from 'react';
import { Image, StyleSheet, View } from 'react-native';

import { GradientBackground } from '@/components/auth/gradient-background';

export default function SplashScreen() {
  useEffect(() => {
    const timer = setTimeout(() => {
      router.push('/(auth)/intro');
    }, 1800);
    return () => clearTimeout(timer);
  }, []);

  return (
    <View style={styles.container}>
      <GradientBackground />
      <Image
        source={require('@/assets/images/common/logo_default.png')}
        style={styles.logo}
        resizeMode="contain"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logo: {
    width: 161,
    height: 161,
  },
});
