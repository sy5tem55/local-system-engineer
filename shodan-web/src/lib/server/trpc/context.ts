import { PrismaClient } from '@prisma/client';
import { browser } from '$app/environment';
import type { RequestEvent } from '@sveltejs/kit';

// Singleton so HMR in dev doesn't open a new SQLite connection per reload.
// The generated client lives at node_modules/.prisma/client (re-exported by
// '@prisma/client'); the `file:./dev.db` URL in prisma/schema.prisma is
// resolved relative to the schema file by the generated client, so no
// runtime path juggling is needed.
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (!browser) globalForPrisma.prisma = prisma;

export const createContext = async (_opts: { event: RequestEvent }) => {
  return {
    prisma,
  };
};

export type Context = Awaited<ReturnType<typeof createContext>>;
