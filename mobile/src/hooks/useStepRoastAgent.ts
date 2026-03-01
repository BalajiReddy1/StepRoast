import { useState, useCallback, useRef, useEffect } from 'react';
import {
    StreamVideoClient,
    Call,
} from '@stream-io/video-react-native-sdk';
import { StreamChat, Channel } from 'stream-chat';

// Default — will be overridden at runtime via the settings input
const DEFAULT_BACKEND_URL = 'https://orange-yodel-gjp6g6q9grr29v4w-8000.app.github.dev';

interface StepRoastState {
    isConnected: boolean;
    isJudging: boolean;
    score: number | null;
    verdict: string | null;
    vibeLevel: number;
    liveCommentary: string | null;
    error: string | null;
    stepCount: number;
}

interface TokenResponse {
    token: string;
    user_id: string;
    api_key: string;
}

interface MetricsResponse {
    step_count: number;
    avg_speed: number;
    current_speed: number;
    frame_count: number;
    persons_detected: number;
    summary: string;
    commentary?: string;
    all_commentary?: string[];
}

/**
 * Clamp a value to 0–100 and compute a "vibe" percentage from foot speed.
 */
function speedToVibe(avgSpeed: number): number {
    // 0 speed → 0 vibe, 40+ speed → 100 vibe
    return Math.min(100, Math.max(0, Math.round((avgSpeed / 40) * 100)));
}

export function useStepRoastAgent() {
    const [state, setState] = useState<StepRoastState>({
        isConnected: false,
        isJudging: false,
        score: null,
        verdict: null,
        vibeLevel: 0,
        liveCommentary: null,
        error: null,
        stepCount: 0,
    });

    const clientRef = useRef<StreamVideoClient | null>(null);
    const callRef = useRef<Call | null>(null);
    const chatClientRef = useRef<StreamChat | null>(null);
    const chatChannelRef = useRef<Channel | null>(null);
    const sessionIdRef = useRef<string | null>(null);
    const isStartingRef = useRef<boolean>(false);
    const metricsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const backendUrlRef = useRef<string>(DEFAULT_BACKEND_URL);
    
    // Accumulate chat fragments into complete sentences
    const chatBufferRef = useRef<string>('');
    const lastCompleteRef = useRef<string>('');

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (metricsIntervalRef.current) clearInterval(metricsIntervalRef.current);
            if (chatChannelRef.current) chatChannelRef.current.stopWatching().catch(() => {});
            if (chatClientRef.current) chatClientRef.current.disconnectUser().catch(() => {});
            if (callRef.current) callRef.current.leave().catch(() => {});
            if (clientRef.current) clientRef.current.disconnectUser().catch(() => {});
        };
    }, []);

    // ── Poll /metrics for vibe meter + step count + AI commentary ─────
    const startMetricsPolling = useCallback((url: string) => {
        if (metricsIntervalRef.current) clearInterval(metricsIntervalRef.current);
        metricsIntervalRef.current = setInterval(async () => {
            try {
                const res = await fetch(`${url}/metrics`);
                if (!res.ok) return;
                const data: MetricsResponse = await res.json();
                
                // DEBUG: log what we're getting
                console.log('[METRICS]', JSON.stringify({ commentary: data.commentary, all: data.all_commentary?.length }));
                
                setState(prev => {
                    const newCommentary = data.commentary && data.commentary.length > 0
                        ? `🎤 ${data.commentary}`
                        : prev.liveCommentary;
                    
                    // DEBUG: log state update
                    if (newCommentary !== prev.liveCommentary) {
                        console.log('[STATE UPDATE] liveCommentary:', newCommentary);
                    }
                    
                    return {
                        ...prev,
                        vibeLevel: speedToVibe(data.avg_speed),
                        stepCount: data.step_count,
                        liveCommentary: newCommentary,
                    };
                });
            } catch {
                // silently ignore — metrics are best-effort
            }
        }, 1000); // poll every 1s for snappy updates
    }, []);

    const stopMetricsPolling = useCallback(() => {
        if (metricsIntervalRef.current) {
            clearInterval(metricsIntervalRef.current);
            metricsIntervalRef.current = null;
        }
    }, []);

    // ── Connect to Stream ──────────────────────────────────────────────
    const connect = useCallback(async (backendUrl: string) => {
        try {
            setState(prev => ({ ...prev, error: null, liveCommentary: 'Connecting to StepRoast...' }));

            const url = backendUrl || DEFAULT_BACKEND_URL;
            backendUrlRef.current = url;
            const res = await fetch(`${url}/token?user_id=mobile-dancer`);
            if (!res.ok) throw new Error(`Token request failed: ${res.status}`);
            const data: TokenResponse = await res.json();

            const client = StreamVideoClient.getOrCreateInstance({
                apiKey: data.api_key,
                user: { id: data.user_id, name: 'Dancer' },
                token: data.token,
            });
            clientRef.current = client;

            setState(prev => ({ ...prev, isConnected: true, liveCommentary: 'Connected! Ready to dance.' }));
            return client;
        } catch (err: any) {
            const msg = err.message || 'Connection failed';
            setState(prev => ({ ...prev, error: msg, liveCommentary: null }));
            throw err;
        }
    }, []);

    // ── Start judging session ──────────────────────────────────────────
    const startJudging = useCallback(async (backendUrl: string) => {
        if (isStartingRef.current) return;
        isStartingRef.current = true;
        try {
            setState(prev => ({ ...prev, error: null, liveCommentary: 'Connecting...' }));
            
            // Reset chat buffers for new session
            chatBufferRef.current = '';
            lastCompleteRef.current = '';

            // Fresh start
            if (clientRef.current) {
                await clientRef.current.disconnectUser().catch(() => {});
                clientRef.current = null;
            }

            const url = backendUrl || DEFAULT_BACKEND_URL;
            backendUrlRef.current = url;
            const client = await connect(url) as StreamVideoClient;

            // Create & join call
            const callId = `steproast-${Date.now()}`;
            const call = client.call('default', callId);
            await call.join({ create: true });
            callRef.current = call;

            // Show camera immediately — no waiting
            setState(prev => ({
                ...prev,
                isJudging: true,
                score: null,
                verdict: null,
                vibeLevel: 0,
                stepCount: 0,
                liveCommentary: '🎥 Camera is live!',
            }));

            // Enable camera + mic in parallel
            await Promise.all([
                call.camera.enable(),
                call.microphone.enable(),
            ]);

            setState(prev => ({ ...prev, liveCommentary: '🤖 Summoning the AI judge...' }));

            // Reduced stabilization wait (agent-side handles its own delay)
            await new Promise(resolve => setTimeout(resolve, 1500));

            // Spawn the AI agent into this call
            const sessionRes = await fetch(`${url}/sessions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ call_id: callId, call_type: 'default' }),
            });

            if (!sessionRes.ok) {
                const errData = await sessionRes.json().catch(() => ({}));
                throw new Error(errData.detail || `Session start failed: ${sessionRes.status}`);
            }

            const sessionData = await sessionRes.json();
            sessionIdRef.current = sessionData.session_id;

            // Connect to Stream Chat to receive AI roasts
            // (Backend posts commentary to Chat channel, not custom events)
            try {
                const tokenRes = await fetch(`${url}/token?user_id=mobile-dancer`);
                const tokenData: TokenResponse = await tokenRes.json();
                
                const chatClient = StreamChat.getInstance(tokenData.api_key);
                await chatClient.connectUser(
                    { id: tokenData.user_id, name: 'Dancer' },
                    tokenData.token
                );
                chatClientRef.current = chatClient;
                
                const channel = chatClient.channel('messaging', callId);
                await channel.watch();
                chatChannelRef.current = channel;
                
                channel.on('message.new', (event) => {
                    const text = event.message?.text;
                    if (text) {
                        // Accumulate fragments into sentences
                        chatBufferRef.current += text;
                        const trimmed = chatBufferRef.current.trim();
                        const wordCount = trimmed.split(/\s+/).filter(w => w.length > 0).length;
                        const isComplete = /[.!?]$/.test(trimmed);
                        
                        // Show text once we have 2+ words OR sentence is complete
                        // This gives ~1-2 sec response time instead of 6-8 sec
                        if (wordCount >= 2 || isComplete) {
                            const typingCursor = isComplete ? '' : ' ▌';
                            setState(prev => ({
                                ...prev,
                                liveCommentary: `🎤 ${trimmed}${typingCursor}`,
                            }));
                        }
                        
                        // Reset buffer when sentence is complete
                        if (isComplete) {
                            lastCompleteRef.current = trimmed;
                            chatBufferRef.current = '';
                        }
                    }
                });
                console.log('[CHAT] Listening to channel:', callId);
            } catch (chatErr) {
                console.warn('[CHAT] Failed to connect:', chatErr);
            }

            setState(prev => ({
                ...prev,
                liveCommentary: '🔥 AI Coach is ready. Show me your moves!',
            }));

            // Reset starting flag — session is live now
            isStartingRef.current = false;

            // Start polling metrics for vibe meter + AI commentary
            startMetricsPolling(url);

            // Listen for custom events from the agent (text commentary)
            call.on('custom', (event: any) => {
                try {
                    const payload = event?.custom;
                    if (!payload) return;

                    if (payload.type === 'commentary' && payload.text) {
                        setState(prev => ({
                            ...prev,
                            liveCommentary: payload.text,
                        }));
                    }

                    if (payload.type === 'score' && payload.score != null) {
                        setState(prev => ({
                            ...prev,
                            score: payload.score,
                            verdict: payload.verdict || null,
                        }));
                    }
                } catch {
                    // ignore malformed events
                }
            });
        } catch (err: any) {
            isStartingRef.current = false;
            const msg = err.message || 'Failed to start judging';
            setState(prev => ({ ...prev, error: msg, isJudging: false, liveCommentary: null }));
        }
    }, [connect, startMetricsPolling]);

    // ── Stop coaching ───────────────────────────────────────────────────
    const FAREWELL_MESSAGES = [
        "Great session! Those feet are getting sharper. See you next time! 💪",
        "Nice work! Keep practicing and you'll be unstoppable. 🔥",
        "Session complete! Remember: every pro started as a beginner. Keep going! 🌟",
        "That's a wrap! Your footwork is improving — I can tell. 👏",
        "Good effort today! Come back tomorrow and let's level up. 📈",
        "See you next time! Those ankles have potential. 🎯",
        "Session ended. Keep that energy and practice makes perfect! ⚡",
        "Until next time! The floor felt that workout. 💯",
    ];

    const stopJudging = useCallback(async (backendUrl: string) => {
        try {
            stopMetricsPolling();
            isStartingRef.current = false;

            // Show farewell message immediately
            const farewellMsg = FAREWELL_MESSAGES[Math.floor(Math.random() * FAREWELL_MESSAGES.length)];
            setState(prev => ({
                ...prev,
                liveCommentary: `🎤 ${farewellMsg}`,
            }));

            // End the agent session on backend
            if (sessionIdRef.current) {
                const url = backendUrl || backendUrlRef.current;
                console.log('[STOP] Deleting session:', sessionIdRef.current);
                try {
                    const res = await fetch(`${url}/sessions/${sessionIdRef.current}`, {
                        method: 'DELETE',
                    });
                    console.log('[STOP] Session DELETE response:', res.status);
                } catch (e) {
                    console.warn('[STOP] Session DELETE failed:', e);
                }
                sessionIdRef.current = null;
            }

            // Disconnect from Stream Chat
            if (chatChannelRef.current) {
                await chatChannelRef.current.stopWatching().catch(() => {});
                chatChannelRef.current = null;
            }
            if (chatClientRef.current) {
                await chatClientRef.current.disconnectUser().catch(() => {});
                chatClientRef.current = null;
            }
            
            // Reset chat buffer
            chatBufferRef.current = '';
            lastCompleteRef.current = '';

            // Leave the call
            if (callRef.current) {
                await callRef.current.leave();
                callRef.current = null;
            }

            // Keep farewell showing, but mark as not judging
            setState(prev => ({
                ...prev,
                isJudging: false,
            }));
        } catch (err: any) {
            setState(prev => ({ ...prev, isJudging: false, error: err.message }));
        }
    }, [stopMetricsPolling]);

    const getClient = useCallback(() => clientRef.current, []);
    const getCall = useCallback(() => callRef.current, []);

    return {
        ...state,
        connect,
        startJudging,
        stopJudging,
        getClient,
        getCall,
    };
}
