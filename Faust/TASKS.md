# TASKS.md — Faust

## Current State

**12 of 12 phases complete. 1 new phase open.**

| Suite | Pass | Fail | Skip |
|-------|------|------|------|
| Gate 3 (`npm test`) | 11 | 0 | 0 |
| Gate 2 (`npm run test:gate2`) | 8 | 0 | 1 (live model test — requires `GATE2_LIVE=1` + `LLAMA_URL`) |

Node: v22.22.3 · Plugins: runner, search · Server: `http://localhost:8787`

## Conventions

- **Read first** — always read the full file before modifying it.
- **Frozen files** — never edit files listed in `CLAUDE.md → FROZEN files`. Violating this breaks cross-gate contracts and will fail acceptance tests.
- **Test-driven** — after each phase, run the `acceptance-cmd`. If it fails, read the error from stderr, fix only files in `files-modify`, retest. Max 3 retry cycles per phase.
- **One change at a time** — one targeted change, then verify. Don't batch modifications.
- **No npm install** — dependencies are already installed. Only run `npm install` if a phase explicitly adds new deps to `package.json`.
- **Native filesystem only** — work in `/home/sy5/projects/Faust/`. Never touch `/mnt/c/` (30× slower, breaks binary permissions).
- **After completing a phase** — update `CLAUDE.md` if any "Key constraints" or counts changed. Keep docs in sync with code.

## Open Tasks

### Phase 9: Room management — delete rooms + clear messages

- **id:** P-9
- **status:** DONE
- **deps:** []
- **files-modify:** `gate2-group-server/src/db.ts`, `gate2-group-server/src/server.ts`, `web/index.html`
- **files-read:** `gate2-group-server/src/protocol.ts` (for Room, Membership shapes), `gate2-group-server/src/schema.ts` (for Message shape)
- **files-frozen:** `gate2-group-server/src/protocol.ts`, `gate2-group-server/src/schema.ts`, `gate2-group-server/test/acceptance.test.ts`, `test/acceptance.test.ts`
- **acceptance-cmd:** `cd /home/sy5/projects/Faust && npm run test:all`
- **acceptance-expected:** Gate 3: 11 pass, 0 fail. Gate 2: 8 pass, 0 fail, 1 skip.
- **on-failure:** Run failing suite with `--test-name-pattern`. Read stderr. Fix only `files-modify`. Do NOT edit frozen files. Max 3 retries.

**Goal:** Room creators can delete rooms and clear all messages in a room. The web client shows controls for both.

**What to do:**

1. Read `gate2-group-server/src/db.ts` fully.

2. In `db.ts`, add `ownerId TEXT` column to the `rooms` table CREATE statement and an `ALTER TABLE rooms ADD COLUMN ownerId TEXT` migration (try/catch).

3. In `db.ts`, update `createRoom(name)` → `createRoom(name, ownerId?)` — store the creator's accountId as `ownerId`.

4. In `db.ts`, add these methods to the `Store` interface and implementation:
   - `getRoomOwner(roomId): string | undefined` — returns the `ownerId` from the rooms table
   - `deleteRoom(roomId): boolean` — deletes the room, its memberships, and its messages. Returns `true` if the room existed.
   - `clearMessages(roomId): void` — deletes all messages in a room by `DELETE FROM messages WHERE room_id = ?`

5. Read `gate2-group-server/src/server.ts` fully.

6. In `server.ts`, update `POST /rooms` to pass `accountId` as the owner: `store.createRoom(b.name!, accountId)`.

7. In `server.ts`, add `DELETE /rooms/:id` route:
   - Verify caller is the room owner (`store.getRoomOwner(roomId) === accountId`). If not, return 403 `"Only the room owner can delete this room"`.
   - Call `store.deleteRoom(roomId)`.
   - Broadcast `{ type: "room_removed", roomId }` to all subscribers.
   - Return `{ ok: true }`.

8. In `server.ts`, add `POST /rooms/:id/clear` route:
   - Verify caller is the room owner. If not, return 403.
   - Call `store.clearMessages(roomId)`.
   - Broadcast `{ type: "room_cleared", roomId }` to all subscribers.
   - Return `{ ok: true }`.

9. Read `web/index.html` fully.

10. In `web/index.html`, add action buttons to the room header (`.roomhdr`):
    - A "🗑" (or "Delete room") button — calls `DELETE /rooms/:id`, then removes the room from the sidebar and resets the chat pane.
    - A "🧹" (or "Clear") button — calls `POST /rooms/:id/clear`, then clears the message pane.

11. In `web/index.html`, handle the new WebSocket frame types in `ws.onmessage`:
    - `room_removed` → remove room from sidebar, if current room then show empty state
    - `room_cleared` → clear the message pane

**Pitfalls:**
- **Do not edit `protocol.ts`** — the `ServerFrame` union type is frozen. New broadcast frame types (`room_removed`, `room_cleared`) are sent as plain JSON via `broadcastToRoom()`. The web client handles them as dynamic JSON. No TypeScript type needed.
- **Do not change the `Room` interface** in `protocol.ts`. The `ownerId` is a DB-level column only — it's not part of the wire contract. The server checks ownership via `getRoomOwner()`, not from the Room object itself.
- **`createRoom` signature change** — `createRoom(name, ownerId?)` is backward-compatible because `ownerId` is optional. Existing tests that call `createRoom(name)` still work.
- **Deleting a room also deletes memberships and messages** — use three DELETE statements in one `deleteRoom()` call, in the right order (messages first → memberships → room) for foreign-key safety.
- **The REST `POST /rooms` route** currently calls `store.createRoom(b.name!)` — change it to `store.createRoom(b.name!, accountId)` where `accountId` is the authenticated user parsed from the Bearer token.

---

### Phase 10: Moderation tools — delete messages + kick users

- **id:** P-10
- **status:** DONE
- **deps:** [P-9] <!-- needs room ownership model from P-9 -->
- **files-modify:** `gate2-group-server/src/db.ts`, `gate2-group-server/src/server.ts`, `web/index.html`
- **files-read:** `gate2-group-server/src/protocol.ts` (for Account, Membership shapes)
- **files-frozen:** `gate2-group-server/src/protocol.ts`, `gate2-group-server/src/schema.ts`, `gate2-group-server/test/acceptance.test.ts`, `test/acceptance.test.ts`
- **acceptance-cmd:** `cd /home/sy5/projects/Faust && npm run test:all`
- **acceptance-expected:** Gate 3: 11 pass, 0 fail. Gate 2: 8 pass, 0 fail, 1 skip.
- **on-failure:** Run failing suite with `--test-name-pattern`. Read stderr. Fix only `files-modify`. Do NOT edit frozen files. Max 3 retries.

**Goal:** Room owners can delete individual messages and kick users from rooms. The web client shows hover-to-reveal delete buttons on messages and a member list with kick controls.

**What to do:**

1. Read `gate2-group-server/src/db.ts` and `gate2-group-server/src/server.ts` fully.

2. In `db.ts`, add these methods to the `Store` interface and implementation:
   - `deleteMessage(messageId): boolean` — deletes a single message by id. Returns `true` if it existed.
   - `removeMember(roomId, accountId): boolean` — deletes the membership row. Returns `true` if it existed.
   - `listMembers(roomId): Array<{accountId: string, joinedAt: number}>` — lists all memberships for a room.

3. In `server.ts`, add `DELETE /rooms/:id/messages/:messageId` route:
   - Verify caller is the room owner. Return 403 if not.
   - Call `store.deleteMessage(messageId)`.
   - Broadcast `{ type: "message_deleted", roomId, messageId }` to all subscribers.
   - Return `{ ok: true }`.

4. In `server.ts`, add `POST /rooms/:id/kick` route:
   - Body: `{ accountId: string }`
   - Verify caller is the room owner. Return 403 if not.
   - Verify the target is a member. Return 404 if not.
   - Cannot kick the room owner. Return 403 if target is the owner.
   - Call `store.removeMember(roomId, targetAccountId)`.
   - Broadcast `{ type: "member_kicked", roomId, accountId: targetAccountId }` to all subscribers.
   - Return `{ ok: true }`.

5. In `server.ts`, add `GET /rooms/:id/members` route:
   - Must be a member to view. Return 403 if not.
   - Call `store.listMembers(roomId)`.
   - Return the membership list as JSON.

6. In `web/index.html`, add a member list panel:
   - Add a "Members" section in the sidebar (below "This room") that shows a list of room members fetched from `GET /rooms/:id/members`.
   - Each member row shows the handle and a "✕" kick button (visible only to the room owner — compare `S.accountId` against the stored owner).
   - Refresh the member list when opening a room and when `member_kicked` / `presence` frames arrive.

7. In `web/index.html`, add per-message delete button:
   - On hover over a `.msg` element, show a small "✕" button in the top-right corner (CSS: position relative on `.msg`, position absolute on the button, `opacity: 0` → `opacity: 1` on `.msg:hover`).
   - Only visible to the room owner — check `S.accountId` against room owner stored in `S.roomOwner`.
   - On click: `DELETE /rooms/:id/messages/:messageId`, then remove the `.msg` element from the DOM.

8. In `web/index.html`, handle new WebSocket frame types:
   - `message_deleted` → find the `.msg` element by message id (`el.dataset.id`) and remove it from the DOM.
   - `member_kicked` → if the kicked user is `S.accountId`, leave the room; otherwise refresh the member list.

9. Store the room owner in client state: when opening a room, fetch `GET /rooms/:id/members` and set `S.roomOwner` from the `ownerId` field. Add `data-id` attribute to each `.msg` element for deletion targeting.

**Pitfalls:**
- **Room owner identity in the web client** — the `GET /rooms/:id/members` response doesn't include `ownerId` unless you add it. Simplest: add `ownerId` to the room data. Since the rooms list already returns room objects, add an `/rooms/:id/info` endpoint that returns `{ ...room, ownerId }` or piggy-back on `GET /rooms` (which returns all rooms with their DB rows). Alternative: the server already stores `ownerId` in the rooms table — just return it. You can add a `GET /rooms/:id` endpoint that includes `ownerId`.
- **Do not edit `protocol.ts`**. Same rule as P-9 — new broadcast frame types are plain JSON.
- **The `messageId` in the DELETE route** — parse it from `pathname` after `/rooms/:id/messages/`. Example: `/rooms/r_abc123/messages/u:joe:1718000000000-abc123`.
- **Kick yourself edge case** — if the owner tries to kick themselves, return 403. If a non-owner kicks someone, return 403.
- **Message `id` format** — messages have ids like `u:joe:1718000000000-abc123`. The colon and special chars need URL-encoding in the DELETE path. The web client should use `encodeURIComponent(messageId)`. The server's route regex needs to match the full id including colons.

---

### Phase 11: Acoustic feedback — sound on join and new messages

- **id:** P-11
- **status:** DONE
- **deps:** [P-9, P-10] <!-- after room management UI is stable -->
- **files-modify:** `web/index.html`
- **files-read:** none (web-client-only change)
- **files-frozen:** all backend files, all test files
- **acceptance-cmd:** `cd /home/sy5/projects/Faust && npm run test:all`
- **acceptance-expected:** Gate 3: 11 pass, 0 fail. Gate 2: 8 pass, 0 fail, 1 skip. (No regression — this is a visual/audio feature.)
- **on-failure:** This phase cannot break existing tests. If tests fail, revert the `web/index.html` change that caused it.

**Goal:** Subtle acoustic feedback when users join/leave rooms and when new messages arrive. A mute toggle in the top bar.

**What to do:**

1. Read `web/index.html` fully.

2. Generate short sound effects using the Web Audio API (oscillator-based — no external audio files needed):
   - **Join chime**: a short ascending two-tone (C5→E5, 80ms each, sine wave, soft gain 0.15). Play when receiving a `presence` frame with `online: true`.
   - **Leave tone**: a short descending tone (E5→C5, 80ms each, sine wave, gain 0.1). Play when receiving a `presence` frame with `online: false`.
   - **Message pop**: a single short sine blip (G5, 60ms, gain 0.08). Play when receiving a new `message` frame (only if the sender is not `S.accountId` — don't self-notify).
   - **Kick alert**: a lower double-beep (A4, 100ms × 2, gain 0.2). Play when receiving a `member_kicked` frame where `accountId === S.accountId`.

3. Create a helper function `playTone(freq, duration, gain, type='sine')` that uses `AudioContext`:
   ```js
   let _actx;
   function playTone(freq, dur, vol=0.1, type='sine'){
     if(!S.soundOn) return;
     if(!_actx) _actx = new (window.AudioContext||window.webkitAudioContext)();
     const o=_actx.createOscillator(), g=_actx.createGain();
     o.type=type; o.frequency.value=freq;
     g.gain.setValueAtTime(vol,_actx.currentTime);
     g.gain.exponentialRampToValueAtTime(0.001,_actx.currentTime+dur);
     o.connect(g); g.connect(_actx.destination);
     o.start(); o.stop(_actx.currentTime+dur);
   }
   ```
   Then compose the multi-tone effects from `playTone()` calls with `setTimeout` for sequencing.

4. Add a `S.soundOn = true` flag and a 🔊/🔇 toggle button in the top bar:
   ```html
   <button id="soundbtn" onclick="toggleSound()">🔊</button>
   ```
   ```js
   function toggleSound(){ S.soundOn=!S.soundOn; $('soundbtn').textContent=S.soundOn?'🔊':'🔇'; }
   ```

5. Wire the sound calls into the existing `ws.onmessage` handler:
   - `type === 'presence'` → play join/leave tone
   - `type === 'message'` → play message pop (if not self)
   - `type === 'member_kicked'` → play kick alert (if self)

6. **Resume AudioContext on first user gesture** — browsers require a user gesture before `AudioContext` can play. Add a one-time `document.addEventListener('click', resumeAudio, {once: true})` that calls `_actx.resume()` if it exists.

**Pitfalls:**
- **AudioContext autoplay policy** — Chrome/Firefox block audio until the user clicks. The one-time click listener above resolves this. Don't try to circumvent it — just resume on first gesture.
- **Don't import audio files** — the Web Audio API oscillator approach keeps the client self-contained (no external files). Pure tones are sufficient for the opencode aesthetic.
- **Keep volumes low** — the opencode aesthetic is subtle, not jarring. Gain values 0.08–0.2 are appropriate.
- **Sound on/off persists across room changes** — `S.soundOn` is a session-level flag, not per-room.
- **Self-notification suppression** — check `m.author.id === S.accountId` before playing the message pop. Don't play sounds for your own messages.

---

### Phase 12: UI animations — message transitions, hover effects, smooth scroll

- **id:** P-12
- **status:** DONE
- **deps:** [P-9, P-10, P-11] <!-- after all feature UI is stable -->
- **files-modify:** `web/index.html`
- **files-read:** `design-tokens/opencode-tokens.json` (for consistent transition timings)
- **files-frozen:** all backend files, all test files
- **acceptance-cmd:** `cd /home/sy5/projects/Faust && npm run test:all`
- **acceptance-expected:** Gate 3: 11 pass, 0 fail. Gate 2: 8 pass, 0 fail, 1 skip. (No regression — CSS-only feature.)
- **on-failure:** This phase cannot break existing tests. If tests fail, revert the `web/index.html` change.

**Goal:** Polished micro-animations for message appearance, room switching, hover states, and presence indicators. Feels alive without being distracting.

**What to do:**

1. Read `web/index.html` fully.

2. Add CSS custom properties for animation timing (inside the `:root` block):
   ```css
   --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
   --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
   --dur-fast: 120ms;
   --dur-normal: 200ms;
   --dur-slow: 350ms;
   ```

3. **Message slide-in animation** — new messages slide up from below and fade in:
   ```css
   @keyframes msg-in {
     from { opacity: 0; transform: translateY(8px); }
     to { opacity: 1; transform: translateY(0); }
   }
   .msg { animation: msg-in var(--dur-normal) var(--ease-out) both; }
   ```
   - Only animate NEW messages (from WebSocket), not historical messages loaded on room open. Add a CSS class like `.msg-history` that disables the animation: `.msg-history { animation: none; }`. Apply `.msg-history` to messages loaded from `GET /rooms/:id/messages`, and omit it for messages from `ws.onmessage`.

4. **Smooth auto-scroll** — when a new message arrives, scroll to bottom smoothly:
   ```js
   p.scrollTo({ top: p.scrollHeight, behavior: 'smooth' });
   ```
   Replace the current `p.scrollTop = p.scrollHeight` in `addMsg()`.

5. **Room switch transition** — when switching rooms, fade the pane:
   ```css
   @keyframes fade-in {
     from { opacity: 0; }
     to { opacity: 1; }
   }
   #pane.switching { animation: fade-in var(--dur-normal) var(--ease-out); }
   ```
   In `openRoom()`, add `$('pane').classList.add('switching')` and remove it after the animation ends.

6. **Hover transitions** — smooth transitions on interactive elements:
   ```css
   .room { transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast); }
   button { transition: border-color var(--dur-fast), background var(--dur-fast); }
   .cmd-chip { transition: border-color var(--dur-fast), color var(--dur-fast); }
   .composer input { transition: border-color var(--dur-fast); }
   ```

7. **Presence pulse** — when someone comes online, add a subtle pulse to the "Members" section or a status indicator:
   ```css
   @keyframes pulse-online {
     0% { box-shadow: 0 0 0 0 rgba(127, 216, 143, 0.4); }
     70% { box-shadow: 0 0 0 6px rgba(127, 216, 143, 0); }
     100% { box-shadow: 0 0 0 0 rgba(127, 216, 143, 0); }
   }
   .presence-online { animation: pulse-online 1.2s var(--ease-out); }
   ```

8. **Message delete button animation** — the hover-reveal "✕" button fades in smoothly:
   ```css
   .msg .msg-delete { transition: opacity var(--dur-fast); }
   ```

9. **Plugin result card entrance** — plugin cards get a slightly more dramatic entrance (scale + fade):
   ```css
   @keyframes card-in {
     from { opacity: 0; transform: translateY(4px) scale(0.98); }
     to { opacity: 1; transform: translateY(0) scale(1); }
   }
   .msg.plugin-result { animation: card-in var(--dur-slow) var(--ease-spring) both; }
   ```

10. **Reduced motion support** — respect the user's OS preference:
    ```css
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
    }
    ```

**Pitfalls:**
- **Don't animate historical messages** — loading a room with 50 past messages should not play 50 animations simultaneously. Use the `.msg-history` class trick described in step 3.
- **`scrollTo({behavior: 'smooth'})`** may not work in all browsers — add a feature check or just use it (it's supported in all modern browsers).
- **Animation performance** — only animate `transform` and `opacity` (these are GPU-composited). Don't animate `width`, `height`, `top`, `left` — they cause layout reflows.
- **Don't over-animate** — the opencode aesthetic is restrained and dark. Animations should feel like subtle polish, not a demo reel. Fast durations (120–350ms) and subtle movements (8px max translate).
- **`prefers-reduced-motion`** is essential for accessibility. Some users have motion sensitivity. The media query in step 10 is non-negotiable.
- **Room `.switching` class cleanup** — remove it after the animation ends with `$('pane').addEventListener('animationend', ()=> $('pane').classList.remove('switching'), {once:true})`. Don't use `setTimeout` — it can drift.

---

### Phase 13: Agent Communication Protocol — structured message types for inter-agent conferencing

- **id:** P-13
- **status:** TODO
- **deps:** [P-10, P-11, P-12]
- **files-modify:** `gate2-group-server/src/db.ts`, `gate2-group-server/src/server.ts`, `web/index.html`
- **files-read:** `gate2-group-server/src/protocol.ts` (for Message shape, REST route patterns), `gate2-group-server/src/schema.ts` (for Message interface, serialize/deserialize)
- **files-frozen:** `gate2-group-server/src/protocol.ts`, `gate2-group-server/src/schema.ts`, `gate2-group-server/test/acceptance.test.ts`, `gate2-group-server/src/tokens.ts`, `test/acceptance.test.ts`, `test/runner-integration.test.ts`
- **acceptance-cmd:** `cd /home/sy5/projects/Faust && npm run test:all`
- **acceptance-expected:** Gate 3: 11 pass, 0 fail. Gate 2: 8 pass, 0 fail, 1 skip.
- **on-failure:** Run failing suite with `--test-name-pattern`. Read stderr. Fix only `files-modify`. Do NOT edit frozen files. Max 3 retries.

**Goal:** Add message metadata for agent-to-agent communication types (command, result, status, chat) so Faust can serve as a structured conference bridge between Hermes, LSE, and SY5.

**What to do:**

1. Read `gate2-group-server/src/db.ts` fully.

2. In `db.ts`, add DB columns to the `messages` table:
   - Add `message_type TEXT DEFAULT 'chat'` to the `CREATE TABLE IF NOT EXISTS messages` statement
   - Add `target_participant TEXT` column for directed @mention routing
   - Add `ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT 'chat'` migration (try/catch)
   - Add `ALTER TABLE messages ADD COLUMN target_participant TEXT` migration (try/catch)

3. In `db.ts`, update `appendMessage(m)` to accept and store the new fields:
   - `m.type` → written to `message_type` column (default `'chat'` if absent)
   - `m.target` → written to `target_participant` column (nullable)
   - Valid types: `'command'`, `'result'`, `'status'`, `'chat'`

4. In `db.ts`, update `listMessages(roomId, opts)` to include the new columns in the SELECT and return them as part of each message object:
   - After deserializing each message from `serialized`, augment it with `type` and `target` from the DB columns
   - The frozen `Message` interface in `schema.ts` does NOT have `type`/`target` fields — the server adds these as extra response fields at the HTTP/WebSocket layer. The `serialized` column still holds the canonical JSON without them.

5. Read `gate2-group-server/src/server.ts` fully.

6. In `server.ts`, update `POST /rooms/:id/messages` (both HTTP and WebSocket `send` frame):
   - Accept optional `type` field in the request body/frame: `{ content, type?, target? }`
   - Valid types: `'command'` (agent requests/commands), `'result'` (execution output), `'status'` (system notifications), `'chat'` (human conversation — default)
   - Accept optional `target` field for directed messages (e.g. `"u:hermes"`, `"m:lse"`)
   - Parse `@mentions` from `content` to auto-detect target if `target` is not explicitly provided: extract `@handle` patterns, look up the handle in the room's membership, set `target` to the matched accountId
   - Store `type` and `target` via `appendMessage()` (pass through the augmented message object)
   - Include `type` and `target` in the broadcast frame: `{ type: "message", message: { ...message, type, target } }`

7. In `server.ts`, update the REST `GET /rooms/:id/messages` response:
   - Augment each message in the response array with its `type` and `target` from the DB

8. Read `web/index.html` fully.

9. In `web/index.html`, add message type styling via left border color:
   ```css
   .msg { border-left: 3px solid transparent; padding-left: 10px; }
   .msg[data-type="command"] { border-left-color: var(--secondary); }   /* blue — agent requests */
   .msg[data-type="result"]   { border-left-color: var(--ok); }         /* green — execution output */
   .msg[data-type="status"]   { border-left-color: var(--warn); }       /* yellow — system notifications */
   .msg[data-type="chat"]     { border-left-color: transparent; }        /* no border — normal conversation */
   ```

10. In `web/index.html`, add message type badge on each message:
    - In the `.who` line, append a small type badge after the name: `<span class="badge type-badge">CMD</span>` for command, `RES` for result, `STS` for status. Chat gets no badge (it's the default).
    ```css
    .type-badge { font-size: 9px; padding: 1px 4px; border-radius: 3px; text-transform: uppercase; letter-spacing: .04em; }
    .type-badge.cmd  { background: rgba(92,156,245,0.15); color: var(--secondary); }
    .type-badge.res  { background: rgba(127,216,143,0.15); color: var(--ok); }
    .type-badge.sts  { background: rgba(230,192,123,0.15); color: var(--warn); }
    ```

11. In `web/index.html`, enhance @mention highlighting for agent identities:
    - When a message has a `target` field matching `S.accountId`, add a subtle highlight: `<div class="msg targeted" data-type="...">`
    - CSS: `.msg.targeted { background: rgba(92,156,245,0.04); }`
    - Highlight `@hermes`, `@lse`, `@sy5` mentions distinctly: use `var(--accent)` color for agent handles (vs `var(--secondary)` for regular mentions)

12. In `web/index.html`, add message type selector in the composer:
    - Add a small type toggle before the input field: four options `[💬 chat] [⚡ cmd] [📋 result] [📢 status]`
    - Default to `chat`. Selection persists until changed.
    - On send, include `type` in the WebSocket frame or REST body
    ```html
    <div class="composer">
      <div class="type-toggle">
        <button class="tsel active" data-type="chat" onclick="setMsgType('chat',this)">💬</button>
        <button class="tsel" data-type="command" onclick="setMsgType('command',this)">⚡</button>
        <button class="tsel" data-type="result" onclick="setMsgType('result',this)">📋</button>
        <button class="tsel" data-type="status" onclick="setMsgType('status',this)">📢</button>
      </div>
      <input id="input" ... />
      <button onclick="send()">Send</button>
    </div>
    ```
    ```js
    S.msgType = 'chat';
    function setMsgType(t,btn){ S.msgType=t; document.querySelectorAll('.tsel').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); }
    ```
    Update `send()` to include `type: S.msgType` in the frame.

**Pitfalls:**
- **Backward compatibility** — existing messages default to `'chat'` type via the DB `DEFAULT 'chat'` clause. Existing tests that create messages without a `type` field will still work.
- **Do NOT edit `schema.ts`** — the frozen `Message` interface does not have `type` or `target` fields. These are DB-level and response-level additions only. The `serialized` column still holds canonical JSON without them. The server reattaches `type`/`target` from the DB columns when returning messages via REST/WebSocket.
- **Do NOT edit `protocol.ts`** — the `ServerFrame` and `ClientFrame` union types are frozen. The `type` field on the message is a MESSAGE-level field, not a FRAME-level field. The frame still uses `{ type: "message", message: {...} }` where the nested message object now carries an extra `type` and `target`.
- **@mention parsing** — use a simple regex like `/@([a-zA-Z0-9_-]+)/g` on the message content. Look up each captured handle in the room's member list (via `store.listAgentsInRoom()` + human members) to resolve the `target` accountId. If the handle doesn't match any member, ignore it (don't set `target`).
- **WebSocket `send` frame** — the `ClientFrame` type is frozen and only has `{ type: "send", roomId, content }`. Adding `messageType` and `target` fields to the frame is additive — the server reads them if present, defaults if absent. This does not change the `ClientFrame` type definition.
- **Color coding must be subtle** — the opencode aesthetic is restrained. Use thin left borders (3px), not full backgrounds. Small badges, not banners.
- **Message type in the serialized column** — do NOT store `type`/`target` inside the `serialized` JSON. They go in their own DB columns. The `serialized` column holds the canonical `Message` shape (frozen). `type`/`target` are reattached at read time from the DB columns.

**Conference workflow example:**

```
Hermes:  [type:command, target:@lse]    "Check disk usage on node4090"
LSE:     [type:result]                   "df -h output: /dev/sda1 93G 45G 48G 49%"
SY5:     [type:chat]                     "Looks good, let's proceed"
LSE:     [type:status]                   "Command executed successfully"
```

This gives Faust the foundation for structured agent communication while keeping it fully usable as a regular chat app.

## Phase Template

```markdown
## Phase N: <title>

- **id:** P-N
- **status:** TODO
- **deps:** []            <!-- phase IDs that must complete first -->
- **files-modify:** []    <!-- explicit list — only these may be edited -->
- **files-read:** []      <!-- read before modifying to understand context -->
- **files-frozen:** []    <!-- must NOT be edited (subset of CLAUDE.md frozen list) -->
- **acceptance-cmd:** <single shell command>
- **acceptance-expected:** <machine-checkable assertion, e.g. "11 pass, 0 fail">
- **on-failure:** Run the failing test with `node --import tsx --test --test-name-pattern '<pattern>' test/<file>`. Read stderr. Fix only `files-modify`. Do NOT edit frozen files. Max 3 retries.

**Goal:** <one-line summary>

**What to do:**
1. <step>
2. <step>

**Pitfalls:**
- <common mistake and how to avoid>
```

## Completed History

| Phase | Summary | Result |
|-------|---------|--------|
| P-1 | Fix Gate 2 test runner (esbuild binary permission) | `npm run test:gate2` → 8 pass, 0 fail, 1 skip ✅ |
| P-2 | Add `room_id` column to messages table, SQL-filter by room | gate2 tests green, no full-table JS scan ✅ |
| P-3 | Build Gate 3 opencode web client (plugin cards, syntax highlighting, diff view) | Self-contained 403-line `web/index.html`, eye-verified ✅ |
| P-4 | Wire Gate 3 web client into `src/index.ts` | `npm start` → Gate 3 client served at `:8787` ✅ |
| P-5 | Build `/run` exec plugin + wire `exec` capability in host | `plugins/runner/`, hostCapabilities.exec via `child_process.spawn` ✅ |
| P-6 | Quality fixes (salted hashing, persistent tokens, dynamic Node binary, timer leak, JSON parse errors) | Both test suites green ✅ |
| P-7 | Consolidation & cleanup (Zone.Identifier files, .gitignore, git init) | Clean working tree ✅ |
| P-8 | Integration tests for `/run` exec plugin | `test/runner-integration.test.ts` — 2 E2E tests, 11 total pass ✅ |
| P-9 | Room management (delete rooms, clear messages, owner model) | `npm run test:all` → all green ✅ |
| P-10 | Moderation tools (delete messages, kick users, member list) | `npm run test:all` → all green ✅ |

### Phase details (archived)

<details>
<summary>P-1: Fix Gate 2 test runner</summary>

**Goal:** Gate 2 acceptance tests all pass.

**What was done:** esbuild binary permission fixed via `rm -rf node_modules && npm install` in gate2-group-server.

**Acceptance:** `cd gate2-group-server && npm test` → 8 pass, 0 fail, 1 skip.
</details>

<details>
<summary>P-2: Fix db.ts — add room_id column</summary>

**Goal:** The `messages` table gets a `room_id TEXT` column. `listMessages(roomId)` queries by `room_id` instead of loading and filtering all messages in JavaScript.

**What was done:**
- Added `room_id TEXT` column to `CREATE TABLE IF NOT EXISTS messages`
- Added `ALTER TABLE messages ADD COLUMN room_id TEXT` migration (wrapped in try-catch)
- `appendMessage(m)` now stores `m.room` in the `room_id` column
- `listMessages(roomId, opts)` uses `WHERE room_id = ?` SQL filter instead of full-table JS scan
- Removed all abandoned refactoring comments

**Acceptance:** `cd gate2-group-server && npm test` → 8 pass, 0 fail, 1 skip.
</details>

<details>
<summary>P-3: Build the Gate 3 opencode web client</summary>

**Goal:** Replace the placeholder `web/index.html` with a full opencode-themed web client that extends the Gate 2 client with plugin result rendering and the complete component kit.

**What was done:**
- Built 403-line self-contained `web/index.html` with:
  - Plugin result rendering (bordered cards with plugin badge for `author.kind === "model"` + `role === "system"`)
  - Syntax highlighting (keywords, types, strings, numbers, comments, function calls)
  - Diff view support (`+++`/`---` prefixed lines with green/red coloring)
  - Panel borders with `--panel` background and `--border` borders
  - Auto-discovered commands sidebar
  - All design tokens from `design-tokens/opencode-tokens.json`
- No external CDN dependencies — fully self-contained

**Acceptance:** Manual verification at `http://localhost:8787` — opencode dark theme, plugin cards, syntax highlighting.
</details>

<details>
<summary>P-4: Wire Gate 3 web client into server</summary>

**Goal:** `src/index.ts` serves the Gate 3 web client (from Phase 3) same-origin, not the Gate 2 client.

**What was done:**
- Changed `WEB_CLIENT` in `src/index.ts` from Gate 2 path to `join(PROJECT_ROOT, "web", "index.html")`
- Server now serves Gate 3 client at `http://localhost:8787`

**Acceptance:** `npm start` → Gate 3 client served same-origin. `npm test` → 9 pass.
</details>

<details>
<summary>P-5: Build exec/code-runner plugin</summary>

**Goal:** A reference plugin (`/run`) that uses the `exec` capability to execute shell commands and return output.

**What was done:**
- Created `plugins/runner/manifest.json` (exec capability, `/run` command)
- Created `plugins/runner/plugin.js` (executes commands via `ctx.exec.run()`, returns formatted output)
- Wired `exec` capability in `src/index.ts` hostCapabilities using `child_process.spawn` with 30s timeout
- Server loads 2 plugins: search + runner

**Acceptance:** `npm test` → 9 pass. Manual: `/run echo hello` → returns `✓ exit=0` with output.
</details>

<details>
<summary>P-6: Quality fixes</summary>

**Goal:** Fix known code quality issues that aren't functional bugs but will bite at scale.

**What was done:**
- **6a:** Salted password hashing — `crypto.randomBytes(16)` salt per password, stored in `salt` column
- **6b:** Persistent auth tokens — moved in-memory `tokenMap` to SQLite `tokens` table
- **6c:** Dynamic Node binary resolution — `findNodeBinary()` checks `process.execPath` first, falls back to nvm paths
- **6d:** Timer leak fix — `clearTimeout(timer)` in `finally` block after `Promise.race`
- **6e:** JSON.parse error handling — both `JSON.parse(bodyText)` calls in `server.ts` wrapped in try-catch

**Acceptance:** `npm test` → 9 pass. `npm run test:gate2` → 8 pass, 0 fail, 1 skip.
</details>

<details>
<summary>P-7: Consolidation & cleanup</summary>

**Goal:** Final project hygiene. Clean git status. No artifacts.

**What was done:**
- Deleted runtime artifacts (`gate3-plugin-forge/server.log`)
- Verified `.gitignore` covers: `node_modules/`, `dist/`, `*.log`, `*.sqlite`, `.DS_Store`, `data/`, `*:Zone.Identifier`
- Initialized git repo, committed all changes

**Acceptance:** `npm run test:all` → all green. `git status` → clean.
</details>

<details>
<summary>P-8: Integration tests for /run</summary>

**Goal:** E2E integration tests for the `/run` exec plugin against the real server.

**What was done:**
- Created `test/fixtures/runner/` — test fixture plugin for exec capability
- Created `test/runner-integration.test.ts` — 2 integration tests:
  1. `/run echo hello` → verifies exit=0 and output appear in-room via HTTP API
  2. `/run` (no args) → verifies usage hint returned
- Gate 3 total: 11 pass (9 original + 2 integration)

**Acceptance:** `npm test` → 11 pass, 0 fail.
</details>

<details>
<summary>P-9: Room management — delete rooms + clear messages</summary>

**Goal:** Room creators can delete rooms and clear all messages. Owner model in DB.

**What was done:**
- Added `ownerId TEXT` column to rooms table + migration
- `createRoom(name, ownerId?)` — stores creator as owner
- `getRoomOwner(roomId)`, `deleteRoom(roomId)`, `clearMessages(roomId)` in Store
- `GET /rooms/:id` — returns room info with ownerId
- `DELETE /rooms/:id` — owner-only, broadcasts `room_removed`
- `POST /rooms/:id/clear` — owner-only, broadcasts `room_cleared`
- Web client: 🗑/🧹 buttons in room header, WS handlers for `room_removed`/`room_cleared`

**Acceptance:** `npm run test:all` → Gate 2: 8 pass, Gate 3: 11 pass, zero regressions.
</details>

## Appendix: File Registry

### Frozen files — DO NOT EDIT

| Path | Owner | Purpose |
|------|-------|---------|
| `src/plugin-contract.ts` | Gate 3 | Third-party plugin API surface (manifest, capabilities, PluginContext) |
| `src/schema.ts` | Gate 3 | Canonical Message/Author types (vendored from Gate 1) |
| `src/tokens.ts` | Gate 3 | opencode design token loader + CIE76 color distance |
| `test/acceptance.test.ts` | Gate 3 | The grader (9 tests) |
| `test/runner-integration.test.ts` | Gate 3 | E2E integration tests (2 tests) |
| `test/fixtures/*/plugin.js` | Gate 3 | Third-party test plugins |
| `test/fixtures/*/manifest.json` | Gate 3 | Their manifests |
| `design-tokens/opencode-tokens.json` | Shared | Visual contract (all gates consume) |
| `gate2-group-server/src/protocol.ts` | Gate 2 | Wire contract (REST/WebSocket DTOs) |
| `gate2-group-server/src/schema.ts` | Gate 2 | Schema (same shape as Gate 3's) |
| `gate2-group-server/src/tokens.ts` | Gate 2 | Token loader |
| `gate2-group-server/test/acceptance.test.ts` | Gate 2 | Gate 2 grader (8 tests + 1 skip) |

### Modifiable source files

| Path | Module | Exports |
|------|--------|---------|
| `src/registry.ts` | Gate 3 | `PluginRegistry` — runtime load, lazy subprocess spawn |
| `src/sandbox.ts` | Gate 3 | `buildContext`, `invoke`, `spawnPlugin` — capability gating + subprocess isolation |
| `src/host.ts` | Gate 3 | `PluginHost` — dispatch command/message with IPC brokering |
| `src/index.ts` | Gate 3 | Entry — compose Gate 2 server + PluginHost + plugins + web client |
| `src/plugin-runner.js` | Gate 3 | Subprocess entry — JSON-lines IPC, capability proxies |
| `gate2-group-server/src/db.ts` | Gate 2 | `Store` / `openStore` — SQLite (sql.js) data layer |
| `gate2-group-server/src/auth.ts` | Gate 2 | `Auth` / `makeAuth` — register, login, bearer tokens |
| `gate2-group-server/src/server.ts` | Gate 2 | `createServer` — HTTP REST + WebSocket |
| `gate2-group-server/src/orchestrator.ts` | Gate 2 | `MentionReplyPolicy`, `runTurn` — bounded agent reply chains |
| `gate2-group-server/src/agents.ts` | Gate 2 | `generateAgentReply` — LLM prompt builder |
| `gate2-group-server/src/model_live.ts` | Gate 2 | `makeLiveModelClient` — OpenAI-compatible client |
| `gate2-group-server/src/index.ts` | Gate 2 | Standalone Gate 2 entry point |

### Config / meta files

| Path | Notes |
|------|-------|
| `package.json` | Top-level compose package |
| `gate2-group-server/package.json` | Gate 2 sub-package |
| `tsconfig.json` | TypeScript config |
| `.gitignore` | `node_modules/`, `dist/`, `*.log`, `*.sqlite`, `.DS_Store`, `data/`, `*:Zone.Identifier` |
| `plugins/*/manifest.json` | Plugin manifests (auto-loaded at startup) |
| `plugins/*/plugin.js` | Plugin implementations (plain .js, no transpiler) |
| `web/index.html` | Gate 3 web client (self-contained, no build step) |

### Prerequisite check

```bash
node -e "const v=+process.version.slice(1).split('.')[0]; process.exit(v<22)"
# exits 0 if Node 22+ (required for --permission subprocess model)
```
