// src/index.ts — Entry point: npm start
import { openStore } from "./db.js";
import { makeLiveModelClient } from "./model_live.js";
import { createServer } from "./server.js";

const DB_PATH = process.env.DB_PATH ?? "data/gate2.sqlite";
const PORT = Number(process.env.PORT ?? 8787);

async function main() {
  const store = openStore(DB_PATH);
  const model = makeLiveModelClient();
  const server = createServer({ store, model });

  const port = await server.listen(PORT);
  console.log(`Group server listening on ${server.url()}`);

  // Graceful shutdown
  process.on("SIGINT", async () => {
    console.log("\nShutting down...");
    await server.close();
    store.close();
    process.exit(0);
  });

  process.on("SIGTERM", async () => {
    console.log("\nShutting down...");
    await server.close();
    store.close();
    process.exit(0);
  });
}

main().catch((err) => {
  console.error("Failed to start:", err);
  process.exit(1);
});
