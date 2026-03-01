import React, { useState, useEffect, useRef } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    SafeAreaView,
    Animated,
    TextInput,
    Alert,
    ScrollView,
    StatusBar,
    Platform,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import VibeMeter from '../components/VibeMeter';
import ScoreCard from '../components/ScoreCard';

interface AgentHook {
    isConnected: boolean;
    isJudging: boolean;
    score: number | null;
    verdict: string | null;
    vibeLevel: number;
    liveCommentary: string | null;
    error: string | null;
    stepCount: number;
    connect: (backendUrl: string) => Promise<any>;
    startJudging: (backendUrl: string) => Promise<void>;
    stopJudging: (backendUrl: string) => Promise<void>;
}

interface JudgeScreenProps {
    onBack: () => void;
    agent: AgentHook;
}

// Default backend URL — your computer's WiFi IP
const DEFAULT_BACKEND_URL = 'https://orange-yodel-gjp6g6q9grr29v4w-8000.app.github.dev';

export default function JudgeScreen({ onBack, agent }: JudgeScreenProps) {
    const [countdown, setCountdown] = useState<number | null>(null);
    const [elapsed, setElapsed] = useState(0);
    const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND_URL);
    const [showSettings, setShowSettings] = useState(false);
    const [permission, requestPermission] = useCameraPermissions();
    const [farewellMode, setFarewellMode] = useState(false);
    const wasJudgingRef = useRef(false);

    const pulseAnim = useRef(new Animated.Value(1)).current;

    // Pulse animation for the recording indicator
    useEffect(() => {
        if (agent.isJudging) {
            const pulse = Animated.loop(
                Animated.sequence([
                    Animated.timing(pulseAnim, {
                        toValue: 1.3,
                        duration: 600,
                        useNativeDriver: true,
                    }),
                    Animated.timing(pulseAnim, {
                        toValue: 1,
                        duration: 600,
                        useNativeDriver: true,
                    }),
                ])
            );
            pulse.start();
            return () => pulse.stop();
        }
    }, [agent.isJudging]);

    // Timer while judging
    useEffect(() => {
        if (agent.isJudging) {
            const interval = setInterval(() => {
                setElapsed(prev => prev + 1);
            }, 1000);
            return () => clearInterval(interval);
        }
    }, [agent.isJudging]);

    // Detect when judging stops → show farewell screen for 4 seconds
    useEffect(() => {
        if (wasJudgingRef.current && !agent.isJudging) {
            // Just stopped judging — show farewell mode
            setFarewellMode(true);
            const timeout = setTimeout(() => {
                setFarewellMode(false);
                setElapsed(0); // Reset timer for next session
            }, 4000);
            return () => clearTimeout(timeout);
        }
        wasJudgingRef.current = agent.isJudging;
    }, [agent.isJudging]);

    // Show errors
    useEffect(() => {
        if (agent.error) {
            Alert.alert('StepRoast Error', agent.error);
        }
    }, [agent.error]);

    const startCountdown = async () => {
        // Request camera permission if not already granted
        if (!permission?.granted) {
            const result = await requestPermission();
            if (!result.granted) {
                Alert.alert('Camera Required', 'StepRoast needs camera access to judge your footwork!');
                return;
            }
        }
        setCountdown(3);
        setElapsed(0);
    };

    useEffect(() => {
        if (countdown !== null && countdown > 0) {
            const t = setTimeout(() => setCountdown(countdown - 1), 1000);
            return () => clearTimeout(t);
        } else if (countdown === 0) {
            // Show "GO!" for 600ms before starting
            setCountdown(-1); // -1 = "GO!" state
        } else if (countdown === -1) {
            const t = setTimeout(() => {
                setCountdown(null);
                agent.startJudging(backendUrl);
            }, 600);
            return () => clearTimeout(t);
        }
    }, [countdown]);

    const stopJudging = () => {
        agent.stopJudging(backendUrl);
    };

    const formatTime = (s: number) => {
        const mins = Math.floor(s / 60);
        const secs = s % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <SafeAreaView style={styles.container}>
            <StatusBar barStyle="light-content" backgroundColor="#0a0a0a" />
            {/* Camera preview — full screen background when judging */}
            {agent.isJudging && (
                <CameraView
                    style={styles.cameraFill}
                    facing="front"
                />
            )}

            {/* Header */}
            <View style={styles.header}>
                <TouchableOpacity onPress={onBack} style={styles.backButton}>
                    <Text style={styles.backText}>← Back</Text>
                </TouchableOpacity>

                <TouchableOpacity onPress={() => setShowSettings(!showSettings)}>
                    <Text style={styles.settingsIcon}>⚙️</Text>
                </TouchableOpacity>

                {agent.isJudging && (
                    <View style={styles.liveIndicator}>
                        <Animated.View
                            style={[styles.liveDot, { transform: [{ scale: pulseAnim }] }]}
                        />
                        <Text style={styles.liveText}>LIVE</Text>
                        <Text style={styles.timerText}>{formatTime(elapsed)}</Text>
                    </View>
                )}
            </View>

            {/* Backend URL Settings */}
            {showSettings && (
                <View style={styles.settingsBox}>
                    <Text style={styles.settingsLabel}>Backend URL:</Text>
                    <TextInput
                        style={styles.settingsInput}
                        value={backendUrl}
                        onChangeText={setBackendUrl}
                        placeholder="http://your-ip:8000"
                        placeholderTextColor="#666"
                        autoCapitalize="none"
                        autoCorrect={false}
                    />
                    <Text style={styles.settingsHint}>
                        Use your computer's IP if on physical device
                    </Text>
                </View>
            )}

            <View style={styles.content}>
                {/* Countdown overlay */}
                {countdown !== null && (
                    <View style={styles.countdownOverlay}>
                        <Text style={styles.countdownText}>
                            {countdown === -1 ? 'GO!' : countdown === 0 ? 'GO!' : countdown}
                        </Text>
                        <Text style={styles.countdownSub}>
                            {countdown === -1 || countdown === 0 ? '🔥 Let\'s see those feet!' : 'Get your feet ready!'}
                        </Text>
                    </View>
                )}

                {/* Judging state — overlay on camera preview */}
                {agent.isJudging && (
                    <ScrollView
                        style={styles.judgingOverlayScroll}
                        contentContainerStyle={styles.judgingOverlay}
                        showsVerticalScrollIndicator={false}
                    >
                        {/* Live AI commentary bubble */}
                        <View style={styles.commentaryBox}>
                            <Text style={styles.commentaryText}>
                                {agent.liveCommentary || '🤖 Waiting for AI...'}
                            </Text>
                        </View>

                        {/* Timer */}
                        <View style={styles.statsRow}>
                            <View style={styles.stepCounter}>
                                <Text style={styles.stepCountText}>⏱ {formatTime(elapsed)}</Text>
                            </View>
                        </View>

                        <VibeMeter level={agent.vibeLevel} />

                        {/* Final score card (appears when AI gives verdict) */}
                        {agent.score !== null && agent.verdict !== null && (
                            <ScoreCard score={agent.score} verdict={agent.verdict} />
                        )}

                        <TouchableOpacity style={styles.stopButton} onPress={stopJudging}>
                            <Text style={styles.stopButtonText}>⏹ STOP SESSION</Text>
                        </TouchableOpacity>
                    </ScrollView>
                )}

                {/* Farewell screen — shows roast after stopping */}
                {farewellMode && !agent.isJudging && (
                    <View style={styles.farewellContent}>
                        <Text style={styles.farewellIcon}>🎤💀</Text>
                        <Text style={styles.farewellTitle}>SESSION OVER</Text>
                        <View style={styles.farewellBox}>
                            <Text style={styles.farewellText}>
                                {agent.liveCommentary || 'Peace out, dancer!'}
                            </Text>
                        </View>
                        <Text style={styles.farewellTimer}>⏱ {formatTime(elapsed)}</Text>
                        <Text style={styles.farewellHint}>Returning to menu...</Text>
                    </View>
                )}

                {/* Idle state */}
                {!agent.isJudging && !farewellMode && countdown === null && (
                    <View style={styles.idleContent}>
                        <Text style={styles.cameraIcon}>📹</Text>
                        <Text style={styles.idleTitle}>Ready for Coaching</Text>
                        <Text style={styles.idleHint}>
                            Place your phone on the floor with camera facing up, then hit
                            start. The AI Coach will give real-time feedback on your footwork!
                        </Text>
                        <TouchableOpacity
                            style={styles.startButton}
                            onPress={startCountdown}
                        >
                            <Text style={styles.startButtonText}>🎤 START</Text>
                        </TouchableOpacity>
                    </View>
                )}
            </View>
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#0a0a0a',
        paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight : 0,
    },
    cameraFill: {
        ...StyleSheet.absoluteFillObject,
        top: Platform.OS === 'android' ? (StatusBar.currentHeight || 0) : 0,
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 20,
        paddingTop: 16,
        paddingBottom: 8,
        zIndex: 10,
    },
    backButton: {
        paddingVertical: 8,
        paddingRight: 16,
    },
    backText: {
        color: '#e94560',
        fontSize: 16,
        fontWeight: '600',
    },
    settingsIcon: {
        fontSize: 22,
    },
    liveIndicator: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 20,
        gap: 8,
    },
    liveDot: {
        width: 10,
        height: 10,
        borderRadius: 5,
        backgroundColor: '#e94560',
    },
    liveText: {
        color: '#e94560',
        fontWeight: '800',
        fontSize: 14,
    },
    timerText: {
        color: '#aaa',
        fontSize: 14,
        fontVariant: ['tabular-nums'],
    },
    // Settings
    settingsBox: {
        marginHorizontal: 20,
        marginBottom: 12,
        backgroundColor: '#1a1a2e',
        borderRadius: 12,
        padding: 16,
        zIndex: 10,
    },
    settingsLabel: {
        color: '#aaa',
        fontSize: 12,
        marginBottom: 6,
        textTransform: 'uppercase',
        letterSpacing: 1,
    },
    settingsInput: {
        backgroundColor: '#0d1b2a',
        borderRadius: 8,
        padding: 12,
        color: '#fff',
        fontSize: 14,
        borderWidth: 1,
        borderColor: '#2a2a4e',
    },
    settingsHint: {
        color: '#666',
        fontSize: 11,
        marginTop: 6,
    },
    content: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: 24,
    },
    // Countdown
    countdownOverlay: {
        alignItems: 'center',
    },
    countdownText: {
        fontSize: 120,
        fontWeight: '900',
        color: '#e94560',
    },
    countdownSub: {
        fontSize: 18,
        color: '#aaa',
        marginTop: 16,
    },
    // Judging overlay on camera
    judgingOverlayScroll: {
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        maxHeight: '55%',
    },
    judgingOverlay: {
        paddingHorizontal: 20,
        paddingBottom: 40,
        paddingTop: 8,
        alignItems: 'center',
    },
    commentaryBox: {
        backgroundColor: 'rgba(26, 26, 46, 0.95)',
        borderRadius: 16,
        padding: 20,
        marginBottom: 16,
        borderLeftWidth: 4,
        borderLeftColor: '#e94560',
        width: '100%',
        minHeight: 60,
    },
    commentaryText: {
        color: '#fff',
        fontSize: 20,
        fontWeight: '700',
        textAlign: 'center',
        lineHeight: 28,
    },
    statsRow: {
        flexDirection: 'row',
        gap: 12,
        marginBottom: 12,
    },
    stepCounter: {
        backgroundColor: 'rgba(26, 26, 46, 0.85)',
        paddingHorizontal: 20,
        paddingVertical: 8,
        borderRadius: 20,
        marginBottom: 12,
    },
    stepCountText: {
        color: '#e94560',
        fontSize: 16,
        fontWeight: '800',
        letterSpacing: 1,
    },
    stopButton: {
        marginTop: 16,
        backgroundColor: 'rgba(192, 57, 43, 0.9)',
        paddingHorizontal: 40,
        paddingVertical: 16,
        borderRadius: 30,
    },
    stopButtonText: {
        color: '#fff',
        fontSize: 18,
        fontWeight: '800',
        letterSpacing: 1,
    },
    // Farewell screen after stopping
    farewellContent: {
        alignItems: 'center',
        paddingHorizontal: 20,
    },
    farewellIcon: {
        fontSize: 64,
        marginBottom: 16,
    },
    farewellTitle: {
        fontSize: 32,
        fontWeight: '900',
        color: '#e94560',
        marginBottom: 20,
        letterSpacing: 2,
    },
    farewellBox: {
        backgroundColor: 'rgba(26, 26, 46, 0.95)',
        borderRadius: 16,
        padding: 24,
        marginBottom: 20,
        borderLeftWidth: 4,
        borderLeftColor: '#e94560',
        width: '100%',
    },
    farewellText: {
        color: '#fff',
        fontSize: 18,
        fontWeight: '600',
        textAlign: 'center',
        lineHeight: 26,
    },
    farewellTimer: {
        color: '#888',
        fontSize: 18,
        fontWeight: '600',
        marginBottom: 8,
    },
    farewellHint: {
        color: '#666',
        fontSize: 14,
        fontStyle: 'italic',
    },
    // Idle
    idleContent: {
        alignItems: 'center',
    },
    cameraIcon: {
        fontSize: 64,
        marginBottom: 16,
    },
    idleTitle: {
        fontSize: 28,
        fontWeight: '800',
        color: '#fff',
        marginBottom: 12,
    },
    idleHint: {
        color: '#888',
        fontSize: 16,
        textAlign: 'center',
        lineHeight: 24,
        marginBottom: 32,
        paddingHorizontal: 20,
    },
    startButton: {
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
        fontSize: 22,
        fontWeight: '800',
        color: '#fff',
        letterSpacing: 2,
    },
});
