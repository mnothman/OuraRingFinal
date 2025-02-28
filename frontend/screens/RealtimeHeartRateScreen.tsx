import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import axios from 'axios';

interface HeartRateData {
  bpm: number;
  timestamp: string;
}

const RealtimeHeartRateScreen = () => {
  const [heartRateData, setHeartRateData] = useState<HeartRateData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHeartRateData = async () => {
      try {
        const response = await axios.get('http://localhost:5001/data/real_time_heart_rate');
        setHeartRateData(response.data);
      } catch (err) {
        setError(err.message);
      }
    };

    fetchHeartRateData();
    const interval = setInterval(fetchHeartRateData, 60000); // Update every minute

    return () => clearInterval(interval);
  }, []);

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