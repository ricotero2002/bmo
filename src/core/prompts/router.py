from langchain_core.prompts import ChatPromptTemplate

FIND_RELEVANT_CHUNK_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """Determine whether the "Proposition" should belong to any of the existing chunks.
        Follow these STRICT rules:
        1. TOPICAL COHESION: Group propositions ONLY if they belong to the EXACT same specific sub-topic, event, or architectural component.
        2. LOGICAL BOUNDARIES: If a proposition shifts to a different category (e.g., from infrastructure/costs to legal/terms, or from project tasks to personal reminders), you MUST return 'No chunks'.
        3. PURITY > CONSOLIDATION: It is BETTER to have multiple smaller, pure chunks than a single chunk with mixed topics. Coherence within a chunk is the highest priority.
        4. If it aligns perfectly with the logical flow of an existing chunk, return its ID.
        """
    ),
    ("user", "Few-Shot Examples:\n{few_shots}\n\nCurrent Chunks:\n--Start of current chunks--\n{current_chunk_outline}\n--End of current chunks--"),
    ("user", "Determine if the following statement should belong to one of the chunks outlined:\n{proposition}")
])
