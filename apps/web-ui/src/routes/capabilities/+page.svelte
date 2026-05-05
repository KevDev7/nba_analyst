<script lang="ts">
  type CapabilityExample = {
    prompt: string;
    note: string;
  };

  type CapabilityGroup = {
    kicker: string;
    title: string;
    description: string;
    examples: CapabilityExample[];
  };

  const capabilityGroups: CapabilityGroup[] = [
    {
      kicker: "Rankings",
      title: "Leaderboards With Basketball Intent",
      description: "Ask for top, bottom, best, worst, most, or fewest across players and teams.",
      examples: [
        {
          prompt: "Who are the best defensive teams this season?",
          note: "Understands that lower defensive rating is better."
        },
        {
          prompt: "Which players have the fewest turnovers over the last 10 games?",
          note: "Handles low-is-good quantity rankings."
        }
      ]
    },
    {
      kicker: "Trends",
      title: "Time-Based Team And Player Views",
      description: "Ask for monthly, weekly, yearly, season-by-season, or recent-window trends.",
      examples: [
        {
          prompt: "Show month over month team net rating over the past year",
          note: "Buckets team net rating by calendar month."
        },
        {
          prompt: "Show season by season team wins",
          note: "Uses NBA season grain instead of calendar years."
        }
      ]
    },
    {
      kicker: "Comparisons",
      title: "Named Entity Matchups",
      description: "Compare players or teams directly, including time-bucketed comparisons.",
      examples: [
        {
          prompt: "Compare Lakers and Warriors by points month by month over the past year",
          note: "Compares two teams across monthly buckets."
        },
        {
          prompt: "Compare Brunson and Tatum scoring over the last 10 games",
          note: "Resolves player names and summarizes the gap."
        }
      ]
    },
    {
      kicker: "Tables",
      title: "Player And Team Stat Tables",
      description: "Ask for entity rows with stats, metadata, limits, and recent windows.",
      examples: [
        {
          prompt: "Show me the top 5 players and their total points for the Knicks over the last 10 games",
          note: "Builds a player table filtered to a team context."
        },
        {
          prompt: "Show teams and their points, assists, and rebounds in the 2025-26 regular season",
          note: "Returns multiple stats in one table."
        }
      ]
    },
    {
      kicker: "Find",
      title: "Filtered Game Logs",
      description: "Find matching games or game rows with display columns and sorting.",
      examples: [
        {
          prompt: "Find Lakers games over 120 points and show date, opponent, score",
          note: "Combines team, score, opponent, and date fields."
        },
        {
          prompt: "Show Jalen Brunson game by game points over his last 10 games",
          note: "Returns a player game log instead of a trend."
        }
      ]
    },
    {
      kicker: "Context",
      title: "Basketball Context Filters",
      description: "Use natural filters like road, home, bench, starter, conference, and postseason.",
      examples: [
        {
          prompt: "Rank teams by net rating on the road over the last 10 games",
          note: "Treats road as away-game context."
        },
        {
          prompt: "Top players by points in the 2024-25 postseason",
          note: "Separates season scope from playoff season type."
        }
      ]
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
    <p>Examples of questions NBA Insight can answer.</p>
  </div>

  <section class="capabilities-grid" aria-label="Supported question examples">
    {#each capabilityGroups as group}
      <article class="capability-section">
        <div class="capability-copy">
          <p class="section-kicker">{group.kicker}</p>
          <h2>{group.title}</h2>
          <p>{group.description}</p>
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
</section>
