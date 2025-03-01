import React, { useEffect } from 'react';
import { View, Button, StyleSheet, Alert } from 'react-native';
import * as Linking from 'expo-linking';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

interface QueryParams {
  token?: string;
  user?: string;
}

const BACKEND_URL = Constants.expoConfig?.extra?.backendUrl || 'https://b33a-2601-207-380-fb60-d023-11f-59af-4505.ngrok-free.app';

const LoginScreen = ({ navigation, route }: { navigation: any; route: any }) => {
  useEffect(() => {
    // Handle deep link when coming back from OAuth
    const handleDeepLink = async (event: { url: string }) => {
      try {
        console.log('Received deep link URL:', event.url); // Debug log
        const url = event.url;
        const { path, queryParams } = Linking.parse(url);
        
        console.log('Parsed deep link:', { path, queryParams }); // Debug log
        
        if (path === 'oauth-callback') {
          const params = queryParams as QueryParams;
          const token = params?.token;
          const user = params?.user;
          
          console.log('OAuth callback params:', { token: token?.substring(0, 10) + '...', user }); // Debug log (truncate token for security)
          
          if (token && user) {
            // Store the token securely
            await SecureStore.setItemAsync('oauth_token', token);
            await SecureStore.setItemAsync('user_id', user);
            
            // Navigate to the main screen
            navigation.replace('RealtimeHeartRate');
          } else {
            console.error('Missing token or user in callback');
            Alert.alert('Error', 'Login failed - missing token or user');
          }
        }
      } catch (error) {
        console.error('Error handling deep link:', error);
        Alert.alert('Error', 'Failed to handle login callback');
      }
    };

    // Set up deep link listener
    const subscription = Linking.addEventListener('url', handleDeepLink);

    // Check for initial URL
    Linking.getInitialURL().then(url => {
      if (url) {
        console.log('Initial URL:', url); // Debug log
        handleDeepLink({ url });
      }
    });

    return () => {
      subscription.remove();
    };
  }, [navigation]);

  const handleLogin = async () => {
    try {
      // Generate a new state parameter
      const state = Math.random().toString(36).substring(2, 15);
      
      // Store the state in secure storage
      await SecureStore.setItemAsync('oauth_state', state);
      
      // Use environment variable for backend URL
      const loginUrl = `${BACKEND_URL}/auth/login?state=${state}`;
      
      console.log('Opening URL:', loginUrl); // Debug log
      await Linking.openURL(loginUrl);
    } catch (error) {
      console.error("Failed to initiate login", error);
      Alert.alert("Error", "Failed to open login page");
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
    padding: 20,
  },
});

export default LoginScreen;
