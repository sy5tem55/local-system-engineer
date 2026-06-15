export default {
  async onCommand(e, ctx) {
    if (!ctx.net) return { content: "ERR: no net capability" };
    return { content: await ctx.net.fetchText(e.args) };
  },
};
