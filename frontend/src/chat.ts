// The chat screen (component-specs.md, ChatScreen and its children). The
// markup is in index.html. Message HTML comes from the server, already
// sanitized (ADR-05), and is the only string inserted as HTML; names and
// every other text go in with textContent inside <bdi>.

import type { ApiFailure, ApiResult } from "./api";
import { setBusy, showAlert } from "./login";
import type { ChatMessage, RoomState } from "./room";

const TEXT = {
  unreachable:
    "Message not sent: the chat server could not be reached. Your text is kept; press Send to try again.",
  busy: "Message not sent: the chat is busy. Your text is kept; press Send to try again.",
  blank:
    "Message not sent: there is nothing to send. Type a message, then press Send.",
  rejected:
    "Message not sent: the chat did not accept the request. Your text is kept; press Send to try again.",
  restarted: "The chat restarted, so earlier messages are gone.",
  newTab: " (opens in a new tab)",
} as const;

// Refusals that are not about load get their own words, never "busy".
const SEND_REFUSAL_TEXT: Readonly<Record<string, string>> = {
  message_blank: TEXT.blank,
  bad_request: TEXT.rejected,
};

export const MESSAGE_LIMIT = 4000;
const COUNTER_FROM = 3500;
// A new message scrolls the list down only when the reader is this close
// to the bottom, so reading older messages is not interrupted.
const STICK_TO_BOTTOM_PX = 80;

const timeFormat = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
});

export interface ChatDeps {
  sendMessage(text: string): Promise<ApiResult<null>>;
  onSignedOut(): void;
  onDismissRestarted(): void;
}

export interface ChatView {
  show(viewerName: string, draft?: string): void;
  hide(): void;
  render(state: RoomState): void;
  setReconnecting(visible: boolean): void;
  draft(): string;
  isSending(): boolean;
}

function byId<T extends HTMLElement>(doc: Document, id: string): T {
  const element = doc.getElementById(id);
  if (element === null) {
    throw new Error(`index.html has no element with id "${id}"`);
  }
  return element as T;
}

function textElement(
  doc: Document,
  tag: string,
  text: string,
  className = "",
): HTMLElement {
  const element = doc.createElement(tag);
  element.textContent = text;
  if (className !== "") {
    element.className = className;
  }
  return element;
}

// The sanitizer's allowlist carries no accessibility attributes, so the
// client adds them after inserting the server's HTML (ADR-05).
function enhanceBody(body: HTMLElement, author: string): void {
  const doc = body.ownerDocument;
  body.querySelectorAll("a").forEach((link) => {
    link.classList.add("msg-link");
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.append(textElement(doc, "span", TEXT.newTab, "sr-only"));
  });
  body.querySelectorAll("pre").forEach((block) => {
    block.classList.add("code-block");
    block.tabIndex = 0;
    block.setAttribute("role", "region");
    block.setAttribute("aria-label", `Code from ${author}`);
  });
  body
    .querySelectorAll(":not(pre) > code")
    .forEach((code) => code.classList.add("code-inline"));
}

function renderMessage(
  doc: Document,
  key: string,
  message: ChatMessage,
): HTMLElement {
  const article = doc.createElement("article");
  article.className = `chat ${message.own ? "chat-end" : "chat-start"}`;
  article.dataset.key = key;
  article.dataset.seq = String(message.seq);
  const header = doc.createElement("div");
  header.className = "chat-header";
  header.id = `msg-${key.replace(":", "-")}`;
  article.setAttribute("aria-labelledby", header.id);
  const time = textElement(
    doc,
    "time",
    timeFormat.format(new Date(message.receivedAt)),
  );
  time.setAttribute("datetime", message.receivedAt);
  header.append(textElement(doc, "bdi", message.author, "author"), " ", time);
  const body = doc.createElement("div");
  body.className = message.own
    ? "chat-bubble chat-bubble-secondary"
    : "chat-bubble";
  body.innerHTML = message.html;
  enhanceBody(body, message.author);
  article.append(header, body);
  return article;
}

// Updates the list in place, so screen readers announce only new messages
// (role="log") and focus inside a kept message is not lost. Returns the
// messages the list did not show before; a reconnect that replays known
// messages returns none.
function syncMessages(list: HTMLElement, state: RoomState): ChatMessage[] {
  const keyOf = (m: ChatMessage): string => `${state.instance ?? ""}:${m.seq}`;
  const wanted = new Set(state.messages.map(keyOf));
  const existing = new Map<string, HTMLElement>();
  list.querySelectorAll<HTMLElement>("article").forEach((article) => {
    const key = article.dataset.key ?? "";
    if (wanted.has(key)) {
      existing.set(key, article);
    } else {
      article.remove();
    }
  });
  const added: ChatMessage[] = [];
  state.messages.forEach((message, index) => {
    const key = keyOf(message);
    let article = existing.get(key);
    if (article === undefined) {
      article = renderMessage(list.ownerDocument, key, message);
      added.push(message);
    }
    const at = list.children[index] ?? null;
    if (at !== article) {
      list.insertBefore(article, at);
    }
  });
  return added;
}

function isNearBottom(list: HTMLElement): boolean {
  return (
    list.scrollHeight - list.scrollTop - list.clientHeight <= STICK_TO_BOTTOM_PX
  );
}

interface Follower {
  follow(added: readonly ChatMessage[], wasNearBottom: boolean): void;
}

// Keeps the reader at the latest message, or, while they read history,
// counts others' new messages on the "New messages" button.
function setupFollower(doc: Document, list: HTMLElement): Follower {
  const button = byId<HTMLButtonElement>(doc, "jump-latest");
  let unseen = 0;

  const showUnseen = (count: number): void => {
    unseen = count;
    button.hidden = count === 0;
    button.textContent = `${count} new messages ↓`;
    button.setAttribute("aria-label", `${count} new messages, jump to latest`);
  };
  const jumpToLatest = (): void => {
    list.scrollTop = list.scrollHeight;
    showUnseen(0);
  };

  button.addEventListener("click", jumpToLatest);
  list.addEventListener("scroll", () => {
    if (isNearBottom(list)) {
      showUnseen(0);
    }
  });

  return {
    follow(added, wasNearBottom) {
      if (wasNearBottom || added.some((message) => message.own)) {
        jumpToLatest();
      } else {
        showUnseen(unseen + added.length);
      }
    },
  };
}

function orderNames(names: readonly string[], viewer: string): string[] {
  const others = [...names];
  const viewerAt = others.indexOf(viewer);
  if (viewerAt >= 0) {
    others.splice(viewerAt, 1);
  }
  others.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  return viewerAt >= 0 ? [viewer, ...others] : others;
}

function renderOnline(
  doc: Document,
  names: readonly string[] | null,
  viewer: string,
): void {
  const count = names === null ? "…" : String(names.length);
  doc
    .querySelectorAll("[data-online-count]")
    .forEach((el) => (el.textContent = count));
  const ordered = orderNames(names ?? [], viewer);
  doc.querySelectorAll("[data-online-names]").forEach((list) => {
    const rows = ordered.map((name, index) => {
      const row = doc.createElement("li");
      row.append(textElement(doc, "bdi", name));
      if (index === 0 && name === viewer) {
        row.append(" ", textElement(doc, "span", "(you)", "you"));
      }
      return row;
    });
    list.replaceChildren(...rows);
  });
}

interface Composer {
  draft(): string;
  setDraft(text: string): void;
  isSending(): boolean;
  focus(): void;
}

interface LengthParts {
  box: HTMLTextAreaElement;
  counter: HTMLElement;
  error: HTMLElement;
}

function setAttributeIf(
  element: HTMLElement,
  name: string,
  value: string,
  on: boolean,
): void {
  if (on) {
    element.setAttribute(name, value);
  } else {
    element.removeAttribute(name);
  }
}

function limitText(length: number): string {
  return `This message has ${length.toLocaleString()} characters. The limit is ${MESSAGE_LIMIT.toLocaleString()}.`;
}

// Shows the counter from 3,500 characters and the limit error above
// 4,000. The error is announced only when the person tries to send, so a
// screen reader does not speak on every keystroke. Returns whether the
// text is over the limit.
function showLength(parts: LengthParts, announce: boolean): boolean {
  const { box, counter, error } = parts;
  const length = [...box.value].length;
  const over = length > MESSAGE_LIMIT;
  counter.hidden = length < COUNTER_FROM;
  counter.textContent = `${length.toLocaleString()} / ${MESSAGE_LIMIT.toLocaleString()}`;
  error.hidden = !over;
  error.textContent = over ? limitText(length) : "";
  setAttributeIf(error, "role", "alert", announce && over);
  setAttributeIf(box, "aria-invalid", "true", over);
  return over;
}

// There are no uploads (AC-12): an image-only paste and a dropped file are
// cancelled, so nothing is inserted or sent.
function blockUploads(box: HTMLTextAreaElement): void {
  box.addEventListener("paste", (event) => {
    const data = event.clipboardData;
    if (
      data !== null &&
      data.files.length > 0 &&
      data.getData("text/plain") === ""
    ) {
      event.preventDefault();
    }
  });
  box.addEventListener("drop", (event) => {
    if ((event.dataTransfer?.files.length ?? 0) > 0) {
      event.preventDefault();
    }
  });
}

function setupComposer(doc: Document, deps: ChatDeps): Composer {
  const form = byId<HTMLFormElement>(doc, "message-form");
  const send = byId<HTMLButtonElement>(doc, "send");
  const alert = byId(doc, "send-alert");
  const parts: LengthParts = {
    box: byId<HTMLTextAreaElement>(doc, "message-box"),
    counter: byId(doc, "message-counter"),
    error: byId(doc, "message-error"),
  };
  const { box } = parts;
  let sending = false;
  const dismiss = (): void => alert.replaceChildren();

  const showFailure = (failure: ApiFailure): void => {
    if (failure.kind === "unreachable") {
      showAlert(alert, "error", TEXT.unreachable, dismiss);
    } else if (failure.status === 401) {
      deps.onSignedOut();
    } else if (failure.code === "message_too_long") {
      showLength(parts, true);
    } else {
      const text = SEND_REFUSAL_TEXT[failure.code] ?? TEXT.busy;
      showAlert(alert, "error", text, dismiss);
    }
  };

  const submit = async (): Promise<void> => {
    const text = box.value;
    if (sending || text.trim() === "" || showLength(parts, true)) {
      return;
    }
    sending = true;
    setBusy(send, true, "Sending…");
    const result = await deps.sendMessage(text);
    sending = false;
    setBusy(send, false, "Sending…");
    if (result.kind !== "ok") {
      showFailure(result);
      return;
    }
    dismiss();
    box.value = box.value === text ? "" : box.value;
    showLength(parts, false);
    box.focus();
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void submit();
  });
  box.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      void submit();
    }
  });
  box.addEventListener("input", () => showLength(parts, false));
  blockUploads(box);

  return {
    draft: () => box.value,
    setDraft: (text) => {
      box.value = text;
      showLength(parts, false);
    },
    isSending: () => sending,
    focus: () => box.focus(),
  };
}

// Returns the function that shows the restarted notice once per restart,
// so a later render does not replace the alert the reader is reading.
function setupRestartedNotice(
  doc: Document,
  deps: ChatDeps,
): (restarted: boolean) => void {
  const notices = byId(doc, "notice-area");
  let restartedShown = false;
  return (restarted) => {
    if (restarted && !restartedShown) {
      showAlert(notices, "info", TEXT.restarted, () =>
        deps.onDismissRestarted(),
      );
    } else if (!restarted) {
      notices.replaceChildren();
    }
    notices.hidden = !restarted;
    restartedShown = restarted;
  };
}

export function setupChat(doc: Document, deps: ChatDeps): ChatView {
  const screen = byId(doc, "chat-screen");
  const list = byId(doc, "messages");
  const loading = byId(doc, "messages-loading");
  const empty = byId(doc, "messages-empty");
  const reconnecting = byId(doc, "reconnecting");
  const composer = setupComposer(doc, deps);
  const follower = setupFollower(doc, list);
  const renderRestarted = setupRestartedNotice(doc, deps);
  let viewer = "";

  return {
    show(viewerName, draft = "") {
      viewer = viewerName;
      byId(doc, "viewer-name").textContent = viewerName;
      if (draft !== "") {
        composer.setDraft(draft);
      }
      doc.title = "MSTC Chat";
      screen.hidden = false;
      composer.focus();
    },
    hide() {
      screen.hidden = true;
    },
    render(state) {
      const wasNearBottom = isNearBottom(list);
      const added = syncMessages(list, state);
      loading.hidden = state.instance !== null;
      empty.hidden = state.instance === null || state.messages.length > 0;
      renderRestarted(state.restarted);
      renderOnline(doc, state.names, viewer);
      follower.follow(added, wasNearBottom);
    },
    setReconnecting(visible) {
      reconnecting.hidden = !visible;
    },
    draft: () => composer.draft(),
    isSending: () => composer.isSending(),
  };
}
