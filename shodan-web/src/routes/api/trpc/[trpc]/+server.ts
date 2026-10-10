import { fetchRequestHandler } from '@trpc/server/adapters/fetch';
import type { RequestEvent } from '@sveltejs/kit';
import { appRouter } from '$lib/server/trpc/router';
import { createContext } from '$lib/server/trpc/context';

// Manual tRPC v11 fetch adapter (see trpc_adapter_decision.txt — no
// maintained SvelteKit adapter exists for v11). The [trpc] rest segment
// captures the procedure path (e.g. /api/trpc/search.query); tRPC reads
// the full path from event.url.
function trpcHandler(event: RequestEvent) {
  return fetchRequestHandler({
    endpoint: '/api/trpc',
    req: event.request,
    router: appRouter,
    createContext: async () => createContext({ event }),
  });
}

export const GET = trpcHandler;
export const POST = trpcHandler;
export const DELETE = trpcHandler;
