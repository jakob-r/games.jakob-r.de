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
