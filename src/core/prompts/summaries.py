from langchain_core.prompts import ChatPromptTemplate

NEW_CHUNK_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are the steward of a group of chunks which represent groups of sentences that talk about a similar topic.
        You should generate a very brief 1-sentence summary which will inform viewers what a chunk group is about.

        A good summary will say what the chunk is about, and give any clarifying instructions on what to add to the chunk.

        You will be given a proposition which will go into a new chunk. This new chunk needs a summary.

        Your summaries should anticipate generalization. If you get a proposition about apples, generalize it to food.
        Or month, generalize it to "date and times".

        Example:
        Input: Proposition: Greg likes to eat pizza
        Output: This chunk contains information about the types of food Greg likes to eat.

        Only respond with the new chunk summary, nothing else.
        """
    ),
    ("user", "Determine the summary of the new chunk that this proposition will go into:\n{proposition}")
])

UPDATE_CHUNK_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are the steward of a group of chunks which represent groups of sentences that talk about a similar topic.
        A new proposition was just added to one of your chunks, you should generate a very brief 1-sentence summary 
        which will inform viewers what a chunk group is about.

        Your summaries should anticipate generalization. If you get a proposition about apples, generalize it to food.
        Or month, generalize it to "date and times".

        Example:
        Input: Proposition: Greg likes to eat pizza
        Output: This chunk contains information about the types of food Greg likes to eat.

        Only respond with the chunk new summary, nothing else.
        """
    ),
    ("user", "Chunk's propositions:\n{proposition}\n\nCurrent chunk summary:\n{current_summary}")
])
