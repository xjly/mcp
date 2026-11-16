from pydantic import BaseModel, FiniteFloat


class KnowledgeBase(BaseModel):
    db_id: str
    name: str
    description: str | None
    kb_type: str


class KnowledgeBases(BaseModel):
    databases: list[KnowledgeBase]


class Document(BaseModel):
    file_id: str
    file_name: str
    original_file_name: str | None
    file_type: str | None
    status: str | None


class DocumentPage(BaseModel):
    db_id: str
    files: list[Document]
    limit: int
    offset: int
    total: int
    has_more: bool


class DownloadLink(BaseModel):
    db_id: str
    file_id: str
    file_name: str
    download_url: str
    expires_in_seconds: int


class SearchMatch(BaseModel):
    content: str
    truncated: bool
    file_id: str
    file_name: str
    chunk_id: str | None
    chunk_index: int | None
    score: FiniteFloat | None


class SearchResults(BaseModel):
    db_id: str
    matches: list[SearchMatch]
