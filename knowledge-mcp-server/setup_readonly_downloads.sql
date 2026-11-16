\set ON_ERROR_STOP on

BEGIN;

SELECT has_table_privilege(:'reader_role', 'mcp_kb.documents', 'SELECT') AS catalog_reader \gset
\if :catalog_reader
\else
DO $$ BEGIN RAISE EXCEPTION 'The download reader must already have SELECT on mcp_kb.documents'; END $$;
\endif

CREATE OR REPLACE VIEW mcp_kb.document_downloads WITH (security_barrier = true) AS
SELECT documents.db_id,
       documents.file_id,
       documents.file_name,
       documents.file_type,
       CASE
           WHEN lower(coalesce(documents.file_type, '')) <> 'url'
            AND locator.parts[1] = 'ref-' || replace(left(documents.db_id, 32), '_', '-')
            AND locator.parts[2] !~* '[?&](x-amz-(credential|signature|security-token)|awsaccesskeyid|signature|x-goog-(credential|signature))='
           THEN ('minio://' || locator.parts[1] || '/' || locator.parts[2])::varchar
       END AS storage_path
FROM mcp_kb.documents AS documents
JOIN public.knowledge_files AS files USING (db_id, file_id)
CROSS JOIN LATERAL (
    SELECT regexp_match(files.path, '^(?:(?:minio|s3)://|https?://[^/?#@]+/)([^/?#@]+)/(.+)$', 'i') AS parts
) AS locator;

REVOKE ALL ON mcp_kb.document_downloads FROM PUBLIC;
GRANT SELECT ON mcp_kb.document_downloads TO :"reader_role";

COMMIT;
