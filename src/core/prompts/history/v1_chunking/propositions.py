from langchain_core.prompts import ChatPromptTemplate

# HISTORICAL VERSION: v1_chunking (before "No Rephrasing" rule)
PROPOSITIONS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """Decompose the "Content" into clear, distinct, and standalone propositions.
        Follow these STRICT rules:
        1. NO TRANSLATION: You MUST extract the propositions in the EXACT ORIGINAL LANGUAGE of the source text. Do not translate Spanglish, slang, or idioms.
        2. DECONTEXTUALIZE: Replace pronouns and vague references ("he", "that", "the issue") with the specific entities they refer to based on the surrounding context.
        3. CONTEXTUAL COHESION: If you encounter a list of items sharing a single premise (e.g., a list of pending tasks, a recipe, a sequence of steps), do NOT break them into completely isolated sentences if it destroys their shared meaning. Combine them into a single, cohesive proposition block that retains the parent context.
        4. INDEPENDENCE: Break complex paragraphs into smaller statements ONLY if they represent distinct thoughts, subsystems, or actions.
        Output as a JSON list of strings.
        """
    ),
    ("user", "Few-Shot Examples:\n{few_shots}\n\nDecompose the following:\n{input}")
])
