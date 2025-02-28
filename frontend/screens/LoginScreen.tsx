import React, { useEffect } from 'react';
import { View, Button, StyleSheet, Alert, Text } from 'react-native';
import * as Linking from 'expo-linking';
import Constants from 'expo-constants';
import {
  EXPO_PUBLIC_CLIENT_ID,
  EXPO_PUBLIC_REDIRECT_URI
} from '@env';

const LoginScreen = ({ navigation }: { navigation: any }) => {
  useEffect(() => {
    // This will run when the component mounts
    console.log('Client ID:', EXPO_PUBLIC_CLIENT_ID);
    console.log('Redirect URI:', EXPO_PUBLIC_REDIRECT_URI);
    Alert.alert(
      "Environment Variables",
      `Client ID: ${EXPO_PUBLIC_CLIENT_ID || 'NOT SET'}\n` +
      `Redirect URI: ${EXPO_PUBLIC_REDIRECT_URI || 'NOT SET'}`
    );
  }, []);

  const handleLogin = async () => {
    if (!EXPO_PUBLIC_CLIENT_ID || !EXPO_PUBLIC_REDIRECT_URI) {
      Alert.alert(
        "Configuration Error",
        `Client ID: ${EXPO_PUBLIC_CLIENT_ID || 'NOT SET'}\n` +
        `Redirect URI: ${EXPO_PUBLIC_REDIRECT_URI || 'NOT SET'}`
      );
      return;
    }

    const scope = "email personal daily heartrate workout tag session spo2Daily";

    const authUrl = `https://cloud.ouraring.com/oauth/authorize?` +
      `client_id=${EXPO_PUBLIC_CLIENT_ID}&` +
      `redirect_uri=${encodeURIComponent(EXPO_PUBLIC_REDIRECT_URI)}&` +
      `response_type=code&` +
      `scope=${encodeURIComponent(scope)}`;

    try {
      Alert.alert("About to open URL", authUrl);
      await Linking.openURL(authUrl);
    } catch (error) {
      console.error('Login error:', error);
      Alert.alert(
        "Error",
        `Failed to open URL: ${error}`
      );
    }
  };

  return (
    <View style={styles.container}>
      <Text>Client ID: {EXPO_PUBLIC_CLIENT_ID || 'NOT SET'}</Text>
      <Text>Redirect URI: {EXPO_PUBLIC_REDIRECT_URI || 'NOT SET'}</Text>
      <Button title="Login with Oura Ring" onPress={handleLogin} />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
});

export default LoginScreen;