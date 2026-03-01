import React from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    SafeAreaView,
} from 'react-native';

interface HomeScreenProps {
    onStart: () => void;
}

export default function HomeScreen({ onStart }: HomeScreenProps) {
    return (
        <SafeAreaView style={styles.container}>
            <View style={styles.content}>
                {/* Logo / Title */}
                <Text style={styles.emoji}>🔥</Text>
                <Text style={styles.title}>StepRoast</Text>
                <Text style={styles.subtitle}>Real-Time AI Coach</Text>

                {/* Description */}
                <View style={styles.descriptionBox}>
                    <Text style={styles.description}>
                        Put your phone on the floor, point the camera up at your feet, and
                        DANCE. The AI Coach will analyze your footwork in real-time with
                        instant feedback and encouragement.
                    </Text>
                </View>

                {/* Score Categories */}
                <View style={styles.categories}>
                    <Text style={styles.categoryItem}>⚡ Speed</Text>
                    <Text style={styles.categoryItem}>🎵 Rhythm</Text>
                    <Text style={styles.categoryItem}>🔥 Complexity</Text>
                    <Text style={styles.categoryItem}>💯 Commitment</Text>
                </View>

                {/* Start Button */}
                <TouchableOpacity style={styles.startButton} onPress={onStart}>
                    <Text style={styles.startButtonText}>🎤 START COACHING</Text>
                </TouchableOpacity>
            </View>
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#0a0a0a',
    },
    content: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: 32,
    },
    emoji: {
        fontSize: 72,
        marginBottom: 8,
    },
    title: {
        fontSize: 48,
        fontWeight: '900',
        color: '#fff',
        letterSpacing: 2,
    },
    subtitle: {
        fontSize: 18,
        color: '#e94560',
        marginTop: 4,
        fontWeight: '600',
        letterSpacing: 4,
        textTransform: 'uppercase',
    },
    descriptionBox: {
        marginTop: 32,
        backgroundColor: '#1a1a2e',
        borderRadius: 16,
        padding: 20,
        borderWidth: 1,
        borderColor: '#2a2a4e',
    },
    description: {
        fontSize: 15,
        color: '#aaa',
        textAlign: 'center',
        lineHeight: 22,
    },
    categories: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        justifyContent: 'center',
        marginTop: 28,
        gap: 12,
    },
    categoryItem: {
        fontSize: 16,
        color: '#fff',
        backgroundColor: '#16213e',
        paddingHorizontal: 16,
        paddingVertical: 10,
        borderRadius: 20,
        overflow: 'hidden',
    },
    startButton: {
        marginTop: 40,
        backgroundColor: '#e94560',
        paddingHorizontal: 48,
        paddingVertical: 18,
        borderRadius: 30,
        shadowColor: '#e94560',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.4,
        shadowRadius: 12,
        elevation: 8,
    },
    startButtonText: {
        fontSize: 20,
        fontWeight: '800',
        color: '#fff',
        letterSpacing: 2,
    },
});
