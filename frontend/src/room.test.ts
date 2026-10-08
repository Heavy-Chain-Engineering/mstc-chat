import { describe, expect, it } from "vitest";

import {
  type ChatMessage,
  applyHello,
  applyMessage,
  applyPresence,
  dismissRestarted,
  emptyRoom,
  reloadMemory,
} from "./room";

const INSTANCE = "3f9a0c1d2b4e5f60";
const OTHER = "0123456789abcdef";

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

  it("should order messages by seq when they arrive out of order", () => {
    const state = [message(3), message(1), message(2)].reduce(
      (room, post) => applyMessage(room, INSTANCE, post),
      roomOn(INSTANCE),
    );

    expect(state.messages.map((m) => m.seq)).toEqual([1, 2, 3]);
  });

  it("should ignore a message when it comes from another instance than the room's", () => {
    const state = applyMessage(roomOn(INSTANCE), OTHER, message(1));

    expect(state.messages).toEqual([]);
  });

  it("should clear the restarted notice when the next message arrives", () => {
    const restarted = emptyRoom({
      left: [],
      reloadedFor: INSTANCE,
      restarted: true,
    });
    const live = applyHello(restarted, INSTANCE, 0).state;

    const state = applyMessage(live, INSTANCE, message(1));

    expect(live.restarted).toBe(true);
    expect(state.restarted).toBe(false);
  });

  it("should clear the restarted notice when the reader dismisses it", () => {
    const restarted = emptyRoom({
      left: [],
      reloadedFor: INSTANCE,
      restarted: true,
    });

    expect(dismissRestarted(restarted).restarted).toBe(false);
  });
});

describe("applyHello", () => {
  it("should accept the instance when it is the first hello on the page", () => {
    const { state, action } = applyHello(emptyRoom(), INSTANCE, 0);

    expect(action).toBe("accept");
    expect(state.instance).toBe(INSTANCE);
  });

  it("should keep the messages when the hello repeats the room's instance", () => {
    const shown = applyMessage(roomOn(INSTANCE), INSTANCE, message(1));

    const { state, action } = applyHello(shown, INSTANCE, 1000);

    expect(action).toBe("same");
    expect(state.messages.map((m) => m.seq)).toEqual([1]);
  });

  it("should ask for a reload when a new instance says hello", () => {
    const shown = applyMessage(roomOn(INSTANCE), INSTANCE, message(1));

    const { action } = applyHello(shown, OTHER, 1000);

    expect(action).toBe("reload");
  });

  it("should remember the instances it left when it saves the room for a reload", () => {
    const memory = reloadMemory(roomOn(INSTANCE), OTHER);

    expect(memory).toEqual({
      left: [INSTANCE],
      reloadedFor: OTHER,
      restarted: true,
    });
  });

  it("should empty the room without a reload when the page already reloaded for that instance", () => {
    const afterReload = emptyRoom({
      left: [],
      reloadedFor: OTHER,
      restarted: false,
    });
    const onOld = applyMessage(
      applyHello(afterReload, INSTANCE, 0).state,
      INSTANCE,
      message(1),
    );

    const { state, action } = applyHello(onOld, OTHER, 1000);

    expect(action).toBe("switch");
    expect(state.instance).toBe(OTHER);
    expect(state.messages).toEqual([]);
    expect(state.restarted).toBe(true);
    expect(state.left).toEqual([INSTANCE]);
  });

  it("should reject an instance the page already left when it says hello again", () => {
    const afterReload = emptyRoom({
      left: [INSTANCE],
      reloadedFor: OTHER,
      restarted: true,
    });
    const onNew = applyHello(afterReload, OTHER, 0).state;

    const { state, action } = applyHello(onNew, INSTANCE, 1000);

    expect(action).toBe("reject");
    expect(state.instance).toBe(OTHER);
  });

  it("should accept a left instance when it has been rejected for 10 seconds", () => {
    const fresh = emptyRoom({
      left: [INSTANCE],
      reloadedFor: OTHER,
      restarted: false,
    });
    const onNew = applyHello(fresh, OTHER, 0).state;
    const rejected = applyHello(onNew, INSTANCE, 1000).state;
    const stillRejected = applyHello(rejected, INSTANCE, 10_999);

    const { state, action } = applyHello(stillRejected.state, INSTANCE, 11_000);

    expect(stillRejected.action).toBe("reject");
    expect(action).toBe("switch");
    expect(state.instance).toBe(INSTANCE);
    expect(state.messages).toEqual([]);
  });

  it("should reject a left instance when it is the first hello after a reload", () => {
    const afterReload = emptyRoom({
      left: [INSTANCE],
      reloadedFor: OTHER,
      restarted: true,
    });

    const { state, action } = applyHello(afterReload, INSTANCE, 0);

    expect(action).toBe("reject");
    expect(state.instance).toBeNull();
  });
});

describe("applyPresence", () => {
  it("should replace the online list when a presence event arrives", () => {
    const first = applyPresence(roomOn(INSTANCE), ["Avery", "Jordan"]);

    const state = applyPresence(first, ["Jordan"]);

    expect(first.names).toEqual(["Avery", "Jordan"]);
    expect(state.names).toEqual(["Jordan"]);
  });

  it("should report no online list when no presence event has arrived yet", () => {
    expect(roomOn(INSTANCE).names).toBeNull();
  });
});
