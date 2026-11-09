# IDEA

In this repo I want to host several small multiplayer games.
Ideally they share some components of FE and BE but it should also be possible to extract a game and run it standalone.
Users can set their name and it will be remembered in the browser. Playing works without an account; an optional account keeps name, colour, stats and recent rooms across devices and unlocks friends.
The style of the games should be minimalistic, scribbly with nuanced animations.
We don't want to annoy the user with ads or tracking.
Only use color where it is necessary and helpful.

Source is public under PolyForm Noncommercial: forking and personal use are fine; commercial reuse (ads, paywalls, selling a rebranded copy) is not. The live site is hosted in Europe (Germany).

## Landing page

When the user enters games.jakob-r.de they can 
- see and change their name and their primary color (signed-in users do this on `/account`)
- sign in or open their account, and (signed in) open the friends page, which shows the number of open invites
- see a list of games (each with a small SVG logo) linking to a per-game hub
- see the most recently played games
- if possible resume the game from where they left off
- see some personal stats

## Per-game hub (`/{slug}`)

Each game is reachable at its own URL (e.g. `/sudoku`) for SEO and deep links. The hub shows:
- a short description and logo
- create a new room
- the player’s open sessions for that game

## Common parts

- Color logic: A user sets their primary color and sees other players with their primary color. If the others player color is too similar it will be adjusted. For this we have a function opponent_color(my_color, their_color) which returns a color that is not too similar to my_color or their_color.
- Player modal: clicking another player's name opens a modal. The room creator can remove the player from the room there; signed-in players can add a co-player with an account as a friend.
- Starting player: random in a room's first game, afterwards the loser of the previous game.
- Lobby: players can mark themselves ready, but the host can start at any time. The host can end a running game early, and after a game "New Round" brings everyone back to the lobby.
- Turn notifications: one push switch per device (bell in every game or on `/account`), covering all games.
- Idle mid-game joiners: If a new player enters a running game, does nothing, and closes the browser window, they automatically leave the room.

## Friends (accounts only)

Privacy first: friends never see whether you are online or when you were last active.

- Adding: only from a shared room. Tap a co-player's name → "Add friend" (shown only when both players have an account). No search, no friend link for now.
- Friendships are mutual: a request has to be accepted. Declining is silent (the sender just sees "pending"). Either side can remove the friendship at any time, also silently.
- Names don't have to be unique. If friends share a name (with each other or with you), you see them numbered (e.g. "Anna (2)"), numbered by when you added them.
- Friends see: your name, your colour, the lobbies you host, and the invites you send them. Not: online status, last seen, your friend list, whether you read an invite.
- Friends' lobbies page: lists rooms that friends created and that are still in the lobby phase (no running games). No timestamps, so it doesn't work as an activity indicator. Lobbies without moves disappear after 2 days anyway.
- Invites: the invite button in a room's header (lobby or running game) lets you pick friends to invite. Invites show up in an inbox on the friends page and trigger a push (and optionally a mail). An invite expires with its room. One invite per room per friend, daily cap per sender.
- Settings (`/account`):
  - Friends: incoming and outgoing requests, friend list with remove.
  - Notifications: push on/off (one global switch per device, not per room), email when it's my turn, email when someone invites me (both opt-in, verified addresses only).
- Push notifications are global: one subscription per player and device. Turn pushes go out for any room where it's your turn; invites use the same subscription. An account's devices can only be registered while signed in.
- Turn mails: only if it's still your turn ~15 min later and you are not connected to the room; at most one per room until you have moved. Invite mails: at most one per inviter per day. Every mail has a one-click unsubscribe link.
- Deleting an account removes its friendships, requests and invites. The privacy page describes the friends data.

## Games

### Multiplayer Sudoku

- The starting user creates a new game which will generate a unique game id url.
- The starting user can share the game id url with others to invite them to join.
- The starting user can set the difficulty of the game (easy, medium, hard, expert).
- All players join the game in a shared room with a lobby where they can set themselves as ready.
- All players see the same board and can edit it. Changes are visible to all players.
- All players can add notes to the board (1-9 in the corners). The notes are visible to all players.
- Edits are visible in players colors.

#### Scoring

- A wrong digit is rejected (not placed); the user gets -10 points and their multiplier resets.
- For a filling out the last cell in a row, column or block the user gets 2 points * multiplier
- For filling out more difficult cells the user gets 5 points * multiplier
- For doing correct entries within 10 seconds user gets multiplier = 1.1 * multiplier
- Multiplier is reset to 1 after 10 seconds.
- Scoring can be turned off by the starting user.

### Käsekästchen

- The starting user creates a new game which will generate a unique game id url that they can share with others to invite them to join.
- The starting player can decide how big the board should be (3 to 12 per side, default 6×6).
- The starting player can leave the board rectangular according to the measurements they have set or draw a custom shape within the measurements.
- The game canvas is a grid of squares.
- Round based game.
- Each player can draw a line on the canvas on the grid.
- Lines are shown in the players color.
- As soon as a player closes a square they get a point and are allowed to draw another line.
- If the move does not close a square, it's the next players turn.
- The game ends when all squares are closed.
- The player with the most points wins.

### Co-op Minesweeper

- The starting user creates a new game which will generate a unique game id url that they can share with others to invite them to join.
- The starting user can set the difficulty (`easy` 9×9/10, `medium` 16×16/40, `hard` 30×16/99) and whether scoring is enabled.
- All players join a shared lobby, then dig and flag the same board simultaneously (no turns).
- The first dig is always safe (mines are placed afterward, avoiding that cell and its neighbors).
- Zero-adjacent cells flood-fill when revealed.
- Hitting a mine costs points, reveals the mine with a boom flash, and the game continues.
- Flags are shown in the planting player's color. Players can only remove their own flags; opponent flags can be challenged.
- The game finishes when all safe cells are revealed **or** every mine is secured (correctly flagged or already revealed).

#### Scoring

- Reveal a safe cell: `+1` per newly revealed cell (including flood-fill).
- Hit a mine: `−10`.
- Place a flag: `+2`.
- Remove your own flag: `−3`.
- Challenge an opponent's flag:
  - Flag was correct (mine): challenger `−5`, owner `+5`; cell becomes a confirmed revealed mine.
  - Flag was wrong (safe): challenger `+5`, owner `−5`; flag removed and cell revealed (flood-fill if zero).
- Scoring can be turned off by the starting user.

### Silbenstreit

- Configurable 4x4 to 8x8 grid of letters.
- The grid is filled with short syllables (2–4 letters) drawn roughly by language frequency, with a balanced share of vowels, no letter more than 4 times, and at least one rare letter.
- Up to 4 players (2–4 recommended), round based game.
- At the start user can choose from english, german, french or spanish.
- In a turn a player forms a valid word (at least 2 tiles) from the language dictionary, or passes.
- Every letter in the word becomes "owned" by the player.
- "Owned" letters score points and become colored in the player's color.
- Scores of letters are higher the more rare the letter is: Integer between 1 and 10.
- A owned letter that is completely surrounded by letters of the same color is "protected".
- In a turn a player can select "owned" and unowned letters but not "protected" letters.
- The game ends when there are no more unowned letters, or when everyone has passed twice in a row.
- Scoring can be turned off by the starting user.
- Words must follow classic Scrabble-style rules.
- A played word cannot be reused, nor can any word contained in a played word (after "RUNNER", "RUN" is blocked for everyone).
- Players can see the list of all played words.

### Emoji Charades

A multiplayer game that can be played in person but also remotely.
In each round a player is given a word or phrase (Object, Food, Animal, Brand, Famous Person, Movie Title, TV Show or Quote). 
This main player ("explainer") has to select emojis to describe the word.
The other players ("guessers") see only the emojis and have to guess the word.
If the word is guessed correctly the guesser gets a point.
If the round is timed also the explainer gets a point.

1. The host can select if the game is played in person or remotely, if the game is timed or not, the word language (German or English), whether guessers see the word's category, and whether scores are kept.
2. The explainer order is shuffled at the start of every game.
3. The explainer is given a set of three words which they can choose from.
4. The explainer can create multiple "sentences" just out of emojis (up to 5 with 16 emojis each). The first sentence is the main concept.
5. The guessers see the selected emojis and have to guess the word.
  * In person: The guessers just shout the word out loud and the explainer selects the player who guessed the word correctly.
  * Remotely: The guessers can write the word and the game detects if the word is correct (allowing for typos and slight variations).
6. The guesser who guessed the word correctly gets a point. If the round is timed also the explainer gets a point.
7. The next round starts with a new explainer and a new word.

- Explainers are chosen circularly.
- The explainer can select which sentence they are currently editing.
- The explainer can add, remove, rearrange emojis from the sentence.
- Emojis are sorted by category
  * Categories: Countries, Colors, Shapes, Foods, Animals, People, Things, Concepts, Actions
  * Concepts and actions are antonym pairs
  * Not all available emojis have to be used.
  * For the dev it should be easy to fine tune the selection.
- Timer is 2 minutes but can be adjusted by the host (30 s to 10 min).
- The explainer can give up. If the explainer leaves, the round ends.
- Remote guesses that are almost right get a "Close!" hint.
- Optional AI guesser ("AI 🤖") when an LLM is configured; it only sees what guessers see and types guesses.
- People can join the game at any time.
- The host can end the game at any time and the final scores are shown.

### Spellsprawl

A multiplayer word spelling game with an infinite grid and endless allowed words and letters.
Inspired by scrabble but you only get points for reusing letters.

- The game is played in rounds.
- The grid where the letters are placed is infinite.
- 1 to 8 players.
- Main player can select the language (German, English, French, Spanish) and the end condition, each with an adjustable target:
  * Words played (default 50)
  * First player to reach a score (default 500 points)
  * The grid grows beyond a size (default 500 square units, counting max height * max width)
- A player can pass; the game also ends when everyone has passed twice in a row.
- Every word formed (including cross-words) must be in the dictionary, and a main word can't be played twice.
- Dictionary uses a shared component with silbenstreit.
- Letter scoring is shared with silbenstreit.
- Scoring:
  * A new word itself does not score points.
  * Only the letters that are already on the grid score points (also in cross-words).

UX:
- Letters are entered using system keyboard.
- You can select the first cell and select if your typing will go right or down.
- After putting two letters your direction is locked to horizontal or vertical.
- Diagonal words are not allowed.
- It should be easy to edit your current word.
- Option to cancel the current word or submit it.

### North South Sort

A turn based multiplayer game where players have to place locations on a north south axis.

Locations are generated by a scraping script. 
We search for in three categories:
- Cities (1 point)
- Landmarks and famous sights (2 points)
- Historical events (3 points)

For each location we store the following data:
- Name in English/German
- Latitude and longitude of center
- Min Latitude and Max Latitude (can be approximated)
- Min Longitude and Max Longitude (can be approximated)
- Category
- Short description
- Link to a Wikipedia article
- Country
- Continent

Game settings:
- Language of the names (German/English)
- Continent to play on, or the whole world
- Difficulty (easy/medium/hard: from only well-known to all locations)
- Multiselect: Categories
- Timed: Yes/No for multiplier (×2 within 10 s, ×1.5 within 20 s)
- Game ends after: 
  * Rounds (default 10)
  * Points (default 100)
  * a round where each player has skipped or misplaced a location
  * or when the locations run out

Game play:
1. Main player defines the game settings
2. The game starts with a random city
3. Every player has one location per selected category to choose from (hands are visible to everyone).
4. The active player can decide to place the chosen location north/south of the existing locations or in between them, or skip and swap their whole hand.
5. A placement is correct if the location's latitude range overlaps the gap between its neighbours. Points = base × category value (× speed bonus when timed); the base is higher the narrower the gap (10° / gap, between 1 and 20).
6. If the location is not correctly placed the player loses the location's value and the card is discarded (revealed at the end).
7. The played location is immediately replaced by a new random location of the same category.
8. The game ends when the game end condition is met.

### Fragmentory

A turn based multiplayer game where players try to build big territories by placing square cards with separation lines on the board.
The goal of each player is to build the biggest territories in their own color.


The cards:
- 6 straight lines: two areas
- 12 curves: two areas
- 6 crosses: four areas
- 10 T sections: three areas
- 4 line ending pieces: one area
- 4 blank cards without any line: one area (42 cards in total)
- each card can be rotated
- in an info modal every player can see how many cards of each type are left in the deck-

The board:
- infinite grid
- the used area is (min needed hight for all cards) x (min needed width for all cards)

1. The game starts with an extra T card (the deck keeps all its cards)
2. each player gets a random card from the deck, cards are visible to all players.
3. the active player can rotate his card and decide which of the areas on the card he wants to occupy with their color.
4. the player places the card on the board but it has to match on all sides:
  * empty side to empty side
  * side with a line to side with a line
  * the area you occupy cannot touch an area of another player
  * unoccupied areas can go next to anything (no matter which color) and merge with it
5. if the new card increases the used area, the player gets minus points equal to units of (new used area - old used area)
6. if the new card merges occupied areas of different colors, the color with more cards in the merged area takes it over. If there is a tie the area is marked gray; a gray area is resolved as soon as one color leads by two cards.
7. When the deck is empty, the remaining hand cards are still played; the game ends when no cards are left.

Scoring:
- Increasing the used area decreases the score by the number of units of (new used area - old used area)
- For each card that has an occupied area the player gets one point, except for areas with just one card - this should be indicated by a lighter color.
- Occupied areas that are fully enclosed by lines get double points, indicated by a slightly darker color.

Clarifications:
- 1 to 8 players, no game settings.
- Claiming an area is optional. A card that fits nowhere is discarded.
- A player may only occupy a new area if the move does not increase one of their current areas (no area of the placed card joins an area holding their colour). So the area is chosen after placing the card; the areas that may be occupied are marked with empty circles.
