import { z } from 'zod';
import { publicProcedure } from '../trpc';

// All procedures are explicit user-initiated actions. No procedure here
// auto-logs anything — history entries are only created via addHistory,
// which the UI calls on explicit user actions only.

export const saveSearch = publicProcedure
  .input(z.object({ query: z.string().min(1) }))
  .mutation(async ({ ctx, input }) => {
    return ctx.prisma.savedSearch.create({ data: { query: input.query } });
  });

export const listSavedSearches = publicProcedure.query(async ({ ctx }) => {
  return ctx.prisma.savedSearch.findMany({ orderBy: { createdAt: 'desc' } });
});

export const deleteSearch = publicProcedure
  .input(z.object({ id: z.string() }))
  .mutation(async ({ ctx, input }) => {
    await ctx.prisma.savedSearch.delete({ where: { id: input.id } });
    return { deleted: true };
  });

export const bookmarkDevice = publicProcedure
  .input(
    z.object({
      ip: z.string(),
      port: z.number().int(),
      product: z.string().optional(),
    }),
  )
  .mutation(async ({ ctx, input }) => {
    return ctx.prisma.bookmarkedDevice.create({ data: input });
  });

export const listBookmarks = publicProcedure.query(async ({ ctx }) => {
  return ctx.prisma.bookmarkedDevice.findMany({ orderBy: { createdAt: 'desc' } });
});

export const deleteBookmark = publicProcedure
  .input(z.object({ id: z.string() }))
  .mutation(async ({ ctx, input }) => {
    await ctx.prisma.bookmarkedDevice.delete({ where: { id: input.id } });
    return { deleted: true };
  });

export const addHistory = publicProcedure
  .input(z.object({ type: z.string(), action: z.string(), target: z.string() }))
  .mutation(async ({ ctx, input }) => {
    return ctx.prisma.historyEntry.create({ data: input });
  });

export const listHistory = publicProcedure.query(async ({ ctx }) => {
  return ctx.prisma.historyEntry.findMany({ orderBy: { timestamp: 'desc' } });
});

export const deleteHistory = publicProcedure
  .input(z.object({ id: z.string() }))
  .mutation(async ({ ctx, input }) => {
    await ctx.prisma.historyEntry.delete({ where: { id: input.id } });
    return { deleted: true };
  });

export const clearHistory = publicProcedure.mutation(async ({ ctx }) => {
  const result = await ctx.prisma.historyEntry.deleteMany();
  return { deletedCount: result.count };
});
