-- =============================================================================
-- AgriEnergy Orchestrator — Marketplace Registration
-- =============================================================================
-- Run once per environment to register this module in marketplace_modules.
-- Tenants then activate it via the UI (tenant_installed_modules).
-- =============================================================================

INSERT INTO marketplace_modules (
    id,
    name,
    display_name,
    description,
    remote_entry_url,
    version,
    author,
    category,
    route_path,
    label,
    module_type,
    required_plan_type,
    pricing_tier,
    is_local,
    is_active,
    required_roles,
    metadata
) VALUES (
    'agrienergy',
    'agrienergy',
    'AgriEnergy Orchestrator',
    'Agrivoltaic orchestration: PV simulation, shadow geometry, JSON Logic algorithms, NGSI-LD closed-loop, optional Intelligence and N8N.',
    '/modules/agrienergy/nkz-module.js',
    '1.0.0',
    'k8-benetis',
    'analytics',
    '//agrienergy',
    'AgriEnergy Orchestrator',
    'ADDON_FREE',
    'basic',
    'FREE',
    false,
    true,
    ARRAY['Farmer', 'TenantAdmin', 'PlatformAdmin'],
    '{"icon": "🔧", "color": "#3B82F6"}'::jsonb
) ON CONFLICT (id) DO UPDATE SET
    display_name   = EXCLUDED.display_name,
    description    = EXCLUDED.description,
    remote_entry_url = EXCLUDED.remote_entry_url,
    is_active      = true,
    updated_at     = NOW();
