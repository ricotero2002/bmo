from langchain_core.prompts import ChatPromptTemplate

PROPOSITIONS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """Decompose the "Content" into clear, distinct, and standalone propositions.
        Follow these STRICT rules:
        1. NO TRANSLATION AND NO REPHRASING: You MUST extract the propositions in the EXACT ORIGINAL LANGUAGE of the source text. Use the exact words from the source. Do NOT summarize or add introductory phrases like "The author says" or "This is about".
        2. LITERAL SEGMENTS: If a sentence or list item is clear on its own, do not change a single word. Keep the tone and slang/technical terms identical.
        3. DECONTEXTUALIZE: Replace pronouns and vague references ("he", "that", "the issue") ONLY if absolutely necessary for the proposition to be a standalone thought.
        4. CONTEXTUAL COHESION: If you encounter a list of items sharing a single premise (e.g., a list of pending tasks, a recipe, a sequence of steps), do NOT break them into completely isolated sentences if it destroys their shared meaning. Combine them into a single, cohesive proposition block that retains the parent context.
        5. INDEPENDENCE: Break complex paragraphs into smaller statements ONLY if they represent distinct thoughts, subsystems, or actions.
        Output as a JSON list of strings.
        """
    ),
    ("user", "Few-Shot Examples:\n{few_shots}\n\nDecompose the following:\n{input}")
])
