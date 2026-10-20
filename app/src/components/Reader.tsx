import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View, type ListViewToken } from 'react-native';

import { useTheme, type Theme } from '../theme';
import type { Chapter, Segment } from '../types';

type Item = { key: string; p: number; segs: { idx: number; seg: Segment }[] };

type Props = {
  chapter: Chapter;
  /** Index into chapter.segments of the sentence being spoken. */
  activeSegment: number;
  fontSize: number;
  onSeek: (seconds: number) => void;
};

/** Find the segment playing at `time` (binary search over segment starts). */
export function segmentAt(chapter: Chapter, time: number): number {
  const segs = chapter.segments;
  let lo = 0;
  let hi = segs.length - 1;
  let ans = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segs[mid].start <= time + 0.05) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}

export default function Reader({ chapter, activeSegment, fontSize, onSeek }: Props) {
  const t = useTheme();
  const s = useMemo(() => styles(t, fontSize), [t, fontSize]);
  const list = useRef<FlatList<Item>>(null);
  const [follow, setFollow] = useState(true);
  const [visible, setVisible] = useState<number[]>([]);

  const items = useMemo(() => {
    const out: Item[] = [];
    chapter.segments.forEach((seg, idx) => {
      const last = out[out.length - 1];
      if (last && last.p === seg.p) last.segs.push({ idx, seg });
      else out.push({ key: `${seg.p}:${idx}`, p: seg.p, segs: [{ idx, seg }] });
    });
    return out;
  }, [chapter]);

  const segToItem = useMemo(() => {
    const m: number[] = [];
    items.forEach((it, i) => it.segs.forEach(({ idx }) => (m[idx] = i)));
    return m;
  }, [items]);

  const activeItem = segToItem[activeSegment] ?? 0;

  // Keep the spoken sentence on screen while "follow along" is on.
  useEffect(() => {
    if (!follow || !items.length) return;
    list.current?.scrollToIndex({ index: activeItem, viewPosition: 0.3, animated: true });
  }, [activeItem, follow, items.length]);

  // New chapter: start following again from its top.
  useEffect(() => {
    setFollow(true);
  }, [chapter]);

  const onViewable = useRef(({ viewableItems }: { viewableItems: ListViewToken[] }) => {
    setVisible(viewableItems.map((v) => v.index ?? -1).filter((i) => i >= 0));
  }).current;

  const activeOffScreen = visible.length > 0 && !visible.includes(activeItem);

  return (
    <View style={s.root}>
      <FlatList
        ref={list}
        data={items}
        keyExtractor={(it) => it.key}
        contentContainerStyle={s.content}
        onScrollBeginDrag={() => setFollow(false)}
        onViewableItemsChanged={onViewable}
        initialNumToRender={20}
        windowSize={15}
        onScrollToIndexFailed={({ index, averageItemLength }) => {
          list.current?.scrollToOffset({ offset: index * averageItemLength, animated: false });
          setTimeout(() => list.current?.scrollToIndex({ index, viewPosition: 0.3, animated: true }), 100);
        }}
        renderItem={({ item, index }) => (
          <Paragraph
            item={item}
            active={index === activeItem ? activeSegment : -1}
            styles={s}
            onSeek={onSeek}
          />
        )}
        ListFooterComponent={<View style={{ height: 200 }} />}
      />
      {(!follow || activeOffScreen) && (
        <Pressable
          style={s.followBtn}
          onPress={() => {
            setFollow(true);
            list.current?.scrollToIndex({ index: activeItem, viewPosition: 0.3, animated: true });
          }}
        >
          <Text style={s.followText}>↓ Follow along</Text>
        </Pressable>
      )}
    </View>
  );
}

const Paragraph = memo(function Paragraph({
  item,
  active,
  styles: s,
  onSeek,
}: {
  item: Item;
  active: number;
  styles: ReturnType<typeof styles>;
  onSeek: (seconds: number) => void;
}) {
  const isTitle = item.p < 0;
  return (
    <Text style={isTitle ? s.title : s.para}>
      {item.segs.map(({ idx, seg }, i) => (
        <Text key={idx} style={idx === active ? s.active : undefined} onPress={() => onSeek(seg.start)}>
          {i > 0 ? ' ' : ''}
          {seg.text}
        </Text>
      ))}
    </Text>
  );
});

const styles = (t: Theme, fontSize: number) =>
  StyleSheet.create({
    root: { flex: 1 },
    content: { paddingHorizontal: 20, paddingTop: 12 },
    title: {
      fontSize: fontSize * 1.5,
      fontWeight: '700',
      color: t.text,
      textAlign: 'center',
      marginVertical: 24,
      fontFamily: 'serif',
    },
    para: {
      fontSize,
      lineHeight: fontSize * 1.6,
      color: t.text,
      marginBottom: fontSize * 0.9,
      fontFamily: 'serif',
    },
    active: { backgroundColor: t.highlight, color: t.text },
    followBtn: {
      position: 'absolute',
      alignSelf: 'center',
      bottom: 12,
      backgroundColor: t.accent,
      paddingHorizontal: 16,
      paddingVertical: 8,
      borderRadius: 20,
    },
    followText: { color: t.accentText, fontWeight: '700' },
  });
