from langchain_core.prompts import ChatPromptTemplate

NEW_CHUNK_TITLE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are the steward of a group of chunks which represent groups of sentences that talk about a similar topic.
        You should generate a very brief few word chunk title which will inform viewers what a chunk group is about.

        A good chunk title is brief but encompasses what the chunk is about.

        You will be given a summary of a chunk which needs a title.

        Your titles should anticipate generalization. If you get a proposition about apples, generalize it to food.
        Or month, generalize it to "date and times".

        Example:
        Input: Summary: This chunk is about dates and times that the author talks about
        Output: Date & Times

        Only respond with the new chunk title, nothing else.
        """
    ),
    ("user", "Determine the title of the chunk that this summary belongs to:\n{summary}")
])

UPDATE_CHUNK_TITLE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are the steward of a group of chunks which represent groups of sentences that talk about a similar topic.
        A new proposition was just added to one of your chunks, you should generate a very brief updated chunk title 
        which will inform viewers what a chunk group is about.

        Your title should anticipate generalization.

        Only respond with the new chunk title, nothing else.
        """
    ),
    ("user", "Chunk's propositions:\n{proposition}\n\nChunk summary:\n{current_summary}\n\nCurrent chunk title:\n{current_title}")
])
