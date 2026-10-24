# IDEA

Ih this repo I want to host several small multiplayer games.
Ideally they share some components of FE and BE but it should also be possible to extract a game and run it standalone.
Users can set their name and it will be remembered in the browser.
The style of the games should be minimalistic, scribbly with nuanced animations.
We don't want to annoy the user with ads or tracking.
Only use color where it is necessary and helpful.

## Not now
- For now we don't need authentication, but we want to be able to add it later.
- For now we don't add a chat function but might be added later.


## Landing page

When the user enters games.jakob-r.de they can 
- see and change their name and their primary color
- see a list of games
- see the most recently played games
- if possible resume the game from where they left off
- see some personal stats

## Common parts

- Color logic: A user sets their primary color and sees other players with their primary color. If the others player color is too similar it will be adjusted. For this we have a function opponent_color(my_color, their_color) which returns a color that is not too similar to my_color or their_color.

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

### Silbenstreit

- Configurable 4x4, to 8x8 grid of letters.
- Letters drawn randomly but slightly proportional to language frequencies. Replacements are allowed. Still make sure to include rare letters.
- 2 players, round based game.
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

#### Scoring

- Reveal a safe cell: `+1` per newly revealed cell (including flood-fill).
- Hit a mine: `−10`.
- Place a flag: `+2`.
- Remove your own flag: `−3`.
- Challenge an opponent's flag:
  - Flag was correct (mine): challenger `−5`, owner `+5`; cell becomes a confirmed revealed mine.
  - Flag was wrong (safe): challenger `+5`, owner `−5`; flag removed and cell revealed (flood-fill if zero).
- Scoring can be turned off by the starting user.

