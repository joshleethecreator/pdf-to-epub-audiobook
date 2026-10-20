import Ionicons from '@expo/vector-icons/Ionicons';
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  AppState,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
  type GestureResponderEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import Reader, { segmentAt } from '../components/Reader';
import { bookFile, bookFraction, loadBook, loadProgress, loadSettings, saveProgress, saveSettings } from '../storage';
import { formatDuration, formatTime, useTheme, type Theme } from '../theme';
import type { Book } from '../types';

const RATES = [0.8, 1, 1.15, 1.25, 1.5, 1.75, 2];
const SLEEP_OPTIONS = [0, 15, 30, 45, 60]; // minutes; 0 = off
const FONT_SIZES = [15, 17, 19, 22, 25];

type Props = { bookId: string; onBack: () => void };

/** Where we want the player to be once the (new) chapter file has loaded. */
type Pending = { chapter: number; position: number; play: boolean };

export default function BookScreen({ bookId, onBack }: Props) {
  const t = useTheme();
  const s = useMemo(() => styles(t), [t]);

  const [book, setBook] = useState<Book | null>(null);
  const [chapter, setChapter] = useState(0);
  const [tab, setTab] = useState<'read' | 'chapters'>('read');
  const [rate, setRate] = useState(1);
  const [fontIdx, setFontIdx] = useState(1);
  const [sleepAt, setSleepAt] = useState<number | null>(null);
  const [sleepIdx, setSleepIdx] = useState(0);
  const pending = useRef<Pending | null>(null);

  // Load the book and the saved position.
  useEffect(() => {
    let alive = true;
    (async () => {
      const [b, p, st] = await Promise.all([loadBook(bookId), loadProgress(bookId), loadSettings()]);
      if (!alive) return;
      const ch = p && !p.finished ? Math.min(p.chapter, b.chapters.length - 1) : 0;
      pending.current = { chapter: ch, position: p && !p.finished ? p.position : 0, play: false };
      setRate(st.rate);
      setChapter(ch);
      setBook(b);
    })();
    return () => {
      alive = false;
    };
  }, [bookId]);

  useEffect(() => {
    setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: true, interruptionMode: 'doNotMix' });
  }, []);

  const current = book?.chapters[chapter];
  const source = useMemo(() => (book && current ? { uri: bookFile(book.id, current.audio).uri } : null), [book, current]);
  // A new source creates a fresh player (the hook releases the old one).
  const player = useAudioPlayer(source, { updateInterval: 250 });
  const status = useAudioPlayerStatus(player);

  // Lock screen / notification controls.
  useEffect(() => {
    if (!book || !current) return;
    try {
      player.setActiveForLockScreen(
        true,
        { title: current.title, artist: book.author, albumTitle: book.title },
        { showSeekBackward: true, showSeekForward: true },
      );
    } catch {
      // not supported on this platform (e.g. web)
    }
  }, [player, book, current]);

  // Apply a pending seek/play once the chapter file is ready.
  useEffect(() => {
    const p = pending.current;
    if (!status.isLoaded || !p || p.chapter !== chapter) return;
    pending.current = null;
    player.setPlaybackRate(rate);
    (async () => {
      if (p.position > 0) await player.seekTo(p.position);
      if (p.play) player.play();
    })();
  }, [status.isLoaded, chapter, player, rate]);

  // ----- progress saving ---------------------------------------------------
  const latest = useRef({ chapter, position: 0 });
  latest.current = { chapter, position: status.currentTime || latest.current.position };

  const persist = useCallback(
    (finished = false) => {
      if (!book || pending.current) return; // don't overwrite the saved spot before we've restored it
      const p = { chapter: latest.current.chapter, position: latest.current.position, updatedAt: Date.now() };
      saveProgress(book.id, { ...p, fraction: bookFraction(book, p), finished });
    },
    [book],
  );

  useEffect(() => {
    if (!status.playing) return;
    const id = setInterval(() => persist(), 5000);
    return () => clearInterval(id);
  }, [status.playing, persist]);

  useEffect(() => {
    if (!status.playing) persist(); // paused
  }, [status.playing, persist]);

  useEffect(() => {
    const sub = AppState.addEventListener('change', (st) => st !== 'active' && persist());
    return () => {
      sub.remove();
      persist();
    };
  }, [persist]);

  // ----- navigation ----------------------------------------------------------
  const goTo = useCallback(
    (ch: number, position: number, play: boolean) => {
      if (!book) return;
      ch = Math.max(0, Math.min(book.chapters.length - 1, ch));
      if (ch === chapter) {
        player.seekTo(Math.max(0, position));
        if (play) player.play();
      } else {
        pending.current = { chapter: ch, position, play };
        latest.current = { chapter: ch, position };
        setChapter(ch);
      }
    },
    [book, chapter, player],
  );

  // Auto-advance at the end of a chapter.
  useEffect(() => {
    if (!status.didJustFinish || !book) return;
    if (chapter < book.chapters.length - 1) {
      goTo(chapter + 1, 0, true);
    } else {
      persist(true);
    }
  }, [status.didJustFinish]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sleep timer.
  useEffect(() => {
    if (!sleepAt) return;
    const id = setInterval(() => {
      if (Date.now() >= sleepAt) {
        player.pause();
        setSleepAt(null);
        setSleepIdx(0);
      }
    }, 1000);
    return () => clearInterval(id);
  }, [sleepAt, player]);

  const skip = (delta: number) => {
    const target = status.currentTime + delta;
    if (target < 0 && chapter > 0 && book) {
      goTo(chapter - 1, book.chapters[chapter - 1].duration + target, status.playing);
    } else if (book && current && target > current.duration && chapter < book.chapters.length - 1) {
      goTo(chapter + 1, 0, status.playing);
    } else {
      player.seekTo(Math.max(0, target));
    }
  };

  const playingRef = useRef(false);
  playingRef.current = status.playing;
  // Stable so the reader's memoized paragraphs don't all re-render on every status tick.
  const seekInChapter = useCallback((sec: number) => goTo(chapter, sec, playingRef.current), [goTo, chapter]);

  const togglePlay = () => (status.playing ? player.pause() : player.play());

  const cycleRate = () => {
    const next = RATES[(RATES.indexOf(rate) + 1) % RATES.length] ?? 1;
    setRate(next);
    player.setPlaybackRate(next);
    saveSettings({ rate: next });
  };

  const cycleSleep = () => {
    const idx = (sleepIdx + 1) % SLEEP_OPTIONS.length;
    setSleepIdx(idx);
    setSleepAt(SLEEP_OPTIONS[idx] ? Date.now() + SLEEP_OPTIONS[idx] * 60_000 : null);
  };

  const [barWidth, setBarWidth] = useState(1);
  const onBarPress = (e: GestureResponderEvent) => {
    if (!current) return;
    player.seekTo((e.nativeEvent.locationX / barWidth) * (status.duration || current.duration));
  };

  if (!book || !current) {
    return (
      <SafeAreaView style={[s.root, s.center]}>
        <ActivityIndicator color={t.accent} size="large" />
      </SafeAreaView>
    );
  }

  const time = pending.current?.chapter === chapter ? pending.current.position : status.currentTime;
  const duration = status.duration || current.duration;
  const active = segmentAt(current, time);
  const sleepLeft = sleepAt ? Math.max(0, Math.ceil((sleepAt - Date.now()) / 60_000)) : 0;

  return (
    <SafeAreaView style={s.root} edges={['top', 'left', 'right', 'bottom']}>
      <View style={s.header}>
        <Pressable onPress={onBack} hitSlop={12} style={s.headerBtn}>
          <Ionicons name="chevron-back" size={26} color={t.text} />
        </Pressable>
        <View style={s.headerMid}>
          <Text style={s.bookTitle} numberOfLines={1}>
            {book.title}
          </Text>
          <Text style={s.chapterTitle} numberOfLines={1}>
            {current.title}
          </Text>
        </View>
        <Pressable onPress={() => setFontIdx((fontIdx + 1) % FONT_SIZES.length)} hitSlop={12} style={s.headerBtn}>
          <Ionicons name="text" size={22} color={t.text} />
        </Pressable>
      </View>

      <View style={s.tabs}>
        {(['read', 'chapters'] as const).map((k) => (
          <Pressable key={k} onPress={() => setTab(k)} style={[s.tab, tab === k && s.tabActive]}>
            <Text style={[s.tabText, tab === k && s.tabTextActive]}>{k === 'read' ? 'Read' : 'Chapters'}</Text>
          </Pressable>
        ))}
      </View>

      <View style={s.body}>
        {tab === 'read' ? (
          <Reader
            chapter={current}
            activeSegment={active}
            fontSize={FONT_SIZES[fontIdx]}
            onSeek={seekInChapter}
          />
        ) : (
          <FlatList
            data={book.chapters}
            keyExtractor={(_, i) => String(i)}
            initialScrollIndex={Math.max(0, chapter - 3)}
            getItemLayout={(_, i) => ({ length: 60, offset: 60 * i, index: i })}
            renderItem={({ item, index }) => (
              <Pressable
                style={[s.chRow, index === chapter && s.chRowActive]}
                onPress={() => {
                  goTo(index, 0, status.playing);
                  setTab('read');
                }}
              >
                <Text style={[s.chNum, index < chapter && s.chDone]}>{index + 1}</Text>
                <Text style={[s.chTitle, index === chapter && s.chTitleActive]} numberOfLines={1}>
                  {item.title}
                </Text>
                <Text style={s.chDur}>{formatDuration(item.duration)}</Text>
              </Pressable>
            )}
          />
        )}
      </View>

      <View style={s.player}>
        <Pressable onPress={onBarPress} onLayout={(e) => setBarWidth(e.nativeEvent.layout.width)} style={s.barTouch}>
          <View style={s.bar}>
            <View style={[s.barFill, { width: `${Math.min(100, (time / Math.max(1, duration)) * 100)}%` }]} />
          </View>
        </Pressable>
        <View style={s.times}>
          <Text style={s.time}>{formatTime(time)}</Text>
          <Text style={s.time}>
            Ch {chapter + 1}/{book.chapters.length} · {Math.round(bookFraction(book, { chapter, position: time, updatedAt: 0 }) * 100)}%
          </Text>
          <Text style={s.time}>-{formatTime(duration - time)}</Text>
        </View>

        <View style={s.controls}>
          <Pressable onPress={() => goTo(chapter - 1, 0, status.playing)} disabled={chapter === 0} hitSlop={8}>
            <Ionicons name="play-skip-back" size={26} color={chapter === 0 ? t.border : t.text} />
          </Pressable>
          <Pressable onPress={() => skip(-15)} hitSlop={8}>
            <Ionicons name="play-back" size={30} color={t.text} />
            <Text style={s.skipLabel}>15</Text>
          </Pressable>
          <Pressable onPress={togglePlay} style={s.playBtn}>
            <Ionicons name={status.playing ? 'pause' : 'play'} size={34} color={t.accentText} />
          </Pressable>
          <Pressable onPress={() => skip(30)} hitSlop={8}>
            <Ionicons name="play-forward" size={30} color={t.text} />
            <Text style={s.skipLabel}>30</Text>
          </Pressable>
          <Pressable
            onPress={() => goTo(chapter + 1, 0, status.playing)}
            disabled={chapter >= book.chapters.length - 1}
            hitSlop={8}
          >
            <Ionicons
              name="play-skip-forward"
              size={26}
              color={chapter >= book.chapters.length - 1 ? t.border : t.text}
            />
          </Pressable>
        </View>

        <View style={s.extras}>
          <Pressable onPress={cycleRate} style={s.pill}>
            <Text style={s.pillText}>{rate}×</Text>
          </Pressable>
          <Pressable onPress={cycleSleep} style={[s.pill, sleepAt ? s.pillOn : null]}>
            <Ionicons name="moon" size={14} color={sleepAt ? t.accentText : t.text} />
            <Text style={[s.pillText, sleepAt ? { color: t.accentText } : null]}>
              {sleepAt ? ` ${sleepLeft} min` : ' Sleep'}
            </Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: t.bg },
    center: { alignItems: 'center', justifyContent: 'center' },
    header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 8, paddingVertical: 6 },
    headerBtn: { padding: 8 },
    headerMid: { flex: 1, alignItems: 'center' },
    bookTitle: { color: t.muted, fontSize: 12 },
    chapterTitle: { color: t.text, fontSize: 16, fontWeight: '600' },
    tabs: { flexDirection: 'row', marginHorizontal: 16, borderRadius: 10, backgroundColor: t.card, padding: 3 },
    tab: { flex: 1, paddingVertical: 7, alignItems: 'center', borderRadius: 8 },
    tabActive: { backgroundColor: t.accent },
    tabText: { color: t.muted, fontWeight: '600' },
    tabTextActive: { color: t.accentText },
    body: { flex: 1 },
    chRow: {
      height: 60,
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 20,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: t.border,
    },
    chRowActive: { backgroundColor: t.highlight },
    chNum: { width: 36, color: t.muted, fontVariant: ['tabular-nums'] },
    chDone: { color: t.accent },
    chTitle: { flex: 1, color: t.text, fontSize: 15 },
    chTitleActive: { fontWeight: '700' },
    chDur: { color: t.muted, fontSize: 13, marginLeft: 8 },
    player: {
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: t.border,
      backgroundColor: t.card,
      paddingHorizontal: 20,
      paddingTop: 6,
      paddingBottom: 8,
    },
    barTouch: { paddingVertical: 10 },
    bar: { height: 4, borderRadius: 2, backgroundColor: t.border, overflow: 'hidden' },
    barFill: { height: 4, backgroundColor: t.accent },
    times: { flexDirection: 'row', justifyContent: 'space-between' },
    time: { color: t.muted, fontSize: 12, fontVariant: ['tabular-nums'] },
    controls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', marginTop: 8 },
    skipLabel: { color: t.muted, fontSize: 10, textAlign: 'center', marginTop: -2 },
    playBtn: {
      width: 64,
      height: 64,
      borderRadius: 32,
      backgroundColor: t.accent,
      alignItems: 'center',
      justifyContent: 'center',
    },
    extras: { flexDirection: 'row', justifyContent: 'center', gap: 12, marginTop: 10 },
    pill: {
      flexDirection: 'row',
      alignItems: 'center',
      borderWidth: 1,
      borderColor: t.border,
      borderRadius: 16,
      paddingHorizontal: 14,
      paddingVertical: 5,
    },
    pillOn: { backgroundColor: t.accent, borderColor: t.accent },
    pillText: { color: t.text, fontWeight: '600', fontSize: 13 },
  });
