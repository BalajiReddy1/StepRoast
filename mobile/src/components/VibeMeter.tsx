import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface VibeMeterProps {
    level: number; // 0-100
}

export default function VibeMeter({ level }: VibeMeterProps) {
    const getVibeEmoji = () => {
        if (level > 80) return '🔥';
        if (level > 60) return '😎';
        if (level > 40) return '🤔';
        if (level > 20) return '😬';
        return '💀';
    };

    return (
        <View style={styles.container}>
            <Text style={styles.emoji}>{getVibeEmoji()}</Text>
            <View style={styles.barBackground}>
                <View style={[styles.barFill, { width: `${level}%` }]} />
            </View>
            <Text style={styles.label}>Vibe: {level}%</Text>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        alignItems: 'center',
        padding: 16,
    },
    emoji: {
        fontSize: 48,
    },
    barBackground: {
        width: '80%',
        height: 12,
        backgroundColor: '#333',
        borderRadius: 6,
        marginTop: 12,
        overflow: 'hidden',
    },
    barFill: {
        height: '100%',
        backgroundColor: '#e94560',
        borderRadius: 6,
    },
    label: {
        color: '#aaa',
        marginTop: 8,
        fontSize: 14,
    },
});
