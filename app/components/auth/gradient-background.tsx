import { LinearGradient } from 'expo-linear-gradient';
import { StyleSheet, type ViewProps } from 'react-native';

export function GradientBackground({ style, children, ...rest }: ViewProps) {
  return (
    <LinearGradient
      colors={['#FEF4F3', '#FFFFFF', '#FFF8F8', '#FFF2F1']}
      locations={[0, 0.394, 0.688, 1]}
      style={[StyleSheet.absoluteFill, style]}
      {...rest}>
      {children}
    </LinearGradient>
  );
}
