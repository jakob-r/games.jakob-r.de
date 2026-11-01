# Draft: privacy section for games.jakob-r.de

Meant to be added to https://www.jakob-r.de/privacy/ (e.g. as a new section after "3. Hosting by GitHub Pages").
Placeholders are marked `[…]`. Before publishing: conclude the AVV with netcup (customer control panel) and fill in the log retention. Section 2 ("Principles") currently says the page is fully static; it should
be scoped to www.jakob-r.de, e.g. "This applies to www.jakob-r.de. For games.jakob-r.de see section 4."

---

## 4. Games at games.jakob-r.de

At games.jakob-r.de I operate a small collection of multiplayer browser games. There is no registration,
no cookies, no analytics or tracking and no advertising. All fonts, scripts and images are served from
games.jakob-r.de itself; no content is loaded from third-party servers.

### 4.1 Hosting and server logs

games.jakob-r.de runs on a server operated by me that I rent from netcup GmbH, Emmy-Noether-Straße 10,
76131 Karlsruhe, Germany. The server is located in Germany. I have concluded a data processing agreement
with netcup (Art. 28 GDPR).

When you visit the site, the web server processes technically necessary data, in particular your IP
address, date and time of the request, the requested URL and the browser identifier (user agent). This
data is written to server log files to ensure secure operation and to analyse errors, and is deleted
after [N] days.

The legal basis is Art. 6(1)(f) GDPR. My legitimate interest is the secure and reliable operation of the
website.

### 4.2 Playing a game

To play, you choose a display name (a nickname is enough, it does not need to be your real name). When
you join a game, the following data is processed on the server:

- a randomly generated player ID (not linked to your identity),
- your display name and your chosen colour,
- the game state, your moves, scores and ready status within the game room,
- per-game statistics (games played, games won, scores) linked to the player ID.

Your display name, colour, moves and scores are visible to everyone who has the link to the same game room.
The data is processed in order to provide the game you requested; the legal basis is Art. 6(1)(b) GDPR.

Game rooms, including the players' names and moves, are deleted automatically: rooms without any moves
after 2 days of inactivity, all other rooms after 1 year of inactivity. The host of a room can delete it
at any time. Per-game statistics are deleted automatically after 1 year without a new game.

### 4.3 Storage in your browser

The website stores your player ID, display name, colour and notification settings in your browser's local
storage (`localStorage`) so that you are recognised when you return to a game. This data is not sent
anywhere until you join a game, and it is not used for tracking. You can delete it at any time via your
browser settings. Storing it is strictly necessary to provide the game you requested (§ 25(2) no. 2 TDDDG).

### 4.4 Push notifications (optional)

If you explicitly enable it, the website can notify you when it is your turn. Your browser then creates a
push subscription, which is stored on my server together with the game room and your player ID. To deliver
notifications, my server sends them to the push service of your browser's vendor, e.g. Google (Chrome),
Mozilla (Firefox), Apple (Safari) or Microsoft (Edge). The content of the notifications is end-to-end
encrypted; the push service only sees technical data such as the subscription address and the time of
delivery. These providers may process data in the USA; Google, Apple and Microsoft are certified under the
EU-U.S. Data Privacy Framework.

The legal basis is your consent (Art. 6(1)(a) GDPR). You can withdraw it at any time by turning off the
notification bell in the game or by revoking the permission in your browser. The subscription is deleted
when you turn notifications off, when the push service reports it as expired, or when the game room is
deleted.
