import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import BookScreen from './src/screens/BookScreen';
import LibraryScreen from './src/screens/LibraryScreen';

export default function App() {
  const [openBook, setOpenBook] = useState<string | null>(null);
  return (
    <SafeAreaProvider>
      <StatusBar style="auto" />
      {openBook ? (
        <BookScreen key={openBook} bookId={openBook} onBack={() => setOpenBook(null)} />
      ) : (
        <LibraryScreen onOpen={setOpenBook} />
      )}
    </SafeAreaProvider>
  );
}
