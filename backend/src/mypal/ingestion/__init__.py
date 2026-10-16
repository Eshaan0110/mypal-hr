"""Document ingestion: turn an uploaded policy file into validated, traceable draft chunks.

Pipeline:  file checks -> parse (PDF or DOCX) -> quality assessment -> chunking -> store as draft.
Nothing in this package publishes a policy; publication is a separate, approved step (Phase 7).
"""
