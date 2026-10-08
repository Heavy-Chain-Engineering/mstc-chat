// The login page (component-specs.md, LoginPage). The markup is in
// index.html; this module adds its states and errors.

import type { ApiFailure, ApiResult, NameAnswer } from "./api";

const TEXT = {
  nameBlank: "Enter a display name.",
  nameTooLong: "Use 50 characters or fewer.",
  wrongPassword: "That class password is not right. Check it and try again.",
  unreachable:
    "Could not reach the chat server. Check your connection and press Join again.",
  tooLarge:
    "That request was too large. Shorten your display name and try again.",
  busy: "The chat is busy right now. Wait a few seconds and press Join again.",
  serverError:
    "The chat server had a problem. Wait a few seconds and press Join again.",
  sessionEnded: "Your session has ended. Join again to keep chatting.",
} as const;

export interface LoginDeps {
  login(name: string, password: string): Promise<ApiResult<NameAnswer>>;
  onJoined(name: string): void;
}

export interface LoginView {
  show(options?: { sessionEnded?: boolean }): void;
  hide(): void;
}

function byId<T extends HTMLElement>(doc: Document, id: string): T {
  const element = doc.getElementById(id);
  if (element === null) {
    throw new Error(`index.html has no element with id "${id}"`);
  }
  return element as T;
}

// Shows one alert in `container`, replacing any alert already there. The
// chat screen uses it too. The message is inserted as text.
export function showAlert(
  container: HTMLElement,
  variant: "error" | "info",
  message: string,
  onDismiss?: () => void,
): void {
  const template = byId<HTMLTemplateElement>(
    container.ownerDocument,
    `alert-${variant}`,
  );
  const alert = template.content.firstElementChild?.cloneNode(
    true,
  ) as HTMLElement;
  const text = alert.querySelector<HTMLElement>("[data-text]");
  const dismiss = alert.querySelector<HTMLButtonElement>("[data-dismiss]");
  if (text === null || dismiss === null) {
    throw new Error(
      `The alert-${variant} template lacks its text or dismiss element`,
    );
  }
  text.textContent = message;
  if (onDismiss === undefined) {
    dismiss.remove();
  } else {
    dismiss.hidden = false;
    dismiss.addEventListener("click", onDismiss);
  }
  container.replaceChildren(alert);
}

// Puts a button in its busy state: spinner, busy label, aria-busy.
export function setBusy(
  button: HTMLButtonElement,
  busy: boolean,
  busyLabel: string,
): void {
  const label = button.querySelector<HTMLElement>("[data-label]");
  const spinner = button.querySelector<HTMLElement>(".loading");
  if (label === null || spinner === null) {
    throw new Error(`Button #${button.id} lacks its label or spinner`);
  }
  label.dataset.idle ??= label.textContent ?? "";
  label.textContent = busy ? busyLabel : label.dataset.idle;
  spinner.hidden = !busy;
  if (busy) {
    button.setAttribute("aria-busy", "true");
  } else {
    button.removeAttribute("aria-busy");
  }
}

export function setupLogin(doc: Document, deps: LoginDeps): LoginView {
  const screen = byId(doc, "login-screen");
  const form = byId<HTMLFormElement>(doc, "login-form");
  const name = byId<HTMLInputElement>(doc, "login-name");
  const password = byId<HTMLInputElement>(doc, "login-password");
  const join = byId<HTMLButtonElement>(doc, "login-join");
  const alert = byId(doc, "login-alert");
  const nameError = byId(doc, "login-name-error");
  let submitting = false;

  const showNameError = (message: string): void => {
    nameError.textContent = message;
    nameError.hidden = false;
    name.setAttribute("aria-invalid", "true");
    name.setAttribute("aria-describedby", "login-name-hint login-name-error");
    name.focus();
  };

  const clearErrors = (): void => {
    alert.replaceChildren();
    nameError.hidden = true;
    nameError.textContent = "";
    name.removeAttribute("aria-invalid");
    name.setAttribute("aria-describedby", "login-name-hint");
    password.removeAttribute("aria-invalid");
    password.removeAttribute("aria-describedby");
  };

  const showWrongPassword = (): void => {
    showAlert(alert, "error", TEXT.wrongPassword);
    password.value = "";
    password.setAttribute("aria-invalid", "true");
    password.setAttribute("aria-describedby", "login-alert");
    password.focus();
  };

  const showFailure = (failure: ApiFailure): void => {
    if (failure.kind === "unreachable") {
      showAlert(alert, "error", TEXT.unreachable);
      join.focus();
    } else if (failure.code === "wrong_password") {
      showWrongPassword();
    } else if (failure.code === "name_blank") {
      showNameError(TEXT.nameBlank);
    } else if (failure.code === "name_too_long") {
      showNameError(TEXT.nameTooLong);
    } else if (failure.status === 413) {
      showAlert(alert, "error", TEXT.tooLarge);
    } else if (failure.status === 429) {
      showAlert(alert, "error", TEXT.busy);
    } else {
      showAlert(alert, "error", TEXT.serverError);
    }
  };

  const submit = async (): Promise<void> => {
    if (submitting) {
      return;
    }
    clearErrors();
    if (name.value.trim() === "") {
      showNameError(TEXT.nameBlank);
      return;
    }
    submitting = true;
    setBusy(join, true, "Joining…");
    const result = await deps.login(name.value, password.value);
    submitting = false;
    setBusy(join, false, "Joining…");
    if (result.kind === "ok") {
      password.value = "";
      deps.onJoined(result.data.name);
      return;
    }
    showFailure(result);
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void submit();
  });

  return {
    show(options = {}) {
      clearErrors();
      if (options.sessionEnded === true) {
        showAlert(alert, "info", TEXT.sessionEnded);
      }
      doc.title = "Join — MSTC Chat";
      screen.hidden = false;
      name.focus();
    },
    hide() {
      screen.hidden = true;
    },
  };
}
