import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

interface HeartRateData {
  bpm: number;
  timestamp: string;
}

const BACKEND_URL = Constants.expoConfig?.extra?.backendUrl || 'https://b33a-2601-207-380-fb60-d023-11f-59af-4505.ngrok-free.app';

const RealtimeHeartRateScreen = ({ navigation }: { navigation: any }) => {
  const [heartRateData, setHeartRateData] = useState<HeartRateData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHeartRateData = async () => {
      try {
        // Get the stored access token
        const token = await SecureStore.getItemAsync('oauth_token');
        if (!token) {
          setError('No access token found. Please login again.');
          navigation.replace('Login');
          return;
        }

        // Make the request with the token
        const response = await axios.get(`${BACKEND_URL}/data/real_time_heart_rate`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        setHeartRateData(response.data);
      } catch (err: any) {
        console.error('Error fetching heart rate:', err.response?.data || err.message);
        if (err.response?.status === 401) {
          // Token expired or invalid
          navigation.replace('Login');
        }
        setError(err.response?.data?.detail || err.message);
      }
    };

    fetchHeartRateData();
    const interval = setInterval(fetchHeartRateData, 60000); // Update every minute

    return () => clearInterval(interval);
  }, [navigation]);

  if (error) {
    return (
      <View style={styles.container}>
        <Text style={styles.error}>Error: {error}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Real-time Heart Rate</Text>
      {heartRateData && (
        <View style={styles.dataContainer}>
          <Text style={styles.value}>{heartRateData.bpm} BPM</Text>
          <Text style={styles.timestamp}>
            Last updated: {new Date(heartRateData.timestamp).toLocaleString()}
          </Text>
        </View>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 16,
  },
  dataContainer: {
    backgroundColor: '#f5f5f5',
    padding: 16,
    borderRadius: 8,
  },
  value: {
    fontSize: 48,
    fontWeight: 'bold',
    textAlign: 'center',
  },
  timestamp: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    marginTop: 8,
  },
  error: {
    color: 'red',
    fontSize: 16,
    textAlign: 'center',
  },
});

export default RealtimeHeartRateScreen;