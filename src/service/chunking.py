import uuid
import logging
from typing import List, Optional
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownTextSplitter
from pydantic import BaseModel

from src.core.prompts import (
    PROPOSITIONS_PROMPT, FIND_RELEVANT_CHUNK_PROMPT, 
    NEW_CHUNK_SUMMARY_PROMPT, NEW_CHUNK_TITLE_PROMPT,
    UPDATE_CHUNK_SUMMARY_PROMPT, UPDATE_CHUNK_TITLE_PROMPT,
    GLOBAL_SUMMARY_PROMPT
)
from src.core.prompts.few_shots import PROPOSITIONS_FEW_SHOTS, ROUTER_FEW_SHOTS
from src.schemas.metadata import DocumentMetadataExtraction
from datetime import datetime, timezone
from langsmith import tracing_context

logger = logging.getLogger(__name__)

class ChunkID(BaseModel):
    chunk_id: Optional[str]

class Sentences(BaseModel):
    sentences: List[str]

class AgenticChunker:
    """Implementa chunking proposicional utilizando el ecosistema nativo de LangGraph/Agents."""
    def __init__(self, llm_factory):
        self.plain_agent = llm_factory.create()
        self.sentences_agent = llm_factory.create(response_format=Sentences)
        self.chunk_id_agent = llm_factory.create(response_format=ChunkID)
        self.chunks = {}
        self.id_truncate_limit = 5

    def _get_propositions(self, text: str) -> List[str]:
        messages = PROPOSITIONS_PROMPT.format_messages(
            few_shots=PROPOSITIONS_FEW_SHOTS,
            input=text
        )
        try:
            with tracing_context(enabled=False):
                result = self.sentences_agent.invoke(messages, config={"callbacks": []})
            if result and result.sentences:
                return result.sentences
        except Exception as e:
            logger.error(f"Error extrayendo proposiciones: {e}")
        return [text]

    def chunk(self, text: str) -> List[Document]:
        self.chunks = {}
        paragraphs = text.split("\n\n")
        
        all_propositions = []
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
            propositions = self._get_propositions(paragraph)
            all_propositions.extend(propositions)
            
        self.add_propositions(all_propositions)
        
        docs = []
        for c_id, chunk_data in self.chunks.items():
            content = " ".join(chunk_data['propositions'])
            metadata = {
                "chunk_type": "agentic",
                "chunk_title": chunk_data.get('title', 'Sin título'),
                "chunk_summary": chunk_data.get('summary', 'Sin resumen')
            }
            docs.append(Document(page_content=content, metadata=metadata))
            
        return docs

    def add_propositions(self, propositions: List[str]):
        for proposition in propositions:
            self.add_proposition(proposition)
    
    def add_proposition(self, proposition: str):
        if len(self.chunks) == 0:
            self._create_new_chunk(proposition)
            return

        chunk_id = self._find_relevant_chunk(proposition)

        if chunk_id:
            self.add_proposition_to_chunk(chunk_id, proposition)
        else:
            self._create_new_chunk(proposition)

    def add_proposition_to_chunk(self, chunk_id, proposition):
        self.chunks[chunk_id]['propositions'].append(proposition)
        self.chunks[chunk_id]['summary'] = self._update_chunk_summary(self.chunks[chunk_id])
        self.chunks[chunk_id]['title'] = self._update_chunk_title(self.chunks[chunk_id])

    def _update_chunk_summary(self, chunk) -> str:
        messages = UPDATE_CHUNK_SUMMARY_PROMPT.format_messages(
            proposition="\n".join(chunk['propositions']),
            current_summary=chunk['summary']
        )
        with tracing_context(enabled=False):
            res = self.plain_agent.invoke(messages, config={"callbacks": []})
        return res.content
    
    def _update_chunk_title(self, chunk) -> str:
        messages = UPDATE_CHUNK_TITLE_PROMPT.format_messages(
            proposition="\n".join(chunk['propositions']),
            current_summary=chunk['summary'],
            current_title=chunk['title']
        )
        with tracing_context(enabled=False):
            res = self.plain_agent.invoke(messages, config={"callbacks": []})
        return res.content

    def _get_new_chunk_summary(self, proposition) -> str:
        messages = NEW_CHUNK_SUMMARY_PROMPT.format_messages(proposition=proposition)
        with tracing_context(enabled=False):
            res = self.plain_agent.invoke(messages, config={"callbacks": []})
        return res.content
    
    def _get_new_chunk_title(self, summary) -> str:
        messages = NEW_CHUNK_TITLE_PROMPT.format_messages(summary=summary)
        with tracing_context(enabled=False):
            res = self.plain_agent.invoke(messages, config={"callbacks": []})
        return res.content

    def _create_new_chunk(self, proposition):
        new_chunk_id = str(uuid.uuid4())[:self.id_truncate_limit]
        new_chunk_summary = self._get_new_chunk_summary(proposition)
        new_chunk_title = self._get_new_chunk_title(new_chunk_summary)

        self.chunks[new_chunk_id] = {
            'chunk_id' : new_chunk_id,
            'propositions': [proposition],
            'title' : new_chunk_title,
            'summary': new_chunk_summary,
            'chunk_index' : len(self.chunks)
        }
    
    def get_chunk_outline(self) -> str:
        chunk_outline = ""
        for chunk_id, chunk in self.chunks.items():
            chunk_outline += f"Chunk ({chunk['chunk_id']}): {chunk['title']}\nSummary: {chunk['summary']}\n\n"
        return chunk_outline

    def _find_relevant_chunk(self, proposition) -> Optional[str]:
        current_chunk_outline = self.get_chunk_outline()
        messages = FIND_RELEVANT_CHUNK_PROMPT.format_messages(
            few_shots=ROUTER_FEW_SHOTS,
            proposition=proposition,
            current_chunk_outline=current_chunk_outline
        )

        try:
            with tracing_context(enabled=False):
                result = self.chunk_id_agent.invoke(messages, config={"callbacks": []})
            if result and result.chunk_id:
                chunk_found = result.chunk_id
                if len(chunk_found) == self.id_truncate_limit and chunk_found in self.chunks:
                    return chunk_found
        except Exception as e:
            logger.debug(f"Fallo al extraer ChunkID: {e}")
        return None

class GlobalSummarizer:
    def __init__(self, llm_factory):
        self.fast_agent = llm_factory.create(response_format=DocumentMetadataExtraction)
        
    def analyze(self, text: str) -> Optional[DocumentMetadataExtraction]:
        # Tomar los primeros 5000 caracteres como muestra
        sample = text[:5000]
        messages = GLOBAL_SUMMARY_PROMPT.format_messages(input=sample)
        try:
            result = self.fast_agent.invoke(messages)
            return result
        except Exception as e:
            logger.error(f"Error en GlobalSummarizer: {e}")
            return None

class ChunkingRouter:
    @staticmethod
    def _is_structured_or_long(text: str, filename: str) -> bool:
        # Si tiene extensiones que suelen ser estructuradas
        if filename.endswith(".pdf") or filename.endswith(".docx"): 
            return True
        # Si el texto contiene headers de Markdown (# Titulo)
        if "#" in text and ("\n# " in text or text.startswith("# ")):
            return True
        return False

    def route_and_split(self, llm_factory, text: str, filename: str, global_context: Optional[DocumentMetadataExtraction] = None) -> List[Document]:
        """
        Decide qué estrategia de chunking usar (Markdown o Agéntico) y ejecuta la división.
        """
        # 1. Decisión de estrategia
        if len(text) > 20000:
            logger.info("Documento muy grande (> 20000 chars), forzando MarkdownTextSplitter")
            use_agentic = False
        elif global_context:
            use_agentic = global_context.requires_agentic_chunking
        else:
            use_agentic = not self._is_structured_or_long(text, filename)
            
        # 2. Ejecución
        if not use_agentic:
            logger.info(f"Ruteo: Usando MarkdownTextSplitter para {filename}")
            splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
            # Usamos create_documents envuelto en una lista porque espera una lista de textos
            chunks = splitter.create_documents([text])
            # Marcamos explícitamente como markdown para el retriever
            for chunk in chunks:
                chunk.metadata["chunk_type"] = "markdown"
        else:
            logger.info(f"Ruteo: Usando AgenticChunker para {filename}")
            agentic = AgenticChunker(llm_factory)
            chunks = agentic.chunk(text)
            
        return chunks

class ChunkingService:
    def __init__(self):
        self.router = ChunkingRouter()

    def process(self, original_document: Document, llm_factory) -> List[Document]:
        text = original_document.page_content
        filename = original_document.metadata.get("source", "unknown")
        
        # 1. Global Summarization
        summarizer = GlobalSummarizer(llm_factory)
        global_context = summarizer.analyze(text)
        
        # 2. Ruteo y división (delegado al router)
        chunks = self.router.route_and_split(llm_factory, text, filename, global_context)
        
        # Filtrar chunks vacíos para evitar error 400 en el embedder (Gemini)
        chunks = [c for c in chunks if c.page_content.strip()]
            
        # 3. Post-procesamiento e inyección de metadata
        for i, chunk in enumerate(chunks):
            base_meta = original_document.metadata.copy()
            
            # Transformación Pre-Chunking (Paso 1.1) y parseo de fecha
            if global_context:
                base_meta["doc_type"] = global_context.doc_type
                
                # Pre-fijar el contexto global
                chunk.page_content = f"[Contexto Global de {global_context.doc_type}: {global_context.global_summary}]\n\n{chunk.page_content}"
                
                # Si el LLM extrajo fecha y el usuario NO la proveyó manualmente, usamos la del documento (Paso 1.2)
                if global_context.document_date and not base_meta.get("custom_date"):
                    try:
                        parsed_date = datetime.strptime(global_context.document_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        base_meta["created_at"] = parsed_date.timestamp()
                        base_meta["document_date_str"] = global_context.document_date[:10]
                    except ValueError:
                        pass
                        
            # Si el splitter no puso índice, lo ponemos nosotros secuencialmente
            if "chunk_index" not in chunk.metadata or chunk.metadata["chunk_index"] is None:
                chunk.metadata["chunk_index"] = i
            base_meta.update(chunk.metadata)
            chunk.metadata = base_meta
            
        return chunks
