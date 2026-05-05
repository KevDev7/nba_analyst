<script lang="ts">
  type Example = {
    prompt: string;
    note: string;
  };

  type Capability = {
    kicker: string;
    title: string;
    description: string;
    signals: string[];
    examples: Example[];
  };

  type ReferenceGroup = {
    title: string;
    items: string[];
  };

  const capabilities: Capability[] = [
    {
      kicker: "Rank",
      title: "Order players or teams by what matters",
      description:
        "Ask for top, bottom, best, worst, most, or fewest. NBA Insights can use basketball-aware ordering when lower is actually better.",
      signals: ["top and bottom", "best and worst", "most and fewest", "player or team leaderboards"],
      examples: [
        {
          prompt: "Who are the best defensive teams this season?",
          note: "Ranks defense in the right direction instead of treating every stat as higher-is-better."
        },
        {
          prompt: "Which players have the fewest turnovers over the last 10 games?",
          note: "Understands low-volume rankings for mistakes, fouls, and other lower-is-better stats."
        },
        {
          prompt: "Top 10 road rebounding teams over the last 10 games",
          note: "Combines location context, recency, team scope, and a ranking."
        }
      ]
    },
    {
      kicker: "Context",
      title: "Narrow the basketball situation",
      description:
        "Layer real NBA context onto the same question: home, road, starter, bench, opponent, conference, regular season, playoffs, and named teams or players.",
      signals: ["home or road", "starter or bench", "opponent context", "regular season or playoffs"],
      examples: [
        {
          prompt: "Top bench scorers over the last 10 games",
          note: "Uses bench language as a player-game context instead of a separate stat."
        },
        {
          prompt: "Rank Eastern Conference teams by win percentage this season",
          note: "Applies a team context before ranking the result."
        },
        {
          prompt: "Which players had the highest true shooting in the 2024-25 playoffs?",
          note: "Separates season and season type without needing rigid wording."
        }
      ]
    },
    {
      kicker: "Filter",
      title: "Filter before or after the stat is calculated",
      description:
        "Some questions narrow the games first. Others ask for only the players or teams whose calculated totals, averages, or ratings clear a threshold.",
      signals: ["before calculation", "after calculation", "numeric thresholds", "and/or style conditions"],
      examples: [
        {
          prompt: "Show teams with net rating above 5 this season",
          note: "Filters by a calculated team efficiency result."
        },
        {
          prompt: "Show players averaging at least 8 assists over the last 10 games",
          note: "Keeps only players whose average clears the threshold."
        },
        {
          prompt: "Rank teams by net rating on the road over the last 10 games",
          note: "Narrows to road games before calculating each team's rating."
        }
      ]
    },
    {
      kicker: "Compare",
      title: "Compare named players or teams",
      description:
        "Compare two or more entities across one metric, several metrics, or time buckets, then get a plain-language read on the gap.",
      signals: ["two-way comparisons", "multi-entity comparisons", "multi-stat comparisons", "time-bucketed comparisons"],
      examples: [
        {
          prompt: "Compare Brunson and Tatum by points, assists, and rebounds over the last 10 games",
          note: "Compares multiple player stats in one answer."
        },
        {
          prompt: "Compare Lakers and Warriors by rebounds month by month over the past year",
          note: "Turns the comparison into a monthly team view."
        },
        {
          prompt: "Compare Celtics, Nuggets, and Thunder by net rating this season",
          note: "Handles more than two teams in the same comparison."
        }
      ]
    },
    {
      kicker: "Trend",
      title: "Track movement over basketball time",
      description:
        "Ask for daily, weekly, monthly, yearly, or season-by-season movement when you want to see how a stat changes instead of a single table.",
      signals: ["daily", "weekly", "monthly", "yearly", "season by season"],
      examples: [
        {
          prompt: "Show monthly team net rating over the past year",
          note: "Buckets team efficiency into calendar months."
        },
        {
          prompt: "Show weekly average assists by team over the past year",
          note: "Creates a passing trend across teams."
        },
        {
          prompt: "Show season-by-season win percentage for teams",
          note: "Uses NBA seasons instead of calendar years."
        }
      ]
    },
    {
      kicker: "Find",
      title: "Find games and game logs",
      description:
        "Use find-style questions when you want matching rows: games, team game logs, player game logs, dates, opponents, scores, and selected columns.",
      signals: ["game logs", "player logs", "team logs", "display columns"],
      examples: [
        {
          prompt: "Find Celtics games with more than 15 threes and show date, opponent, three-pointers made",
          note: "Returns matching games with the columns you asked for."
        },
        {
          prompt: "Show Jalen Brunson game-by-game assists over his last 10 games",
          note: "Returns a player game log instead of a season summary."
        },
        {
          prompt: "Find Lakers games where the opponent scored under 100 and show date, opponent, score",
          note: "Combines opponent context, scoring filters, and game details."
        }
      ]
    },
    {
      kicker: "Tables",
      title: "Build custom stat tables",
      description:
        "Ask for the rows and stats you care about. NBA Insights can return multi-stat player or team tables and chartable artifacts when the shape fits.",
      signals: ["multi-stat output", "player rows", "team rows", "tables and charts"],
      examples: [
        {
          prompt: "Show teams and their steals, blocks, and rebounds in the 2025-26 regular season",
          note: "Combines defensive and rebounding stats in one table."
        },
        {
          prompt: "Show players and their assist-to-turnover ratio over the last 10 games",
          note: "Uses an efficiency stat instead of only box-score volume."
        },
        {
          prompt: "Show Knicks players by total offensive rebounds over the last 10 games",
          note: "Builds a team-filtered player table."
        }
      ]
    }
  ];

  const languageGroups: ReferenceGroup[] = [
    {
      title: "Ordering words",
      items: ["top", "bottom", "best", "worst", "highest", "lowest", "most", "fewest"]
    },
    {
      title: "Context words",
      items: ["home", "road", "bench", "starter", "opponent", "East", "West", "playoffs"]
    },
    {
      title: "Time words",
      items: ["last 10 games", "past year", "monthly", "weekly", "season by season", "2024-25"]
    },
    {
      title: "Threshold words",
      items: ["above 5", "under 100", "at least 8", "more than 15", "between dates"]
    }
  ];

  const statGroups: ReferenceGroup[] = [
    {
      title: "Scoring and shooting",
      items: ["points", "FG%", "3PM", "3P%", "FT%", "true shooting", "eFG%", "paint points"]
    },
    {
      title: "Creation and control",
      items: ["assists", "turnovers", "AST:TO", "usage", "minutes", "fouls drawn"]
    },
    {
      title: "Defense and glass",
      items: ["steals", "blocks", "rebounds", "offensive rebounds", "opponent points", "defensive rating"]
    },
    {
      title: "Team quality",
      items: ["wins", "losses", "win percentage", "pace", "offensive rating", "net rating", "plus/minus"]
    }
  ];

  const showcaseExamples: Example[] = [
    {
      prompt: "Which teams had net rating above 5 this season, ordered from best to worst?",
      note: "Calculated threshold plus direction-aware ordering."
    },
    {
      prompt: "Compare Lakers and Warriors rebounding by month over the past year",
      note: "Named teams, time buckets, comparison, and chartable output."
    },
    {
      prompt: "Find Celtics games with more than 15 threes and fewer than 12 turnovers",
      note: "A row search with multiple basketball conditions."
    }
  ];
</script>

<svelte:head>
  <title>Capabilities | NBA Analyst</title>
  <meta name="description" content="Examples of questions NBA Insights can answer." />
</svelte:head>

<section class="capabilities-page" aria-labelledby="capabilities-title">
  <header class="capabilities-header">
    <p class="eyebrow">Guide</p>
    <h1 id="capabilities-title">Capabilities</h1>
    <p>
      A practical map of what NBA Insights can answer today across rankings, context filters,
      calculated thresholds, comparisons, trends, custom tables, and game logs.
    </p>
  </header>

  <section class="capabilities-snapshot" aria-label="Capability summary">
    <div>
      <strong>Players, teams, games, seasons</strong>
      <span>Ask across core NBA entities without naming the data shape.</span>
    </div>
    <div>
      <strong>2020-21 through 2025-26</strong>
      <span>Use seasons, recent windows, date ranges, and time trends.</span>
    </div>
    <div>
      <strong>Tables, charts, summaries</strong>
      <span>Answers can return text, tables, and chartable results.</span>
    </div>
  </section>

  <section class="capability-showcase" aria-labelledby="showcase-title">
    <div>
      <p class="section-kicker">Try These</p>
      <h2 id="showcase-title">Showcase Questions</h2>
    </div>

    <div class="showcase-list">
      {#each showcaseExamples as example}
        <figure class="capability-prompt spotlight">
          <blockquote>{example.prompt}</blockquote>
          <figcaption>{example.note}</figcaption>
        </figure>
      {/each}
    </div>
  </section>

  <section class="capabilities-grid" aria-label="Supported question types">
    {#each capabilities as capability}
      <article class="capability-section">
        <div class="capability-copy">
          <p class="section-kicker">{capability.kicker}</p>
          <h2>{capability.title}</h2>
          <p>{capability.description}</p>
          <p class="capability-signals">{capability.signals.join(" / ")}</p>
        </div>

        <div class="capability-prompts">
          {#each capability.examples as example}
            <figure class="capability-prompt">
              <blockquote>{example.prompt}</blockquote>
              <figcaption>{example.note}</figcaption>
            </figure>
          {/each}
        </div>
      </article>
    {/each}
  </section>

  <section class="capabilities-reference" aria-label="Supported language and stats">
    <article class="capability-reference-card">
      <div>
        <p class="section-kicker">Language</p>
        <h2>Ways You Can Phrase A Question</h2>
      </div>

      <div class="capability-list-grid">
        {#each languageGroups as group}
          <section class="capability-list">
            <h3>{group.title}</h3>
            <p>{group.items.join(", ")}</p>
          </section>
        {/each}
      </div>
    </article>

    <article class="capability-reference-card">
      <div>
        <p class="section-kicker">Stats</p>
        <h2>Stats You Can Mix In</h2>
      </div>

      <div class="capability-list-grid">
        {#each statGroups as group}
          <section class="capability-list">
            <h3>{group.title}</h3>
            <p>{group.items.join(", ")}</p>
          </section>
        {/each}
      </div>
    </article>
  </section>
</section>
