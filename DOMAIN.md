# MSTC Chat — Domain Briefing

---

## Domain

MSTC Chat is a teaching demo. It is a small, throwaway web chat room for one
live university lecture on spec-driven development, given to a class of
master's students. It is not a business and has no customers.

---

## Core Problem

During a live lecture, often held over Zoom, students have no good shared
channel for sending the lecturer quick feedback, questions and links. The
lecturer does not want to use Zoom chat. Without a channel, students' comments
and links get lost or never get sent. The app has a second purpose: it is the
worked example in the lecture itself. The lecturer shows a spec turning into a
running app deployed on real, lightweight cloud infrastructure.

---

## How MSTC Chat Makes Money

It does not make money. It has no revenue and no paying users. Its value is
educational. The demo must work smoothly in front of the class, and its code
and spec must be simple enough to explain in a lecture. Hosting must cost close
to nothing.

---

## What MSTC Chat Does

A student opens the URL the lecturer shares and sees a login page. The student
enters a display name, an email address and a pre-shared class password. The
lecturer sets that password through configuration, not in code. When the
password is right, the server gives the browser a signed session cookie and
shows the chat screen.

On the chat screen, every signed-in participant can type a message and send
it. The server broadcasts each message at once to every connected participant.
URLs in messages become clickable links. The page uses daisyUI for its look.

The server holds all state in memory: the participants who are connected and
the recent messages. There is no database. When the server restarts, the chat
history is gone, which is acceptable for a one-lecture room. The app runs as a
single container on Google Cloud Run, which supplies the public HTTPS URL.

Actors:
- **Lecturer**: sets the class password, deploys the app, shares the URL and
  reads the chat during the lecture.
- **Student**: signs in and sends messages and links.
- **Google Cloud Run**: hosts the one server instance and terminates HTTPS.

---

## Operational & Regulatory Constraints

- **No formal compliance regime applies.** The app has no SOC 2, PCI or HIPAA
  scope and no uptime SLA.
- **Students' names and email addresses are personal data.** Privacy rules for
  student data (for example GDPR or FERPA, depending on the institution) favour
  collecting little and keeping it briefly. The app therefore keeps names and
  emails only in memory, never writes them to disk or a database, and never
  logs them or message text.
- **The class password is a shared secret.** It lives in an environment
  variable or Cloud Run secret and never in the repository.
- **The app must run during one live lecture.** Availability matters only for
  that window. Cloud Run must keep one instance warm, so no student waits for
  a cold start.
- **Cost must stay near zero.** The deployment uses one small Cloud Run
  instance and no paid add-ons.

---

## Product Core

- **Participant**: a person signed in with a display name and email. It is not
  an account. It exists only while the server runs.
- **Class password**: the one pre-shared password every participant enters. It
  is not per-user, and it is not HTTP Basic auth's browser popup.
- **Session**: the signed cookie that proves a browser passed the login. It
  carries the participant's name and email.
- **Message**: one chat entry with its author's display name, its text and the
  time the server received it. Its text is untrusted input.
- **Chat room**: the single shared stream of messages. There is exactly one
  room; the app has no channels and no direct messages.
- **Connection**: one browser's open live stream (Server-Sent Events) that
  receives broadcast messages.

| Term | Means | Does not mean |
|---|---|---|
| Login | The name, email and class-password form | A user account or OAuth sign-in |
| Broadcast | The server sending a message to every open connection | Email or push notification |

---

## What MSTC Chat Is Not

- It is not a general chat product. It has one room, one class and one
  password.
- It keeps no permanent history. It has no database, no export and no archive.
- It has no user accounts, no registration, no password reset and no roles,
  other than an optional lecturer view if a spec adds one.
- It does not send email or verify email addresses.
- It does not support file uploads, images, reactions or threads.
- It is not built to scale past one server instance or one classroom.

---

## Risk Posture

Unrecoverable failures (they happen live in front of the class):
1. **Script injection.** A student posts HTML or JavaScript that runs in every
   other participant's browser. Master's students will try this.
2. **The class password or session secret leaks into the public repository.**
3. **The app is down or broken during the lecture**, so the demo fails on
   stage.

Merely expensive failures:
4. **Split chat.** Cloud Run scales to a second instance, and participants on
   different instances stop seeing each other's messages.
5. **Lost history.** The server restarts and the chat history disappears.
6. **Unexpected cloud cost** from a misconfigured service or abuse.
7. **Spam or flooding** by a participant who knows the password.

---

## Design Implications

1. Because message text is untrusted and students will probe it, the system
   must escape all user text before it renders, and turn only `http` and
   `https` URLs into links.
2. Because all state lives in one process's memory, the deployment must pin
   Cloud Run to exactly one instance.
3. Because the demo runs live, the deployment must keep one instance warm, and
   browsers must reconnect to the live stream on their own after a dropped
   connection.
4. Because the class password and cookie-signing key are secrets, the system
   must read them from the environment, and the repository must never hold
   them.
5. Because names and emails are personal data, the system must keep them only
   in memory and must never log them or message text.
6. Because the app is a teaching example, the code must stay small and
   readable, with no database and no infrastructure beyond one container.
7. Because one participant can flood the room, the system must cap message
   length and keep only a bounded number of recent messages in memory.

---

*This document is the source of truth for domain understanding. Any implementation
decision that contradicts this document must be flagged and resolved before proceeding.*
