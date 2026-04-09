from langchain_core.prompts import ChatPromptTemplate

FIND_RELEVANT_CHUNK_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """Determine whether the "Proposition" should belong to any of the existing chunks.
        Follow these STRICT rules:
        1. TOPICAL COHESION: Group propositions that belong to the same specific sub-topic, event, or architectural component.
        2. LOGICAL GROUPING: If a proposition discusses a different aspect of the SAME project or meeting (e.g., from migration costs to migration backups), it is ALRIGHT to group them together to maintain context.
        3. AVOID FRAGMENTATION: Only create a new chunk if the topic changes completely (e.g., from technical infra to office expenses). It is BETTER to have a slightly larger, cohesive chunk than multiple single-proposition chunks.
        4. If it aligns with the logical flow of an existing chunk, return its ID.
        """
    ),
    ("user", "Few-Shot Examples:\n{few_shots}\n\nCurrent Chunks:\n--Start of current chunks--\n{current_chunk_outline}\n--End of current chunks--"),
    ("user", "Determine if the following statement should belong to one of the chunks outlined:\n{proposition}")
])
