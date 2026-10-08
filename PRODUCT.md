# MSTC Chat

A live chat room for one MSTC lecture at Texas McCombs, where students send the lecturer feedback, questions and links.

This file describes the product, its users and its voice, so that every screen and message reads
the same way. `DESIGN.md` beside it describes the visual system. `DOMAIN.md` holds the domain
rules, which win over this file.

The design agent wrote this file on 2026-10-08 from the person's design direction in the
feature's `request.md`, its `spec.md` and the brand research in its `research/design-web.md`.
impeccable was not installed, so no impeccable capture ran. The person reviews it with the design.

## The product

MSTC Chat is a small, single-room chat for one live lecture on spec-driven development in the
Master of Science in Technology Commercialization (MSTC) program at the McCombs School of
Business, The University of Texas at Austin. Students open a link, type a display name and the
class password, and join one shared room. Every message reaches everyone within two seconds.
Messages support Markdown, so students can paste code and links.

It is also the lecture's worked example: the lecturer shows the spec and redeploys the app in
class. So the screens must look finished and on brand, and stay simple enough to explain.

It is not a general chat product: one room, one class, no accounts, no history after a restart,
no uploads, no reactions and no threads.

## Users

- **Students**: master's students, many joining over Zoom on a laptop, some on a phone. They
  send short feedback, questions and links, and paste code. Some will try to break the page
  with HTML or script; it must show their text literally.
- **The lecturer**: reads the room while teaching, often projected on a shared screen. Needs
  names and messages readable at a glance, and a room that keeps working through a live
  redeploy.

## Primary surfaces

1. **Login page**: display name, class password, "Join".
2. **Chat screen**: the messages, who is online, and the message box.

## Brand

The look follows The University of Texas at Austin's brand and the McCombs School of Business's
guidance: burnt orange as the one strong color, white and Limestone surfaces, Charcoal text,
Libre Franklin and Charis SIL type, and plenty of white space. The aim is "elegant and on brand":
calm, professional, and recognisably UT, without imitating an official logo.

- Naming: on first mention, "Master of Science in Technology Commercialization", "McCombs School
  of Business" and "The University of Texas at Austin"; afterwards "MSTC", "Texas McCombs" and
  "UT" ([UT-E], [MC-N]).
- Logo: none for now. The login page shows the text "MSTC Chat" in Charis SIL. Official logos
  need permission from UT's Office of Brand, Trademarks and Licensing before they appear on this
  site ([MC-CB]); `DESIGN.md` reserves a slot for one.

## Voice

Courteous, plain and brief, in the "consistent and elevated" voice McCombs asks for ([MC-H]).
Every message says what happened and what to do next, in a full sentence.

- Write: "That class password is not right. Check it and try again."
- Not: "Invalid credentials!" or "Oops! Something went wrong."
- Write: "Reconnecting to the room… Messages sent meanwhile will appear when the connection
  returns."
- Not: "Connection lost!!"

No exclamation marks in errors, no jokes, no emoji, no blame.

## Accessibility

WCAG 2.2 AA for both screens: text contrast at least 4.5:1, controls and focus rings at least
3:1, full keyboard use, visible focus, 44 px controls, status messages announced to screen
readers, and no motion when the system asks for reduced motion. The person asked for WCAG AA;
the 2.2 version is the design skill's default and the person may change it.

## What success looks like

Students use the room instead of Zoom chat: at least 20 messages during the lecture
(`value-hypothesis.yaml`), and the room stays up through the in-class redeploy.

## Sources

| Key | URL |
|---|---|
| UT-E | https://umac.utexas.edu/resources/editorial-style-guide/ |
| MC-N | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/45580961 |
| MC-H | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/207230133 |
| MC-CB | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/214958781 |
| MSTC | https://www.mccombs.utexas.edu/graduate/specialized-masters/ms-technology-commercialization/ |
