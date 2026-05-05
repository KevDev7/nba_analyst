<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import "@fontsource/cormorant-garamond/500.css";
  import "@fontsource/inter/400.css";
  import "@fontsource/inter/500.css";
  import "@fontsource/jetbrains-mono/400.css";
  import "$lib/shadcn.css";
  import "$lib/styles.css";

  let { children } = $props();
  const currentPath = $derived(page.url.pathname);

  function isActive(path: string) {
    return currentPath === path;
  }

  async function startNewChat() {
    await goto(`/?new=${Date.now()}`);
  }
</script>

<main class="chat-shell">
  <aside class="sidebar" aria-label="NBA Analyst navigation">
    <a class="brand" href="/">
      <span class="brand-mark" aria-hidden="true">*</span>
      <span>NBA Insights (beta)</span>
    </a>

    <button type="button" class="sidebar-action" onclick={startNewChat}>New chat</button>

    <nav class="sidebar-section" aria-label="Pages">
      <p class="sidebar-label">Pages</p>
      <a class:active={isActive("/")} class="chat-link" href="/" aria-current={isActive("/") ? "page" : undefined}>
        Home
      </a>
      <a
        class:active={isActive("/glossary")}
        class="chat-link"
        href="/glossary"
        aria-current={isActive("/glossary") ? "page" : undefined}
      >
        Data &amp; Glossary
      </a>
    </nav>

    <nav class="sidebar-section" aria-label="Threads">
      <p class="sidebar-label">Threads</p>
      <button class="chat-link chat-history-placeholder" type="button" disabled>Current chat</button>
    </nav>
  </aside>

  <header class="mobile-topbar" aria-label="NBA Analyst">
    <a class="brand" href="/">
      <span class="brand-mark" aria-hidden="true">*</span>
      <span>NBA Insights (beta)</span>
    </a>
    <nav class="mobile-nav" aria-label="Pages">
      <a class:active={isActive("/")} href="/">Home</a>
      <a class:active={isActive("/glossary")} href="/glossary">Glossary</a>
    </nav>
  </header>

  {@render children()}
</main>
