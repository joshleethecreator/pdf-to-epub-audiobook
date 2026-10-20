/** Matches app-bundle/book.json written by the generator. */
export type Segment = {
  text: string;
  /** Paragraph index within the chapter; -1 is the spoken chapter title. */
  p: number;
  start: number;
  end: number;
};

export type Chapter = {
  title: string;
  audio: string;
  duration: number;
  segments: Segment[];
};

export type Book = {
  format: 'pdf2audiobook';
  version: number;
  id: string;
  title: string;
  author: string;
  cover: string | null;
  duration: number;
  chapters: Chapter[];
};

export type LibraryEntry = {
  id: string;
  title: string;
  author: string;
  duration: number;
  chapterCount: number;
  hasCover: boolean;
  addedAt: number;
};

export type Progress = {
  chapter: number;
  position: number;
  updatedAt: number;
  /** Share of the whole book listened to, 0..1 (for the library list). */
  fraction?: number;
  finished?: boolean;
};
