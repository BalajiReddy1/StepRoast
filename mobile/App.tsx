import React, { useState, useRef } from 'react';
import { StatusBar } from 'expo-status-bar';
import HomeScreen from './src/screens/HomeScreen';
import JudgeScreen from './src/screens/JudgeScreen';
import { useStepRoastAgent } from './src/hooks/useStepRoastAgent';

export default function App() {
  const [screen, setScreen] = useState<'home' | 'judge'>('home');
  const agent = useStepRoastAgent();

  return (
    <>
      {screen === 'home' ? (
        <HomeScreen onStart={() => setScreen('judge')} />
      ) : (
        <JudgeScreen
          onBack={() => {
            agent.stopJudging('');
            setScreen('home');
          }}
          agent={agent}
        />
      )}
      <StatusBar style="light" />
    </>
  );
}
