// The JSON API (design.md, "API Contracts"). Every call returns a typed
// result and never throws for an HTTP status or a network failure, so each
// screen decides what to show for each outcome.

export type ApiFailure =
  | { readonly kind: "error"; readonly status: number; readonly code: string }
  | { readonly kind: "unreachable" };

export type ApiResult<T> =
  { readonly kind: "ok"; readonly data: T } | ApiFailure;

export interface NameAnswer {
  readonly name: string;
}

// A request with no answer after this long counts as unreachable (AC-11).
const REQUEST_TIMEOUT_MS = 10_000;

// Used when an error body is not the server's JSON, for example a proxy's
// HTML page.
const CODE_BY_STATUS: Readonly<Record<number, string>> = {
  400: "bad_request",
  401: "signed_out",
  403: "cross_site",
  413: "too_large",
  429: "busy",
};

function codeForStatus(status: number): string {
  return (
    CODE_BY_STATUS[status] ?? (status >= 500 ? "server_error" : "unexpected")
  );
}

async function errorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "error" in body) {
      const code = body.error;
      if (typeof code === "string") {
        return code;
      }
    }
  } catch (error: unknown) {
    if (!(error instanceof SyntaxError)) {
      throw error;
    }
  }
  return codeForStatus(response.status);
}

async function request(
  path: string,
  init: RequestInit,
): Promise<Response | null> {
  try {
    return await fetch(path, {
      ...init,
      credentials: "same-origin",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error: unknown) {
    // fetch rejects with a TypeError on a network failure and a
    // DOMException when the timeout aborts it; both mean no answer.
    if (error instanceof TypeError || error instanceof DOMException) {
      return null;
    }
    throw error;
  }
}

async function readName(response: Response): Promise<NameAnswer> {
  const body = (await response.json()) as { name?: unknown };
  if (typeof body.name !== "string") {
    throw new TypeError(`Expected a name in the ${response.url} answer`);
  }
  return { name: body.name };
}

async function call<T>(
  path: string,
  init: RequestInit,
  read: (response: Response) => Promise<T>,
): Promise<ApiResult<T>> {
  const response = await request(path, init);
  if (response === null) {
    return { kind: "unreachable" };
  }
  if (!response.ok) {
    return {
      kind: "error",
      status: response.status,
      code: await errorCode(response),
    };
  }
  return { kind: "ok", data: await read(response) };
}

function postJson(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function login(
  name: string,
  password: string,
): Promise<ApiResult<NameAnswer>> {
  return call("/api/login", postJson({ name, password }), readName);
}

export function session(): Promise<ApiResult<NameAnswer>> {
  return call("/api/session", { method: "GET" }, readName);
}

export function sendMessage(text: string): Promise<ApiResult<null>> {
  return call("/api/messages", postJson({ text }), () => Promise.resolve(null));
}

export function leave(tab: string): void {
  navigator.sendBeacon("/api/leave", tab);
}
