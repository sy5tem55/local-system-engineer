// plugins/search/plugin.js — SearXNG search plugin (plain JS, ESM default export)
const SEARXNG_URL = "http://localhost:8088";

export default {
  async onCommand(e, ctx) {
    const query = e.args.trim();
    if (!query) {
      return { content: "Usage: `/search <query>`" };
    }

    try {
      const url = `${SEARXNG_URL}/search?q=${encodeURIComponent(query)}&format=json&categories=general&engines=google&time_range=month`;
      const raw = await ctx.net.fetchText(url);
      const data = JSON.parse(raw);

      const results = (data.results || []).slice(0, 8);
      if (results.length === 0) {
        return { content: `No results found for: \`${query}\`` };
      }

      let lines = [`**Search results for:** \`${query}\` (${results.length} found)\n`];
      for (let i = 0; i < results.length; i++) {
        const r = results[i];
        const title = r.title || "(no title)";
        const link = r.url || "#";
        const snippet = (r.content || "").slice(0, 180);
        lines.push(`${i + 1}. [${title}](${link})`);
        if (snippet) lines.push(`   ${snippet}`);
        lines.push("");
      }

      return { content: lines.join("\n"), kind: "text" };
    } catch (err) {
      return { content: `Search failed: ${err.message}`, kind: "text" };
    }
  },
};
