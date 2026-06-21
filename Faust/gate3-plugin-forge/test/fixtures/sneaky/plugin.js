export default {
  onCommand(_e, ctx) {
    return { content: ctx.net ? "LEAK: net was granted!" : "ok: net correctly withheld" };
  },
};
