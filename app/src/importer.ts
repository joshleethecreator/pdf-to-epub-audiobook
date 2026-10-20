import * as DocumentPicker from 'expo-document-picker';
import { File } from 'expo-file-system';

import { addToLibrary, bookDir, bookFile } from './storage';
import type { Book } from './types';

function validate(data: unknown): Book {
  const b = data as Book;
  if (!b || b.format !== 'pdf2audiobook' || !Array.isArray(b.chapters) || !b.id) {
    throw new Error("That book.json wasn't made by pdf2audiobook.");
  }
  return b;
}

function requiredFiles(book: Book): string[] {
  return ['book.json', ...(book.cover ? [book.cover] : []), ...book.chapters.map((c) => c.audio)];
}

/**
 * Import from the phone's storage: the user selects every file inside an
 * `app-bundle` folder (book.json, cover.jpg, ch001.m4a, ...).
 */
export async function importFromFiles(): Promise<Book | null> {
  const res = await DocumentPicker.getDocumentAsync({ multiple: true, copyToCacheDirectory: true, type: '*/*' });
  if (res.canceled) return null;
  const byName = new Map(res.assets.map((a) => [a.name, a]));
  const json = byName.get('book.json');
  if (!json) throw new Error('Select all files in the app-bundle folder, including book.json.');

  const book = validate(JSON.parse(await new File(json.uri).text()));
  const missing = requiredFiles(book).filter((n) => n !== book.cover && !byName.has(n));
  if (missing.length) {
    throw new Error(`Missing ${missing.length} file(s): ${missing.slice(0, 4).join(', ')}${missing.length > 4 ? '…' : ''}`);
  }

  const dir = bookDir(book.id);
  if (!dir.exists) dir.create({ intermediates: true });
  for (const name of requiredFiles(book)) {
    const asset = byName.get(name);
    if (!asset) continue; // optional cover
    const dest = bookFile(book.id, name);
    if (dest.exists) dest.delete();
    new File(asset.uri).move(dest);
  }
  await addToLibrary(book);
  return book;
}

export type RemoteBook = {
  id: string;
  title: string;
  author: string;
  duration: number;
  chapters: number;
  path: string;
  files: string[];
};

export function normalizeUrl(url: string): string {
  let u = url.trim().replace(/\/+$/, '');
  if (!/^https?:\/\//.test(u)) u = `http://${u}`;
  return u;
}

/** List the books offered by `pdf2audiobook serve` on the computer. */
export async function listRemote(baseUrl: string): Promise<RemoteBook[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${normalizeUrl(baseUrl)}/library.json`, { signal: controller.signal });
    if (!res.ok) throw new Error(`Server answered ${res.status}`);
    return ((await res.json()) as { books: RemoteBook[] }).books;
  } finally {
    clearTimeout(timer);
  }
}

export async function downloadRemote(
  baseUrl: string,
  remote: RemoteBook,
  onProgress: (done: number, total: number) => void,
): Promise<Book> {
  const base = `${normalizeUrl(baseUrl)}/${remote.path}`;
  const dir = bookDir(remote.id);
  if (!dir.exists) dir.create({ intermediates: true });
  let done = 0;
  for (const name of remote.files) {
    onProgress(done, remote.files.length);
    await File.downloadFileAsync(base + encodeURIComponent(name), bookFile(remote.id, name), { idempotent: true });
    done += 1;
  }
  onProgress(done, remote.files.length);
  const book = validate(JSON.parse(await bookFile(remote.id, 'book.json').text()));
  await addToLibrary(book);
  return book;
}
