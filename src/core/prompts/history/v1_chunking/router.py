from langchain_core.prompts import ChatPromptTemplate

# HISTORICAL VERSION: v1_chunking (before "If in doubt, No Chunks" rule)
FIND_RELEVANT_CHUNK_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """Determine whether the "Proposition" should belong to any of the existing chunks.
        Follow these STRICT rules:
        1. STRICT TOPICAL ALIGNMENT: Do not group propositions just because they belong to the same broad category (e.g., "Technology" or "Work"). They must share the exact specific sub-topic, event, or immediate architectural component.
        2. If a proposition shifts the focus to a new component, a new problem, or a different context (e.g., from Database configuration to UI changes), return "No chunks" to force a new chunk creation.
        3. If it perfectly aligns with the immediate discussion of an existing chunk, return the chunk ID.
        """
    ),
    ("user", "Few-Shot Examples:\n{few_shots}\n\nCurrent Chunks:\n--Start of current chunks--\n{current_chunk_outline}\n--End of current chunks--"),
    ("user", "Determine if the following statement should belong to one of the chunks outlined:\n{proposition}")
])
