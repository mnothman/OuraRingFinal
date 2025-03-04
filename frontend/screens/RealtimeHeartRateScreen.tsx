import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import axios, { AxiosError } from 'axios';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

interface HeartRateData {
  bpm: number;
  timestamp: string;
}

interface ErrorResponse {
  detail: string;
}

const BACKEND_URL = Constants.expoConfig?.extra?.backendUrl || 'https://d03b-2601-207-380-fb60-9996-b006-c610-fbd5.ngrok-free.app';

const RealtimeHeartRateScreen = ({ navigation }: { navigation: any }) => {
  const [heartRateData, setHeartRateData] = useState<HeartRateData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchHeartRateData = async () => {
      try {
        setIsLoading(true);
        setError(null);
        
        // Get the stored access token
        const token = await SecureStore.getItemAsync('oauth_token');
        if (!token) {
          setError('No access token found. Please login again.');
          navigation.replace('Login');
          return;
        }

        // Log the token for debugging
        console.log('Using token:', token.substring(0, 10) + '...');

        // Make the request with the token
        const response = await axios.get(`${BACKEND_URL}/data/real_time_heart_rate`, {
          headers: {
            'Authorization': `Bearer ${token.trim()}`
          }
        });

        // Log the response for debugging
        console.log('Response status:', response.status);
        console.log('Response data:', response.data);

        // Validate response data
        const data = response.data;
        if (data && typeof data.bpm === 'number' && typeof data.timestamp === 'string') {
          setHeartRateData(data);
        } else {
          console.error('Invalid data format:', data);
          setError('Invalid data format received from server');
        }
      } catch (err) {
        console.error('Error fetching heart rate:', err);
        
        if (axios.isAxiosError(err)) {
          const axiosError = err as AxiosError<ErrorResponse>;
          console.error('Full error response:', axiosError.response?.data);
          
          if (axiosError.response?.status === 401) {
            setError('Session expired. Please login again.');
            navigation.replace('Login');
          } else if (axiosError.response?.status === 404) {
            setError('No heart rate data available. Please wait a few minutes and try again.');
          } else if (axiosError.response?.status === 422) {
            // Handle validation error (usually means the token is not properly formatted)
            const validationError = axiosError.response.data;
            console.error('Validation error details:', validationError);
            
            // Try to refresh the token
            const userId = await SecureStore.getItemAsync('user_id');
            if (userId) {
              try {
                const refreshResponse = await axios.get(`${BACKEND_URL}/auth/refresh?user_id=${userId}`);
                if (refreshResponse.data.access_token) {
                  await SecureStore.setItemAsync('oauth_token', refreshResponse.data.access_token);
                  setError('Token refreshed. Please try again.');
                  return;
                }
              } catch (refreshError) {
                console.error('Error refreshing token:', refreshError);
              }
            }
            
            setError('Invalid authorization token. Please try logging in again.');
            navigation.replace('Login');
          } else {
            const errorDetail = axiosError.response?.data?.detail || 'Unknown error';
            setError(`Failed to fetch heart rate data: ${errorDetail}`);
          }
        } else {
          setError('An unexpected error occurred. Please try again.');
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchHeartRateData();
    const interval = setInterval(fetchHeartRateData, 60000); // Update every minute

    return () => clearInterval(interval);
  }, [navigation]);

  if (isLoading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color="#4CAF50" />
        <Text style={styles.loadingText}>Loading heart rate data...</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={[styles.container, styles.centered]}>
        <Text style={styles.error}>{error}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Real-time Heart Rate</Text>
      {heartRateData ? (
        <View style={styles.dataContainer}>
          <Text style={styles.value}>{heartRateData.bpm} BPM</Text>
          <Text style={styles.timestamp}>
            Last updated: {new Date(heartRateData.timestamp).toLocaleString()}
          </Text>
        </View>
      ) : (
        <Text style={styles.noData}>No heart rate data available</Text>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
    backgroundColor: '#fff',
  },
  centered: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 16,
    color: '#333',
  },
  dataContainer: {
    backgroundColor: '#f5f5f5',
    padding: 16,
    borderRadius: 8,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  value: {
    fontSize: 48,
    fontWeight: 'bold',
    textAlign: 'center',
    color: '#4CAF50',
  },
  timestamp: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    marginTop: 8,
  },
  error: {
    color: '#d32f2f',
    fontSize: 16,
    textAlign: 'center',
    backgroundColor: '#ffebee',
    padding: 16,
    borderRadius: 8,
    marginVertical: 16,
  },
  loadingText: {
    marginTop: 16,
    color: '#666',
    fontSize: 16,
  },
  noData: {
    fontSize: 18,
    color: '#666',
    textAlign: 'center',
    marginTop: 32,
  },
});

export default RealtimeHeartRateScreen;