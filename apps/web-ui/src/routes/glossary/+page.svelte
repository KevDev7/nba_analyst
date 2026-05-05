<svelte:head>
  <title>Data & Glossary | NBA Analyst</title>
  <meta name="description" content="NBA Analyst data and glossary reference." />
</svelte:head>

<section class="glossary-page" aria-labelledby="glossary-title">
  <div class="glossary-header">
    <p class="eyebrow">Reference</p>
    <h1 id="glossary-title">Data &amp; Glossary</h1>
    <p>
      A plain-language guide to the data NBA Insights can answer questions about.
    </p>
  </div>

  <section class="glossary-card" aria-label="Data and glossary content">
    <article class="glossary-section">
      <h2>What Data Is Included</h2>
      <ul>
        <li>NBA data from the 2020-21 season through the 2025-26 season.</li>
        <li>Players, teams, arenas, games, player game logs, team game logs, and season summaries.</li>
        <li>Regular season, playoffs, play-in, and NBA Cup final data where available.</li>
        <li>Game-level stats are the lowest supported detail today.</li>
      </ul>
    </article>

    <article class="glossary-section">
      <h2>People, Teams &amp; Places</h2>
      <div class="stat-groups">
        <ul>
          <li>Player names, position, position group, latest team, jersey number, birth date, school or college, country, height, and weight.</li>
          <li>Player draft year, draft round, and draft pick number.</li>
          <li>Team name, city, state, country, abbreviation, conference, and division.</li>
        </ul>
        <ul>
          <li>Arena name, city, state, country, and time zone.</li>
          <li>Home team, away team, opponent, and latest team references are shown as basketball names rather than raw IDs.</li>
        </ul>
      </div>
    </article>

    <article class="glossary-section">
      <h2>Ways To Filter Or Group</h2>
      <div class="stat-groups">
        <ul>
          <li>Player, team, opponent, home team, away team, and arena.</li>
          <li>Season, season type, game date, game start time, month, and year.</li>
          <li>Regular season, playoffs, play-in, and NBA Cup final games where available.</li>
        </ul>
        <ul>
          <li>Home or away.</li>
          <li>Starter status.</li>
          <li>Win or loss result.</li>
          <li>Player age during a season, number of teams played for, and whether a player had a multi-team season.</li>
        </ul>
      </div>
    </article>

    <article class="glossary-section">
      <h2>Box Score Stats</h2>
      <div class="stat-groups">
        <ul>
          <li>Points or team score (PTS)</li>
          <li>Assists (AST)</li>
          <li>Rebounds (REB), offensive rebounds (OREB), and defensive rebounds (DREB)</li>
          <li>Steals (STL)</li>
          <li>Blocks (BLK) and opponent blocks</li>
          <li>Turnovers (TOV)</li>
        </ul>
        <ul>
          <li>Minutes (MIN)</li>
          <li>Plus/minus (+/-)</li>
          <li>Offensive fouls, personal fouls (PF), and technical fouls</li>
          <li>Fouls drawn</li>
          <li>Games played (GP), games started (GS), wins/losses (W/L), and win percentage (W%)</li>
          <li>Point differential</li>
        </ul>
      </div>
    </article>

    <article class="glossary-section">
      <h2>Shooting &amp; Scoring Details</h2>
      <div class="stat-groups">
        <ul>
          <li>Field goals: made, attempted, and percentage (FGM, FGA, FG%)</li>
          <li>Two-pointers: made, attempted, and percentage (2PM, 2PA, 2P%)</li>
          <li>Three-pointers: made, attempted, and percentage (3PM, 3PA, 3P%)</li>
          <li>Free throws: made, attempted, and percentage (FTM, FTA, FT%)</li>
        </ul>
        <ul>
          <li>Fast break points</li>
          <li>Points in the paint</li>
          <li>Second chance points</li>
          <li>Points off turnovers</li>
        </ul>
      </div>
    </article>

    <article class="glossary-section">
      <h2>Opponent &amp; Team Result Stats</h2>
      <ul>
        <li>Team questions can use opponent versions of common box score, shooting, fouling, rebounding, turnover, and scoring-detail stats.</li>
        <li>Examples include opponent score, opponent assists, opponent rebounds, opponent shooting, opponent fast break points, opponent points in the paint, opponent second chance points, and opponent points off turnovers.</li>
      </ul>
    </article>

    <article class="glossary-section">
      <h2>Advanced &amp; Possession Stats</h2>
      <div class="stat-groups">
        <ul>
          <li>Offensive possessions, defensive possessions, and total possessions</li>
          <li>Pace</li>
          <li>Offensive rating (ORtg)</li>
          <li>Defensive rating (DRtg)</li>
          <li>Net rating (NetRtg)</li>
          <li>Usage percentage (USG%)</li>
        </ul>
        <ul>
          <li>Assist percentage (AST%) and assist-to-turnover ratio (AST/TO)</li>
          <li>True shooting percentage (TS%)</li>
          <li>Effective field goal percentage (eFG%)</li>
          <li>Three-point attempt rate (3PAr) and free throw attempt rate (FTr)</li>
          <li>Offensive rebound (ORB%), defensive rebound (DRB%), total rebound (TRB%), steal (STL%), and block (BLK%) percentages</li>
        </ul>
      </div>
    </article>

    <article class="glossary-section">
      <h2>Season-Level Questions</h2>
      <ul>
        <li>Most box score, shooting, fouling, possession, and advanced stats can be asked over a full season or season type.</li>
        <li>Season questions can use totals, per-game values, percentages, rates, rankings, comparisons, and trends.</li>
        <li>You can ask about a player’s season, a player’s season with a specific team, or a team’s season without needing to specify how the data is stored.</li>
      </ul>
    </article>

    <article class="glossary-section">
      <h2>Supported Calculations</h2>
      <div class="stat-groups">
        <ul>
          <li>Totals</li>
          <li>Averages</li>
          <li>Per-game stats</li>
          <li>Per-36 minute scoring</li>
          <li>Percentages and rates</li>
        </ul>
        <ul>
          <li>Rankings</li>
          <li>Comparisons</li>
          <li>Monthly, yearly, and season trends</li>
          <li>Recent windows like last 5 or last 10 games</li>
        </ul>
      </div>
    </article>

    <article class="glossary-section">
      <h2>Things To Know</h2>
      <ul>
        <li>First season, last season, draft team, possession-by-possession, period-by-period, lineup, on/off, clutch, and shot-location analysis are not included yet.</li>
      </ul>
    </article>
  </section>
</section>
