// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import page from "../index.html?raw";
import type { ApiResult } from "./api";
import { type ChatDeps, setupChat } from "./chat";
import { type ChatMessage, type RoomState, emptyRoom } from "./room";

const INSTANCE = "3f9a0c1d2b4e5f60";

function byId<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (element === null) {
    throw new Error(`index.html has no #${id}`);
  }
  return element as T;
}

const box = () => byId<HTMLTextAreaElement>("message-box");
const sendButton = () => byId<HTMLButtonElement>("send");
const sendAlertText = () =>
  byId("send-alert").querySelector("[data-text]")?.textContent ?? "";
const articles = () => [...byId("messages").querySelectorAll("article")];

function settle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function message(
  seq: number,
  overrides: Partial<ChatMessage> = {},
): ChatMessage {
  return {
    seq,
    author: "Avery",
    html: `<p>message ${seq}</p>`,
    receivedAt: "2026-10-08T15:02:03.123Z",
    own: false,
    ...overrides,
  };
}

function room(overrides: Partial<RoomState> = {}): RoomState {
  return { ...emptyRoom(), instance: INSTANCE, names: [], ...overrides };
}

function start(
  result: ApiResult<null> = { kind: "ok", data: null },
  draft = "",
) {
  const sendMessage = vi.fn<ChatDeps["sendMessage"]>(() =>
    Promise.resolve(result),
  );
  const onSignedOut = vi.fn();
  const onDismissRestarted = vi.fn();
  const view = setupChat(document, {
    sendMessage,
    onSignedOut,
    onDismissRestarted,
  });
  view.show("Casey", draft);
  return { view, sendMessage, onSignedOut, onDismissRestarted };
}

function press(key: string, options: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key,
    cancelable: true,
    bubbles: true,
    ...options,
  });
  box().dispatchEvent(event);
  return event;
}

function type(text: string): void {
  box().value = text;
  box().dispatchEvent(new Event("input", { bubbles: true }));
}

function clipboardEvent(name: string, files: File[], text: string): Event {
  const event = new Event(name, { cancelable: true, bubbles: true });
  const data = {
    files,
    types: files.length > 0 ? ["Files"] : [],
    getData: () => text,
  };
  Object.defineProperty(
    event,
    name === "paste" ? "clipboardData" : "dataTransfer",
    {
      value: data,
    },
  );
  return event;
}

const image = () =>
  new File([new Uint8Array([137, 80, 78, 71])], "shot.png", {
    type: "image/png",
  });

beforeEach(() => {
  document.body.innerHTML = new DOMParser().parseFromString(
    page,
    "text/html",
  ).body.innerHTML;
});

describe("message box keys (AC-5)", () => {
  it("should send the text when the person presses Enter", async () => {
    const { sendMessage } = start();
    type("hello\nsecond line");

    const event = press("Enter");
    await settle();

    expect(event.defaultPrevented).toBe(true);
    expect(sendMessage).toHaveBeenCalledWith("hello\nsecond line");
  });

  it("should add a line and send nothing when the person presses Shift+Enter", async () => {
    const { sendMessage } = start();
    type("hello");

    const event = press("Enter", { shiftKey: true });
    await settle();

    expect(event.defaultPrevented).toBe(false);
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("should send nothing when Enter confirms an input-method composition", async () => {
    const { sendMessage } = start();
    type("こんにちは");

    press("Enter", { isComposing: true });
    await settle();

    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("should send nothing when the box holds only spaces and line breaks", async () => {
    const { sendMessage } = start();
    type("  \n  ");

    press("Enter");
    sendButton().click();
    await settle();

    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("should send the text when the person presses Send", async () => {
    const { sendMessage } = start();
    type("from the button");

    sendButton().click();
    await settle();

    expect(sendMessage).toHaveBeenCalledWith("from the button");
  });

  it("should clear the box and keep focus when the server accepts the message", async () => {
    start();
    type("hello");

    sendButton().click();
    await settle();

    expect(box().value).toBe("");
    expect(document.activeElement).toBe(box());
  });
});

describe("failed sends (AC-11)", () => {
  it("should say there is nothing to send and never busy when the server answers message_blank", async () => {
    start({ kind: "error", status: 422, code: "message_blank" });
    type("\u200b");

    sendButton().click();
    await settle();

    expect(sendAlertText()).toBe(
      "Message not sent: there is nothing to send. Type a message, then press Send.",
    );
    expect(box().value).toBe("\u200b");
  });

  it("should say the request was not accepted and never busy when the server answers bad_request", async () => {
    start({ kind: "error", status: 400, code: "bad_request" });
    type("keep me");

    sendButton().click();
    await settle();

    expect(sendAlertText()).toBe(
      "Message not sent: the chat did not accept the request. Your text is kept; press Send to try again.",
    );
    expect(box().value).toBe("keep me");
  });

  it("should say so and keep the text when the server cannot be reached", async () => {
    start({ kind: "unreachable" });
    type("keep me");

    sendButton().click();
    await settle();

    expect(sendAlertText()).toBe(
      "Message not sent: the chat server could not be reached. Your text is kept; press Send to try again.",
    );
    expect(box().value).toBe("keep me");
  });

  it("should say the chat is busy and keep the text when the server answers 429", async () => {
    start({ kind: "error", status: 429, code: "busy" });
    type("keep me");

    sendButton().click();
    await settle();

    expect(sendAlertText()).toBe(
      "Message not sent: the chat is busy. Your text is kept; press Send to try again.",
    );
    expect(box().value).toBe("keep me");
  });

  it("should report signed out and keep the draft when the server answers 401", async () => {
    const { onSignedOut } = start({
      kind: "error",
      status: 401,
      code: "signed_out",
    });
    type("keep me");

    sendButton().click();
    await settle();

    expect(onSignedOut).toHaveBeenCalledTimes(1);
    expect(box().value).toBe("keep me");
  });

  it("should remove the alert when the reader dismisses it", async () => {
    start({ kind: "unreachable" });
    type("keep me");
    sendButton().click();
    await settle();

    byId("send-alert")
      .querySelector<HTMLButtonElement>("[data-dismiss]")
      ?.click();

    expect(byId("send-alert").children).toHaveLength(0);
  });
});

describe("message length (AC-7)", () => {
  it("should not send and should show the limit when the text has more than 4,000 characters", async () => {
    const { sendMessage } = start();
    type("x".repeat(4001));

    sendButton().click();
    await settle();

    expect(sendMessage).not.toHaveBeenCalled();
    expect(byId("message-error").textContent).toBe(
      "This message has 4,001 characters. The limit is 4,000.",
    );
    expect(byId("message-error").getAttribute("role")).toBe("alert");
    expect(byId("message-counter").textContent).toBe("4,001 / 4,000");
    expect(box().getAttribute("aria-invalid")).toBe("true");
  });

  it("should send when the text has exactly 4,000 characters", async () => {
    const { sendMessage } = start();
    type("x".repeat(4000));

    sendButton().click();
    await settle();

    expect(sendMessage).toHaveBeenCalledTimes(1);
  });
});

describe("no uploads (AC-12)", () => {
  it("should cancel the paste and send nothing when the clipboard holds only an image", async () => {
    const { sendMessage } = start();
    type("before");

    const event = clipboardEvent("paste", [image()], "");
    box().dispatchEvent(event);
    await settle();

    expect(event.defaultPrevented).toBe(true);
    expect(box().value).toBe("before");
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("should let a text paste through when the clipboard holds text", () => {
    start();

    const event = clipboardEvent("paste", [], "a link https://example.edu");
    box().dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
  });

  it("should cancel a file dropped on the message box and send nothing", async () => {
    const { sendMessage } = start();

    const event = clipboardEvent("drop", [image()], "");
    box().dispatchEvent(event);
    await settle();

    expect(event.defaultPrevented).toBe(true);
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("should offer no file input on the chat screen", () => {
    start();

    expect(document.querySelector("input[type=file]")).toBeNull();
  });
});

describe("message rendering", () => {
  it("should keep a code block's line breaks in a monospace panel when a message holds one (AC-8)", () => {
    const { view } = start();

    view.render(
      room({
        messages: [
          message(1, { html: "<pre><code>line 1\nline 2\n</code></pre>" }),
        ],
      }),
    );

    const block = byId("messages").querySelector("pre");
    expect(block?.classList.contains("code-block")).toBe(true);
    expect(block?.querySelector("code")?.textContent).toBe("line 1\nline 2\n");
    expect(block?.getAttribute("tabindex")).toBe("0");
    expect(block?.getAttribute("role")).toBe("region");
    expect(block?.getAttribute("aria-label")).toBe("Code from Avery");
  });

  it("should show a name holding HTML as text when the author's name contains a script tag (AC-13)", () => {
    const { view } = start();

    view.render(
      room({ messages: [message(1, { author: "<script>alert(1)</script>" })] }),
    );

    const author = byId("messages").querySelector("bdi");
    expect(author?.textContent).toBe("<script>alert(1)</script>");
    expect(byId("messages").querySelector("script")).toBeNull();
  });

  it("should put own messages on the other side when the server marks them own (AC-6)", () => {
    const { view } = start();

    view.render(
      room({
        messages: [message(1, { own: false }), message(2, { own: true })],
      }),
    );

    const [others, own] = articles();
    expect(others?.classList.contains("chat-start")).toBe(true);
    expect(own?.classList.contains("chat-end")).toBe(true);
    expect(
      own
        ?.querySelector(".chat-bubble")
        ?.classList.contains("chat-bubble-secondary"),
    ).toBe(true);
  });

  it("should show the author's name and the local hours and minutes when a message renders (AC-6)", () => {
    const { view } = start();

    view.render(room({ messages: [message(1, { author: "Jordan" })] }));

    const time = articles()[0]?.querySelector("time");
    expect(articles()[0]?.querySelector("bdi")?.textContent).toBe("Jordan");
    expect(time?.getAttribute("datetime")).toBe("2026-10-08T15:02:03.123Z");
    expect(time?.textContent).toMatch(/^\d{1,2}:\d{2}/);
    expect(articles()[0]?.getAttribute("aria-labelledby")).toBe(
      articles()[0]?.querySelector(".chat-header")?.id,
    );
  });

  it("should tell screen readers that a link opens a new tab when a message holds a link", () => {
    const { view } = start();

    view.render(
      room({
        messages: [
          message(1, {
            html: '<p><a href="https://example.edu" target="_blank" rel="noopener noreferrer">https://example.edu</a></p>',
          }),
        ],
      }),
    );

    const link = byId("messages").querySelector("a");
    expect(link?.textContent).toBe("https://example.edu (opens in a new tab)");
    expect(link?.querySelector(".sr-only")?.textContent).toBe(
      " (opens in a new tab)",
    );
    expect(link?.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("should show each message once and only the room's messages when the room renders again", () => {
    const { view } = start();
    view.render(room({ messages: [message(1), message(2)] }));

    view.render(room({ messages: [message(2), message(3)] }));

    expect(articles().map((a) => a.dataset.seq)).toEqual(["2", "3"]);
  });
});

describe("room states (AC-10, AC-19)", () => {
  it("should show the loading state when no server has said hello yet", () => {
    const { view } = start();

    view.render(emptyRoom());

    expect(byId("messages-loading").hidden).toBe(false);
    expect(byId("messages-empty").hidden).toBe(true);
  });

  it("should show the empty room when the room has no messages", () => {
    const { view } = start();

    view.render(room());

    expect(byId("messages-empty").hidden).toBe(false);
    expect(byId("messages-loading").hidden).toBe(true);
  });

  it("should show the restarted notice and the empty room when the chat restarted", () => {
    const { view } = start();
    view.render(room({ messages: [message(1)] }));

    view.render(room({ restarted: true }));

    expect(byId("notice-area").textContent).toContain(
      "The chat restarted, so earlier messages are gone.",
    );
    expect(byId("notice-area").hidden).toBe(false);
    expect(articles()).toHaveLength(0);
    expect(byId("messages-empty").hidden).toBe(false);
  });

  it("should ask to dismiss the restarted notice when the reader presses Dismiss", () => {
    const { view, onDismissRestarted } = start();
    view.render(room({ restarted: true }));

    byId("notice-area")
      .querySelector<HTMLButtonElement>("[data-dismiss]")
      ?.click();

    expect(onDismissRestarted).toHaveBeenCalledTimes(1);
  });

  it("should show the reconnecting notice when the stream is down and hide it when it returns", () => {
    const { view } = start();

    view.setReconnecting(true);
    const shown = !byId("reconnecting").hidden;
    view.setReconnecting(false);

    expect(shown).toBe(true);
    expect(byId("reconnecting").hidden).toBe(true);
  });

  it("should put the saved draft back in the box when the page shows after a reload", () => {
    const { view } = start({ kind: "ok", data: null }, "half-written question");

    expect(box().value).toBe("half-written question");
    expect(view.draft()).toBe("half-written question");
  });
});

describe("online list (AC-9)", () => {
  it("should list the viewer first with (you), then the others alphabetically", () => {
    const { view } = start();

    view.render(room({ names: ["jordan", "Casey", "Avery"] }));

    const column = document.querySelector("aside [data-online-names]");
    const rows = [...(column?.querySelectorAll("li") ?? [])].map(
      (li) => li.textContent,
    );
    expect(rows).toEqual(["Casey (you)", "Avery", "jordan"]);
    expect(
      document.querySelector("aside [data-online-count]")?.textContent,
    ).toBe("3");
  });

  it("should show an ellipsis for the count when no presence event has arrived", () => {
    const { view } = start();

    view.render(room({ names: null }));

    expect(
      document.querySelector("summary [data-online-count]")?.textContent,
    ).toBe("…");
  });

  it("should show a name holding HTML as text in the online list", () => {
    const { view } = start();

    view.render(room({ names: ["<img src=x onerror=alert(1)>"] }));

    expect(document.querySelector("[data-online-names] img")).toBeNull();
    expect(document.querySelector("[data-online-names] bdi")?.textContent).toBe(
      "<img src=x onerror=alert(1)>",
    );
  });
});

describe("new messages button (AC-1 to AC-4)", () => {
  // jsdom has no layout, so each test gives the list a 400 px window and
  // sets how tall its content is.
  const WINDOW_PX = 400;
  const CONTENT_PX = 1000;
  const SCROLLED_UP_TOP = 200;
  const list = () => byId("messages");
  const jumpButton = () => byId<HTMLButtonElement>("jump-latest");
  const distanceFromBottom = () =>
    list().scrollHeight - list().scrollTop - list().clientHeight;

  function setContentHeight(px: number): void {
    Object.defineProperty(list(), "scrollHeight", {
      configurable: true,
      value: px,
    });
    Object.defineProperty(list(), "clientHeight", {
      configurable: true,
      value: WINDOW_PX,
    });
  }

  function scrollTo(top: number): void {
    list().scrollTop = top;
    list().dispatchEvent(new Event("scroll"));
  }

  // The first message fits the window, so the reader starts at the bottom;
  // then the content grows and the reader scrolls 400 px above the bottom.
  function startScrolledUp() {
    const started = start();
    setContentHeight(WINDOW_PX);
    started.view.render(room({ messages: [message(1)] }));
    setContentHeight(CONTENT_PX);
    scrollTo(SCROLLED_UP_TOP);
    return started;
  }

  it("should keep the reader's place and show the count of others' new messages when the reader has scrolled up", () => {
    const button = jumpButton();
    const { view } = startScrolledUp();

    view.render(room({ messages: [message(1), message(2), message(3)] }));
    view.render(
      room({ messages: [message(1), message(2), message(3), message(4)] }),
    );

    expect(list().scrollTop).toBe(SCROLLED_UP_TOP);
    expect(button.hidden).toBe(false);
    expect(button.textContent).toBe("3 new messages ↓");
    expect(button.getAttribute("aria-label")).toBe(
      "3 new messages, jump to latest",
    );
  });

  it("should keep the count when the room renders again with no new messages after a reconnect", () => {
    const button = jumpButton();
    const { view } = startScrolledUp();
    const twoNew = room({ messages: [message(1), message(2), message(3)] });

    view.render(twoNew);
    view.render(twoNew);

    expect(button.getAttribute("aria-label")).toBe(
      "2 new messages, jump to latest",
    );
  });

  it("should scroll to the bottom and hide the button when the reader clicks it", () => {
    const button = jumpButton();
    const { view } = startScrolledUp();
    view.render(room({ messages: [message(1), message(2)] }));
    const shownBeforeClick = !button.hidden;

    button.click();

    expect(shownBeforeClick).toBe(true);
    expect(distanceFromBottom()).toBeLessThanOrEqual(0);
    expect(button.hidden).toBe(true);
  });

  it("should hide the button and start counting again from 1 when the reader scrolls back to within 80 px of the bottom", () => {
    const button = jumpButton();
    const { view } = startScrolledUp();
    view.render(room({ messages: [message(1), message(2), message(3)] }));

    scrollTo(CONTENT_PX - WINDOW_PX - 80);
    const hiddenNearBottom = button.hidden;
    scrollTo(SCROLLED_UP_TOP);
    view.render(
      room({ messages: [message(1), message(2), message(3), message(4)] }),
    );

    expect(hiddenNearBottom).toBe(true);
    expect(button.hidden).toBe(false);
    expect(button.getAttribute("aria-label")).toBe(
      "1 new messages, jump to latest",
    );
  });

  it("should scroll to the bottom and hide the button when the participant's own message arrives while scrolled up", () => {
    const button = jumpButton();
    const { view } = startScrolledUp();
    view.render(room({ messages: [message(1), message(2)] }));
    const shownBeforeOwn = !button.hidden;

    view.render(
      room({
        messages: [message(1), message(2), message(3, { own: true })],
      }),
    );

    expect(shownBeforeOwn).toBe(true);
    expect(distanceFromBottom()).toBeLessThanOrEqual(0);
    expect(button.hidden).toBe(true);
  });

  it("should follow new messages and show no button when the reader is at the bottom", () => {
    const button = jumpButton();
    const { view } = start();
    setContentHeight(CONTENT_PX);
    scrollTo(CONTENT_PX - WINDOW_PX);

    view.render(room({ messages: [message(1), message(2)] }));

    expect(distanceFromBottom()).toBeLessThanOrEqual(0);
    expect(button.hidden).toBe(true);
  });
});

describe("arrival", () => {
  it("should show the viewer's name and focus the message box when the chat shows", () => {
    start();

    expect(byId("viewer-name").textContent).toBe("Casey");
    expect(byId("chat-screen").hidden).toBe(false);
    expect(document.activeElement).toBe(box());
  });
});
