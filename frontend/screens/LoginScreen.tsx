import React from 'react';
import { View, Button, StyleSheet, Alert } from 'react-native';
import * as Linking from 'expo-linking';
import Constants from 'expo-constants';
import {
  EXPO_PUBLIC_CLIENT_ID
} from '@env';

const LoginScreen = ({ navigation }: { navigation: any }) => {
  const handleLogin = async () => {
    if (!EXPO_PUBLIC_CLIENT_ID) {
      Alert.alert(
        "Configuration Error",
        "Client ID is not configured properly."
      );
      return;
    }

    // Use your development IP address
    const redirectUri = 'exp://10.0.0.47:19000/--/auth/callback';
    console.log('Using redirect URI:', redirectUri);

    const scope = 'daily heartrate personal';

    const authUrl = `https://cloud.ouraring.com/oauth/authorize?` +
      `client_id=${EXPO_PUBLIC_CLIENT_ID}&` +
      `redirect_uri=${encodeURIComponent(redirectUri)}&` +
      `response_type=code&` +
      `scope=${encodeURIComponent(scope)}`;

    try {
      console.log('Opening auth URL:', authUrl);
      await Linking.openURL(authUrl);
    } catch (error) {
      console.error('Login error:', error);
      Alert.alert(
        "Error",
        "Could not open authentication page. Please try again."
      );
    }
  };

  return (
    <View style={styles.container}>
      <Button title="Login with Oura Ring" onPress={handleLogin} />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});

export default LoginScreen;