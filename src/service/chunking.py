import uuid
import logging
from typing import List, Optional
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownTextSplitter
from pydantic import BaseModel

from src.core.prompts import (
    PROPOSITIONS_PROMPT, FIND_RELEVANT_CHUNK_PROMPT, 
    NEW_CHUNK_SUMMARY_PROMPT, NEW_CHUNK_TITLE_PROMPT,
    UPDATE_CHUNK_SUMMARY_PROMPT, UPDATE_CHUNK_TITLE_PROMPT
)

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
        messages = PROPOSITIONS_PROMPT.format_messages(input=text)
        try:
            result = self.sentences_agent.invoke(messages)
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
                "chunk_title": chunk_data['title'],
                "chunk_summary": chunk_data['summary'],
                "chunk_type": "agentic"
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
        res = self.plain_agent.invoke(messages)
        return res.content
    
    def _update_chunk_title(self, chunk) -> str:
        messages = UPDATE_CHUNK_TITLE_PROMPT.format_messages(
            proposition="\n".join(chunk['propositions']),
            current_summary=chunk['summary'],
            current_title=chunk['title']
        )
        res = self.plain_agent.invoke(messages)
        return res.content

    def _get_new_chunk_summary(self, proposition) -> str:
        messages = NEW_CHUNK_SUMMARY_PROMPT.format_messages(proposition=proposition)
        res = self.plain_agent.invoke(messages)
        return res.content
    
    def _get_new_chunk_title(self, summary) -> str:
        messages = NEW_CHUNK_TITLE_PROMPT.format_messages(summary=summary)
        res = self.plain_agent.invoke(messages)
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
            proposition=proposition,
            current_chunk_outline=current_chunk_outline
        )

        try:
            result = self.chunk_id_agent.invoke(messages)
            if result and result.chunk_id:
                chunk_found = result.chunk_id
                if len(chunk_found) == self.id_truncate_limit and chunk_found in self.chunks:
                    return chunk_found
        except Exception as e:
            logger.debug(f"Fallo al extraer ChunkID: {e}")
        return None

class ChunkingRouter:
    @staticmethod
    def _is_structured_or_long(text: str, filename: str) -> bool:
        if len(text) > 3000: return True
        if filename.endswith(".pdf") or filename.endswith(".docx"): return True
        if "# " in text or "## " in text: return True
        return False

    def route_and_split(self, llm_factory, document_text: str, filename: str) -> List[Document]:
        if self._is_structured_or_long(document_text, filename):
            logger.info(f"Ruteo: Usando MarkdownTextSplitter para {filename}")
            splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
            return getattr(splitter, "create_documents")([document_text])
        else:
            logger.info(f"Ruteo: Usando AgenticChunker para {filename}")
            agentic = AgenticChunker(llm_factory)
            return agentic.chunk(document_text)

class ChunkingService:
    def __init__(self):
        self.router = ChunkingRouter()

    def process(self, original_document: Document, llm_factory) -> List[Document]:
        text = original_document.page_content
        filename = original_document.metadata.get("source", "unknown")
        
        chunks = self.router.route_and_split(llm_factory, text, filename)
        
        for i, chunk in enumerate(chunks):
            base_meta = original_document.metadata.copy()
            # Si el splitter no puso índice, lo ponemos nosotros secuencialmente
            if "chunk_index" not in chunk.metadata or chunk.metadata["chunk_index"] is None:
                chunk.metadata["chunk_index"] = i
            base_meta.update(chunk.metadata)
            chunk.metadata = base_meta
            
        return chunks
