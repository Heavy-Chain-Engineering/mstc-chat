// Start-up: ask whether this browser is signed in, show the login or the
// chat screen, and connect the chat screen to the live stream.

import "./styles.css";

import { leave, login, sendMessage, session } from "./api";
import { setupChat } from "./chat";
import { setupLogin } from "./login";
import { RoomStream, readReloadMemory, waitForSession } from "./stream";

// A file dropped anywhere on the page must not open in the tab (AC-12).
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

const saved = readReloadMemory(sessionStorage);
let stream: RoomStream | null = null;

const chat = setupChat(document, {
  sendMessage,
  onSignedOut: () => signOut(),
  onDismissRestarted: () => stream?.dismissRestarted(),
});

const loginView = setupLogin(document, {
  login,
  onJoined: (name) => enterChat(name, ""),
});

function signOut(): void {
  stream?.stop();
  stream = null;
  chat.hide();
  loginView.show({ sessionEnded: true });
}

function enterChat(name: string, draft: string): void {
  loginView.hide();
  chat.show(name, draft);
  const memory = stream?.room ?? saved.memory;
  stream?.stop();
  stream = new RoomStream({
    tab: crypto.randomUUID(),
    memory: {
      left: memory.left,
      reloadedFor: memory.reloadedFor,
      restarted: memory.restarted,
    },
    handlers: {
      onRoom: (state) => chat.render(state),
      onReconnecting: (visible) => chat.setReconnecting(visible),
      onSignedOut: signOut,
    },
    deps: {
      openSource: (url) => new EventSource(url),
      checkSession: session,
      sendLeave: leave,
      storage: sessionStorage,
      reload: () => location.reload(),
      getDraft: () => chat.draft(),
      now: () => Date.now(),
    },
  });
  chat.render(stream.room);
  stream.open();
}

window.addEventListener("pagehide", (event) =>
  stream?.handlePageHide(event.persisted),
);
window.addEventListener("pageshow", (event) =>
  stream?.handlePageShow(event.persisted),
);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Only a 401 sends the page to login. While the server cannot answer, the
// chat screen shows with the restored draft and the reconnecting notice.
async function start(): Promise<void> {
  let retried = false;
  const signedIn = await waitForSession({
    checkSession: session,
    sleep,
    onRetrying: () => {
      retried = true;
      chat.show("", saved.draft);
      chat.setReconnecting(true);
    },
  });
  if (signedIn === null) {
    chat.hide();
    loginView.show({ sessionEnded: saved.draft !== "" });
    return;
  }
  chat.setReconnecting(false);
  enterChat(signedIn.name, retried ? "" : saved.draft);
}

void start();
