-- Habilitar Row Level Security en las tablas principales de Nexora

ALTER TABLE clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agendamientos ENABLE ROW LEVEL SECURITY;
ALTER TABLE tareas ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;

-- Crear una función para obtener el tenant_id actual del contexto de la sesión
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS text AS $$
  SELECT current_setting('app.current_tenant', true);
$$ LANGUAGE sql STABLE;

-- Políticas para Clientes
CREATE POLICY tenant_isolation_clientes ON clientes
    FOR ALL
    USING (tenant_id = current_tenant_id());

-- Políticas para Agendamientos
CREATE POLICY tenant_isolation_agendamientos ON agendamientos
    FOR ALL
    USING (tenant_id = current_tenant_id());

-- Políticas para Tareas
CREATE POLICY tenant_isolation_tareas ON tareas
    FOR ALL
    USING (tenant_id = current_tenant_id());

-- Políticas para Usuarios
CREATE POLICY tenant_isolation_usuarios ON usuarios
    FOR ALL
    USING (tenant_id = current_tenant_id());

/*
NOTA PARA EL BACKEND (FastAPI):
Antes de ejecutar queries en SQLAlchemy, se debe ejecutar:
db.execute(text(f"SET LOCAL app.current_tenant = '{user.tenant_id}'"))
Para que Postgres sepa qué tenant está haciendo la consulta.
*/
