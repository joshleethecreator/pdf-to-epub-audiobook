# Audiobook Reader (mobile app)

Expo / React Native app for books made by the [generator](../generator).
See the [main README](../README.md#2-put-it-on-your-phone) for how to run it and import books.

- `src/screens/LibraryScreen.tsx` — library, "continue listening", Wi-Fi and file import
- `src/screens/BookScreen.tsx` — player (speed, sleep timer, chapters, lock screen), saves your position every few seconds and whenever you pause or leave the app
- `src/components/Reader.tsx` — chapter text with the spoken sentence highlighted; tap a sentence to jump there
- `src/importer.ts`, `src/storage.ts` — importing bundles and storing books/progress on the phone

```bash
npm install
npx expo start        # then scan the QR code with Expo Go
npm run typecheck
```

Note: Android blocks plain `http://` in release builds by default. Expo Go and
development builds allow it; for a release build, add `expo-build-properties` with
`android.usesCleartextTraffic: true` if you want Wi-Fi import, or use file import.
