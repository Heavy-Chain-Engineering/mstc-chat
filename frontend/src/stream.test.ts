import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiResult, NameAnswer } from "./api";
import type { RoomState } from "./room";
import {
  type EventSourceLike,
  type KeyValueStore,
  RELOAD_KEY,
  RoomStream,
  readReloadMemory,
  waitForSession,
} from "./stream";

const TAB = "0b6f6c1e-8f3a-4a4e-9a51-1f6c2d3e4f50";
const OLD = "3f9a0c1d2b4e5f60";
const NEW = "0123456789abcdef";
const CONNECTING = 0;
const CLOSED = 2;

class FakeSource implements EventSourceLike {
  readyState = CONNECTING;
  closed = false;
  private readonly listeners = new Map<string, ((event: Event) => void)[]>();

  constructor(readonly url: string) {}

  addEventListener(type: string, listener: (event: Event) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.closed = true;
    this.readyState = CLOSED;
  }

  emit(type: string, data: unknown, lastEventId = ""): void {
    const event = new MessageEvent(type, {
      data: JSON.stringify(data),
      lastEventId,
    });
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }

  hello(instance: string): void {
    this.readyState = 1;
    this.emit("hello", { instance });
  }

  fail(readyState: number): void {
    this.readyState = readyState;
    this.listeners
      .get("error")
      ?.forEach((listener) => listener(new Event("error")));
  }
}

class MemoryStore implements KeyValueStore {
  readonly items = new Map<string, string>();

  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.items.set(key, value);
  }

  removeItem(key: string): void {
    this.items.delete(key);
  }
}

interface Harness {
  stream: RoomStream;
  sources: FakeSource[];
  rooms: RoomState[];
  notices: boolean[];
  signedOut: ReturnType<typeof vi.fn>;
  reload: ReturnType<typeof vi.fn>;
  leave: ReturnType<typeof vi.fn>;
  store: MemoryStore;
}

function setup(
  options: {
    session?: ApiResult<NameAnswer>;
    store?: MemoryStore;
    draft?: string;
  } = {},
): Harness {
  const sources: FakeSource[] = [];
  const rooms: RoomState[] = [];
  const notices: boolean[] = [];
  const signedOut = vi.fn();
  const reload = vi.fn();
  const leave = vi.fn();
  const store = options.store ?? new MemoryStore();
  const session = options.session ?? { kind: "ok", data: { name: "Avery" } };
  const stream = new RoomStream({
    tab: TAB,
    memory: readReloadMemory(store).memory,
    handlers: {
      onRoom: (state) => rooms.push(state),
      onReconnecting: (visible) => notices.push(visible),
      onSignedOut: signedOut,
    },
    deps: {
      openSource: (url) => {
        const source = new FakeSource(url);
        sources.push(source);
        return source;
      },
      checkSession: () => Promise.resolve(session),
      sendLeave: leave,
      storage: store,
      reload,
      getDraft: () => options.draft ?? "",
      now: () => Date.now(),
    },
  });
  stream.open();
  return { stream, sources, rooms, notices, signedOut, reload, leave, store };
}

function last<T>(items: T[]): T | undefined {
  return items[items.length - 1];
}

function current(h: Harness): FakeSource {
  const source = last(h.sources);
  if (source === undefined) {
    throw new Error("no stream was opened");
  }
  return source;
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("RoomStream: opening", () => {
  it("should open the stream with this tab's id when it starts", () => {
    const h = setup();

    expect(current(h).url).toBe(`/api/stream?tab=${TAB}`);
  });

  it("should remember the instance when the first hello arrives", () => {
    const h = setup();

    current(h).hello(OLD);

    expect(last(h.rooms)?.instance).toBe(OLD);
  });
});

describe("RoomStream: events", () => {
  it("should add a message with its own flag when a message event arrives", () => {
    const h = setup();
    current(h).hello(OLD);

    current(h).emit(
      "message",
      {
        seq: 41,
        author: "Avery",
        html: "<p>Hi</p>",
        receivedAt: "2026-10-08T15:02:03.123Z",
        own: true,
      },
      `${OLD}:41`,
    );

    expect(last(h.rooms)?.messages).toEqual([
      {
        seq: 41,
        author: "Avery",
        html: "<p>Hi</p>",
        receivedAt: "2026-10-08T15:02:03.123Z",
        own: true,
      },
    ]);
  });

  it("should replace the online list when a presence event arrives", () => {
    const h = setup();
    current(h).hello(OLD);
    current(h).emit("presence", { names: ["Avery", "Jordan"] });

    current(h).emit("presence", { names: ["Jordan"] });

    expect(last(h.rooms)?.names).toEqual(["Jordan"]);
  });
});

describe("RoomStream: reconnecting notice", () => {
  it("should show the notice when the stream has been down for 3 seconds", () => {
    const h = setup();
    current(h).hello(OLD);

    current(h).fail(CONNECTING);
    vi.advanceTimersByTime(2999);
    const before = [...h.notices];
    vi.advanceTimersByTime(1);

    expect(before).not.toContain(true);
    expect(last(h.notices)).toBe(true);
  });

  it("should not show the notice when the stream cycles and says hello within 3 seconds", () => {
    const h = setup();
    current(h).hello(OLD);

    current(h).fail(CONNECTING);
    vi.advanceTimersByTime(1000);
    current(h).hello(OLD);
    vi.advanceTimersByTime(5000);

    expect(h.notices).not.toContain(true);
  });

  it("should hide the notice when the same instance says hello again", () => {
    const h = setup();
    current(h).hello(OLD);
    current(h).fail(CONNECTING);
    vi.advanceTimersByTime(3000);

    current(h).hello(OLD);

    expect(last(h.notices)).toBe(false);
  });
});

describe("RoomStream: refused stream", () => {
  it("should report signed out and open no new stream when the session check answers 401", async () => {
    const h = setup({
      session: { kind: "error", status: 401, code: "signed_out" },
    });
    current(h).hello(OLD);

    current(h).fail(CLOSED);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(h.signedOut).toHaveBeenCalledTimes(1);
    expect(h.sources).toHaveLength(1);
  });

  it("should retry after 2, 4 and then 10 seconds when the session check fails otherwise", async () => {
    const h = setup({ session: { kind: "unreachable" } });

    current(h).fail(CLOSED);
    await vi.advanceTimersByTimeAsync(1999);
    const beforeFirst = h.sources.length;
    await vi.advanceTimersByTimeAsync(1);
    current(h).fail(CLOSED);
    await vi.advanceTimersByTimeAsync(4000);
    current(h).fail(CLOSED);
    await vi.advanceTimersByTimeAsync(9999);
    const beforeThird = h.sources.length;
    await vi.advanceTimersByTimeAsync(1);

    expect(beforeFirst).toBe(1);
    expect(beforeThird).toBe(3);
    expect(h.sources).toHaveLength(4);
    expect(h.signedOut).not.toHaveBeenCalled();
  });
});

describe("RoomStream: new instance (redeploy or restart)", () => {
  it("should save the draft, the restarted flag and the instance, then reload, when a new instance says hello", () => {
    const h = setup({ draft: "half-written question" });
    current(h).hello(OLD);

    current(h).hello(NEW);

    expect(h.reload).toHaveBeenCalledTimes(1);
    expect(JSON.parse(h.store.getItem(RELOAD_KEY) ?? "null")).toEqual({
      left: [OLD],
      reloadedFor: NEW,
      restarted: true,
      draft: "half-written question",
    });
  });

  it("should restore the draft once and show the restarted notice after the reload", () => {
    const h = setup({ draft: "half-written question" });
    current(h).hello(OLD);
    current(h).hello(NEW);

    const first = readReloadMemory(h.store);
    const second = readReloadMemory(h.store);

    expect(first.draft).toBe("half-written question");
    expect(first.memory.restarted).toBe(true);
    expect(second.draft).toBe("");
    expect(second.memory.restarted).toBe(false);
    expect(h.store.getItem(RELOAD_KEY)).not.toContain("half-written question");
  });

  it("should show the empty room with the restarted notice when the new instance says hello after the reload", () => {
    const store = new MemoryStore();
    const before = setup({ store });
    current(before).hello(OLD);
    current(before).hello(NEW);

    const after = setup({ store });
    current(after).hello(NEW);

    expect(after.reload).not.toHaveBeenCalled();
    expect(last(after.rooms)?.messages).toEqual([]);
    expect(last(after.rooms)?.restarted).toBe(true);
  });

  it("should not reload a second time when the page already reloaded for that instance", () => {
    const store = new MemoryStore();
    store.setItem(
      RELOAD_KEY,
      JSON.stringify({ left: [], reloadedFor: NEW, restarted: false }),
    );
    const h = setup({ store });
    current(h).hello(OLD);

    current(h).hello(NEW);

    expect(h.reload).not.toHaveBeenCalled();
    expect(last(h.rooms)?.instance).toBe(NEW);
  });

  it("should reconnect after 1 second without a reload or notice when an instance it left says hello", () => {
    const store = new MemoryStore();
    store.setItem(
      RELOAD_KEY,
      JSON.stringify({ left: [OLD], reloadedFor: NEW, restarted: true }),
    );
    const h = setup({ store });
    current(h).hello(NEW);

    current(h).hello(OLD);
    const closed = h.sources[0]?.closed;
    vi.advanceTimersByTime(999);
    const beforeReconnect = h.sources.length;
    vi.advanceTimersByTime(1);

    expect(closed).toBe(true);
    expect(beforeReconnect).toBe(1);
    expect(h.sources).toHaveLength(2);
    expect(h.reload).not.toHaveBeenCalled();
    expect(h.notices).not.toContain(true);
  });
});

describe("readReloadMemory", () => {
  it.each(["{not json", "null", "42"])(
    "should ignore and remove the record when it is corrupt (%s)",
    (raw) => {
      const store = new MemoryStore();
      store.setItem(RELOAD_KEY, raw);

      const saved = readReloadMemory(store);

      expect(saved).toEqual({
        memory: { left: [], reloadedFor: null, restarted: false },
        draft: "",
      });
      expect(store.getItem(RELOAD_KEY)).toBeNull();
    },
  );
});

describe("waitForSession (start-up)", () => {
  function waiter(answers: ApiResult<NameAnswer>[]) {
    const waits: number[] = [];
    const onRetrying = vi.fn();
    const result = waitForSession({
      checkSession: () =>
        Promise.resolve(answers.shift() ?? { kind: "unreachable" }),
      sleep: (ms) => {
        waits.push(ms);
        return Promise.resolve();
      },
      onRetrying,
    });
    return { result, waits, onRetrying };
  }

  it("should return the name at once when the session is good", async () => {
    const { result, waits, onRetrying } = waiter([
      { kind: "ok", data: { name: "Avery" } },
    ]);

    expect(await result).toEqual({ name: "Avery" });
    expect(waits).toEqual([]);
    expect(onRetrying).not.toHaveBeenCalled();
  });

  it("should report signed out without retrying when the server answers 401", async () => {
    const { result, waits } = waiter([
      { kind: "error", status: 401, code: "signed_out" },
    ]);

    expect(await result).toBeNull();
    expect(waits).toEqual([]);
  });

  it("should show reconnecting and retry after 2, 4 and 10 seconds when the server is unreachable or answers 5xx", async () => {
    const { result, waits, onRetrying } = waiter([
      { kind: "unreachable" },
      { kind: "error", status: 503, code: "server_error" },
      { kind: "unreachable" },
      { kind: "ok", data: { name: "Avery" } },
    ]);

    expect(await result).toEqual({ name: "Avery" });
    expect(waits).toEqual([2000, 4000, 10_000]);
    expect(onRetrying).toHaveBeenCalledTimes(1);
  });
});

describe("RoomStream: page lifecycle", () => {
  it("should send the leave beacon when the page is hidden and not kept in the back/forward cache", () => {
    const h = setup();

    h.stream.handlePageHide(false);

    expect(h.leave).toHaveBeenCalledWith(TAB);
  });

  it("should not send the leave beacon when the page is kept in the back/forward cache", () => {
    const h = setup();

    h.stream.handlePageHide(true);

    expect(h.leave).not.toHaveBeenCalled();
  });

  it("should open a new stream when the page comes back from the back/forward cache", () => {
    const h = setup();

    h.stream.handlePageShow(true);

    expect(h.sources[0]?.closed).toBe(true);
    expect(h.sources).toHaveLength(2);
  });

  it("should not open a second stream when the page is first shown", () => {
    const h = setup();

    h.stream.handlePageShow(false);

    expect(h.sources).toHaveLength(1);
  });
});
