import { router, publicProcedure } from '../trpc';
import { searchRouter } from './search';
import {
  saveSearch,
  listSavedSearches,
  deleteSearch,
  bookmarkDevice,
  listBookmarks,
  deleteBookmark,
  addHistory,
  listHistory,
  deleteHistory,
  clearHistory,
} from './persistence';

export const appRouter = router({
  health: publicProcedure.query(() => 'ok'),
  search: searchRouter,
  saveSearch,
  listSavedSearches,
  deleteSearch,
  bookmarkDevice,
  listBookmarks,
  deleteBookmark,
  addHistory,
  listHistory,
  deleteHistory,
  clearHistory,
});

export type AppRouter = typeof appRouter;
