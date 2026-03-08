from langchain_core.prompts import ChatPromptTemplate

FIND_RELEVANT_CHUNK_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        Determine whether or not the "Proposition" should belong to any of the existing chunks.

        A proposition should belong to a chunk if their meaning, direction, or intention are similar.
        The goal is to group similar propositions and chunks.

        If you think a proposition should be joined with a chunk, return the chunk id.
        If you do not think an item should be joined with an existing chunk, just return "No chunks"

        Example:
        Input:
            - Proposition: "Greg really likes hamburgers"
            - Current Chunks:
                - Chunk ID: 2n4l3d
                - Chunk Name: Places in San Francisco
                - Chunk Summary: Overview of the things to do with San Francisco Places

                - Chunk ID: 93833k
                - Chunk Name: Food Greg likes
                - Chunk Summary: Lists of the food and dishes that Greg likes
        Output: 93833k
        """
    ),
    ("user", "Current Chunks:\n--Start of current chunks--\n{current_chunk_outline}\n--End of current chunks--"),
    ("user", "Determine if the following statement should belong to one of the chunks outlined:\n{proposition}")
])
