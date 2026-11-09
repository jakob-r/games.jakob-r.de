<script lang="ts">
	import SeoHead from '$lib/core/components/SeoHead.svelte';
</script>

<SeoHead
	title="Privacy policy"
	description="How games.jakob-r.de handles your data: no tracking, nicknames, optional accounts, automatic deletion."
	path="/privacy"
/>

<main class="mx-auto w-full max-w-2xl flex-1 px-4 py-6 sm:px-6 sm:py-10">
	<a
		href="/"
		class="text-sm font-medium text-[#6e6a63] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:text-[#1a1917] hover:decoration-[#1a1917]"
	>← All games</a>

	<article class="policy mt-4">
		<h1 class="font-hand text-3xl tracking-tight sm:text-4xl">Privacy policy</h1>
		<p class="text-sm text-[#6e6a63]">Last updated: November 2026</p>

		<h2>1. Controller</h2>
		<p>
			The controller responsible for data processing on games.jakob-r.de is Jakob Richter. Postal address and
			email are listed in the <a href="https://www.jakob-r.de/legal-notice/">legal notice</a>.
		</p>

		<h2>2. Principles</h2>
		<p>
			games.jakob-r.de is a small, non-commercial collection of multiplayer browser games. You can play without
			registering; an account is optional. The only cookie is a session cookie that is set if you sign in
			(see section 5). There is no analytics or tracking and no advertising. All fonts, scripts and images are
			served from games.jakob-r.de itself; no content is loaded from third-party servers.
		</p>

		<h2>3. Hosting and server logs</h2>
		<p>
			The site runs on a server operated by me that I rent from netcup GmbH, Emmy-Noether-Straße 10, 76131
			Karlsruhe, Germany. The server is located in Germany. I have concluded a data processing agreement with
			netcup (Art. 28 GDPR).
		</p>
		<p>
			When you visit the site, your browser transmits technically necessary data, in particular your IP
			address, date and time of the request, the requested URL and the browser identifier (user agent). Your IP
			address is only used to deliver the requested content and is not stored. To ensure secure operation and
			to analyse errors, the web server keeps a log containing the date and time of the request, the requested
			URL (which may include a game room ID or the random player ID described below), the HTTP status, the
			amount of data transferred and the browser identifier. The log contains no IP addresses. Its size is
			limited; older entries are overwritten automatically.
		</p>
		<p>
			The legal basis is Art. 6(1)(f) GDPR. My legitimate interest is the secure and reliable operation of the
			website.
		</p>

		<h2>4. Playing a game</h2>
		<p>
			To play, you choose a display name. A nickname is enough; it does not need to be your real name. When
			you play, the following data is processed on the server:
		</p>
		<ul>
			<li>a randomly generated player ID, which is not linked to your identity,</li>
			<li>your display name and your chosen colour,</li>
			<li>the game state, your moves, scores and ready status within the game room,</li>
			<li>per-game statistics (games played, games won, scores) linked to the player ID.</li>
		</ul>
		<p>
			Your display name, colour, moves and scores are visible to everyone who has the link to the same game
			room. The data is processed to provide the game you requested; the legal basis is Art. 6(1)(b) GDPR.
		</p>
		<p>
			In Emoji Charades the host can add an AI player. If they do, my server sends the emoji hints of the
			current round, the word category (if shown) and the guesses typed so far to OpenRouter (OpenRouter,
			Inc., USA), which forwards them to an AI model provider. Names, player IDs and other personal data are
			not sent. Requests are only routed to providers that do not store or train on them. Nothing is sent
			unless the AI player is turned on.
		</p>
		<p>
			Game rooms, including the players' names and moves, are deleted automatically: rooms without any moves
			after 2 days of inactivity, all other rooms after 1 year of inactivity. The host of a room can delete it
			at any time. Per-game statistics are deleted automatically after 1 year without a new game.
		</p>

		<h2>5. Optional user account</h2>
		<p>
			You can create an account to keep your statistics and recent rooms across devices. You can sign up with
			an email address and password or with Google. The following data is stored on my server:
		</p>
		<ul>
			<li>your email address and an optional display name,</li>
			<li>for email sign-up, a salted hash of your password (never the password itself),</li>
			<li>for Google sign-in, Google's account identifier; I receive your email address and name from Google,</li>
			<li>the player ID linked to your account, and hashes of your login sessions and one-time email links.</li>
		</ul>
		<p>
			If you are signed in, a session cookie (<code>games_session</code>) keeps you logged in for up to 30
			days. It is strictly necessary for the login you requested (§ 25(2) no. 2 TDDDG). While a Google
			sign-in is in progress, another short-lived cookie (up to 10 minutes) protects the process against
			forgery. Confirmation and password-reset emails are sent through the mail server of my email provider Linevast, which also
			registered the domain. Linevast processes the recipient address and the email content for delivery.
		</p>
		<p>
			If you choose Google sign-in, your browser is redirected to Google, which processes data under its own
			privacy policy and may do so in the USA (Google is certified under the EU-U.S. Data Privacy Framework).
			Nothing is sent to Google unless you click that button.
		</p>
		<p>
			Signed-in players can add other signed-in players from a game they share as friends. I store who is
			friends with whom and open friend requests (a request expires after 30 days). Friends see your name and
			colour; they never see whether you are online, when you were last active, your email address or your
			other friends. Declining a request or removing a friend is not shown to the other person.
		</p>
		<p>
			The legal basis is Art. 6(1)(b) GDPR. You can delete your account at any time on the account page; this
			erases your account data, statistics, friendships and the rooms you host. Accounts whose email address was never
			confirmed and that have no active session are deleted automatically after 30 days.
		</p>

		<h2>6. Storage in your browser</h2>
		<p>
			The site stores your player ID, display name, colour and notification settings in your browser's local
			storage so that you are recognised when you come back. The player ID is sent to the server to show your
			recent games and statistics; the data is not used for tracking. You can delete it at any time via your
			browser settings. Storing it is strictly necessary to provide the service you requested (§ 25(2) no. 2
			TDDDG).
		</p>

		<h2>7. Push notifications (optional)</h2>
		<p>
			If you explicitly enable it, the site can notify you when it is your turn. Your browser then creates a
			push subscription for this device, which is stored on my server together with your player ID and used
			for all your games. To
			deliver notifications, my server sends them to the push service of your browser's vendor, e.g. Google
			(Chrome), Mozilla (Firefox), Apple (Safari) or Microsoft (Edge). The content of the notifications is
			end-to-end encrypted; the push service only sees technical data such as the subscription address and the
			time of delivery. These providers may process data in the USA; Google, Apple and Microsoft are certified
			under the EU-U.S. Data Privacy Framework.
		</p>
		<p>
			The legal basis is your consent (Art. 6(1)(a) GDPR). You can withdraw it at any time by turning off the
			notification bell in a game (or the switch on your account page) or by revoking the permission in your
			browser. The subscription is deleted when you turn notifications off, when the push service reports it as
			expired, when you delete your account, or after one year without a visit from that device.
		</p>

		<h2>8. External links</h2>
		<p>
			The site links to other websites, e.g. GitHub and jakob-r.de. No data is transferred to them until you
			click a link. After that, the privacy policy of the respective provider applies.
		</p>

		<h2>9. Your rights</h2>
		<p>You have the right to</p>
		<ul>
			<li>access the data stored about you (Art. 15 GDPR),</li>
			<li>rectification (Art. 16 GDPR),</li>
			<li>erasure (Art. 17 GDPR),</li>
			<li>restriction of processing (Art. 18 GDPR),</li>
			<li>data portability (Art. 20 GDPR),</li>
			<li>object to processing based on Art. 6(1)(f) GDPR (Art. 21 GDPR),</li>
			<li>withdraw your consent at any time with effect for the future (Art. 7(3) GDPR).</li>
		</ul>
		<p>
			To exercise these rights, contact me by email at the address in the
			<a href="https://www.jakob-r.de/legal-notice/">legal notice</a>. Please include your account email or, if you
			play without an account, your player ID so I can find your data; you can see the latter in your
			browser's local storage for this site.
		</p>
		<p>
			You also have the right to lodge a complaint with a data protection supervisory authority, for example
			the Berlin Commissioner for Data Protection and Freedom of Information (Berliner Beauftragte für
			Datenschutz und Informationsfreiheit), Alt-Moabit 59–61, 10555 Berlin, Germany.
		</p>

		<h2>10. Automated decision-making</h2>
		<p>No automated decision-making within the meaning of Art. 22 GDPR takes place.</p>
	</article>
</main>

<style>
	.policy :global(h2) {
		font-family: var(--font-hand);
		font-size: 1.25rem;
		margin-top: 2rem;
		margin-bottom: 0.5rem;
	}
	.policy :global(p),
	.policy :global(ul) {
		margin-top: 0.75rem;
		line-height: 1.65;
	}
	.policy :global(ul) {
		list-style: disc;
		padding-left: 1.25rem;
	}
	.policy :global(a) {
		font-weight: 500;
		text-decoration: underline;
		text-decoration-color: rgb(26 25 23 / 0.3);
		text-underline-offset: 4px;
	}
	.policy :global(a:hover) {
		text-decoration-color: #1a1917;
	}
</style>
