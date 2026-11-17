# Setup (about 10 minutes)

1. **Create the special repo.** On GitHub, make a public repo named exactly like your username
   (`your-username/your-username`). Do not add a README; this kit generates one.
2. **Edit `profile.json`.** Set `github` to your username first.
3. **Preview locally** (Python 3.8+, nothing to install):
   ```
   python build.py
   ```
   Open `assets/player.svg` and `assets/snake.svg` in a browser to see the animation.
4. **Push everything** (`assets/`, `README.md`, `.github/`) to the repo's `main` branch.
5. **Turn on live data.** Enable Actions and run "Refresh profile". It rebuilds twice a day.

## Important: the snake and your real numbers

Until a live build runs with a token, the commit snake shows a *generated sample board*, and it says so
on the image. The workflow uses GitHub's built-in token, which covers public contributions. To include
private contributions, add a fine-grained personal access token as a repo secret named `PROFILE_TOKEN`.
The numbers in `profile.json` under `stats` are placeholders: replace them or let the live build overwrite them.

## What each part is

| Piece | How it works |
|-------|--------------|
| **Your piece** | `piece`: knight, bishop, rook, queen, king or pawn. It hops around the mini board in legal moves (a pawn walks up and promotes to a queen). It also leads the commit snake |
| **Level and rank** | LV = floor(sqrt(total contributions)). Rank title: Pawn under 10, Knight 10-19, Bishop 20-29, Rook 30-39, Queen 40-49, King 50+ |
| **Commit snake** | Sweeps your last year of contributions. Squares light up by activity and are captured as the snake passes, then the board resets |
| **Stats bar** | Language board (64 squares split by language share) plus contributions, commits, PRs, issues, repos, stars, followers and streaks |
| **Skill tree** | `skill_layers`. A neural net where each skill is a piece. States: `done` (developed), `training` (developing), `locked` (not yet on the board). Lit lines appear only between two `done` skills |
| **Games** | `projects`. `status`: `won`, `in play` (add `progress`), `puzzle`. `result` is your metric. Difficulty 1-5 shows as pawn, knight, bishop, rook, queen |
| **Model card** | A collapsible section modelled on a Hugging Face model card |

## Make it more you

- Pick the piece that fits how you work. Knight: unexpected routes. Rook: straight lines, steady. Bishop: diagonal thinking.
- Rewrite the skill layers and attribute ratings honestly. Interviewers will probe them.
- Themes: `walnut` (dark wood), `classic` (green and cream, light), `ink` (black and white diagram).
- `python build.py --snapshot 14` writes static frames to `preview/` if you want PNG exports.
