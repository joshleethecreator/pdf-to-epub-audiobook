import AsyncStorage from '@react-native-async-storage/async-storage';
import { Directory, File, Paths } from 'expo-file-system';

import type { Book, LibraryEntry, Progress } from './types';

const LIBRARY_KEY = 'library:v1';
const progressKey = (id: string) => `progress:v1:${id}`;
const SETTINGS_KEY = 'settings:v1';

export const booksRoot = () => new Directory(Paths.document, 'books');
export const bookDir = (id: string) => new Directory(Paths.document, 'books', id);
export const bookFile = (id: string, name: string) => new File(bookDir(id), name);

export async function loadLibrary(): Promise<LibraryEntry[]> {
  const raw = await AsyncStorage.getItem(LIBRARY_KEY);
  return raw ? (JSON.parse(raw) as LibraryEntry[]) : [];
}

export async function saveLibrary(entries: LibraryEntry[]): Promise<void> {
  await AsyncStorage.setItem(LIBRARY_KEY, JSON.stringify(entries));
}

export async function addToLibrary(book: Book): Promise<void> {
  const lib = (await loadLibrary()).filter((b) => b.id !== book.id);
  lib.unshift({
    id: book.id,
    title: book.title,
    author: book.author,
    duration: book.duration,
    chapterCount: book.chapters.length,
    hasCover: !!book.cover,
    addedAt: Date.now(),
  });
  await saveLibrary(lib);
}

export async function removeFromLibrary(id: string): Promise<void> {
  await saveLibrary((await loadLibrary()).filter((b) => b.id !== id));
  await AsyncStorage.removeItem(progressKey(id));
  const dir = bookDir(id);
  if (dir.exists) dir.delete();
}

export async function loadBook(id: string): Promise<Book> {
  return JSON.parse(await bookFile(id, 'book.json').text()) as Book;
}

export async function loadProgress(id: string): Promise<Progress | null> {
  const raw = await AsyncStorage.getItem(progressKey(id));
  return raw ? (JSON.parse(raw) as Progress) : null;
}

export async function saveProgress(id: string, progress: Progress): Promise<void> {
  await AsyncStorage.setItem(progressKey(id), JSON.stringify(progress));
}

export type Settings = { rate: number; serverUrl: string };
const DEFAULT_SETTINGS: Settings = { rate: 1, serverUrl: '' };

export async function loadSettings(): Promise<Settings> {
  const raw = await AsyncStorage.getItem(SETTINGS_KEY);
  return { ...DEFAULT_SETTINGS, ...(raw ? JSON.parse(raw) : {}) };
}

export async function saveSettings(patch: Partial<Settings>): Promise<void> {
  await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...(await loadSettings()), ...patch }));
}

/** Overall progress through the book, 0..1. */
export function bookFraction(book: Pick<Book, 'chapters' | 'duration'>, p: Progress | null): number {
  if (!p || !book.duration) return 0;
  if (p.finished) return 1;
  const before = book.chapters.slice(0, p.chapter).reduce((s, c) => s + c.duration, 0);
  return Math.min(1, (before + p.position) / book.duration);
}
