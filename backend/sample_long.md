# Spark Chunk Test

Spark RDD is a resilient distributed dataset. It is one of the core abstractions in Apache Spark. RDD supports transformations and actions. Transformations are lazy, and actions trigger execution.

Spark SQL provides DataFrame and Dataset APIs. DataFrame has schema information, so Spark can apply query optimization through Catalyst. This makes structured data processing easier and often more efficient.

Spark DAG scheduler divides a job into stages according to shuffle dependencies. Narrow dependencies can be pipelined, while wide dependencies usually require shuffle and create stage boundaries.

HDFS stores large files across multiple DataNodes. NameNode manages metadata, while DataNodes store actual blocks. This paragraph is included to make the test document long enough for chunk splitting.

In a RAG system, chunking decides how source documents are divided before embedding. A good chunk should preserve semantic completeness and avoid cutting key concepts into unrelated fragments.

KnowFlow uses document chunks as the retrieval unit. Later, each chunk will be embedded and stored in the vector database with metadata such as kb_id, document_id, and chunk_index.
