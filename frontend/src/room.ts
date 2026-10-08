// The page's copy of the room: pure functions over plain data, no DOM
// (ADR-06). The server owns order, history and the online list; this state
// only mirrors what the stream says.

export const HISTORY_LIMIT = 200;

// After a redeploy, Cloud Run can still route a reconnect to the old
// revision for a while. The page refuses an instance it already left, and
// gives in after this long so it never stays disconnected.
export const REJECT_LEFT_INSTANCE_MS = 10_000;

export interface ChatMessage {
  readonly seq: number;
  readonly author: string;
  readonly html: string;
  readonly receivedAt: string;
  readonly own: boolean;
}

// What the page carries across its own reload, in sessionStorage.
export interface InstanceMemory {
  readonly left: readonly string[];
  readonly reloadedFor: string | null;
  readonly restarted: boolean;
}

export interface RoomState {
  readonly instance: string | null;
  readonly left: readonly string[];
  readonly reloadedFor: string | null;
  readonly rejectingSince: number | null;
  readonly messages: readonly ChatMessage[];
  // null until the first presence event, so the list can show "…".
  readonly names: readonly string[] | null;
  readonly restarted: boolean;
}

// accept: first hello on the page. same: the stream came back to the same
// server. switch: a different server, take it without reloading. reject:
// an instance the page already left; reconnect. reload: a new instance;
// reload the page to load its client.
export type HelloAction = "accept" | "same" | "switch" | "reject" | "reload";

export interface HelloResult {
  readonly state: RoomState;
  readonly action: HelloAction;
}

const NO_MEMORY: InstanceMemory = {
  left: [],
  reloadedFor: null,
  restarted: false,
};

export function emptyRoom(memory: InstanceMemory = NO_MEMORY): RoomState {
  return {
    instance: null,
    left: memory.left,
    reloadedFor: memory.reloadedFor,
    rejectingSince: null,
    messages: [],
    names: null,
    restarted: memory.restarted,
  };
}

export function applyHello(
  state: RoomState,
  instance: string,
  now: number,
): HelloResult {
  if (instance === state.instance) {
    return { state: { ...state, rejectingSince: null }, action: "same" };
  }
  if (state.left.includes(instance)) {
    return rejectOrSwitch(state, instance, now);
  }
  if (state.instance === null) {
    return {
      state: { ...state, instance, rejectingSince: null },
      action: "accept",
    };
  }
  if (state.reloadedFor === instance) {
    return { state: switchTo(state, instance), action: "switch" };
  }
  return { state, action: "reload" };
}

function rejectOrSwitch(
  state: RoomState,
  instance: string,
  now: number,
): HelloResult {
  const since = state.rejectingSince ?? now;
  if (now - since >= REJECT_LEFT_INSTANCE_MS) {
    return { state: switchTo(state, instance), action: "switch" };
  }
  return { state: { ...state, rejectingSince: since }, action: "reject" };
}

function leftWith(state: RoomState): string[] {
  const current = state.instance;
  return current === null
    ? [...state.left]
    : [...state.left.filter((i) => i !== current), current];
}

function switchTo(state: RoomState, instance: string): RoomState {
  return {
    ...state,
    instance,
    left: leftWith(state).filter((i) => i !== instance),
    rejectingSince: null,
    messages: [],
    restarted: true,
  };
}

export function reloadMemory(
  state: RoomState,
  instance: string,
): InstanceMemory {
  return { left: leftWith(state), reloadedFor: instance, restarted: true };
}

export function applyMessage(
  state: RoomState,
  instance: string,
  message: ChatMessage,
): RoomState {
  if (instance !== state.instance) {
    return state;
  }
  if (state.messages.some((shown) => shown.seq === message.seq)) {
    return state;
  }
  const messages = [...state.messages, message]
    .sort((a, b) => a.seq - b.seq)
    .slice(-HISTORY_LIMIT);
  return { ...state, messages, restarted: false };
}

export function applyPresence(
  state: RoomState,
  names: readonly string[],
): RoomState {
  return { ...state, names: [...names] };
}

export function dismissRestarted(state: RoomState): RoomState {
  return { ...state, restarted: false };
}
