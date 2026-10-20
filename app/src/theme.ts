import { useColorScheme } from 'react-native';

const light = {
  bg: '#FAF7F2',
  card: '#FFFFFF',
  text: '#1F1B16',
  muted: '#7A7168',
  border: '#E6DFD5',
  accent: '#C2551E',
  accentText: '#FFFFFF',
  highlight: '#FBE3C9',
  danger: '#B3261E',
};

const dark: typeof light = {
  bg: '#141210',
  card: '#1F1C19',
  text: '#EDE6DD',
  muted: '#9C9288',
  border: '#332E29',
  accent: '#F08A4B',
  accentText: '#1A120C',
  highlight: '#4A3424',
  danger: '#F2B8B5',
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? dark : light;
}

export function formatTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}
