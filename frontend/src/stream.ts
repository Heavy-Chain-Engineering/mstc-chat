// The live stream (ADR-04 as the VP ruled on 2026-10-08): one EventSource
// per tab, the reconnecting notice, the session check when the stream is
// refused, the reload on a new server instance, and the leave beacon.

import type { ApiResult, NameAnswer } from "./api";
import {
  type ChatMessage,
  type InstanceMemory,
  type RoomState,
  applyHello,
  applyMessage,
  applyPresence,
  dismissRestarted,
  emptyRoom,
  reloadMemory,
} from "./room";

export interface EventSourceLike {
  readonly readyState: number;
  addEventListener(type: string, listener: (event: Event) => void): void;
  close(): void;
}

export type KeyValueStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export const RELOAD_KEY = "mstc-chat.reload";

// The server ends each stream every 20 s and the browser reconnects 1 s
// later, so only a stream down this long is a real drop.
const DOWN_NOTICE_MS = 3000;
const REJECT_RECONNECT_MS = 1000;
const RETRY_DELAYS_MS = [2000, 4000];
const RETRY_STEADY_MS = 10_000;
const EVENT_SOURCE_CLOSED = 2;

export interface StreamHandlers {
  onRoom(state: RoomState): void;
  onReconnecting(visible: boolean): void;
  onSignedOut(): void;
}

export interface StreamDeps {
  openSource(url: string): EventSourceLike;
  checkSession(): Promise<ApiResult<NameAnswer>>;
  sendLeave(tab: string): void;
  storage: KeyValueStore;
  reload(): void;
  getDraft(): string;
  now(): number;
}

export interface RoomStreamOptions {
  tab: string;
  memory: InstanceMemory;
  handlers: StreamHandlers;
  deps: StreamDeps;
}

const NO_MEMORY: InstanceMemory = {
  left: [],
  reloadedFor: null,
  restarted: false,
};

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

// Reads what the page saved before its own reload. The draft and the
// restarted flag are handed back once and then removed, so no message
// text stays in the browser.
export function readReloadMemory(storage: KeyValueStore): {
  memory: InstanceMemory;
  draft: string;
} {
  const raw = storage.getItem(RELOAD_KEY);
  if (raw === null) {
    return { memory: NO_MEMORY, draft: "" };
  }
  const saved = JSON.parse(raw) as Record<string, unknown>;
  const memory: InstanceMemory = {
    left: stringList(saved.left),
    reloadedFor:
      typeof saved.reloadedFor === "string" ? saved.reloadedFor : null,
    restarted: saved.restarted === true,
  };
  storage.setItem(RELOAD_KEY, JSON.stringify({ ...memory, restarted: false }));
  return { memory, draft: typeof saved.draft === "string" ? saved.draft : "" };
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const m = value as Record<string, unknown>;
  return (
    typeof m.seq === "number" &&
    typeof m.author === "string" &&
    typeof m.html === "string" &&
    typeof m.receivedAt === "string" &&
    typeof m.own === "boolean"
  );
}

function eventData(event: Event): unknown {
  return JSON.parse((event as MessageEvent<string>).data);
}

export class RoomStream {
  private state: RoomState;
  private source: EventSourceLike | null = null;
  private downTimer: ReturnType<typeof setTimeout> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private retries = 0;
  private noticeShown = false;
  private stopped = false;

  constructor(private readonly options: RoomStreamOptions) {
    this.state = emptyRoom(options.memory);
  }

  get room(): RoomState {
    return this.state;
  }

  open(): void {
    this.stopped = false;
    this.clearRetry();
    this.source?.close();
    const source = this.options.deps.openSource(
      `/api/stream?tab=${this.options.tab}`,
    );
    this.source = source;
    const on = (type: string, handle: (event: Event) => void): void => {
      source.addEventListener(type, (event) => {
        if (source === this.source && !this.stopped) {
          handle(event);
        }
      });
    };
    on("hello", (event) => this.onHello(event));
    on("message", (event) => this.onMessage(event));
    on("presence", (event) => this.onPresence(event));
    on("error", () => this.onError(source));
  }

  stop(): void {
    this.stopped = true;
    this.source?.close();
    this.clearRetry();
    this.clearDown();
  }

  dismissRestarted(): void {
    this.update(dismissRestarted(this.state));
  }

  handlePageHide(persisted: boolean): void {
    if (!persisted) {
      this.options.deps.sendLeave(this.options.tab);
    }
  }

  handlePageShow(persisted: boolean): void {
    if (persisted) {
      this.open();
    }
  }

  private update(state: RoomState): void {
    this.state = state;
    this.options.handlers.onRoom(state);
  }

  private onHello(event: Event): void {
    const { instance } = eventData(event) as { instance: string };
    this.markUp();
    const result = applyHello(this.state, instance, this.options.deps.now());
    if (result.action === "reload") {
      this.reloadFor(instance);
      return;
    }
    this.update(result.state);
    if (result.action === "reject") {
      this.source?.close();
      this.retryTimer = setTimeout(() => this.open(), REJECT_RECONNECT_MS);
    }
  }

  private onMessage(event: Event): void {
    const message = eventData(event);
    if (!isChatMessage(message)) {
      throw new TypeError("The stream sent a message event that lacks a field");
    }
    const instance =
      (event as MessageEvent<string>).lastEventId.split(":")[0] ?? "";
    this.update(applyMessage(this.state, instance, message));
  }

  private onPresence(event: Event): void {
    const { names } = eventData(event) as { names: unknown };
    this.update(applyPresence(this.state, stringList(names)));
  }

  private onError(source: EventSourceLike): void {
    this.startDown();
    if (source.readyState === EVENT_SOURCE_CLOSED) {
      source.close();
      void this.checkAfterRefusal();
    }
  }

  private async checkAfterRefusal(): Promise<void> {
    const answer = await this.options.deps.checkSession();
    if (this.stopped) {
      return;
    }
    if (answer.kind === "error" && answer.status === 401) {
      this.stop();
      this.options.handlers.onSignedOut();
      return;
    }
    const delay = RETRY_DELAYS_MS[this.retries] ?? RETRY_STEADY_MS;
    this.retries += 1;
    this.retryTimer = setTimeout(() => this.open(), delay);
  }

  private reloadFor(instance: string): void {
    const saved = {
      ...reloadMemory(this.state, instance),
      draft: this.options.deps.getDraft(),
    };
    this.options.deps.storage.setItem(RELOAD_KEY, JSON.stringify(saved));
    this.stop();
    this.options.deps.reload();
  }

  private markUp(): void {
    this.clearDown();
    this.retries = 0;
    if (this.noticeShown) {
      this.noticeShown = false;
      this.options.handlers.onReconnecting(false);
    }
  }

  private startDown(): void {
    if (this.downTimer !== null || this.noticeShown) {
      return;
    }
    this.downTimer = setTimeout(() => {
      this.downTimer = null;
      this.noticeShown = true;
      this.options.handlers.onReconnecting(true);
    }, DOWN_NOTICE_MS);
  }

  private clearDown(): void {
    if (this.downTimer !== null) {
      clearTimeout(this.downTimer);
      this.downTimer = null;
    }
  }

  private clearRetry(): void {
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  }
}
