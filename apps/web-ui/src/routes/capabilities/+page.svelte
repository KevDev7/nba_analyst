<script lang="ts">
  type CapabilityExample = {
    prompt: string;
    note: string;
  };

  type CapabilityGroup = {
    kicker: string;
    title: string;
    description: string;
    strengths: string[];
    examples: CapabilityExample[];
  };

  type CapabilityList = {
    title: string;
    items: string[];
  };

  const capabilityGroups: CapabilityGroup[] = [
    {
      kicker: "Rankings",
      title: "Leaderboards That Understand Basketball",
      description:
        "Rank players or teams by volume, efficiency, role, location, season, and low-is-good defensive ideas.",
      strengths: ["top and bottom", "best and worst", "most and fewest", "player or team scope"],
      examples: [
        {
          prompt: "Who are the best defensive teams this season?",
          note: "Understands that lower defensive rating is better."
        },
        {
          prompt: "Which players have the fewest turnovers over the last 10 games?",
          note: "Handles low-is-good quantity rankings."
        },
        {
          prompt: "Top 10 Eastern Conference teams by wins this season",
          note: "Combines conference context with a season leaderboard."
        }
      ]
    },
    {
      kicker: "Trends",
      title: "Trends Across Basketball Time",
      description:
        "Move from daily recency to weekly, monthly, yearly, and season-by-season views without changing how you ask.",
      strengths: ["daily", "weekly", "monthly", "yearly", "season by season"],
      examples: [
        {
          prompt: "Show month over month team net rating over the past year",
          note: "Buckets team efficiency by calendar month."
        },
        {
          prompt: "Show weekly average assists by team over the past year",
          note: "Turns a passing question into a weekly team trend."
        },
        {
          prompt: "Show season by season team win percentage",
          note: "Uses NBA seasons instead of calendar years."
        }
      ]
    },
    {
      kicker: "Comparisons",
      title: "Player And Team Comparisons",
      description:
        "Compare two or more named players or teams, including direct totals and time-bucketed head-to-head views.",
      strengths: ["two-way comparisons", "multi-entity comparisons", "team comparisons", "time buckets"],
      examples: [
        {
          prompt: "Compare Brunson and Tatum by assists over the last 10 games",
          note: "Resolves player names and summarizes the gap."
        },
        {
          prompt: "Compare Lakers and Warriors by rebounds month by month over the past year",
          note: "Compares two teams across monthly buckets."
        },
        {
          prompt: "Compare Celtics, Nuggets, and Thunder net rating this season",
          note: "Handles more than two teams in one comparison."
        }
      ]
    },
    {
      kicker: "Tables",
      title: "Custom Stat Tables",
      description:
        "Ask for player or team rows with the stats you care about, recent windows, team filters, and natural limits.",
      strengths: ["player rows", "team rows", "multi-stat tables", "team-filtered tables"],
      examples: [
        {
          prompt: "Show me players and their assists over the last 10 games",
          note: "Returns a player table ordered by assists."
        },
        {
          prompt: "Show teams and their steals, blocks, and rebounds in the 2025-26 regular season",
          note: "Returns multiple defensive and rebounding stats in one table."
        },
        {
          prompt: "Show me the top 5 players and their total rebounds for the Knicks over the last 10 games",
          note: "Builds a player table inside a team context."
        }
      ]
    },
    {
      kicker: "Find",
      title: "Filtered Game Logs And Rows",
      description:
        "Find matching games or player-game rows when the question is about specific rows rather than one summary.",
      strengths: ["game logs", "player game logs", "numeric filters", "display columns"],
      examples: [
        {
          prompt: "Find Lakers games over 120 points and show date, opponent, score",
          note: "Combines team, score, opponent, and date fields."
        },
        {
          prompt: "Find Celtics games with more than 15 threes and show date, opponent, three-pointers made",
          note: "Filters games by shooting volume and chooses display columns."
        },
        {
          prompt: "Show Jalen Brunson game by game assists over his last 10 games",
          note: "Returns a player game log instead of a trend summary."
        }
      ]
    },
    {
      kicker: "Context",
      title: "Basketball Context Filters",
      description:
        "Layer basketball context onto the same question shape: home, road, starters, bench, conference, regular season, and playoffs.",
      strengths: ["home and road", "starter and bench", "conference", "regular season and playoffs"],
      examples: [
        {
          prompt: "Rank teams by net rating on the road over the last 10 games",
          note: "Treats road as away-game context."
        },
        {
          prompt: "Top bench scorers over the last 10 games",
          note: "Connects bench language to non-starter player games."
        },
        {
          prompt: "Top players by points in the 2024-25 postseason",
          note: "Separates season scope from playoff season type."
        }
      ]
    }
  ];

  const statAreas: CapabilityList[] = [
    {
      title: "Scoring And Shooting",
      items: ["points", "field goal percentage", "3PM", "3PA", "3P%", "true shooting", "eFG%"]
    },
    {
      title: "Creation And Ball Control",
      items: ["assists", "turnovers", "usage", "minutes", "free throws", "personal fouls"]
    },
    {
      title: "Defense And Rebounding",
      items: ["steals", "blocks", "rebounds", "opponent points", "defensive rating"]
    },
    {
      title: "Team Efficiency",
      items: ["wins", "losses", "win percentage", "pace", "offensive rating", "net rating", "plus/minus"]
    }
  ];

  const contextAreas: CapabilityList[] = [
    {
      title: "Who",
      items: ["players", "teams", "named player comparisons", "named team comparisons"]
    },
    {
      title: "Where",
      items: ["home", "road", "team context", "opponent context", "conference"]
    },
    {
      title: "When",
      items: ["this season", "last 10 games", "past year", "date ranges", "playoffs"]
    },
    {
      title: "Shape",
      items: ["rankings", "trends", "comparisons", "tables", "matching games"]
    }
  ];
</script>

<svelte:head>
  <title>Capabilities | NBA Analyst</title>
  <meta name="description" content="Examples of questions NBA Insight can answer." />
</svelte:head>

<section class="capabilities-page" aria-labelledby="capabilities-title">
  <div class="capabilities-header">
    <p class="eyebrow">Guide</p>
    <h1 id="capabilities-title">Capabilities</h1>
    <p>
      A deeper map of what NBA Insight can answer today: rankings, trends, comparisons, stat
      tables, game logs, and basketball context across players and teams.
    </p>
  </div>

  <section class="capabilities-grid" aria-label="Supported question examples">
    {#each capabilityGroups as group}
      <article class="capability-section">
        <div class="capability-copy">
          <p class="section-kicker">{group.kicker}</p>
          <h2>{group.title}</h2>
          <p>{group.description}</p>
          <ul class="capability-strengths" aria-label={`${group.title} supported details`}>
            {#each group.strengths as strength}
              <li>{strength}</li>
            {/each}
          </ul>
        </div>

        <div class="capability-prompts">
          {#each group.examples as example}
            <figure class="capability-prompt">
              <blockquote>{example.prompt}</blockquote>
              <figcaption>{example.note}</figcaption>
            </figure>
          {/each}
        </div>
      </article>
    {/each}
  </section>

  <section class="capabilities-reference" aria-label="Supported stats and contexts">
    <article class="capability-reference-card">
      <div>
        <p class="section-kicker">Stats</p>
        <h2>Stats You Can Mix In</h2>
      </div>

      <div class="capability-list-grid">
        {#each statAreas as area}
          <section class="capability-list">
            <h3>{area.title}</h3>
            <ul>
              {#each area.items as item}
                <li>{item}</li>
              {/each}
            </ul>
          </section>
        {/each}
      </div>
    </article>

    <article class="capability-reference-card">
      <div>
        <p class="section-kicker">Context</p>
        <h2>Ways To Narrow Or Reshape A Question</h2>
      </div>

      <div class="capability-list-grid">
        {#each contextAreas as area}
          <section class="capability-list">
            <h3>{area.title}</h3>
            <ul>
              {#each area.items as item}
                <li>{item}</li>
              {/each}
            </ul>
          </section>
        {/each}
      </div>
    </article>
  </section>
</section>
