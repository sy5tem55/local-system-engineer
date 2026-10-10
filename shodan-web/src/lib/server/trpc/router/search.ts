import { z } from 'zod';
import { router, publicProcedure } from '../trpc';

export const searchRouter = router({
  query: publicProcedure
    .input(
      z.object({
        q: z.string(),
        limit: z.number().int().min(1).max(100).default(20),
      }),
    )
    .query(async ({ input }) => {
      // Only outbound call in the app: local Shodan MCP server proxy.
      // The Python endpoint reads the `query` param (see
      // tools/shodan_mcp_server.py api_search), not `q`.
      const url = `http://127.0.0.1:9702/api/search?query=${encodeURIComponent(input.q)}&limit=${input.limit}`;
      let res: Response;
      try {
        res = await fetch(url);
      } catch {
        // Backend unreachable (process down) — map to backend-down.
        return { ok: false, status: 0, message: 'backend down', data: null };
      }
      if (!res.ok) {
        return {
          ok: false,
          status: res.status,
          message:
            res.status === 503
              ? 'missing key'
              : res.status === 429
                ? 'rate limit'
                : 'backend down',
          data: null,
        };
      }
      const data = await res.json();
      return { ok: true, status: 200, data };
    }),
});
