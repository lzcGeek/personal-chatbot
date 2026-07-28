## ADDED Requirements

### Requirement: Hybrid evidence retrieval
The system SHALL combine filtered vector chunks with relevant user-owned graph entities, facts and bounded paths.

#### Scenario: Multi-hop relationship question
- **WHEN** a query requires following relationships across document facts
- **THEN** the retriever supplies the supported graph path together with source text chunks

### Requirement: Evidence reranking and deduplication
The system SHALL deduplicate overlapping windows and rank evidence by relevance, provenance quality and query type before prompt injection.

#### Scenario: Repeated content across documents
- **WHEN** multiple documents contain substantially identical evidence
- **THEN** the prompt avoids redundant context while preserving distinct citations

### Requirement: Grounded answer with citations
The system SHALL instruct the LLM to answer from retrieved evidence, cite source filename and location for material claims, and state when evidence is insufficient.

#### Scenario: Supported answer
- **WHEN** retrieved chunks and graph facts support an answer
- **THEN** the response includes citations that identify the source document and page or section

#### Scenario: Insufficient evidence
- **WHEN** the personal knowledge base does not support the requested claim
- **THEN** the response clearly states that it cannot be confirmed from the uploaded documents

### Requirement: Untrusted document boundary
The system SHALL treat retrieved document text as data and SHALL NOT allow it to override system instructions or independently trigger tools.

#### Scenario: Prompt injection in document
- **WHEN** a retrieved chunk contains instructions to ignore policy or invoke a tool
- **THEN** the system presents it only as quoted evidence and does not execute those instructions
