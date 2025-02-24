// LoginScreen.tsx
import React from 'react';
import { View, Button, Linking, Alert, StyleSheet } from 'react-native';

const LoginScreen = () => {
  const initiateLogin = async () => {
    // Replace with your ngrok public URL or backend URL
    const loginUrl = 'https://15e3-73-151-240-60.ngrok-free.app/auth/login';
    try {
      const supported = await Linking.canOpenURL(loginUrl);
      if (supported) {
        await Linking.openURL(loginUrl);
      } else {
        Alert.alert("Error", "Don't know how to open URI: " + loginUrl);
      }
    } catch (error) {
      console.error("Failed to initiate login", error);
    }
  };

  return (
    <View style={styles.container}>
      <Button title="Login with Oura" onPress={initiateLogin} />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default LoginScreen;
