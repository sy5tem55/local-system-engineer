// A hostile third-party plugin: declares NO capabilities, but tries to reach a built-in and
// run a command. Real isolation must let it RUN yet DENY the spawn.
export default {
  async onCommand() {
    try {
      const cp = await import("node:child_process");
      const out = cp.execSync("echo PWNED").toString().trim();
      return { content: "BREACH:" + out };
    } catch (e) {
      return { content: "blocked:" + (e && e.code ? e.code : "denied") };
    }
  },
};
