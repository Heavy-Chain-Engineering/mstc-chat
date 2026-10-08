// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import page from "../index.html?raw";
import type { ApiResult, NameAnswer } from "./api";
import { type LoginDeps, setupLogin } from "./login";

type LoginResult = ApiResult<NameAnswer>;

function byId<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (element === null) {
    throw new Error(`index.html has no #${id}`);
  }
  return element as T;
}

const nameInput = () => byId<HTMLInputElement>("login-name");
const passwordInput = () => byId<HTMLInputElement>("login-password");
const joinButton = () => byId<HTMLButtonElement>("login-join");
const alertText = () => byId("login-alert").textContent?.trim() ?? "";

function settle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function start(result: LoginResult | Promise<LoginResult>) {
  const login = vi.fn<LoginDeps["login"]>(() => Promise.resolve(result));
  const onJoined = vi.fn();
  const view = setupLogin(document, { login, onJoined });
  view.show();
  return { login, onJoined, view };
}

async function join(name: string, password: string): Promise<void> {
  nameInput().value = name;
  passwordInput().value = password;
  joinButton().click();
  await settle();
}

beforeEach(() => {
  document.body.innerHTML = new DOMParser().parseFromString(
    page,
    "text/html",
  ).body.innerHTML;
});

describe("login page markup (AC-1)", () => {
  it("should hide the typed password when the class password field renders", () => {
    start({ kind: "ok", data: { name: "Avery" } });

    expect(passwordInput().type).toBe("password");
    expect(
      document.querySelector("label[for=login-password]")?.textContent,
    ).toBe("Class password");
  });

  it("should label the name field and the Join button when the page renders", () => {
    start({ kind: "ok", data: { name: "Avery" } });

    expect(document.querySelector("label[for=login-name]")?.textContent).toBe(
      "Display name",
    );
    expect(joinButton().textContent?.trim()).toBe("Join");
    expect(joinButton().type).toBe("submit");
  });

  it("should put focus in the display name when the page shows", () => {
    start({ kind: "ok", data: { name: "Avery" } });

    expect(document.activeElement).toBe(nameInput());
    expect(byId("login-screen").hidden).toBe(false);
  });
});

describe("joining", () => {
  it("should hand over the server's cleaned name when the password is right", async () => {
    const { login, onJoined } = start({ kind: "ok", data: { name: "Avery" } });

    await join("  Avery  ", "secret words");

    expect(login).toHaveBeenCalledWith("  Avery  ", "secret words");
    expect(onJoined).toHaveBeenCalledWith("Avery");
  });

  it("should show an error and send nothing when the name is blank", async () => {
    const { login } = start({ kind: "ok", data: { name: "Avery" } });

    await join("   ", "secret");

    expect(login).not.toHaveBeenCalled();
    expect(byId("login-name-error").textContent).toBe("Enter a display name.");
    expect(byId("login-name-error").hidden).toBe(false);
    expect(nameInput().getAttribute("aria-invalid")).toBe("true");
  });

  it("should keep the name and clear the password when the password is wrong", async () => {
    start({ kind: "error", status: 401, code: "wrong_password" });

    await join("Avery", "wrong");

    expect(alertText()).toBe(
      "That class password is not right. Check it and try again.",
    );
    expect(byId("login-alert").querySelector("[role=alert]")).not.toBeNull();
    expect(nameInput().value).toBe("Avery");
    expect(passwordInput().value).toBe("");
    expect(passwordInput().getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(passwordInput());
  });

  it("should say so and keep both fields when the server cannot be reached (AC-11)", async () => {
    start({ kind: "unreachable" });

    await join("Avery", "secret");

    expect(alertText()).toBe(
      "Could not reach the chat server. Check your connection and press Join again.",
    );
    expect(nameInput().value).toBe("Avery");
    expect(passwordInput().value).toBe("secret");
    expect(document.activeElement).toBe(joinButton());
  });

  it("should ask for a shorter name when the server refuses a long one", async () => {
    start({ kind: "error", status: 422, code: "name_too_long" });

    await join("A".repeat(50), "secret");

    expect(byId("login-name-error").textContent).toBe(
      "Use 50 characters or fewer.",
    );
    expect(nameInput().value).toBe("A".repeat(50));
  });

  it.each([
    [
      429,
      "busy",
      "The chat is busy right now. Wait a few seconds and press Join again.",
    ],
    [
      503,
      "server_error",
      "The chat server had a problem. Wait a few seconds and press Join again.",
    ],
    [
      400,
      "bad_request",
      "The chat did not accept that request. Press Join to try again.",
    ],
    [
      413,
      "too_large",
      "That request was too large. Shorten your display name and try again.",
    ],
  ])(
    "should show the matching alert when the server answers %i",
    async (status, code, text) => {
      start({ kind: "error", status, code });

      await join("Avery", "secret");

      expect(alertText()).toBe(text);
      expect(nameInput().value).toBe("Avery");
    },
  );

  it("should show Joining and ignore a second press while the answer is pending", async () => {
    let answer: (result: LoginResult) => void = () => undefined;
    const pending = new Promise<LoginResult>((resolve) => {
      answer = resolve;
    });
    const { login } = start(pending);

    await join("Avery", "secret");
    joinButton().click();
    await settle();
    const busyLabel = joinButton().textContent?.trim();
    const busy = joinButton().getAttribute("aria-busy");
    answer({ kind: "ok", data: { name: "Avery" } });
    await settle();

    expect(login).toHaveBeenCalledTimes(1);
    expect(busyLabel).toBe("Joining…");
    expect(busy).toBe("true");
    expect(joinButton().getAttribute("aria-busy")).toBeNull();
  });

  it("should clear the previous alert when the person presses Join again", async () => {
    const results: LoginResult[] = [
      { kind: "error", status: 401, code: "wrong_password" },
      { kind: "ok", data: { name: "Avery" } },
    ];
    const login = vi.fn((): Promise<LoginResult> =>
      Promise.resolve(results.shift() ?? { kind: "unreachable" }),
    );
    setupLogin(document, { login, onJoined: vi.fn() }).show();

    await join("Avery", "wrong");
    await join("Avery", "right");

    expect(alertText()).toBe("");
  });
});

describe("session ended (AC-4)", () => {
  it("should show the session-ended notice when the page shows after a refused session", () => {
    const { view } = start({ kind: "ok", data: { name: "Avery" } });

    view.show({ sessionEnded: true });

    expect(alertText()).toBe(
      "Your session has ended. Join again to keep chatting.",
    );
    expect(byId("login-alert").querySelector("[role=status]")).not.toBeNull();
  });
});
