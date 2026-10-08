import { describe, expect, it } from "vitest";

import { type ChatMessage, applyHello, applyMessage, emptyRoom } from "./room";

const INSTANCE = "3f9a0c1d2b4e5f60";

function message(seq: number): ChatMessage {
  return {
    seq,
    author: "Avery",
    html: `<p>message ${seq}</p>`,
    receivedAt: "2026-10-08T15:02:03.123Z",
    own: false,
  };
}

function roomOn(instance: string) {
  return applyHello(emptyRoom(), instance, 0).state;
}

describe("applyMessage", () => {
  it("should keep exactly one copy when a replay repeats a seq already shown", () => {
    let state = roomOn(INSTANCE);
    state = applyMessage(state, INSTANCE, message(1));
    state = applyMessage(state, INSTANCE, message(2));

    state = applyMessage(state, INSTANCE, message(1));
    state = applyMessage(state, INSTANCE, message(2));

    expect(state.messages.map((m) => m.seq)).toEqual([1, 2]);
  });

  it("should keep only the newest 200 messages when more arrive", () => {
    const posts = Array.from({ length: 205 }, (_, index) => message(index + 1));

    const state = posts.reduce(
      (room, post) => applyMessage(room, INSTANCE, post),
      roomOn(INSTANCE),
    );

    expect(state.messages).toHaveLength(200);
    expect(state.messages[0]?.seq).toBe(6);
    expect(state.messages[199]?.seq).toBe(205);
  });
});
