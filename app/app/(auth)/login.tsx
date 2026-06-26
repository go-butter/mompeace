import { router } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { authColors } from '@/components/auth/colors';
import { GradientBackground } from '@/components/auth/gradient-background';
import { fonts } from '@/constants/fonts';

export default function LoginScreen() {
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');

  return (
    <View style={styles.container}>
      <GradientBackground />

      <Image
        source={require('@/assets/images/common/logo_nottext.png')}
        style={styles.logo}
        resizeMode="contain"
      />

      <View style={styles.textBlock}>
        <Text style={styles.title}>
          <Text style={{ color: authColors.pink }}>맘편하게</Text>
          <Text style={{ color: authColors.brown }}> 시작해요</Text>
        </Text>
        <Text style={styles.subtitle}>
          로그인 하고 바코드 스캔, 맞춤 추천,{'\n'}푸드 다이어리 기능을 이용해 보세요 :)
        </Text>
      </View>

      <View style={styles.card}>
        <TextInput
          style={styles.input}
          placeholder="Enter your id"
          placeholderTextColor={authColors.gray}
          value={id}
          onChangeText={setId}
          autoCapitalize="none"
        />
        <TextInput
          style={styles.input}
          placeholder="Enter your password"
          placeholderTextColor={authColors.gray}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
        />

        <Pressable style={styles.loginButton} onPress={() => router.push('/(tabs)/home')}>
          <Text style={styles.loginButtonText}>로그인</Text>
        </Pressable>

        <Pressable onPress={() => router.push('/(auth)/register')} style={styles.registerLink}>
          <Text style={styles.registerText}>
            아직 계정이 없나요?{'  '}
            <Text style={styles.registerHighlight}>회원가입 &gt;</Text>
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  logo: {
    width: 100,
    height: 68,
    opacity: 0.85,
    marginTop: 117,
    marginLeft: 23,
  },
  textBlock: {
    marginTop: 12,
    marginLeft: 33,
    marginRight: 33,
  },
  title: {
    fontSize: 29,
    fontFamily: fonts.bold,
    textAlign: 'left',
  },
  subtitle: {
    fontSize: 14,
    fontFamily: fonts.regular,
    color: authColors.gray,
    textAlign: 'left',
    marginTop: 8,
    lineHeight: 20,
  },
  card: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: 524,
    backgroundColor: authColors.white,
    borderTopLeftRadius: 25,
    borderTopRightRadius: 25,
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 55,
    shadowColor: '#000',
    shadowOffset: { width: 1, height: 0 },
    shadowOpacity: 0.25,
    shadowRadius: 15,
    elevation: 15,
  },
  input: {
    borderWidth: 1,
    borderColor: authColors.border,
    backgroundColor: authColors.white,
    borderRadius: 999,
    height: 56,
    paddingHorizontal: 20,
    fontSize: 15,
    fontFamily: fonts.regular,
    marginTop: 20,
  },
  loginButton: {
    backgroundColor: authColors.pink,
    borderRadius: 999,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 24,
  },
  loginButtonText: {
    color: authColors.white,
    fontSize: 17,
    fontFamily: fonts.bold,
  },
  registerLink: {
    alignItems: 'center',
    marginTop: 'auto',
  },
  registerText: {
    fontSize: 14,
    fontFamily: fonts.regular,
    color: authColors.gray,
  },
  registerHighlight: {
    color: authColors.pink,
    fontFamily: fonts.regular,
    textDecorationLine: 'underline',
  },
});
