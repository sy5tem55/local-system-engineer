// test/planning.test.ts — Multi-agent planning protocol (LSE 1.7.0-b).
// Deterministic + offline: pure controller state-machine tests, plus a full
// PLANNING→AWAITING_APPROVAL→TASKING→IDLE run through the real runTurn engine
// with a scripted fake ModelClient. Run: `npm test`.
import { test } from "node:test";
import assert from "node:assert/strict";

import type { Message } from "../src/schema.js";
import type { ModelClient, AgentAccount, Room } from "../src/protocol.js";
import { MentionReplyPolicy, runTurn } from "../src/orchestrator.js";
import {
  PlanningController,
  PlanningPolicy,
  parseAssignments,
  CONVERGED_TOKEN,
  DONE_TOKEN,
} from "../src/planning.js";

const ROOM = "r:plan";
const room: Room = { id: ROOM, name: "plan", createdAt: 0 };

function agentMsg(handle: string, content: string): Message {
  return {
    id: `m:${handle}:${Math.random().toString(36).slice(2)}`,
    room: ROOM,
    author: { id: `m:${handle}`, kind: "model", name: handle },
    role: "assistant",
    content,
    ts: Date.now(),
  };
}
function humanMsg(content: string): Message {
  return {
    id: `u:joe:${Math.random().toString(36).slice(2)}`,
    room: ROOM,
    author: { id: "u:joe", kind: "human", name: "joe" },
    role: "user",
    content,
    ts: Date.now(),
  };
}

// ── pure controller ────────────────────────────────────────────────────────────

test("[authored] parseAssignments extracts @handle: task pairs", () => {
  const a = parseAssignments("alice", "@bob: build the API @carol: write docs");
  assert.deepEqual(a, [
    { from: "alice", to: "bob", task: "build the API" },
    { from: "alice", to: "carol", task: "write docs" },
  ]);
  assert.deepEqual(parseAssignments("alice", "no assignments here"), []);
});

test("[authored] startPlanning enters planning with round-robin order", () => {
  const c = new PlanningController();
  c.startPlanning(ROOM, "ship X", ["alice", "bob"]);
  assert.equal(c.phase(ROOM), "planning");
  assert.equal(c.state(ROOM)!.round, 1);
  assert.deepEqual(c.state(ROOM)!.order, ["alice", "bob"]);
  // a framing notice was queued for the moderator to post
  assert.match(c.takeNotices(ROOM).join("\n"), /PLANNING PHASE/);
});

test("[authored] round-robin advances, then converges when all vote in a round", () => {
  const c = new PlanningController();
  c.startPlanning(ROOM, "obj", ["alice", "bob"]);
  c.takeNotices(ROOM); // discard framing

  // round 1: neither converges
  assert.equal(c.nextSpeaker(ROOM), "alice");
  c.observe(ROOM, agentMsg("alice", "proposal"));
  assert.equal(c.nextSpeaker(ROOM), "bob");
  c.observe(ROOM, agentMsg("bob", "counter-proposal"));
  // round boundary, no consensus → round 2 starts at alice
  assert.equal(c.nextSpeaker(ROOM), "alice");
  assert.equal(c.state(ROOM)!.round, 2);

  // round 2: both converge
  c.observe(ROOM, agentMsg("alice", `agree ${CONVERGED_TOKEN}`));
  assert.equal(c.nextSpeaker(ROOM), "bob");
  c.observe(ROOM, agentMsg("bob", `agree ${CONVERGED_TOKEN}`));
  assert.equal(c.nextSpeaker(ROOM), null); // boundary → consensus
  assert.equal(c.phase(ROOM), "awaiting_approval");
  assert.match(c.takeNotices(ROOM).join("\n"), /PLAN CONVERGED/);
});

test("[authored] one dissenter blocks consensus; votes reset each round", () => {
  const c = new PlanningController();
  c.startPlanning(ROOM, "obj", ["alice", "bob"]);
  // round 1: only alice converges
  c.observe(ROOM, agentMsg("alice", `ok ${CONVERGED_TOKEN}`));
  c.observe(ROOM, agentMsg("bob", "I disagree"));
  assert.equal(c.nextSpeaker(ROOM), "alice"); // no consensus → round 2
  assert.equal(c.state(ROOM)!.round, 2);
  // votes reset: alice's round-1 vote does not carry over
  assert.equal(c.state(ROOM)!.votesThisRound.size, 0);
});

test("[authored] planning cap forces awaiting_approval without consensus", () => {
  const c = new PlanningController();
  c.startPlanning(ROOM, "obj", ["alice"], { maxRounds: 2 });
  c.takeNotices(ROOM);
  // round 1
  c.observe(ROOM, agentMsg("alice", "p1"));
  assert.equal(c.nextSpeaker(ROOM), "alice"); // → round 2
  // round 2, still no vote
  c.observe(ROOM, agentMsg("alice", "p2"));
  assert.equal(c.nextSpeaker(ROOM), null); // cap reached
  assert.equal(c.phase(ROOM), "awaiting_approval");
  assert.match(c.takeNotices(ROOM).join("\n"), /CAP REACHED/);
});

test("[authored] approve→tasking and revise→planning guards", () => {
  const c = new PlanningController();
  c.startPlanning(ROOM, "obj", ["alice"], { maxRounds: 1 });
  c.observe(ROOM, agentMsg("alice", "p1"));
  c.nextSpeaker(ROOM); // → awaiting_approval (cap=1)
  assert.equal(c.phase(ROOM), "awaiting_approval");

  // approve from the wrong phase is a no-op
  assert.equal(c.revise("other-room"), false);

  assert.equal(c.approve(ROOM), true);
  assert.equal(c.phase(ROOM), "tasking");
  assert.equal(c.approve(ROOM), false); // already tasking
});

// ── full engine integration ─────────────────────────────────────────────────────

test("[authored] full PLANNING→APPROVE→TASKING run drives agents round-robin", async () => {
  const controller = new PlanningController();
  const policy = new PlanningPolicy(controller, new MentionReplyPolicy());

  const agents: AgentAccount[] = [
    { id: "m:alice", handle: "alice", kind: "model", endpoint: "fake://alice", createdAt: 0 },
    { id: "m:bob", handle: "bob", kind: "model", endpoint: "fake://bob", createdAt: 0 },
  ];

  let tasking = false;
  const calls = new Map<string, number>();
  const model: ModelClient = {
    async complete(req) {
      const h = req.endpoint.replace("fake://", "");
      const n = calls.get(h) ?? 0;
      calls.set(h, n + 1);
      if (tasking) {
        return h === "alice"
          ? `@bob: build the API ${DONE_TOKEN}`
          : `@alice: write the tests ${DONE_TOKEN}`;
      }
      // planning: propose on the first turn, converge afterwards
      return n === 0 ? `${h} proposes a step` : `${h} agrees ${CONVERGED_TOKEN}`;
    },
  };

  const history: Message[] = [];
  const replies: Message[] = [];
  const deps = {
    policy,
    model,
    agentsInRoom: () => agents,
    history: () => history,
    onReply: async (m: Message) => {
      history.push(m);
      replies.push(m);
    },
    budget: 50,
  };

  // human kicks off planning
  controller.startPlanning(ROOM, "ship feature X", ["alice", "bob"]);
  const kickoff = humanMsg("/plan ship feature X");
  history.push(kickoff);
  await runTurn(room, kickoff, deps);

  // planning ran round-robin to consensus in round 2 → 4 agent replies
  assert.equal(replies.length, 4, "alice/bob × 2 rounds");
  assert.deepEqual(
    replies.map((r) => r.author.name),
    ["alice", "bob", "alice", "bob"],
  );
  assert.equal(controller.phase(ROOM), "awaiting_approval");
  assert.match(controller.takeNotices(ROOM).join("\n"), /PLAN CONVERGED/);

  // human admin approves → tasking
  tasking = true;
  assert.equal(controller.approve(ROOM), true);
  const approve = humanMsg("/approve");
  history.push(approve);
  await runTurn(room, approve, deps);

  // tasking: one round, both place an assignment + [[DONE]] → idle
  assert.equal(controller.phase(ROOM), "idle");
  const st = controller.state(ROOM)!;
  assert.deepEqual(st.assignments, [
    { from: "alice", to: "bob", task: "build the API" },
    { from: "bob", to: "alice", task: "write the tests" },
  ]);
  assert.match(controller.takeNotices(ROOM).join("\n"), /TASKING COMPLETE[\s\S]*build the API/);
});

test("[authored] idle room delegates to the mention-reply fallback", async () => {
  const controller = new PlanningController();
  const policy = new PlanningPolicy(controller, new MentionReplyPolicy());
  const agents: AgentAccount[] = [
    { id: "m:alice", handle: "alice", kind: "model", endpoint: "fake://alice", createdAt: 0 },
  ];
  const replies: Message[] = [];
  const history: Message[] = [];
  const deps = {
    policy,
    model: { async complete() { return "hi from alice"; } } as ModelClient,
    agentsInRoom: () => agents,
    history: () => history,
    onReply: async (m: Message) => { history.push(m); replies.push(m); },
    budget: 6,
  };

  // no planning active → mention-reply: @alice gets one reply, unmentioned gets none
  const m1 = humanMsg("hello @alice");
  history.push(m1);
  await runTurn(room, m1, deps);
  assert.equal(replies.length, 1);

  const m2 = humanMsg("nobody mentioned");
  history.push(m2);
  await runTurn(room, m2, deps);
  assert.equal(replies.length, 1, "no new reply without a mention");
});
