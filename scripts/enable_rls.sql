-- DEPRECATED: este archivo NO habilita RLS ni debe ejecutarse como mecanismo
-- de seguridad. El antiguo borrador cubría solo cuatro tablas, no configuraba
-- el contexto por solicitud y podía crear una falsa sensación de aislamiento.
-- La app autentica mediante JWT propio y SQLAlchemy; todavía no integra
-- Supabase Auth ni establece app.current_tenant en cada transacción.
--
-- Ejecuta esta consulta de solo lectura desde Supabase SQL Editor para revisar
-- qué tablas con tenant_id tienen RLS y políticas. No muestra datos de clientes.

SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_rls,
    COALESCE(
        array_agg(p.polname ORDER BY p.polname)
            FILTER (WHERE p.polname IS NOT NULL),
        ARRAY[]::name[]
    ) AS policies
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN information_schema.columns AS col
  ON col.table_schema = n.nspname
 AND col.table_name = c.relname
 AND col.column_name = 'tenant_id'
LEFT JOIN pg_policy AS p ON p.polrelid = c.oid
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
ORDER BY n.nspname, c.relname;
