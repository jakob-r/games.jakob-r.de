# IDEA

Ih this repo I want to host several small multiplayer games.
Ideally they share some components of FE and BE but it should also be possible to extract a game and run it standalone.
Users can set their name and it will be remembered in the browser.
The style of the games should be minimalistic, scribbly with nuanced animations.
We don't want to annoy the user with ads or tracking.
Only use color where it is necessary and helpful.

Source is public under PolyForm Noncommercial: forking and personal use are fine; commercial reuse (ads, paywalls, selling a rebranded copy) is not. The live site is hosted in Europe (Germany).

## Not now
- For now we don't need authentication, but we want to be able to add it later.
- For now we don't add a chat function but might be added later.


## Landing page

When the user enters games.jakob-r.de they can 
- see and change their name and their primary color
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
- Player removal: As a room creator, clicking on another player's name opens a confirmation modal to remove them from the room.
- Idle mid-game joiners: If a new player enters a running game, does nothing, and closes the browser window, they automatically leave the room.

## Games

### Multiplayer Sudoku

- The starting user creates a new game which will generate a unique game id url.
- The starting user can share the game id url with others to invite them to join.
- The starting user can set the difficulty of the game.
- All players join the game in a shared room with a lobby where they can set themselves as ready.
- All players see the same board and can edit it. Changes are visible to all players.
- All players can add notes to the board (1-9 in the corners). The notes are visible to all players.
- Edits are visible in players colors.

#### Scoring

- For a mistake the user gets -10 points.
- For a filling out the last cell in a row, column or block the user gets 2 points * multiplier
- For filling out more difficult cells the user gets 5 points * multiplier
- For doing correct entries within 10 seconds user gets multiplier = 1.1 * multiplier
- Multiplier is reset to 1 after 10 seconds.
- Scoring can be turned off by the starting user.

### Käsekästchen

- The starting user creates a new game which will generate a unique game id url that they can share with others to invite them to join.
- The starting player can decide how big the board should be.
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

- Configurable 4x4, to 8x8 grid of letters.
- Letters drawn randomly but slightly proportional to language frequencies. Replacements are allowed. Still make sure to include rare letters.
- 2 to 4 players, round based game.
- At the start user can choose from english, german, french or spanish.
- In a turn a player forms a valid word from the language dictionary.
- Every letter in the word becomes "owned" by the player.
- "Owned" letters score points and become colored in the player's color.
- Scores of letters are higher the more rare the letter is: Integer between 1 and 10.
- A owned letter that is completely surrounded by letters of the same color is "protected".
- In a turn a player can select "owned" and unowned letters but not "protected" letters.
- The game ends when there are no more unowned letters.
- Words must follow classic Scrabble-style rules.
- A played word cannot be reused.
- Players can see the list of all played words.

### Emoji Concept

A multiplayer game that can be played in person but also remotely.
In each round a player is given a word or phrase (Object, Food, Animal, Brand, Famous Person, Movie Title, TV Show or Quote). 
This main player ("explainer") has to select emojis to describe the word.
The other players ("guessers") see only the emojis and have to guess the word.
If the word is guessed correctly the guesser gets a point.
If the round is timed also the explainer gets a point.

1. The host can select if the game is played in person or remotely and if the game is timed or not.
2. From the joined players a explainer is chosen randomly.
3. The explainer is given a set of three words which they can choose from.
4. The explainer can create multiple "sentences" just out of emojis. The first sentence is the main concept.
6. The guessers see the selected emojis and have to guess the word.
  * In person: The guessers just shout the word out loud and the explainer selects the player who guessed the word correctly.
  * Remotely: The guessers can write the word and the game detects if the word is correct (allowing for typos and slight variations).
7. The guesser who guessed the word correctly gets a point. If the round is timed also the explainer gets a point.
8. The next round starts with a new explainer and a new word.

- Explainers are chosen circularly.
- The explainer can select which sentence they are currently editing.
- The explainer can add, remove, rearrange emojis from the sentence.
- Emojis are sorted by category
  * Categories: Countries, Colors, Shapes, Foods, Animals, People, Things, Concepts, Actions
  * Concepts and actions are antonym pairs
  * Not all available emojis have to be used.
  * For the dev it should be easy to fine tune the selection.
- Timer is 2 minutes but can be adjusted by the host.
- The explainer can give up.
- People can join the game at any time.
- The host can end the game at any time and the final scores are shown.

### Spellsprawl

A multiplayer word spelling game with an infinite grid and endless allowed words and letters.
Inspired by scrabble but you only get points for reusing letters.

- The game is played in rounds.
- The grid where the letters are placed is infinite.
- 1 to 8 players.
- Main player can select end condition:
  * 50 Words played
  * First player to reach 500 points wins.
  * As soon as the grid takes more then 500 square units the game ends. (Counting max height * max width = number of square units of grid)
- Dictionary uses a shared component with silbenstreit.
- Letter scoring is shared with silbenstreit.
- Scoring:
  * A new word itself does not score points.
  * Only the letters that are already on the grid score points.

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
- Continent to play on
- Multiselect: Categories
- Timed: Yes/No for multiplier
- Game ends after: 
  * Rounds
  * Points
  * a round where each player has skipped or misplaced a location

Game play:
1. Main player defines the game settings
2. The game starts with a random city
3. Every player has 3 places to choose from, one per category
4. The active player can decide to place the chosen location north/south of the existing locations or in between them.
5. If the location is correcty places (with tollerance for the min and max latitude and longitude) the player gets a point.
6. If the location is not correctly placed the player gets a penalty according to the value of the location.
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
- each card can be rotated
- in an info modal every player can see how many cards of each type are left in the deck-

The board:
- infinite grid
- the used area is (min needed hight for all cards) x (min needed width for all cards)

1. The game starts with a cross card
2. each player gets a random card from the deck, cards are visible to all players.
3. the active player can rotate his card and decide which of the areas on the card he wants to occupy with their color.
4. the player places the card on the board but it has to match on all sides:
  * empty side to empty side
  * side with a line to side with a line
  * a occupied side cannot go next to a occupied side of another player
  * an empty side can got next to an occupied side (no matter which color) and it will take the color of the occupied side
5. if the new card increases the used area, the player gets minus points equal to units of (new used area - old used area)
6. if the new card merges two occupied areas of different colors the color area with more units takes over the area. If there is a tie the area will be marked gray. The tie will be resolved as soon as one color area is bigger by two units.
7. The game ends when the deck is empty.

Scoring:
- Increasing the used area decreases the score by the number of units of (new used area - old used area)
- For each card that has an occupied area the player gets one point, except for areas with just one card - this should be indicated by a lighter color.
- Occupied areas that are fully enclosed by lines get double points, indicated by a slightly darker color.








