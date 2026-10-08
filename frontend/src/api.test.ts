import { afterEach, describe, expect, it, vi } from "vitest";

import { leave, login, sendMessage, session } from "./api";

type FetchArgs = [input: string, init?: RequestInit];

function answer(
  status: number,
  body: string | null,
  contentType = "application/json",
) {
  const fake = vi.fn<(...args: FetchArgs) => Promise<Response>>(() =>
    Promise.resolve(
      new Response(body, { status, headers: { "Content-Type": contentType } }),
    ),
  );
  vi.stubGlobal("fetch", fake);
  return fake;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("login", () => {
  it("should post the name and password as JSON and return the server's cleaned name", async () => {
    const fake = answer(200, JSON.stringify({ name: "Avery" }));

    const result = await login("  Avery  ", "secret words");

    expect(result).toEqual({ kind: "ok", data: { name: "Avery" } });
    const [url, init] = fake.mock.calls[0] ?? [];
    expect(url).toBe("/api/login");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      name: "  Avery  ",
      password: "secret words",
    });
  });

  it("should return the server's error code when the password is wrong", async () => {
    answer(401, JSON.stringify({ error: "wrong_password" }));

    const result = await login("Avery", "wrong");

    expect(result).toEqual({
      kind: "error",
      status: 401,
      code: "wrong_password",
    });
  });

  it("should return unreachable when the network fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    const result = await login("Avery", "secret");

    expect(result).toEqual({ kind: "unreachable" });
  });

  it("should map the status code when the error body is not JSON", async () => {
    answer(413, "<html>Request Entity Too Large</html>", "text/html");

    const result = await login("Avery", "secret");

    expect(result).toEqual({ kind: "error", status: 413, code: "too_large" });
  });

  it("should report a server error when a 5xx answer has no JSON body", async () => {
    answer(502, "Bad Gateway", "text/plain");

    const result = await login("Avery", "secret");

    expect(result).toEqual({
      kind: "error",
      status: 502,
      code: "server_error",
    });
  });
});

describe("session", () => {
  it("should return the signed-in name when the cookie is good", async () => {
    answer(200, JSON.stringify({ name: "Jordan" }));

    expect(await session()).toEqual({ kind: "ok", data: { name: "Jordan" } });
  });

  it("should return signed_out when a 401 answer has no JSON body", async () => {
    answer(401, "", "text/plain");

    expect(await session()).toEqual({
      kind: "error",
      status: 401,
      code: "signed_out",
    });
  });
});

describe("sendMessage", () => {
  it("should post the text as JSON and succeed when the server answers 204", async () => {
    const fake = answer(204, null);

    const result = await sendMessage("hello\nworld");

    expect(result).toEqual({ kind: "ok", data: null });
    const [url, init] = fake.mock.calls[0] ?? [];
    expect(url).toBe("/api/messages");
    expect(JSON.parse(String(init?.body))).toEqual({ text: "hello\nworld" });
  });

  it("should return the server's code when the message is refused", async () => {
    answer(422, JSON.stringify({ error: "message_too_long" }));

    expect(await sendMessage("x")).toEqual({
      kind: "error",
      status: 422,
      code: "message_too_long",
    });
  });
});

describe("leave", () => {
  it("should send the tab id as the beacon's body to the leave route", () => {
    const beacon = vi.fn(() => true);
    vi.stubGlobal("navigator", { sendBeacon: beacon });

    leave("0b6f6c1e-8f3a-4a4e-9a51-1f6c2d3e4f50");

    expect(beacon).toHaveBeenCalledWith(
      "/api/leave",
      "0b6f6c1e-8f3a-4a4e-9a51-1f6c2d3e4f50",
    );
  });
});
