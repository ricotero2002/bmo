from langchain_core.prompts import ChatPromptTemplate

PROPOSITIONS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """Decompose the "Content" into clear and concise propositions.
        1. Split complex sentences into simple ones, but ONLY if they contain distinct ideas that can stand alone. Do not break related technical concepts.
        2. Decontextualize each proposition by replacing pronouns with the specific entities they refer to.
        3. Ensure each proposition is a complete, standalone thought.
        4. Present the results as a list of strings, formatted in JSON.
        """
    ),
    ("user", "Decompose the following:\n{input}")
])
