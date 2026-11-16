\set ON_ERROR_STOP on

BEGIN;

SELECT EXISTS (
    SELECT 1 FROM public.knowledge_bases
    WHERE db_id = :'db_id' AND kb_type = 'milvus'
) AS target_exists \gset
\if :target_exists
\else
DO $$ BEGIN RAISE EXCEPTION 'The requested Milvus knowledge base does not exist'; END $$;
\endif

-- Create a dedicated schema once. An existing schema requires a deliberate DBA review.
CREATE SCHEMA mcp_kb;
REVOKE ALL ON SCHEMA mcp_kb FROM PUBLIC;

CREATE VIEW mcp_kb.databases WITH (security_barrier = true) AS
SELECT
    db_id,
    name,
    description,
    kb_type,
    embed_info->>'model_id' AS embedding_model_id,
    embed_info->>'name' AS embedding_model,
    CASE WHEN (embed_info->>'dimension') ~ '^[1-9][0-9]{0,8}$'
         THEN (embed_info->>'dimension')::integer
    END AS embedding_dimension
FROM public.knowledge_bases
WHERE db_id = :'db_id' AND kb_type = 'milvus';

CREATE VIEW mcp_kb.documents WITH (security_barrier = true) AS
SELECT
    db_id,
    file_id,
    filename AS file_name,
    original_filename AS original_file_name,
    file_type,
    status
FROM public.knowledge_files
WHERE db_id = :'db_id' AND is_folder IS NOT TRUE;

REVOKE ALL ON mcp_kb.databases, mcp_kb.documents FROM PUBLIC;
GRANT USAGE ON SCHEMA mcp_kb TO :"reader_role";
GRANT SELECT ON mcp_kb.databases, mcp_kb.documents TO :"reader_role";

COMMIT;
