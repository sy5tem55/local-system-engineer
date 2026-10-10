<script lang="ts">
  import { z } from 'zod';
  import { createMutation, createQuery, useQueryClient } from '@tanstack/svelte-query';
  import { trpc } from '$lib/trpc/client';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert';
  import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '$lib/components/ui/table';
  import { Button } from '$lib/components/ui/button';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';

  const searchSchema = z.object({
    q: z.string().min(1, 'Query is required').max(512),
    limit: z.coerce.number().int().min(1).max(100).default(20),
  });
  type SearchInput = z.infer<typeof searchSchema>;
  type Row = {
    ip: string;
    device?: string | null;
    ports?: number[] | string;
    location?: { country?: string; city?: string } | null;
    geo?: { country?: string } | null;
  };
  type ErrorInfo = { title: string; detail: string; hint?: string };

  // --- state -----------------------------------------------------------------
  let query = $state('');
  let limit = $state(20);
  let queryError = $state<string | null>(null);
  let results = $state<Row[]>([]);
  let lastQuery = $state<string | null>(null);
  let errorInfo = $state<ErrorInfo | null>(null);

  const queryClient = useQueryClient();

  // --- tRPC queries -----------------------------------------------------------
  const savedSearchesQuery = createQuery(() => ({
    queryKey: ['saved-searches'],
    queryFn: () => trpc.listSavedSearches.query(),
  }));
  const bookmarksQuery = createQuery(() => ({
    queryKey: ['bookmarks'],
    queryFn: () => trpc.listBookmarks.query(),
  }));
  const historyQuery = createQuery(() => ({
    queryKey: ['history'],
    queryFn: () => trpc.listHistory.query(),
  }));

  const savedSearches = $derived(savedSearchesQuery.data ?? []);
  const bookmarks = $derived(bookmarksQuery.data ?? []);
  const history = $derived(historyQuery.data ?? []);
  const bookmarkedIps = $derived(new Set(bookmarks.map((b) => b.ip)));

  // --- tRPC mutations ----------------------------------------------------------
  const searchMut = createMutation(() => ({
    mutationFn: async (input: SearchInput) => {
      const r = await trpc.search.query.query(input);
      if (!r.ok) {
        const e = new Error((r as { message?: string }).message ?? 'search failed') as Error & { status?: number };
        e.status = r.status;
        throw e;
      }
      const rows = (r.data?.rows ?? []) as Row[];
      return { rows, total: (r.data?.total as number) ?? rows.length };
    },
    onSuccess: (data, input) => {
      results = data.rows;
      lastQuery = input.q;
      errorInfo = null;
      addHistoryMut.mutate({ type: 'search', action: 'run', target: input.q });
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
    onError: (e) => {
      errorInfo = describeError(e);
    },
  }));

  const saveSearchMut = createMutation(() => ({
    mutationFn: (q: string) => trpc.saveSearch.mutate({ query: q }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-searches'] });
    },
    onError: (e) => {
      errorInfo = describeError(e);
    },
  }));

  const deleteSearchMut = createMutation(() => ({
    mutationFn: (id: string) => trpc.deleteSearch.mutate({ id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-searches'] });
    },
  }));

  const bookmarkDeviceMut = createMutation(() => ({
    mutationFn: (d: { ip: string; port: number; product?: string }) =>
      trpc.bookmarkDevice.mutate(d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bookmarks'] });
    },
    onError: (e) => {
      errorInfo = describeError(e);
    },
  }));

  const deleteBookmarkMut = createMutation(() => ({
    mutationFn: (id: string) => trpc.deleteBookmark.mutate({ id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bookmarks'] });
    },
  }));

  const addHistoryMut = createMutation(() => ({
    mutationFn: (h: { type: string; action: string; target: string }) =>
      trpc.addHistory.mutate(h),
  }));

  const deleteHistoryMut = createMutation(() => ({
    mutationFn: (id: string) => trpc.deleteHistory.mutate({ id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  }));

  const clearHistoryMut = createMutation(() => ({
    mutationFn: () => trpc.clearHistory.mutate(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  }));

  // --- helpers ------------------------------------------------------------------
  function describeError(err: unknown): ErrorInfo {
    const e = err as Error & { status?: number; code?: string; data?: { code?: string } };
    const status = e?.status;
    const msg = e?.message ?? String(err);
    if (status === 429) {
      return {
        title: 'Shodan rate limit',
        detail: msg,
        hint: 'Shodan throttled the request — wait a bit, then retry.',
      };
    }
    if (status === 403) {
      return {
        title: 'Shodan blocked the request',
        detail: msg,
        hint: 'Likely IP/data-center blocking. Retry later or use a different network.',
      };
    }
    if (status === 503) {
      return {
        title: 'Shodan key missing',
        detail: msg,
        hint: 'Export SHODAN_API_KEY on the backend and restart it.',
      };
    }
    if (status && status >= 500) {
      return { title: 'Shodan error', detail: msg };
    }
    if (e?.code === 'P2002' || e?.data?.code === 'P2002') {
      return { title: 'Already saved', detail: 'This device is already bookmarked.' };
    }
    return { title: 'Error', detail: msg };
  }

  function onSearchSubmit() {
    const parsed = searchSchema.safeParse({ q: query, limit });
    if (!parsed.success) {
      queryError = parsed.error.issues[0]?.message ?? 'Invalid input';
      return;
    }
    queryError = null;
    searchMut.mutate(parsed.data);
  }

  function runSaved(q: string) {
    query = q;
    onSearchSubmit();
  }

  function portsText(row: Row): string {
    if (Array.isArray(row.ports)) {
      const shown = row.ports.slice(0, 8).join(', ');
      return row.ports.length > 8 ? `${shown} +${row.ports.length - 8}…` : shown;
    }
    return row.ports ? String(row.ports) : '—';
  }

  function locationText(row: Row): string {
    const c = row.location?.country ?? row.geo?.country;
    const city = row.location?.city;
    if (!c && !city) return '—';
    return [city, c].filter(Boolean).join(', ');
  }
</script>

<svelte:head>
  <title>Shodan console</title>
</svelte:head>

<div class="min-h-screen bg-background text-foreground p-6 space-y-8">
  <!-- search bar -->
  <Card>
    <CardHeader class="flex-row items-center justify-between">
      <div>
        <CardTitle>Shodan search</CardTitle>
        <CardDescription>
          Filter with <span class="font-mono">port</span>, <span class="font-mono">vuln</span>,
          <span class="font-mono">ssl</span>, <span class="font-mono">org</span>… — e.g.
          <span class="font-mono">port:22 vuln:openSSL</span>
        </CardDescription>
      </div>
      <span class="text-xs text-muted-foreground">
        {searchMut.isPending ? 'Searching…' : `${results.length} results`}
      </span>
    </CardHeader>
    <CardContent>
      <form
        class="flex flex-wrap gap-3 items-end"
        onsubmit={(e) => {
          e.preventDefault();
          onSearchSubmit();
        }}
      >
        <div class="grow min-w-[240px] space-y-1.5">
          <Label for="shodan-query">Query</Label>
          <Input
            id="shodan-query"
            bind:value={query}
            placeholder="port:22 vuln:openSSL"
            aria-invalid={queryError ? true : undefined}
          />
          {#if queryError}
            <p class="text-xs text-destructive">{queryError}</p>
          {/if}
        </div>
        <div class="w-28 space-y-1.5">
          <Label for="shodan-limit">Limit</Label>
          <Input id="shodan-limit" type="number" min="1" max="100" bind:value={limit} />
        </div>
        <Button type="submit" disabled={searchMut.isPending}>
          {searchMut.isPending ? 'Searching…' : 'Search'}
        </Button>
        {#if lastQuery && !searchMut.isPending}
          <Button type="button" variant="outline" disabled={saveSearchMut.isPending}
            onclick={() => { if (lastQuery) saveSearchMut.mutate(lastQuery); }}>
            {saveSearchMut.isPending ? 'Saving…' : 'Save query'}
          </Button>
        {/if}
      </form>
    </CardContent>
  </Card>

  <!-- error banner -->
  {#if errorInfo}
    <Alert variant="destructive">
      <AlertTitle>{errorInfo.title}</AlertTitle>
      <AlertDescription>
        {errorInfo.detail}{errorInfo.hint ? ` — ${errorInfo.hint}` : ''}
      </AlertDescription>
    </Alert>
  {/if}

  <!-- results table -->
  {#if results.length > 0}
    <Card>
      <CardHeader>
        <CardTitle>Results for “{lastQuery}”</CardTitle>
      </CardHeader>
      <CardContent>
        <div class="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>IP</TableHead>
                <TableHead>Ports</TableHead>
                <TableHead>Device</TableHead>
                <TableHead>Location</TableHead>
                <TableHead class="w-24 text-right">Save</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {#each results as row (row.ip)}
                <TableRow>
                  <TableCell class="font-mono">{row.ip}</TableCell>
                  <TableCell>
                    <span class="font-mono text-xs">{portsText(row)}</span>
                  </TableCell>
                  <TableCell>{row.device ?? '—'}</TableCell>
                  <TableCell class="text-xs">{locationText(row)}</TableCell>
                  <TableCell class="text-right">
                    <Button
                      size="sm"
                      variant={bookmarkedIps.has(row.ip) ? 'secondary' : 'default'}
                      disabled={
                        bookmarkDeviceMut.isPending ||
                        bookmarkedIps.has(row.ip) ||
                        !(Array.isArray(row.ports) ? row.ports.length > 0 : !!row.ports)
                      }
                      onclick={() =>
                        bookmarkDeviceMut.mutate({
                          ip: row.ip,
                          port: Array.isArray(row.ports) ? row.ports[0] : Number(row.ports) || 0,
                          product: row.device ?? undefined,
                        })}
                    >
                      {bookmarkedIps.has(row.ip) ? 'Saved' : 'Save'}
                    </Button>
                  </TableCell>
                </TableRow>
              {/each}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  {:else if !searchMut.isPending}
    <div class="text-muted-foreground text-sm text-center py-12">
      Run a search to see results.
    </div>
  {/if}

  <div class="grid gap-6 lg:grid-cols-3">
    <!-- saved searches -->
    <Card>
      <CardHeader>
        <CardTitle>Saved searches</CardTitle>
      </CardHeader>
      <CardContent class="space-y-2">
        {#each savedSearches as s (s.id)}
          <div class="flex items-center gap-2 text-sm">
            <button
              class="font-mono text-xs hover:underline grow text-left"
              onclick={() => runSaved(s.query)}
            >
              {s.query}
            </button>
            <Button size="sm" variant="ghost" onclick={() => deleteSearchMut.mutate(s.id)}>✕</Button>
          </div>
        {:else}
          <p class="text-xs text-muted-foreground">Search, then hit “Save query”.</p>
        {/each}
      </CardContent>
    </Card>

    <!-- bookmarks -->
    <Card>
      <CardHeader>
        <CardTitle>Bookmarked devices</CardTitle>
      </CardHeader>
      <CardContent class="space-y-2">
        {#each bookmarks as b (b.id)}
          <div class="flex items-center gap-2 text-sm">
            <span class="font-mono text-xs">{b.ip}</span>
            <span class="text-xs text-muted-foreground grow truncate">
              :{b.port}{b.product ? ` · ${b.product}` : ''}
            </span>
            <Button size="sm" variant="ghost" onclick={() => deleteBookmarkMut.mutate(b.id)}>✕</Button>
          </div>
        {:else}
          <p class="text-xs text-muted-foreground">Save devices from results to track them here.</p>
        {/each}
      </CardContent>
    </Card>

    <!-- history -->
    <Card>
      <CardHeader class="flex-row items-center justify-between">
        <CardTitle>Recent actions</CardTitle>
        {#if history.length > 0}
          <Button size="sm" variant="ghost" onclick={() => clearHistoryMut.mutate()}>Clear</Button>
        {/if}
      </CardHeader>
      <CardContent class="space-y-2">
        {#each history.slice(0, 8) as h (h.id)}
          <div class="flex items-center gap-2 text-sm">
            <button
              class="font-mono text-xs hover:underline grow text-left"
              onclick={() => runSaved(h.target)}
            >
              {h.action}: {h.target}
            </button>
            <Button size="sm" variant="ghost" onclick={() => deleteHistoryMut.mutate(h.id)}>✕</Button>
          </div>
        {:else}
          <p class="text-xs text-muted-foreground">Search actions appear here.</p>
        {/each}
      </CardContent>
    </Card>
  </div>
</div>
