import os
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

class PromptLoader:
    @staticmethod
    def load(version: str, file_name: str = "system.jinja2") -> ChatPromptTemplate:
        # Busca en src/core/prompts/<version>/<file_name>
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "core", "prompts", version, file_name)
        
        if not os.path.exists(path):
            # Fallback en caso de que la ruta no exista
            if file_name == "system.jinja2":
                return ChatPromptTemplate.from_messages([
                    ("system", "Eres un asistente experto."),
                    MessagesPlaceholder(variable_name="messages")
                ])
            else:
                return ChatPromptTemplate.from_messages([("human", "Falló la carga de {file_name}")])
            
        with open(path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
            
        # El user usó formato jinja2 para renderizar variables como {{ user_name }}
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages")
        ], template_format="jinja2")