import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { downloadRemote, importFromFiles, listRemote, type RemoteBook } from '../importer';
import {
  bookFile,
  loadLibrary,
  loadProgress,
  loadSettings,
  removeFromLibrary,
  saveSettings,
} from '../storage';
import { formatDuration, useTheme, type Theme } from '../theme';
import type { LibraryEntry, Progress } from '../types';

type Props = { onOpen: (id: string) => void };

export default function LibraryScreen({ onOpen }: Props) {
  const t = useTheme();
  const s = styles(t);
  const [books, setBooks] = useState<LibraryEntry[]>([]);
  const [progress, setProgress] = useState<Record<string, Progress | null>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [serverOpen, setServerOpen] = useState(false);

  const refresh = useCallback(async () => {
    const lib = await loadLibrary();
    setBooks(lib);
    const entries = await Promise.all(lib.map(async (b) => [b.id, await loadProgress(b.id)] as const));
    setProgress(Object.fromEntries(entries));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const lastPlayed = books
    .filter((b) => progress[b.id] && !progress[b.id]?.finished)
    .sort((a, b) => (progress[b.id]?.updatedAt ?? 0) - (progress[a.id]?.updatedAt ?? 0))[0];

  async function onImportFiles() {
    try {
      setBusy('Importing…');
      const book = await importFromFiles();
      if (book) await refresh();
    } catch (e) {
      Alert.alert('Import failed', String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  }

  function confirmDelete(b: LibraryEntry) {
    Alert.alert('Remove book?', `"${b.title}" and its audio will be deleted from this phone.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          await removeFromLibrary(b.id);
          refresh();
        },
      },
    ]);
  }

  return (
    <SafeAreaView style={s.root} edges={['top', 'left', 'right']}>
      <Text style={s.h1}>Library</Text>

      {lastPlayed && (
        <Pressable style={s.continue} onPress={() => onOpen(lastPlayed.id)}>
          <Text style={s.continueLabel}>CONTINUE LISTENING</Text>
          <Text style={s.continueTitle} numberOfLines={1}>
            {lastPlayed.title}
          </Text>
          <Text style={s.continueMeta}>
            Chapter {(progress[lastPlayed.id]?.chapter ?? 0) + 1} of {lastPlayed.chapterCount} ·{' '}
            {Math.round(fractionOf(lastPlayed, progress[lastPlayed.id]) * 100)}% done
          </Text>
        </Pressable>
      )}

      <FlatList
        data={books}
        keyExtractor={(b) => b.id}
        contentContainerStyle={books.length ? s.list : s.emptyList}
        ListEmptyComponent={
          <View style={s.empty}>
            <Text style={s.emptyTitle}>No books yet</Text>
            <Text style={s.emptyText}>
              Generate one on your computer with{'\n'}
              <Text style={s.mono}>python -m pdf2audiobook generate book.pdf</Text>
              {'\n\n'}then import it below.
            </Text>
          </View>
        }
        renderItem={({ item }) => {
          const frac = fractionOf(item, progress[item.id]);
          const cover = item.hasCover ? bookFile(item.id, 'cover.jpg') : null;
          return (
            <Pressable style={s.row} onPress={() => onOpen(item.id)} onLongPress={() => confirmDelete(item)}>
              {cover?.exists ? (
                <Image source={{ uri: cover.uri }} style={s.cover} />
              ) : (
                <View style={[s.cover, s.coverPlaceholder]}>
                  <Text style={s.coverLetter}>{item.title.slice(0, 1)}</Text>
                </View>
              )}
              <View style={s.rowBody}>
                <Text style={s.title} numberOfLines={2}>
                  {item.title}
                </Text>
                <Text style={s.meta} numberOfLines={1}>
                  {item.author} · {item.chapterCount} chapters · {formatDuration(item.duration)}
                </Text>
                <View style={s.bar}>
                  <View style={[s.barFill, { width: `${frac * 100}%` }]} />
                </View>
                <Text style={s.meta}>{frac >= 1 ? 'Finished' : frac > 0 ? `${Math.round(frac * 100)}%` : 'Not started'}</Text>
              </View>
            </Pressable>
          );
        }}
      />

      <View style={s.actions}>
        <Pressable style={[s.btn, s.btnPrimary]} onPress={() => setServerOpen(true)}>
          <Text style={s.btnPrimaryText}>Import from computer (Wi-Fi)</Text>
        </Pressable>
        <Pressable style={s.btn} onPress={onImportFiles}>
          <Text style={s.btnText}>Import files from phone</Text>
        </Pressable>
        <Text style={s.hint}>Long-press a book to remove it.</Text>
      </View>

      <ServerImport
        visible={serverOpen}
        onClose={() => setServerOpen(false)}
        onImported={() => {
          setServerOpen(false);
          refresh();
        }}
      />

      {busy && (
        <View style={s.overlay}>
          <ActivityIndicator color={t.accent} size="large" />
          <Text style={s.overlayText}>{busy}</Text>
        </View>
      )}
    </SafeAreaView>
  );
}

function fractionOf(entry: LibraryEntry, p: Progress | null | undefined): number {
  if (!p) return 0;
  if (p.finished) return 1;
  return p.fraction ?? p.chapter / Math.max(1, entry.chapterCount);
}

function ServerImport({
  visible,
  onClose,
  onImported,
}: {
  visible: boolean;
  onClose: () => void;
  onImported: () => void;
}) {
  const t = useTheme();
  const s = styles(t);
  const [url, setUrl] = useState('');
  const [remote, setRemote] = useState<RemoteBook[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (visible) {
      loadSettings().then((st) => setUrl(st.serverUrl));
      setRemote(null);
      setError(null);
    }
  }, [visible]);

  async function connect() {
    setError(null);
    setStatus('Connecting…');
    try {
      const books = await listRemote(url);
      setRemote(books);
      await saveSettings({ serverUrl: url });
    } catch (e) {
      setError(
        `Couldn't reach ${url}. Is \`python -m pdf2audiobook serve\` running, and are both devices on the same Wi-Fi?\n\n(${String((e as Error).message ?? e)})`,
      );
    } finally {
      setStatus(null);
    }
  }

  async function download(b: RemoteBook) {
    try {
      await downloadRemote(url, b, (done, total) => setStatus(`Downloading ${b.title}… ${done}/${total} files`));
      onImported();
    } catch (e) {
      setError(`Download failed: ${String((e as Error).message ?? e)}`);
    } finally {
      setStatus(null);
    }
  }

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} presentationStyle="pageSheet">
      <SafeAreaView style={s.root}>
        <View style={s.modalHeader}>
          <Text style={s.h2}>Import from computer</Text>
          <Pressable onPress={onClose} hitSlop={12}>
            <Text style={s.link}>Close</Text>
          </Pressable>
        </View>
        <Text style={s.emptyText}>
          On your computer run <Text style={s.mono}>python -m pdf2audiobook serve</Text> and type the address it prints:
        </Text>
        <TextInput
          style={s.input}
          value={url}
          onChangeText={setUrl}
          placeholder="http://192.168.1.20:8765"
          placeholderTextColor={t.muted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          onSubmitEditing={connect}
        />
        <Pressable style={[s.btn, s.btnPrimary]} onPress={connect} disabled={!url || !!status}>
          <Text style={s.btnPrimaryText}>Connect</Text>
        </Pressable>
        {error && <Text style={s.error}>{error}</Text>}
        {status && (
          <View style={s.statusRow}>
            <ActivityIndicator color={t.accent} />
            <Text style={s.meta}> {status}</Text>
          </View>
        )}
        {remote && (
          <FlatList
            data={remote}
            keyExtractor={(b) => b.id}
            ListEmptyComponent={<Text style={s.emptyText}>No finished books in the output folder yet.</Text>}
            renderItem={({ item }) => (
              <Pressable style={s.row} onPress={() => download(item)} disabled={!!status}>
                <View style={s.rowBody}>
                  <Text style={s.title}>{item.title}</Text>
                  <Text style={s.meta}>
                    {item.author} · {item.chapters} chapters · {formatDuration(item.duration)}
                  </Text>
                </View>
                <Text style={s.link}>Download</Text>
              </Pressable>
            )}
          />
        )}
      </SafeAreaView>
    </Modal>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: t.bg, paddingHorizontal: 16 },
    h1: { fontSize: 32, fontWeight: '700', color: t.text, marginTop: 12, marginBottom: 12 },
    h2: { fontSize: 22, fontWeight: '700', color: t.text },
    continue: { backgroundColor: t.accent, borderRadius: 14, padding: 16, marginBottom: 12 },
    continueLabel: { color: t.accentText, opacity: 0.8, fontSize: 11, fontWeight: '700', letterSpacing: 1 },
    continueTitle: { color: t.accentText, fontSize: 18, fontWeight: '700', marginTop: 4 },
    continueMeta: { color: t.accentText, opacity: 0.85, marginTop: 2 },
    list: { paddingBottom: 12 },
    emptyList: { flexGrow: 1, justifyContent: 'center' },
    empty: { alignItems: 'center', padding: 24 },
    emptyTitle: { fontSize: 18, fontWeight: '600', color: t.text, marginBottom: 8 },
    emptyText: { color: t.muted, textAlign: 'center', lineHeight: 20, marginVertical: 8 },
    mono: { fontFamily: 'monospace', color: t.text },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: t.card,
      borderRadius: 12,
      padding: 12,
      marginBottom: 10,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
    },
    cover: { width: 56, height: 80, borderRadius: 6, marginRight: 12, backgroundColor: t.border },
    coverPlaceholder: { alignItems: 'center', justifyContent: 'center' },
    coverLetter: { fontSize: 24, fontWeight: '700', color: t.muted },
    rowBody: { flex: 1 },
    title: { fontSize: 16, fontWeight: '600', color: t.text },
    meta: { fontSize: 13, color: t.muted, marginTop: 2 },
    bar: { height: 4, backgroundColor: t.border, borderRadius: 2, marginTop: 8, overflow: 'hidden' },
    barFill: { height: 4, backgroundColor: t.accent },
    actions: { paddingVertical: 12 },
    btn: {
      borderRadius: 12,
      paddingVertical: 14,
      alignItems: 'center',
      marginTop: 8,
      borderWidth: 1,
      borderColor: t.border,
      backgroundColor: t.card,
    },
    btnText: { color: t.text, fontWeight: '600', fontSize: 15 },
    btnPrimary: { backgroundColor: t.accent, borderColor: t.accent },
    btnPrimaryText: { color: t.accentText, fontWeight: '700', fontSize: 15 },
    hint: { color: t.muted, fontSize: 12, textAlign: 'center', marginTop: 8 },
    overlay: {
      ...StyleSheet.absoluteFill,
      backgroundColor: 'rgba(0,0,0,0.45)',
      alignItems: 'center',
      justifyContent: 'center',
    },
    overlayText: { color: '#fff', marginTop: 12, fontSize: 15 },
    modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginVertical: 16 },
    link: { color: t.accent, fontWeight: '600', fontSize: 15 },
    input: {
      borderWidth: 1,
      borderColor: t.border,
      backgroundColor: t.card,
      color: t.text,
      borderRadius: 10,
      padding: 12,
      fontSize: 16,
      marginTop: 8,
    },
    error: { color: t.danger, marginTop: 12, lineHeight: 20 },
    statusRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12 },
  });
