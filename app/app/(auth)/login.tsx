import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { authColors } from '@/components/auth/colors';
import { GradientBackground } from '@/components/auth/gradient-background';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, loginUser } from '@/lib/api-client';

export default function LoginScreen() {
  const { login } = useAuth();
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const handleLogin = async () => {
    if (!id.trim() || !password.trim()) {
      setError('아이디와 비밀번호를 입력해 주세요.');
      return;
    }

    setError(null);
    setLoading(true);
    try {
      const response = await loginUser({ login_id: id, password });
      login({
        user_id: response.user_id,
        nickname: response.nickname,
        login_id: response.login_id,
        pregnancy_week: response.pregnancy_week,
        due_date: response.due_date,
        allergy_info: response.allergy_info,
      });
      if (!isMountedRef.current) return;
      if (response.pregnancy_week === null || response.pregnancy_week === undefined) {
        router.push('/(auth)/input');
      } else {
        router.push('/(tabs)/home');
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError((err as Error).message);
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

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
        <View style={styles.passwordFieldWrapper}>
          <TextInput
            style={[styles.input, styles.passwordInput]}
            placeholder="Enter your password"
            placeholderTextColor={authColors.gray}
            value={password}
            onChangeText={setPassword}
            secureTextEntry={!passwordVisible}
          />
          <Pressable
            style={styles.eyeButton}
            onPress={() => setPasswordVisible((prev) => !prev)}
            hitSlop={8}>
            <Ionicons
              name={passwordVisible ? 'eye-off-outline' : 'eye-outline'}
              size={20}
              color={authColors.gray}
            />
          </Pressable>
        </View>

        {error && <Text style={styles.errorText}>{error}</Text>}

        <Pressable
          style={[styles.loginButton, loading && styles.buttonDisabled]}
          onPress={handleLogin}
          disabled={loading}>
          <View style={styles.buttonContent}>
            {loading && <ActivityIndicator size="small" color={authColors.white} />}
            <Text style={styles.loginButtonText}>{loading ? '로그인 중...' : '로그인'}</Text>
          </View>
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
  passwordFieldWrapper: {
    position: 'relative',
  },
  passwordInput: {
    paddingRight: 48,
  },
  eyeButton: {
    position: 'absolute',
    right: 16,
    top: 20,
    bottom: 0,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loginButton: {
    backgroundColor: authColors.pink,
    borderRadius: 999,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 24,
  },
  buttonContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  loginButtonText: {
    color: authColors.white,
    fontSize: 17,
    fontFamily: fonts.bold,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  errorText: {
    color: authColors.pink,
    fontSize: 13,
    fontFamily: fonts.regular,
    marginTop: 12,
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
