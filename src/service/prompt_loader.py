import os
from jinja2 import Template
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.core.prompts.agent_few_shots import AGENT_FEW_SHOTS


class PromptLoader:
    @staticmethod
    def load(version: str = "rag_v3", file_name: str = "system.jinja2") -> ChatPromptTemplate:
        """
        Carga el system prompt desde src/core/prompts/<version>/<file_name>.

        Para rag_v3 y superiores, pre-renderiza la variable {{ few_shots }} en load time
        (es una constante, no depende del contexto de ejecución). Las variables dinámicas
        como {{ user_name }} y {{ today }} son resueltas en runtime por LangChain.

        Args:
            version:   Subdirectorio del prompt (default: "rag_v3").
            file_name: Nombre del archivo de template (default: "system.jinja2").

        Returns:
            ChatPromptTemplate con el system prompt y MessagesPlaceholder para el historial.
        """
        version = version or "rag_v4"
        file_name = file_name or "system.jinja2"
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "core", "prompts", version, file_name)

        if not os.path.exists(path):
            if file_name == "system.jinja2":
                return ChatPromptTemplate.from_messages([
                    ("system", "Eres un asistente experto."),
                    MessagesPlaceholder(variable_name="messages")
                ])
            else:
                return ChatPromptTemplate.from_messages([
                    ("human", f"Falló la carga de {file_name}")
                ])

        with open(path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

        # Pre-renderizar {{ few_shots }} en load time (constante de módulo).
        # El resto de variables Jinja2 ({{ user_name }}, {{ today }}) las resuelve
        # LangChain en runtime vía template_format="jinja2".
        pre_rendered = Template(system_prompt).render(few_shots=AGENT_FEW_SHOTS)

        return ChatPromptTemplate.from_messages([
            ("system", pre_rendered),
            MessagesPlaceholder(variable_name="messages")
        ], template_format="jinja2")

    @staticmethod
    def get_prompt(file_name: str, version: str = "rag_v3", **kwargs) -> str:
        """
        Lee y renderiza un template Jinja2 devolviendo el string resultante.
        Útil para calificadores y prompts auxiliares que no requieren historial de mensajes.
        """
        version = version or "rag_v4"
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "core", "prompts", version, file_name)

        if not os.path.exists(path):
            raise FileNotFoundError(f"Template no encontrado: {path}")

        with open(path, "r", encoding="utf-8") as f:
            template_text = f.read()

        return Template(template_text).render(**kwargs)