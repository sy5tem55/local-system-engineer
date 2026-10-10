import { initTRPC, TRPCError } from '@trpc/server';
import type { Context } from './context';

const t = initTRPC.context<Context>().create({
  errorFormatter({ shape, error }) {
    // Surface the machine-readable TRPC error code to the browser client.
    return {
      ...shape,
      data: {
        ...shape.data,
        code: error.code,
        ...(error instanceof TRPCError ? { message: error.message } : {}),
      },
    };
  },
});

export const router = t.router;
export const publicProcedure = t.procedure;
