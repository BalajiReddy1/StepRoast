import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface ScoreCardProps {
    score: number;
    verdict: string;
}

export default function ScoreCard({ score, verdict }: ScoreCardProps) {
    return (
        <View style={styles.card}>
            <Text style={styles.score}>{score}/100</Text>
            <Text style={styles.verdict}>{verdict}</Text>
        </View>
    );
}

const styles = StyleSheet.create({
    card: {
        backgroundColor: '#1a1a2e',
        borderRadius: 16,
        padding: 24,
        alignItems: 'center',
        margin: 16,
    },
    score: {
        fontSize: 64,
        fontWeight: 'bold',
        color: '#e94560',
    },
    verdict: {
        fontSize: 18,
        color: '#fff',
        marginTop: 8,
        textAlign: 'center',
    },
});
