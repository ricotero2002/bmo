from langchain_core.prompts import ChatPromptTemplate

PROPOSITIONS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """Decompose the "Content" into clear and simple propositions, ensuring they are interpretable out of
        context.
        1. Split compound sentence into simple sentences. Maintain the original phrasing from the input
        whenever possible.
        2. For any named entity that is accompanied by additional descriptive information, separate this
        information into its own distinct proposition.
        3. Decontextualize the proposition by adding necessary modifier to nouns or entire sentences
        and replacing pronouns (e.g., "it", "he", "she", "they", "this", "that") with the full name of the
        entities they refer to.
        4. Present the results as a list of strings, formatted in JSON.
        """
    ),
    ("user", "Decompose the following:\n{input}")
])
