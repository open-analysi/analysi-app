-- =============================================================================
-- Baseline schema (collapsed from V001..V123)
-- =============================================================================
-- This migration represents the full DDL of the Analysi schema as of the
-- open-source release baseline. It supersedes the prior V001..V123 migration
-- chain. All subsequent changes should be new migrations starting at V002.
--
-- Generated via pg_dump --schema-only against a DB that had V001..V123 applied,
-- then:
--   - stripped pg_dump session SET directives (flyway manages its own session)
--   - excluded flyway_schema_history, runtime partitions (_pYYYYMMDD), default
--     partitions (_default), and the partman.template_public_* tables
--   - appended explicit partman.create_parent() + retention + pg_cron setup,
--     since runtime state is not captured by pg_dump --schema-only
--
-- Idempotency: every partman registration + pg_cron schedule uses IF NOT EXISTS
-- guards so `flyway repair` / re-runs behave correctly.
-- =============================================================================

-- pg_partman extension requires its schema to exist first.
CREATE SCHEMA IF NOT EXISTS partman;

--
--




--


--
-- Name: pg_partman; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_partman WITH SCHEMA partman;


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: component_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.component_kind AS ENUM (
    'ku',
    'task',
    'module'
);


--
-- Name: component_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.component_status AS ENUM (
    'enabled',
    'disabled',
    'deprecated'
);


--
-- Name: content_review_pipeline_mode; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.content_review_pipeline_mode AS ENUM (
    'review',
    'review_transform'
);


--
-- Name: content_review_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.content_review_status AS ENUM (
    'pending',
    'approved',
    'flagged',
    'applied',
    'rejected',
    'failed'
);


--
-- Name: extraction_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.extraction_status AS ENUM (
    'pending',
    'completed',
    'rejected',
    'applied',
    'failed'
);


--
-- Name: index_build_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.index_build_status AS ENUM (
    'pending',
    'building',
    'completed',
    'failed',
    'outdated'
);


--
-- Name: kdg_relationship_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.kdg_relationship_type AS ENUM (
    'uses',
    'generates',
    'updates',
    'calls',
    'transforms_into',
    'summarizes_into',
    'indexes_into',
    'derived_from',
    'enriches',
    'contains',
    'includes',
    'depends_on',
    'references',
    'staged_for',
    'feedback_for'
);


--
-- Name: ku_index_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.ku_index_type AS ENUM (
    'vector',
    'fulltext',
    'hybrid'
);


--
-- Name: ku_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.ku_type AS ENUM (
    'table',
    'document',
    'tool',
    'index'
);


--
-- Name: module_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.module_type AS ENUM (
    'skill'
);


--
-- Name: check_node_instance_status(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_node_instance_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.status NOT IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'paused') THEN
        RAISE EXCEPTION 'Invalid node instance status: %', NEW.status;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: check_workflow_run_status(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_workflow_run_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.status NOT IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'paused') THEN
        RAISE EXCEPTION 'Invalid workflow run status: %', NEW.status;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: create_control_events_partition(date); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.create_control_events_partition(partition_date date) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
    partition_name TEXT;
    start_date     TEXT;
    end_date       TEXT;
BEGIN
    partition_name := 'control_events_' || TO_CHAR(partition_date, 'YYYY_MM');
    start_date     := DATE_TRUNC('month', partition_date)::DATE::TEXT;
    end_date       := (DATE_TRUNC('month', partition_date) + INTERVAL '1 month')::DATE::TEXT;

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF control_events
         FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );

    RETURN partition_name;
END;
$$;


-- (Dropped legacy function create_integration_runs_partition — referenced
-- the integration_runs table which V121 removed. pg_dump captured the dead
-- function because the table drop doesn't cascade through a function body
-- that resolves its table reference via dynamic SQL. Excluded from baseline.)


--
-- Name: create_task(character varying, character varying, text, text, text, character varying, character varying, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.create_task(p_tenant_id character varying, p_name character varying, p_description text, p_script text, p_directive text DEFAULT NULL::text, p_function character varying DEFAULT NULL::character varying, p_scope character varying DEFAULT 'user'::character varying, p_llm_config jsonb DEFAULT '{}'::jsonb) RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_component_id UUID;
    v_task_id UUID;
BEGIN
    INSERT INTO components (tenant_id, kind, name, description, authored_by)
    VALUES (p_tenant_id, 'task', p_name, p_description, 'system')
    RETURNING id INTO v_component_id;

    INSERT INTO tasks (component_id, script, directive, function, scope, llm_config)
    VALUES (v_component_id, p_script, p_directive, p_function, p_scope, p_llm_config)
    RETURNING id INTO v_task_id;

    RETURN v_component_id;
END;
$$;


--
-- Name: create_task_runs_partition(date); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.create_task_runs_partition(partition_date date) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
    partition_name TEXT;
    start_date TEXT;
    end_date TEXT;
BEGIN
    partition_name := 'task_runs_' || TO_CHAR(partition_date, 'YYYY_MM_DD');
    start_date := partition_date::TEXT;
    end_date := (partition_date + INTERVAL '1 day')::DATE::TEXT;

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I PARTITION OF task_runs
        FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date);

    RETURN partition_name;
END;
$$;


--
-- Name: generic_update_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.generic_update_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: get_and_increment_alert_id(character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_and_increment_alert_id(p_tenant_id character varying) RETURNS character varying
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_counter INTEGER;
    v_next_id VARCHAR;
BEGIN
    -- Insert or update the counter atomically
    INSERT INTO alert_id_counters (tenant_id, counter, updated_at)
    VALUES (p_tenant_id, 1, NOW())
    ON CONFLICT (tenant_id)
    DO UPDATE SET
        counter = alert_id_counters.counter + 1,
        updated_at = NOW()
    RETURNING counter INTO v_counter;

    -- Generate the ID
    v_next_id := 'AID-' || v_counter;

    RETURN v_next_id;
END;
$$;


--
-- Name: update_checkpoints_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_checkpoints_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_integration_runs_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_integration_runs_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_integration_schedules_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_integration_schedules_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_integrations_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_integrations_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_schedules_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_schedules_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_task_runs_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_task_runs_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_workflow_timestamp(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_workflow_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

--
-- Name: activity_audit_trails; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity_audit_trails (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    tenant_id character varying(255) NOT NULL,
    actor_type character varying(50) DEFAULT 'user'::character varying NOT NULL,
    action character varying(100) NOT NULL,
    resource_type character varying(100),
    resource_id character varying(255),
    details jsonb,
    ip_address character varying(45),
    user_agent text,
    request_id character varying(100),
    source character varying(50) DEFAULT 'unknown'::character varying,
    actor_id uuid DEFAULT '00000000-0000-0000-0000-000000000001'::uuid NOT NULL,
    CONSTRAINT activity_audit_trail_actor_type_check CHECK (((actor_type)::text = ANY ((ARRAY['user'::character varying, 'system'::character varying, 'api_key'::character varying, 'workflow'::character varying, 'external_user'::character varying])::text[])))
)
PARTITION BY RANGE (created_at);


--
-- Name: alert_analyses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_analyses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    alert_id uuid NOT NULL,
    tenant_id character varying(255) NOT NULL,
    status character varying DEFAULT 'pending'::character varying,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    current_step text,
    steps_progress jsonb DEFAULT '{}'::jsonb,
    disposition_id uuid,
    confidence integer,
    short_summary text,
    long_summary text,
    workflow_id uuid,
    workflow_run_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    error_message text,
    workflow_gen_retry_count integer DEFAULT 0,
    workflow_gen_last_failure_at timestamp with time zone,
    job_tracking jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT chk_analysis_status CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'paused'::character varying, 'paused_human_review'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[])))
)
PARTITION BY RANGE (created_at);


SET default_table_access_method = heap;

--
-- Name: alert_id_counters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_id_counters (
    tenant_id character varying(255) NOT NULL,
    counter integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: alert_routing_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_routing_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    analysis_group_id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    triggering_event_time timestamp with time zone NOT NULL,
    tenant_id character varying(255) NOT NULL,
    human_readable_id character varying(50) NOT NULL,
    title text NOT NULL,
    source_vendor character varying(255),
    source_product character varying(255),
    rule_name text,
    severity character varying(20) NOT NULL,
    detected_at timestamp with time zone,
    raw_data text NOT NULL,
    current_analysis_id uuid,
    analysis_status character varying DEFAULT 'not_analyzed'::character varying,
    current_disposition_category character varying,
    current_disposition_subcategory character varying,
    current_disposition_display_name character varying,
    current_disposition_confidence integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    source_event_id character varying(500),
    finding_info jsonb DEFAULT '{}'::jsonb NOT NULL,
    ocsf_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    evidences jsonb,
    observables jsonb,
    osint jsonb,
    actor jsonb,
    device jsonb,
    cloud jsonb,
    vulnerabilities jsonb,
    unmapped jsonb,
    severity_id smallint DEFAULT 3 NOT NULL,
    disposition_id smallint,
    verdict_id smallint,
    action_id smallint,
    status_id smallint DEFAULT 1 NOT NULL,
    confidence_id smallint,
    risk_level_id smallint,
    ocsf_time bigint,
    raw_data_hash text DEFAULT ''::text NOT NULL,
    raw_data_hash_algorithm character varying(10) DEFAULT 'SHA-256'::character varying NOT NULL,
    CONSTRAINT chk_alerts_analysis_status CHECK (((analysis_status)::text = ANY ((ARRAY['new'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[]))),
    CONSTRAINT chk_alerts_severity CHECK (((severity)::text = ANY ((ARRAY['critical'::character varying, 'high'::character varying, 'medium'::character varying, 'low'::character varying, 'info'::character varying])::text[])))
)
PARTITION BY RANGE (ingested_at);


--
-- Name: analysis_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_groups (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    title character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    user_id uuid,
    name character varying(255) NOT NULL,
    key_hash character varying(64) NOT NULL,
    key_prefix character varying(16) NOT NULL,
    scopes jsonb DEFAULT '[]'::jsonb NOT NULL,
    last_used_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: artifacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artifacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    name text NOT NULL,
    artifact_type text,
    mime_type text NOT NULL,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    sha256 bytea NOT NULL,
    md5 bytea,
    size_bytes bigint NOT NULL,
    storage_class text NOT NULL,
    inline_content bytea,
    bucket text,
    object_key text,
    task_run_id uuid,
    workflow_run_id uuid,
    workflow_node_instance_id uuid,
    analysis_id uuid,
    alert_id uuid,
    integration_id character varying(255),
    source character varying(50) DEFAULT 'unknown'::character varying NOT NULL,
    content_encoding text,
    deleted_at timestamp with time zone,
    CONSTRAINT artifacts_inline_storage_check CHECK ((((storage_class = 'inline'::text) AND (inline_content IS NOT NULL) AND (bucket IS NULL) AND (object_key IS NULL)) OR ((storage_class = 'object'::text) AND (inline_content IS NULL) AND (bucket IS NOT NULL) AND (object_key IS NOT NULL)))),
    CONSTRAINT artifacts_relationship_check CHECK (((alert_id IS NOT NULL) OR (task_run_id IS NOT NULL) OR (workflow_run_id IS NOT NULL) OR (workflow_node_instance_id IS NOT NULL) OR (analysis_id IS NOT NULL))),
    CONSTRAINT artifacts_source_check CHECK (((source)::text = ANY ((ARRAY['auto_capture'::character varying, 'cy_script'::character varying, 'rest_api'::character varying, 'mcp'::character varying, 'unknown'::character varying])::text[]))),
    CONSTRAINT artifacts_storage_class_check CHECK ((storage_class = ANY (ARRAY['inline'::text, 'object'::text])))
)
PARTITION BY RANGE (created_at);


--
-- Name: chat_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_conversations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    user_id uuid NOT NULL,
    title text,
    page_context jsonb,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    token_count_total integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: chat_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    conversation_id uuid NOT NULL,
    tenant_id character varying(255) NOT NULL,
    role text NOT NULL,
    content jsonb NOT NULL,
    tool_calls jsonb,
    token_count integer,
    model text,
    latency_ms integer,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chat_messages_role_check CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text, 'system'::text, 'tool'::text])))
)
PARTITION BY RANGE (created_at);


--
-- Name: checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.checkpoints (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    owner_id uuid NOT NULL,
    key character varying(255) NOT NULL,
    value jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    owner_type character varying(20) DEFAULT 'task'::character varying NOT NULL
);


--
-- Name: component_graph_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.component_graph_edges (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    source_id uuid NOT NULL,
    target_id uuid NOT NULL,
    relationship_type public.kdg_relationship_type NOT NULL,
    execution_order integer DEFAULT 0,
    is_required boolean DEFAULT false NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chk_kdg_edge_different_components CHECK ((source_id <> target_id))
);


--
-- Name: components; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.components (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    kind public.component_kind NOT NULL,
    name character varying(255) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    version character varying(50) DEFAULT '1.0.0'::character varying NOT NULL,
    status public.component_status DEFAULT 'enabled'::public.component_status NOT NULL,
    visible boolean DEFAULT false NOT NULL,
    system_only boolean DEFAULT false NOT NULL,
    app character varying(100) DEFAULT 'default'::character varying NOT NULL,
    categories text[] DEFAULT '{}'::text[],
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_used_at timestamp with time zone,
    ku_type character varying(50),
    cy_name character varying(255),
    namespace character varying(512) DEFAULT '/'::character varying NOT NULL,
    created_by uuid DEFAULT '00000000-0000-0000-0000-000000000001'::uuid NOT NULL,
    updated_by uuid,
    CONSTRAINT chk_cy_name_format CHECK ((((cy_name)::text ~ '^[a-zA-Z_][a-zA-Z0-9_]*$'::text) OR (cy_name IS NULL)))
);


--
-- Name: content_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_reviews (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    skill_id uuid NOT NULL,
    pipeline_name character varying(50) NOT NULL,
    pipeline_mode public.content_review_pipeline_mode NOT NULL,
    trigger_source character varying(50) NOT NULL,
    document_id uuid,
    original_filename character varying(500),
    sync_checks_passed boolean DEFAULT false NOT NULL,
    sync_checks_result jsonb,
    pipeline_result jsonb,
    transformed_content text,
    summary text,
    status public.content_review_status DEFAULT 'pending'::public.content_review_status NOT NULL,
    applied_document_id uuid,
    rejection_reason text,
    actor_user_id uuid,
    error_message text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp with time zone,
    applied_at timestamp with time zone,
    bypassed boolean DEFAULT false NOT NULL,
    original_content text,
    error_code character varying(100),
    error_detail jsonb,
    job_tracking jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: control_event_dispatches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.control_event_dispatches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    control_event_id uuid NOT NULL,
    rule_id uuid NOT NULL,
    status character varying(50) DEFAULT 'running'::character varying NOT NULL,
    attempt_number integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT control_event_dispatches_status_check CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: control_event_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.control_event_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    channel character varying(100) NOT NULL,
    target_type character varying(20) NOT NULL,
    target_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT control_event_rules_target_type_check CHECK (((target_type)::text = ANY ((ARRAY['task'::character varying, 'workflow'::character varying])::text[])))
);


--
-- Name: control_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.control_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    tenant_id character varying(255) NOT NULL,
    channel character varying(100) NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    retry_count integer DEFAULT 0 NOT NULL,
    claimed_at timestamp with time zone,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    job_tracking jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT control_events_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'claimed'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
)
PARTITION BY RANGE (created_at);


--
-- Name: credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credentials (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    provider character varying(255) NOT NULL,
    account character varying(255) NOT NULL,
    ciphertext text NOT NULL,
    credential_metadata jsonb,
    key_name character varying(255) DEFAULT 'tenant-default'::character varying NOT NULL,
    key_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by uuid
);


--
-- Name: dispositions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dispositions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    category text NOT NULL,
    subcategory text NOT NULL,
    display_name text NOT NULL,
    color_hex text NOT NULL,
    color_name text NOT NULL,
    priority_score integer NOT NULL,
    description text,
    requires_escalation boolean DEFAULT false,
    is_system boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT dispositions_priority_score_check CHECK (((priority_score >= 1) AND (priority_score <= 10)))
);


--
-- Name: flyway_test_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.flyway_test_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: hitl_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hitl_questions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    tenant_id character varying(255) NOT NULL,
    question_ref character varying(255) NOT NULL,
    channel character varying(255) NOT NULL,
    question_text text NOT NULL,
    options jsonb DEFAULT '[]'::jsonb NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    answer character varying(500),
    answered_by character varying(255),
    answered_at timestamp with time zone,
    timeout_at timestamp with time zone NOT NULL,
    task_run_id uuid NOT NULL,
    workflow_run_id uuid,
    node_instance_id uuid,
    analysis_id uuid,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
)
PARTITION BY RANGE (created_at);


--
-- Name: index_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.index_entries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    collection_id uuid NOT NULL,
    tenant_id character varying(255) NOT NULL,
    content text NOT NULL,
    embedding public.vector(1536),
    metadata jsonb DEFAULT '{}'::jsonb,
    source_ref text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    content_hash character varying(64) NOT NULL
);


--
-- Name: integration_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.integration_credentials (
    tenant_id character varying(255) NOT NULL,
    integration_id character varying(255) NOT NULL,
    credential_id uuid NOT NULL,
    is_primary boolean DEFAULT false NOT NULL,
    purpose character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT integration_credentials_purpose_check CHECK ((((purpose)::text = ANY ((ARRAY['read'::character varying, 'write'::character varying, 'admin'::character varying])::text[])) OR (purpose IS NULL)))
);


--
-- Name: integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.integrations (
    integration_id character varying(255) NOT NULL,
    tenant_id character varying(255) NOT NULL,
    integration_type character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    enabled boolean DEFAULT true,
    settings jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    health_status character varying(50),
    last_health_check_at timestamp with time zone
);


--
-- Name: invitations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invitations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    role character varying(50) NOT NULL,
    token_hash character varying(64) NOT NULL,
    invited_by uuid,
    expires_at timestamp with time zone DEFAULT (now() + '7 days'::interval) NOT NULL,
    accepted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: job_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    tenant_id character varying(255) NOT NULL,
    schedule_id uuid,
    target_type character varying(20) NOT NULL,
    target_id uuid NOT NULL,
    task_run_id uuid,
    workflow_run_id uuid,
    integration_id character varying(255),
    action_id character varying(100),
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    triggered_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    job_tracking jsonb DEFAULT '{}'::jsonb NOT NULL
)
PARTITION BY RANGE (created_at);


--
-- Name: kdg_graph_view; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.kdg_graph_view AS
 SELECT e.id,
    e.tenant_id,
    e.source_id,
    sc.name AS source_name,
    sc.kind AS source_kind,
    e.target_id,
    tc.name AS target_name,
    tc.kind AS target_kind,
    e.relationship_type,
    e.execution_order,
    e.is_required,
    e.metadata,
    e.created_at,
    e.updated_at
   FROM ((public.component_graph_edges e
     JOIN public.components sc ON ((e.source_id = sc.id)))
     JOIN public.components tc ON ((e.target_id = tc.id)));


--
-- Name: knowledge_extractions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_extractions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    skill_id uuid NOT NULL,
    document_id uuid NOT NULL,
    status public.extraction_status DEFAULT 'pending'::public.extraction_status NOT NULL,
    classification jsonb,
    relevance jsonb,
    placement jsonb,
    transformed_content text,
    merge_info jsonb,
    validation jsonb,
    applied_document_id uuid,
    rejection_reason text,
    error_message text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    applied_at timestamp with time zone,
    rejected_at timestamp with time zone,
    extraction_summary text,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: knowledge_modules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_modules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    component_id uuid NOT NULL,
    module_type public.module_type DEFAULT 'skill'::public.module_type NOT NULL,
    root_document_path character varying(255) DEFAULT 'SKILL.md'::character varying,
    config jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: knowledge_units; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_units (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    component_id uuid NOT NULL,
    ku_type public.ku_type NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ku_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ku_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    component_id uuid NOT NULL,
    doc_format character varying(50) DEFAULT 'raw'::character varying,
    content text,
    file_path text,
    markdown_content text,
    document_type character varying(50),
    content_source character varying(50),
    source_url text,
    metadata jsonb DEFAULT '{}'::jsonb,
    word_count integer DEFAULT 0,
    character_count integer DEFAULT 0,
    page_count integer DEFAULT 0,
    language character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ku_document_view; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.ku_document_view AS
 SELECT c.id,
    c.tenant_id,
    c.kind,
    c.name,
    c.description,
    c.version,
    c.status,
    c.visible,
    c.system_only,
    c.app,
    c.categories,
    c.created_at,
    c.updated_at,
    c.last_used_at,
    c.ku_type,
    c.cy_name,
    c.namespace,
    c.created_by,
    c.updated_by,
    kd.content,
    kd.doc_format
   FROM ((public.components c
     JOIN public.knowledge_units ku ON ((c.id = ku.component_id)))
     JOIN public.ku_documents kd ON ((c.id = kd.component_id)))
  WHERE ((c.kind = 'ku'::public.component_kind) AND (ku.ku_type = 'document'::public.ku_type));


--
-- Name: ku_indexes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ku_indexes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    component_id uuid NOT NULL,
    index_type public.ku_index_type DEFAULT 'vector'::public.ku_index_type NOT NULL,
    vector_database character varying(100),
    embedding_model character varying(255),
    chunking_config jsonb DEFAULT '{}'::jsonb,
    build_status public.index_build_status DEFAULT 'pending'::public.index_build_status NOT NULL,
    build_started_at timestamp with time zone,
    build_completed_at timestamp with time zone,
    build_error_message text,
    index_stats jsonb DEFAULT '{}'::jsonb,
    last_sync_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    embedding_dimensions integer,
    backend_type character varying(50) DEFAULT 'pgvector'::character varying
);


--
-- Name: ku_tables; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ku_tables (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    component_id uuid NOT NULL,
    schema jsonb DEFAULT '{}'::jsonb,
    row_count integer DEFAULT 0,
    column_count integer DEFAULT 0,
    content jsonb DEFAULT '{}'::jsonb,
    file_path text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ku_table_view; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.ku_table_view AS
 SELECT c.id,
    c.tenant_id,
    c.kind,
    c.name,
    c.description,
    c.version,
    c.status,
    c.visible,
    c.system_only,
    c.app,
    c.categories,
    c.created_at,
    c.updated_at,
    c.last_used_at,
    c.ku_type,
    c.cy_name,
    c.namespace,
    c.created_by,
    c.updated_by,
    kt.content,
    kt.row_count,
    kt.column_count,
    kt.schema
   FROM ((public.components c
     JOIN public.knowledge_units ku ON ((c.id = ku.component_id)))
     JOIN public.ku_tables kt ON ((c.id = kt.component_id)))
  WHERE ((c.kind = 'ku'::public.component_kind) AND (ku.ku_type = 'table'::public.ku_type));


--
-- Name: ku_tools; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ku_tools (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    component_id uuid NOT NULL,
    tool_type character varying(50) NOT NULL,
    mcp_endpoint text,
    mcp_server_config jsonb DEFAULT '{}'::jsonb,
    input_schema jsonb DEFAULT '{}'::jsonb,
    output_schema jsonb DEFAULT '{}'::jsonb,
    auth_type character varying(50) DEFAULT 'none'::character varying,
    credentials_ref text,
    timeout_ms integer DEFAULT 30000,
    rate_limit integer DEFAULT 100,
    integration_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ku_tool_auth_type_check CHECK (((auth_type)::text = ANY ((ARRAY['none'::character varying, 'api_key'::character varying, 'oauth'::character varying, 'basic'::character varying])::text[]))),
    CONSTRAINT ku_tool_tool_type_check CHECK (((tool_type)::text = ANY ((ARRAY['mcp'::character varying, 'native'::character varying, 'app'::character varying])::text[])))
);


--
-- Name: memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memberships (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    tenant_id character varying(255) NOT NULL,
    role character varying(50) NOT NULL,
    invited_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT memberships_role_check CHECK (((role)::text = ANY ((ARRAY['owner'::character varying, 'admin'::character varying, 'analyst'::character varying, 'viewer'::character varying])::text[])))
);


--
-- Name: node_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_templates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    resource_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    input_schema jsonb NOT NULL,
    output_schema jsonb NOT NULL,
    code text NOT NULL,
    language text DEFAULT 'python'::text NOT NULL,
    type text DEFAULT 'static'::text NOT NULL,
    enabled boolean DEFAULT true,
    revision_num integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    kind text NOT NULL,
    tenant_id character varying(255),
    CONSTRAINT node_templates_kind_check CHECK ((kind = ANY (ARRAY['identity'::text, 'merge'::text, 'collect'::text, 'projection'::text, 'branching'::text]))),
    CONSTRAINT node_templates_schemas_valid CHECK (((jsonb_typeof(input_schema) = 'object'::text) AND (jsonb_typeof(output_schema) = 'object'::text))),
    CONSTRAINT node_templates_type_check CHECK ((type = ANY (ARRAY['static'::text, 'dynamic'::text])))
);


--
-- Name: schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schedules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    target_type character varying(20) NOT NULL,
    target_id uuid NOT NULL,
    schedule_type character varying(20) NOT NULL,
    schedule_value character varying(100) NOT NULL,
    timezone character varying(50) DEFAULT 'UTC'::character varying NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    params jsonb,
    origin_type character varying(20) DEFAULT 'user'::character varying NOT NULL,
    integration_id character varying(255),
    next_run_at timestamp with time zone,
    last_run_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: task_generations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_generations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    workflow_generation_id uuid,
    status character varying(50) DEFAULT 'new'::character varying NOT NULL,
    input_context jsonb NOT NULL,
    result jsonb,
    progress_messages jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    source character varying(50) DEFAULT 'workflow_generation'::character varying NOT NULL,
    description text,
    alert_id uuid,
    created_by uuid DEFAULT '00000000-0000-0000-0000-000000000001'::uuid NOT NULL,
    job_tracking jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: task_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    task_id uuid,
    cy_script text,
    status character varying(50) DEFAULT 'running'::character varying NOT NULL,
    duration interval,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    input_type character varying(20),
    input_location text,
    input_content_type character varying(100),
    output_type character varying(20),
    output_location text,
    output_content_type character varying(100),
    executor_config jsonb,
    execution_context jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    workflow_run_id uuid,
    workflow_node_instance_id uuid,
    job_tracking jsonb DEFAULT '{}'::jsonb NOT NULL,
    run_context character varying(20) DEFAULT 'ad_hoc'::character varying NOT NULL,
    CONSTRAINT task_runs_input_type_check CHECK (((input_type)::text = ANY ((ARRAY['inline'::character varying, 's3'::character varying, 'file'::character varying])::text[]))),
    CONSTRAINT task_runs_output_type_check CHECK (((output_type)::text = ANY ((ARRAY['inline'::character varying, 's3'::character varying, 'file'::character varying])::text[]))),
    CONSTRAINT task_runs_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'completed'::character varying, 'failed'::character varying, 'paused'::character varying, 'paused_by_user'::character varying, 'cancelled'::character varying])::text[])))
)
PARTITION BY RANGE (created_at);


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    component_id uuid NOT NULL,
    directive text,
    script text,
    function character varying(255),
    scope character varying(100) DEFAULT 'processing'::character varying,
    schedule character varying(255),
    mode character varying(50) DEFAULT 'saved'::character varying NOT NULL,
    llm_config jsonb DEFAULT '{}'::jsonb,
    last_run_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    data_samples jsonb,
    integration_id character varying(255),
    origin_type character varying(20) DEFAULT 'user'::character varying NOT NULL,
    managed_resource_key character varying(50),
    CONSTRAINT task_mode_check CHECK (((mode)::text = ANY ((ARRAY['ad_hoc'::character varying, 'saved'::character varying])::text[]))),
    CONSTRAINT task_scope_check CHECK (((scope)::text = ANY ((ARRAY['input'::character varying, 'processing'::character varying, 'output'::character varying])::text[])))
);


--
-- Name: task_runs_with_task_info; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.task_runs_with_task_info AS
 SELECT tr.id,
    tr.tenant_id,
    tr.task_id,
    tr.cy_script,
    tr.status,
    tr.duration,
    tr.started_at,
    tr.completed_at,
    tr.input_type,
    tr.input_location,
    tr.input_content_type,
    tr.output_type,
    tr.output_location,
    tr.output_content_type,
    tr.executor_config,
    tr.execution_context,
    tr.created_at,
    tr.updated_at,
    c.name AS task_name,
    c.description AS task_description,
    t.function AS task_function,
    t.scope AS task_scope
   FROM ((public.task_runs tr
     LEFT JOIN public.tasks t ON ((tr.task_id = t.component_id)))
     LEFT JOIN public.components c ON ((t.component_id = c.id)));


--
-- Name: task_view; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.task_view AS
 SELECT c.id,
    c.tenant_id,
    c.kind,
    c.name,
    c.description,
    c.version,
    c.status,
    c.visible,
    c.system_only,
    c.app,
    c.categories,
    c.created_at,
    c.updated_at,
    c.last_used_at,
    c.ku_type,
    c.cy_name,
    c.namespace,
    c.created_by,
    c.updated_by,
    t.script,
    t.directive,
    t.function,
    t.scope,
    t.llm_config,
    t.data_samples
   FROM (public.components c
     JOIN public.tasks t ON ((c.id = t.component_id)))
  WHERE (c.kind = 'task'::public.component_kind);


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    id character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    status character varying(50) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    keycloak_id character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    display_name character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone
);


--
-- Name: workflow_edge_instances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_edge_instances (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    workflow_run_id uuid NOT NULL,
    edge_id text NOT NULL,
    edge_uuid uuid NOT NULL,
    from_instance_id uuid NOT NULL,
    to_instance_id uuid NOT NULL,
    delivered_at timestamp with time zone
)
PARTITION BY RANGE (created_at);


--
-- Name: workflow_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_edges (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workflow_id uuid NOT NULL,
    edge_id text NOT NULL,
    from_node_uuid uuid NOT NULL,
    to_node_uuid uuid NOT NULL,
    alias text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: workflow_node_instances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_node_instances (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    workflow_run_id uuid NOT NULL,
    node_id text NOT NULL,
    node_uuid uuid NOT NULL,
    task_run_id uuid,
    parent_instance_id uuid,
    loop_context jsonb,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    input_type character varying(20),
    input_location text,
    output_type character varying(20),
    output_location text,
    template_id uuid,
    error_message text,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
)
PARTITION BY RANGE (created_at);


--
-- Name: workflow_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_runs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    tenant_id character varying(255) NOT NULL,
    workflow_id uuid,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    input_type character varying(20),
    input_location text,
    output_type character varying(20),
    output_location text,
    error_message text,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    execution_context jsonb,
    job_tracking jsonb DEFAULT '{}'::jsonb NOT NULL
)
PARTITION BY RANGE (created_at);


--
-- Name: workflow_execution_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.workflow_execution_summary AS
 SELECT wr.id AS workflow_run_id,
    wr.tenant_id,
    wr.workflow_id,
    wr.status AS workflow_status,
    wr.created_at,
    wr.started_at,
    wr.completed_at AS ended_at,
    wr.updated_at,
    count(wni.id) AS total_nodes,
    count(
        CASE
            WHEN ((wni.status)::text = 'completed'::text) THEN 1
            ELSE NULL::integer
        END) AS completed_nodes,
    count(
        CASE
            WHEN ((wni.status)::text = 'failed'::text) THEN 1
            ELSE NULL::integer
        END) AS failed_nodes,
    count(
        CASE
            WHEN ((wni.status)::text = 'running'::text) THEN 1
            ELSE NULL::integer
        END) AS running_nodes,
    count(
        CASE
            WHEN ((wni.status)::text = 'pending'::text) THEN 1
            ELSE NULL::integer
        END) AS pending_nodes
   FROM (public.workflow_runs wr
     LEFT JOIN public.workflow_node_instances wni ON ((wr.id = wni.workflow_run_id)))
  GROUP BY wr.id, wr.tenant_id, wr.workflow_id, wr.status, wr.created_at, wr.started_at, wr.completed_at, wr.updated_at;


--
-- Name: workflow_generations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_generations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    analysis_group_id uuid NOT NULL,
    workflow_id uuid,
    status character varying(50) DEFAULT 'running'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp with time zone,
    current_phase jsonb,
    orchestration_results jsonb,
    workspace_path character varying(1024) DEFAULT '/tmp/unknown'::character varying NOT NULL,
    triggering_alert_analysis_id uuid,
    job_tracking jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: workflow_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_nodes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workflow_id uuid NOT NULL,
    node_id text NOT NULL,
    kind text NOT NULL,
    name text NOT NULL,
    task_id uuid,
    node_template_id uuid,
    foreach_config jsonb,
    schemas jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_start_node boolean DEFAULT false NOT NULL,
    CONSTRAINT workflow_nodes_kind_check CHECK ((kind = ANY (ARRAY['task'::text, 'transformation'::text, 'foreach'::text]))),
    CONSTRAINT workflow_nodes_kind_fields CHECK ((((kind = 'task'::text) AND (task_id IS NOT NULL) AND (node_template_id IS NULL) AND (foreach_config IS NULL)) OR ((kind = 'transformation'::text) AND (node_template_id IS NOT NULL) AND (task_id IS NULL) AND (foreach_config IS NULL)) OR ((kind = 'foreach'::text) AND (foreach_config IS NOT NULL) AND (task_id IS NULL) AND (node_template_id IS NULL)))),
    CONSTRAINT workflow_nodes_schemas_valid CHECK ((jsonb_typeof(schemas) = 'object'::text))
);


--
-- Name: workflows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflows (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id character varying(255) NOT NULL,
    name text NOT NULL,
    description text,
    is_dynamic boolean DEFAULT false NOT NULL,
    io_schema jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    planner_id uuid,
    data_samples jsonb,
    status text DEFAULT 'draft'::text NOT NULL,
    is_ephemeral boolean DEFAULT false NOT NULL,
    expires_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by uuid DEFAULT '00000000-0000-0000-0000-000000000001'::uuid NOT NULL,
    app character varying(100) DEFAULT 'default'::character varying NOT NULL,
    CONSTRAINT workflows_io_schema_valid CHECK ((jsonb_typeof(io_schema) = 'object'::text)),
    CONSTRAINT workflows_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'validated'::text, 'invalid'::text])))
);


--
-- Name: activity_audit_trails activity_audit_trail_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_audit_trails
    ADD CONSTRAINT activity_audit_trail_pkey PRIMARY KEY (id, created_at);


--
-- Name: alert_analyses alert_analysis_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_analyses
    ADD CONSTRAINT alert_analysis_pkey PRIMARY KEY (id, created_at);


--
-- Name: alert_id_counters alert_id_counters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_id_counters
    ADD CONSTRAINT alert_id_counters_pkey PRIMARY KEY (tenant_id);


--
-- Name: alert_routing_rules alert_routing_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_routing_rules
    ADD CONSTRAINT alert_routing_rules_pkey PRIMARY KEY (id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id, ingested_at);


--
-- Name: analysis_groups analysis_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_groups
    ADD CONSTRAINT analysis_groups_pkey PRIMARY KEY (id);


--
-- Name: api_keys api_keys_key_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: artifacts artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artifacts
    ADD CONSTRAINT artifacts_pkey PRIMARY KEY (id, created_at);


--
-- Name: chat_messages chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_pkey PRIMARY KEY (id, created_at);


--
-- Name: components component_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.components
    ADD CONSTRAINT component_pkey PRIMARY KEY (id);


--
-- Name: content_reviews content_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_reviews
    ADD CONSTRAINT content_reviews_pkey PRIMARY KEY (id);


--
-- Name: control_event_dispatches control_event_dispatches_control_event_id_rule_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_event_dispatches
    ADD CONSTRAINT control_event_dispatches_control_event_id_rule_id_key UNIQUE (control_event_id, rule_id);


--
-- Name: control_event_dispatches control_event_dispatches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_event_dispatches
    ADD CONSTRAINT control_event_dispatches_pkey PRIMARY KEY (id);


--
-- Name: control_event_rules control_event_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_event_rules
    ADD CONSTRAINT control_event_rules_pkey PRIMARY KEY (id);


--
-- Name: control_events control_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_events
    ADD CONSTRAINT control_events_pkey PRIMARY KEY (id, created_at);


--
-- Name: chat_conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: credentials credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_pkey PRIMARY KEY (id);


--
-- Name: dispositions dispositions_category_subcategory_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dispositions
    ADD CONSTRAINT dispositions_category_subcategory_key UNIQUE (category, subcategory);


--
-- Name: dispositions dispositions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dispositions
    ADD CONSTRAINT dispositions_pkey PRIMARY KEY (id);


--
-- Name: hitl_questions hitl_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hitl_questions
    ADD CONSTRAINT hitl_questions_pkey PRIMARY KEY (id, created_at);


--
-- Name: index_entries index_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.index_entries
    ADD CONSTRAINT index_entries_pkey PRIMARY KEY (id);


--
-- Name: integration_credentials integration_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integration_credentials
    ADD CONSTRAINT integration_credentials_pkey PRIMARY KEY (tenant_id, integration_id, credential_id);


--
-- Name: integrations integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_pkey PRIMARY KEY (tenant_id, integration_id);


--
-- Name: invitations invitations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_pkey PRIMARY KEY (id);


--
-- Name: invitations invitations_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_token_hash_key UNIQUE (token_hash);


--
-- Name: job_runs job_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_runs
    ADD CONSTRAINT job_runs_pkey PRIMARY KEY (id, created_at);


--
-- Name: component_graph_edges kdg_edge_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.component_graph_edges
    ADD CONSTRAINT kdg_edge_pkey PRIMARY KEY (id);


--
-- Name: knowledge_extractions knowledge_extractions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_extractions
    ADD CONSTRAINT knowledge_extractions_pkey PRIMARY KEY (id);


--
-- Name: knowledge_modules knowledge_module_component_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_modules
    ADD CONSTRAINT knowledge_module_component_id_key UNIQUE (component_id);


--
-- Name: knowledge_modules knowledge_module_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_modules
    ADD CONSTRAINT knowledge_module_pkey PRIMARY KEY (id);


--
-- Name: knowledge_units knowledge_unit_component_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_units
    ADD CONSTRAINT knowledge_unit_component_id_key UNIQUE (component_id);


--
-- Name: knowledge_units knowledge_unit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_units
    ADD CONSTRAINT knowledge_unit_pkey PRIMARY KEY (id);


--
-- Name: ku_documents ku_document_component_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_documents
    ADD CONSTRAINT ku_document_component_id_key UNIQUE (component_id);


--
-- Name: ku_documents ku_document_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_documents
    ADD CONSTRAINT ku_document_pkey PRIMARY KEY (id);


--
-- Name: ku_indexes ku_index_component_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_indexes
    ADD CONSTRAINT ku_index_component_id_key UNIQUE (component_id);


--
-- Name: ku_indexes ku_index_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_indexes
    ADD CONSTRAINT ku_index_pkey PRIMARY KEY (id);


--
-- Name: ku_tables ku_table_component_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_tables
    ADD CONSTRAINT ku_table_component_id_key UNIQUE (component_id);


--
-- Name: ku_tables ku_table_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_tables
    ADD CONSTRAINT ku_table_pkey PRIMARY KEY (id);


--
-- Name: ku_tools ku_tool_component_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_tools
    ADD CONSTRAINT ku_tool_component_id_key UNIQUE (component_id);


--
-- Name: ku_tools ku_tool_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_tools
    ADD CONSTRAINT ku_tool_pkey PRIMARY KEY (id);


--
-- Name: memberships memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_pkey PRIMARY KEY (id);


--
-- Name: memberships memberships_user_id_tenant_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_user_id_tenant_id_key UNIQUE (user_id, tenant_id);


--
-- Name: node_templates node_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_templates
    ADD CONSTRAINT node_templates_pkey PRIMARY KEY (id);


--
-- Name: node_templates node_templates_unique_enabled; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_templates
    ADD CONSTRAINT node_templates_unique_enabled UNIQUE (resource_id, enabled) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: schedules schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_pkey PRIMARY KEY (id);


--
-- Name: task_generations task_building_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_generations
    ADD CONSTRAINT task_building_runs_pkey PRIMARY KEY (id);


--
-- Name: checkpoints task_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checkpoints
    ADD CONSTRAINT task_checkpoints_pkey PRIMARY KEY (id);


--
-- Name: tasks task_component_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT task_component_id_key UNIQUE (component_id);


--
-- Name: tasks task_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT task_pkey PRIMARY KEY (id);


--
-- Name: task_runs task_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_runs
    ADD CONSTRAINT task_runs_pkey PRIMARY KEY (id, created_at);


--
-- Name: tenants tenant_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenant_pkey PRIMARY KEY (id);


--
-- Name: credentials uk_credentials_tenant_provider_account; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT uk_credentials_tenant_provider_account UNIQUE (tenant_id, provider, account);


--
-- Name: analysis_groups uq_analysis_groups_tenant_title; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_groups
    ADD CONSTRAINT uq_analysis_groups_tenant_title UNIQUE (tenant_id, title);


--
-- Name: checkpoints uq_checkpoints_tenant_owner_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checkpoints
    ADD CONSTRAINT uq_checkpoints_tenant_owner_key UNIQUE (tenant_id, owner_type, owner_id, key);


--
-- Name: components uq_component_tenant_ns_name_ku_type; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.components
    ADD CONSTRAINT uq_component_tenant_ns_name_ku_type UNIQUE (tenant_id, namespace, name, ku_type);


--
-- Name: component_graph_edges uq_kdg_edge_unique_relationship; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.component_graph_edges
    ADD CONSTRAINT uq_kdg_edge_unique_relationship UNIQUE (tenant_id, source_id, target_id, relationship_type);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_keycloak_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_keycloak_id_key UNIQUE (keycloak_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: workflow_edge_instances workflow_edge_instances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_edge_instances
    ADD CONSTRAINT workflow_edge_instances_pkey PRIMARY KEY (id, created_at);


--
-- Name: workflow_edges workflow_edges_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_pkey PRIMARY KEY (id);


--
-- Name: workflow_edges workflow_edges_unique_edge_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_unique_edge_id UNIQUE (workflow_id, edge_id);


--
-- Name: workflow_generations workflow_generations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_generations
    ADD CONSTRAINT workflow_generations_pkey PRIMARY KEY (id);


--
-- Name: workflow_node_instances workflow_node_instances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_node_instances
    ADD CONSTRAINT workflow_node_instances_pkey PRIMARY KEY (id, created_at);


--
-- Name: workflow_nodes workflow_nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_nodes
    ADD CONSTRAINT workflow_nodes_pkey PRIMARY KEY (id);


--
-- Name: workflow_nodes workflow_nodes_unique_node_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_nodes
    ADD CONSTRAINT workflow_nodes_unique_node_id UNIQUE (workflow_id, node_id);


--
-- Name: workflow_runs workflow_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_runs
    ADD CONSTRAINT workflow_runs_pkey PRIMARY KEY (id, created_at);


--
-- Name: workflows workflows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_pkey PRIMARY KEY (id);


--
-- Name: alerts_human_readable_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX alerts_human_readable_unique ON ONLY public.alerts USING btree (tenant_id, human_readable_id, ingested_at);


--
-- Name: idx_activity_audit_trail_actor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_activity_audit_trail_actor_id ON ONLY public.activity_audit_trails USING btree (actor_id);


--
-- Name: idx_activity_audit_trail_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_activity_audit_trail_source ON ONLY public.activity_audit_trails USING btree (source);


--
-- Name: idx_alert_analysis_retry_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_analysis_retry_status ON ONLY public.alert_analyses USING btree (status, workflow_gen_retry_count) WHERE ((status)::text = 'paused_workflow_building'::text);


--
-- Name: idx_alert_routing_rules_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_routing_rules_group ON public.alert_routing_rules USING btree (analysis_group_id);


--
-- Name: idx_alert_routing_rules_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_routing_rules_tenant ON public.alert_routing_rules USING btree (tenant_id);


--
-- Name: idx_alerts_actor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_actor ON ONLY public.alerts USING gin (actor) WHERE (actor IS NOT NULL);


--
-- Name: idx_alerts_alert_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_alert_id ON ONLY public.alerts USING btree (id);


--
-- Name: idx_alerts_confidence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_confidence ON ONLY public.alerts USING btree (current_disposition_confidence) WHERE (current_disposition_confidence IS NOT NULL);


--
-- Name: idx_alerts_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_created_at ON ONLY public.alerts USING btree (created_at);


--
-- Name: idx_alerts_current_analysis; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_current_analysis ON ONLY public.alerts USING btree (current_analysis_id) WHERE (current_analysis_id IS NOT NULL);


--
-- Name: idx_alerts_device; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_device ON ONLY public.alerts USING gin (device) WHERE (device IS NOT NULL);


--
-- Name: idx_alerts_disposition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_disposition ON ONLY public.alerts USING btree (current_disposition_category) WHERE (current_disposition_category IS NOT NULL);


--
-- Name: idx_alerts_disposition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_disposition_id ON ONLY public.alerts USING btree (tenant_id, disposition_id) WHERE (disposition_id IS NOT NULL);


--
-- Name: idx_alerts_evidences; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_evidences ON ONLY public.alerts USING gin (evidences) WHERE (evidences IS NOT NULL);


--
-- Name: idx_alerts_human_readable; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_human_readable ON ONLY public.alerts USING btree (tenant_id, human_readable_id);


--
-- Name: idx_alerts_observables; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_observables ON ONLY public.alerts USING gin (observables) WHERE (observables IS NOT NULL);


--
-- Name: idx_alerts_ocsf_metadata; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_ocsf_metadata ON ONLY public.alerts USING gin (ocsf_metadata);


--
-- Name: idx_alerts_raw_data_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_raw_data_hash ON ONLY public.alerts USING btree (tenant_id, raw_data_hash) WHERE (raw_data_hash <> ''::text);


--
-- Name: idx_alerts_severity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_severity_id ON ONLY public.alerts USING btree (tenant_id, severity_id);


--
-- Name: idx_alerts_source_event_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_source_event_id ON ONLY public.alerts USING btree (source_event_id);


--
-- Name: idx_alerts_tenant_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_tenant_severity ON ONLY public.alerts USING btree (tenant_id, severity);


--
-- Name: idx_alerts_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_tenant_status ON ONLY public.alerts USING btree (tenant_id, analysis_status);


--
-- Name: idx_alerts_tenant_time_desc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_tenant_time_desc ON ONLY public.alerts USING btree (tenant_id, triggering_event_time DESC);


--
-- Name: idx_analysis_alert; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_alert ON ONLY public.alert_analyses USING btree (alert_id);


--
-- Name: idx_analysis_alert_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_alert_created ON ONLY public.alert_analyses USING btree (alert_id, created_at);


--
-- Name: idx_analysis_groups_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_groups_tenant ON public.analysis_groups USING btree (tenant_id);


--
-- Name: idx_analysis_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_tenant_status ON ONLY public.alert_analyses USING btree (tenant_id, status);


--
-- Name: idx_analysis_workflow_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_workflow_run ON ONLY public.alert_analyses USING btree (workflow_run_id);


--
-- Name: idx_api_keys_key_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_api_keys_key_hash ON public.api_keys USING btree (key_hash);


--
-- Name: idx_api_keys_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_api_keys_tenant_id ON public.api_keys USING btree (tenant_id);


--
-- Name: idx_api_keys_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_api_keys_user_id ON public.api_keys USING btree (user_id);


--
-- Name: idx_artifacts_alert_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_alert_id ON ONLY public.artifacts USING btree (alert_id) WHERE (alert_id IS NOT NULL);


--
-- Name: idx_artifacts_analysis_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_analysis_id ON ONLY public.artifacts USING btree (analysis_id);


--
-- Name: idx_artifacts_artifact_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_artifact_type ON ONLY public.artifacts USING btree (artifact_type);


--
-- Name: idx_artifacts_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_created_at ON ONLY public.artifacts USING btree (created_at);


--
-- Name: idx_artifacts_integration_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_integration_id ON ONLY public.artifacts USING btree (integration_id) WHERE (integration_id IS NOT NULL);


--
-- Name: idx_artifacts_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_source ON ONLY public.artifacts USING btree (source);


--
-- Name: idx_artifacts_storage_class; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_storage_class ON ONLY public.artifacts USING btree (storage_class);


--
-- Name: idx_artifacts_tags_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_tags_gin ON ONLY public.artifacts USING gin (tags);


--
-- Name: idx_artifacts_task_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_task_run_id ON ONLY public.artifacts USING btree (task_run_id);


--
-- Name: idx_artifacts_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_tenant_id ON ONLY public.artifacts USING btree (tenant_id);


--
-- Name: idx_artifacts_workflow_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_workflow_run_id ON ONLY public.artifacts USING btree (workflow_run_id);


--
-- Name: idx_audit_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_action ON ONLY public.activity_audit_trails USING btree (action);


--
-- Name: idx_audit_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_created_at ON ONLY public.activity_audit_trails USING btree (created_at DESC);


--
-- Name: idx_audit_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_resource ON ONLY public.activity_audit_trails USING btree (resource_type, resource_id);


--
-- Name: idx_audit_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_tenant_id ON ONLY public.activity_audit_trails USING btree (tenant_id);


--
-- Name: idx_chat_messages_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_messages_conversation ON ONLY public.chat_messages USING btree (conversation_id, created_at);


--
-- Name: idx_chat_messages_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_messages_tenant ON ONLY public.chat_messages USING btree (tenant_id, created_at DESC);


--
-- Name: idx_component_app; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_component_app ON public.components USING btree (app);


--
-- Name: idx_component_categories; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_component_categories ON public.components USING gin (categories);


--
-- Name: idx_component_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_component_kind ON public.components USING btree (kind);


--
-- Name: idx_component_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_component_status ON public.components USING btree (status);


--
-- Name: idx_component_tenant_cy_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_component_tenant_cy_name ON public.components USING btree (tenant_id, cy_name);


--
-- Name: idx_component_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_component_tenant_id ON public.components USING btree (tenant_id);


--
-- Name: idx_component_tenant_kind_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_component_tenant_kind_status ON public.components USING btree (tenant_id, kind, status);


--
-- Name: idx_component_tenant_ns_ku_type_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_component_tenant_ns_ku_type_name ON public.components USING btree (tenant_id, namespace, ku_type, name);


--
-- Name: idx_control_event_dispatches_event; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_control_event_dispatches_event ON public.control_event_dispatches USING btree (control_event_id);


--
-- Name: idx_control_event_rules_tenant_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_control_event_rules_tenant_channel ON public.control_event_rules USING btree (tenant_id, channel, enabled);


--
-- Name: idx_control_events_status_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_control_events_status_channel ON ONLY public.control_events USING btree (status, channel, created_at);


--
-- Name: idx_control_events_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_control_events_tenant_status ON ONLY public.control_events USING btree (tenant_id, status, created_at);


--
-- Name: idx_conversations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_tenant_id ON public.chat_conversations USING btree (tenant_id, id) WHERE (deleted_at IS NULL);


--
-- Name: idx_conversations_tenant_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_tenant_user ON public.chat_conversations USING btree (tenant_id, user_id, updated_at DESC) WHERE (deleted_at IS NULL);


--
-- Name: idx_cr_active_reviews; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cr_active_reviews ON public.content_reviews USING btree (tenant_id, status, created_at) WHERE (status = ANY (ARRAY['pending'::public.content_review_status, 'flagged'::public.content_review_status, 'approved'::public.content_review_status]));


--
-- Name: idx_cr_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cr_document ON public.content_reviews USING btree (document_id);


--
-- Name: idx_cr_tenant_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cr_tenant_created ON public.content_reviews USING btree (tenant_id, created_at);


--
-- Name: idx_cr_tenant_pipeline_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cr_tenant_pipeline_status ON public.content_reviews USING btree (tenant_id, pipeline_name, status);


--
-- Name: idx_cr_tenant_skill; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cr_tenant_skill ON public.content_reviews USING btree (tenant_id, skill_id);


--
-- Name: idx_cr_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cr_tenant_status ON public.content_reviews USING btree (tenant_id, status);


--
-- Name: idx_credentials_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credentials_provider ON public.credentials USING btree (provider);


--
-- Name: idx_credentials_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credentials_tenant_id ON public.credentials USING btree (tenant_id);


--
-- Name: idx_hitl_questions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hitl_questions_id ON ONLY public.hitl_questions USING btree (id);


--
-- Name: idx_hitl_questions_ref_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hitl_questions_ref_channel ON ONLY public.hitl_questions USING btree (question_ref, channel);


--
-- Name: idx_hitl_questions_status_timeout; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hitl_questions_status_timeout ON ONLY public.hitl_questions USING btree (status, timeout_at) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_hitl_questions_task_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hitl_questions_task_run ON ONLY public.hitl_questions USING btree (task_run_id);


--
-- Name: idx_hitl_questions_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hitl_questions_tenant_status ON ONLY public.hitl_questions USING btree (tenant_id, status, created_at);


--
-- Name: idx_index_entries_content_dedup; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_index_entries_content_dedup ON public.index_entries USING btree (collection_id, tenant_id, content_hash);


--
-- Name: idx_index_entries_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_index_entries_embedding_hnsw ON public.index_entries USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: idx_index_entries_metadata; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_index_entries_metadata ON public.index_entries USING gin (metadata);


--
-- Name: idx_index_entries_tenant_collection; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_index_entries_tenant_collection ON public.index_entries USING btree (tenant_id, collection_id);


--
-- Name: idx_integration_credentials_credential_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_integration_credentials_credential_id ON public.integration_credentials USING btree (credential_id);


--
-- Name: idx_integration_credentials_integration_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_integration_credentials_integration_id ON public.integration_credentials USING btree (integration_id);


--
-- Name: idx_integrations_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_integrations_enabled ON public.integrations USING btree (enabled) WHERE (enabled = true);


--
-- Name: idx_integrations_integration_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_integrations_integration_type ON public.integrations USING btree (integration_type);


--
-- Name: idx_integrations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_integrations_tenant_id ON public.integrations USING btree (tenant_id);


--
-- Name: idx_invitations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invitations_tenant_id ON public.invitations USING btree (tenant_id);


--
-- Name: idx_invitations_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invitations_token_hash ON public.invitations USING btree (token_hash);


--
-- Name: idx_job_runs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_runs_created_at ON ONLY public.job_runs USING btree (created_at DESC);


--
-- Name: idx_job_runs_integration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_runs_integration ON ONLY public.job_runs USING btree (tenant_id, integration_id);


--
-- Name: idx_job_runs_schedule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_runs_schedule ON ONLY public.job_runs USING btree (schedule_id);


--
-- Name: idx_job_runs_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_runs_tenant ON ONLY public.job_runs USING btree (tenant_id);


--
-- Name: idx_kdg_edge_relationship_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kdg_edge_relationship_type ON public.component_graph_edges USING btree (relationship_type);


--
-- Name: idx_kdg_edge_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kdg_edge_source_id ON public.component_graph_edges USING btree (source_id);


--
-- Name: idx_kdg_edge_target_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kdg_edge_target_id ON public.component_graph_edges USING btree (target_id);


--
-- Name: idx_kdg_edge_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kdg_edge_tenant_id ON public.component_graph_edges USING btree (tenant_id);


--
-- Name: idx_kdg_edge_tenant_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kdg_edge_tenant_source ON public.component_graph_edges USING btree (tenant_id, source_id);


--
-- Name: idx_kdg_edge_tenant_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kdg_edge_tenant_target ON public.component_graph_edges USING btree (tenant_id, target_id);


--
-- Name: idx_knowledge_extractions_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_knowledge_extractions_document ON public.knowledge_extractions USING btree (document_id);


--
-- Name: idx_knowledge_extractions_tenant_skill; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_knowledge_extractions_tenant_skill ON public.knowledge_extractions USING btree (tenant_id, skill_id);


--
-- Name: idx_knowledge_extractions_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_knowledge_extractions_tenant_status ON public.knowledge_extractions USING btree (tenant_id, status);


--
-- Name: idx_ku_component_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_component_id ON public.knowledge_units USING btree (component_id);


--
-- Name: idx_ku_document_component_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_document_component_id ON public.ku_documents USING btree (component_id);


--
-- Name: idx_ku_document_content_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_document_content_source ON public.ku_documents USING btree (content_source);


--
-- Name: idx_ku_document_doc_format; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_document_doc_format ON public.ku_documents USING btree (doc_format);


--
-- Name: idx_ku_document_document_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_document_document_type ON public.ku_documents USING btree (document_type);


--
-- Name: idx_ku_document_language; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_document_language ON public.ku_documents USING btree (language);


--
-- Name: idx_ku_document_metadata; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_document_metadata ON public.ku_documents USING gin (metadata);


--
-- Name: idx_ku_index_build_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_index_build_status ON public.ku_indexes USING btree (build_status);


--
-- Name: idx_ku_index_chunking_config; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_index_chunking_config ON public.ku_indexes USING gin (chunking_config);


--
-- Name: idx_ku_index_component_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_index_component_id ON public.ku_indexes USING btree (component_id);


--
-- Name: idx_ku_index_stats; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_index_stats ON public.ku_indexes USING gin (index_stats);


--
-- Name: idx_ku_index_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_index_type ON public.ku_indexes USING btree (index_type);


--
-- Name: idx_ku_table_component_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_table_component_id ON public.ku_tables USING btree (component_id);


--
-- Name: idx_ku_table_content_jsonb; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_table_content_jsonb ON public.ku_tables USING gin (content);


--
-- Name: idx_ku_table_schema; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_table_schema ON public.ku_tables USING gin (schema);


--
-- Name: idx_ku_tool_auth_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_tool_auth_type ON public.ku_tools USING btree (auth_type);


--
-- Name: idx_ku_tool_component_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_tool_component_id ON public.ku_tools USING btree (component_id);


--
-- Name: idx_ku_tool_input_schema; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_tool_input_schema ON public.ku_tools USING gin (input_schema);


--
-- Name: idx_ku_tool_mcp_server_config; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_tool_mcp_server_config ON public.ku_tools USING gin (mcp_server_config);


--
-- Name: idx_ku_tool_output_schema; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_tool_output_schema ON public.ku_tools USING gin (output_schema);


--
-- Name: idx_ku_tool_tool_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_tool_tool_type ON public.ku_tools USING btree (tool_type);


--
-- Name: idx_ku_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ku_type ON public.knowledge_units USING btree (ku_type);


--
-- Name: idx_memberships_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memberships_tenant_id ON public.memberships USING btree (tenant_id);


--
-- Name: idx_memberships_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memberships_user_id ON public.memberships USING btree (user_id);


--
-- Name: idx_node_templates_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_templates_enabled ON public.node_templates USING btree (enabled) WHERE (enabled = true);


--
-- Name: idx_node_templates_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_templates_kind ON public.node_templates USING btree (kind);


--
-- Name: idx_node_templates_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_templates_name ON public.node_templates USING btree (name);


--
-- Name: idx_node_templates_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_templates_resource ON public.node_templates USING btree (resource_id);


--
-- Name: idx_node_templates_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_templates_tenant ON public.node_templates USING btree (tenant_id) WHERE (tenant_id IS NOT NULL);


--
-- Name: idx_node_templates_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_templates_type ON public.node_templates USING btree (type);


--
-- Name: idx_schedules_integration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedules_integration ON public.schedules USING btree (tenant_id, integration_id) WHERE (integration_id IS NOT NULL);


--
-- Name: idx_schedules_next_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedules_next_run ON public.schedules USING btree (next_run_at) WHERE (enabled = true);


--
-- Name: idx_schedules_tenant_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedules_tenant_enabled ON public.schedules USING btree (tenant_id, enabled) WHERE (enabled = true);


--
-- Name: idx_task_building_runs_alert; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_building_runs_alert ON public.task_generations USING btree (alert_id) WHERE (alert_id IS NOT NULL);


--
-- Name: idx_task_building_runs_generation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_building_runs_generation ON public.task_generations USING btree (workflow_generation_id);


--
-- Name: idx_task_building_runs_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_building_runs_source ON public.task_generations USING btree (source);


--
-- Name: idx_task_building_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_building_runs_status ON public.task_generations USING btree (status);


--
-- Name: idx_task_building_runs_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_building_runs_tenant ON public.task_generations USING btree (tenant_id);


--
-- Name: idx_task_component_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_component_id ON public.tasks USING btree (component_id);


--
-- Name: idx_task_data_samples_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_data_samples_gin ON public.tasks USING gin (data_samples);


--
-- Name: idx_task_function; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_function ON public.tasks USING btree (function);


--
-- Name: idx_task_last_run_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_last_run_at ON public.tasks USING btree (last_run_at);


--
-- Name: idx_task_llm_config; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_llm_config ON public.tasks USING gin (llm_config);


--
-- Name: idx_task_runs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_created_at ON ONLY public.task_runs USING btree (created_at);


--
-- Name: idx_task_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_status ON ONLY public.task_runs USING btree (status);


--
-- Name: idx_task_runs_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_task_id ON ONLY public.task_runs USING btree (task_id) WHERE (task_id IS NOT NULL);


--
-- Name: idx_task_runs_tenant_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_tenant_created ON ONLY public.task_runs USING btree (tenant_id, created_at DESC);


--
-- Name: idx_task_runs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_tenant_id ON ONLY public.task_runs USING btree (tenant_id);


--
-- Name: idx_task_runs_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_tenant_status ON ONLY public.task_runs USING btree (tenant_id, status);


--
-- Name: idx_task_runs_workflow_node_instance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_workflow_node_instance_id ON ONLY public.task_runs USING btree (workflow_node_instance_id) WHERE (workflow_node_instance_id IS NOT NULL);


--
-- Name: idx_task_runs_workflow_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_workflow_run_id ON ONLY public.task_runs USING btree (workflow_run_id);


--
-- Name: idx_task_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_scope ON public.tasks USING btree (scope);


--
-- Name: idx_task_view_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_view_name ON public.components USING btree (name) WHERE (kind = 'task'::public.component_kind);


--
-- Name: idx_task_view_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_view_tenant_id ON public.components USING btree (tenant_id) WHERE (kind = 'task'::public.component_kind);


--
-- Name: idx_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tenant_status ON public.tenants USING btree (status);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_keycloak_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_keycloak_id ON public.users USING btree (keycloak_id);


--
-- Name: idx_workflow_app; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_app ON public.workflows USING btree (app);


--
-- Name: idx_workflow_edge_instances_edge_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edge_instances_edge_id ON ONLY public.workflow_edge_instances USING btree (edge_id);


--
-- Name: idx_workflow_edge_instances_edge_uuid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edge_instances_edge_uuid ON ONLY public.workflow_edge_instances USING btree (edge_uuid);


--
-- Name: idx_workflow_edge_instances_from_instance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edge_instances_from_instance_id ON ONLY public.workflow_edge_instances USING btree (from_instance_id);


--
-- Name: idx_workflow_edge_instances_to_instance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edge_instances_to_instance_id ON ONLY public.workflow_edge_instances USING btree (to_instance_id);


--
-- Name: idx_workflow_edge_instances_workflow_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edge_instances_workflow_run_id ON ONLY public.workflow_edge_instances USING btree (workflow_run_id);


--
-- Name: idx_workflow_edges_from_node; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edges_from_node ON public.workflow_edges USING btree (from_node_uuid);


--
-- Name: idx_workflow_edges_nodes; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edges_nodes ON public.workflow_edges USING btree (from_node_uuid, to_node_uuid);


--
-- Name: idx_workflow_edges_to_node; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edges_to_node ON public.workflow_edges USING btree (to_node_uuid);


--
-- Name: idx_workflow_edges_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_edges_workflow ON public.workflow_edges USING btree (workflow_id);


--
-- Name: idx_workflow_generations_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_generations_active ON public.workflow_generations USING btree (tenant_id, analysis_group_id, is_active) WHERE (is_active = true);


--
-- Name: idx_workflow_generations_cleanup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_generations_cleanup ON public.workflow_generations USING btree (status);


--
-- Name: idx_workflow_generations_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_generations_group ON public.workflow_generations USING btree (analysis_group_id);


--
-- Name: idx_workflow_generations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_generations_status ON public.workflow_generations USING btree (status);


--
-- Name: idx_workflow_generations_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_generations_status_created ON public.workflow_generations USING btree (status, created_at);


--
-- Name: idx_workflow_generations_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_generations_tenant ON public.workflow_generations USING btree (tenant_id);


--
-- Name: idx_workflow_generations_triggering_alert; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_generations_triggering_alert ON public.workflow_generations USING btree (triggering_alert_analysis_id) WHERE (triggering_alert_analysis_id IS NOT NULL);


--
-- Name: idx_workflow_node_instances_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_node_instances_node_id ON ONLY public.workflow_node_instances USING btree (node_id);


--
-- Name: idx_workflow_node_instances_node_uuid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_node_instances_node_uuid ON ONLY public.workflow_node_instances USING btree (node_uuid);


--
-- Name: idx_workflow_node_instances_parent_instance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_node_instances_parent_instance_id ON ONLY public.workflow_node_instances USING btree (parent_instance_id);


--
-- Name: idx_workflow_node_instances_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_node_instances_status ON ONLY public.workflow_node_instances USING btree (status);


--
-- Name: idx_workflow_node_instances_task_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_node_instances_task_run_id ON ONLY public.workflow_node_instances USING btree (task_run_id);


--
-- Name: idx_workflow_node_instances_workflow_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_node_instances_workflow_run_id ON ONLY public.workflow_node_instances USING btree (workflow_run_id);


--
-- Name: idx_workflow_nodes_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_nodes_kind ON public.workflow_nodes USING btree (kind);


--
-- Name: idx_workflow_nodes_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_nodes_start ON public.workflow_nodes USING btree (workflow_id) WHERE (is_start_node = true);


--
-- Name: idx_workflow_nodes_task; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_nodes_task ON public.workflow_nodes USING btree (task_id) WHERE (task_id IS NOT NULL);


--
-- Name: idx_workflow_nodes_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_nodes_task_id ON public.workflow_nodes USING btree (task_id) WHERE (task_id IS NOT NULL);


--
-- Name: idx_workflow_nodes_template; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_nodes_template ON public.workflow_nodes USING btree (node_template_id) WHERE (node_template_id IS NOT NULL);


--
-- Name: idx_workflow_nodes_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_nodes_workflow ON public.workflow_nodes USING btree (workflow_id);


--
-- Name: idx_workflow_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_runs_status ON ONLY public.workflow_runs USING btree (status);


--
-- Name: idx_workflow_runs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_runs_tenant_id ON ONLY public.workflow_runs USING btree (tenant_id);


--
-- Name: idx_workflow_runs_tenant_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_runs_tenant_workflow ON ONLY public.workflow_runs USING btree (tenant_id, workflow_id);


--
-- Name: idx_workflow_runs_workflow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_runs_workflow_id ON ONLY public.workflow_runs USING btree (workflow_id);


--
-- Name: idx_workflows_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflows_created ON public.workflows USING btree (created_at);


--
-- Name: idx_workflows_dynamic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflows_dynamic ON public.workflows USING btree (is_dynamic);


--
-- Name: idx_workflows_ephemeral_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflows_ephemeral_expires ON public.workflows USING btree (is_ephemeral, expires_at) WHERE (is_ephemeral = true);


--
-- Name: idx_workflows_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflows_tenant ON public.workflows USING btree (tenant_id);


--
-- Name: ix_knowledge_module_component_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_knowledge_module_component_id ON public.knowledge_modules USING btree (component_id);


--
-- Name: ix_knowledge_module_module_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_knowledge_module_module_type ON public.knowledge_modules USING btree (module_type);


--
-- Name: uq_component_cy_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_component_cy_name ON public.components USING btree (tenant_id, app, cy_name) WHERE (cy_name IS NOT NULL);


--
-- Name: dispositions set_dispositions_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER set_dispositions_updated_at BEFORE UPDATE ON public.dispositions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: checkpoints trigger_checkpoints_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_checkpoints_updated_at BEFORE UPDATE ON public.checkpoints FOR EACH ROW EXECUTE FUNCTION public.update_checkpoints_updated_at();


--
-- Name: components trigger_component_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_component_updated_at BEFORE UPDATE ON public.components FOR EACH ROW EXECUTE FUNCTION public.generic_update_updated_at();


--
-- Name: integrations trigger_integrations_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_integrations_updated_at BEFORE UPDATE ON public.integrations FOR EACH ROW EXECUTE FUNCTION public.update_integrations_updated_at();


--
-- Name: component_graph_edges trigger_kdg_edge_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_kdg_edge_updated_at BEFORE UPDATE ON public.component_graph_edges FOR EACH ROW EXECUTE FUNCTION public.generic_update_updated_at();


--
-- Name: knowledge_units trigger_knowledge_unit_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_knowledge_unit_updated_at BEFORE UPDATE ON public.knowledge_units FOR EACH ROW EXECUTE FUNCTION public.generic_update_updated_at();


--
-- Name: ku_documents trigger_ku_document_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_ku_document_updated_at BEFORE UPDATE ON public.ku_documents FOR EACH ROW EXECUTE FUNCTION public.generic_update_updated_at();


--
-- Name: ku_indexes trigger_ku_index_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_ku_index_updated_at BEFORE UPDATE ON public.ku_indexes FOR EACH ROW EXECUTE FUNCTION public.generic_update_updated_at();


--
-- Name: ku_tables trigger_ku_table_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_ku_table_updated_at BEFORE UPDATE ON public.ku_tables FOR EACH ROW EXECUTE FUNCTION public.generic_update_updated_at();


--
-- Name: ku_tools trigger_ku_tool_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_ku_tool_updated_at BEFORE UPDATE ON public.ku_tools FOR EACH ROW EXECUTE FUNCTION public.generic_update_updated_at();


--
-- Name: workflow_node_instances trigger_node_instance_status_check; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_node_instance_status_check BEFORE INSERT OR UPDATE ON public.workflow_node_instances FOR EACH ROW EXECUTE FUNCTION public.check_node_instance_status();


--
-- Name: schedules trigger_schedules_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_schedules_updated_at BEFORE UPDATE ON public.schedules FOR EACH ROW EXECUTE FUNCTION public.update_schedules_updated_at();


--
-- Name: task_runs trigger_task_runs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_task_runs_updated_at BEFORE UPDATE ON public.task_runs FOR EACH ROW EXECUTE FUNCTION public.update_task_runs_updated_at();


--
-- Name: tasks trigger_task_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_task_updated_at BEFORE UPDATE ON public.tasks FOR EACH ROW EXECUTE FUNCTION public.generic_update_updated_at();


--
-- Name: workflow_node_instances trigger_workflow_node_instances_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_workflow_node_instances_updated_at BEFORE UPDATE ON public.workflow_node_instances FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: workflow_runs trigger_workflow_run_status_check; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_workflow_run_status_check BEFORE INSERT OR UPDATE ON public.workflow_runs FOR EACH ROW EXECUTE FUNCTION public.check_workflow_run_status();


--
-- Name: workflow_runs trigger_workflow_runs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_workflow_runs_updated_at BEFORE UPDATE ON public.workflow_runs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: workflows workflows_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER workflows_updated_at BEFORE UPDATE ON public.workflows FOR EACH ROW EXECUTE FUNCTION public.update_workflow_timestamp();


--
-- Name: alert_analyses alert_analysis_disposition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.alert_analyses
    ADD CONSTRAINT alert_analysis_disposition_id_fkey FOREIGN KEY (disposition_id) REFERENCES public.dispositions(id);


--
-- Name: alert_routing_rules alert_routing_rules_analysis_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_routing_rules
    ADD CONSTRAINT alert_routing_rules_analysis_group_id_fkey FOREIGN KEY (analysis_group_id) REFERENCES public.analysis_groups(id) ON DELETE CASCADE;


--
-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: chat_messages chat_messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.chat_messages
    ADD CONSTRAINT chat_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.chat_conversations(id) ON DELETE RESTRICT;


--
-- Name: content_reviews content_reviews_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_reviews
    ADD CONSTRAINT content_reviews_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: content_reviews content_reviews_applied_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_reviews
    ADD CONSTRAINT content_reviews_applied_document_id_fkey FOREIGN KEY (applied_document_id) REFERENCES public.components(id) ON DELETE SET NULL;


--
-- Name: content_reviews content_reviews_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_reviews
    ADD CONSTRAINT content_reviews_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.components(id) ON DELETE SET NULL;


--
-- Name: content_reviews content_reviews_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_reviews
    ADD CONSTRAINT content_reviews_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: control_event_dispatches control_event_dispatches_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_event_dispatches
    ADD CONSTRAINT control_event_dispatches_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.control_event_rules(id) ON DELETE CASCADE;


--
-- Name: chat_conversations conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_conversations
    ADD CONSTRAINT conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: components fk_component_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.components
    ADD CONSTRAINT fk_component_created_by FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: components fk_component_updated_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.components
    ADD CONSTRAINT fk_component_updated_by FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: credentials fk_credentials_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT fk_credentials_created_by FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: task_generations fk_task_building_runs_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_generations
    ADD CONSTRAINT fk_task_building_runs_created_by FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: task_runs fk_task_runs_task_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.task_runs
    ADD CONSTRAINT fk_task_runs_task_id FOREIGN KEY (task_id) REFERENCES public.tasks(component_id) ON DELETE SET NULL;


--
-- Name: workflow_edge_instances fk_workflow_edge_instances_edge_uuid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.workflow_edge_instances
    ADD CONSTRAINT fk_workflow_edge_instances_edge_uuid FOREIGN KEY (edge_uuid) REFERENCES public.workflow_edges(id) ON DELETE CASCADE;


--
-- Name: workflow_node_instances fk_workflow_node_instances_node_uuid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.workflow_node_instances
    ADD CONSTRAINT fk_workflow_node_instances_node_uuid FOREIGN KEY (node_uuid) REFERENCES public.workflow_nodes(id) ON DELETE CASCADE;


--
-- Name: workflow_node_instances fk_workflow_node_instances_template_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.workflow_node_instances
    ADD CONSTRAINT fk_workflow_node_instances_template_id FOREIGN KEY (template_id) REFERENCES public.node_templates(id) ON DELETE SET NULL;


--
-- Name: workflow_nodes fk_workflow_nodes_task_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_nodes
    ADD CONSTRAINT fk_workflow_nodes_task_id FOREIGN KEY (task_id) REFERENCES public.components(id) ON DELETE RESTRICT;


--
-- Name: workflow_nodes fk_workflow_nodes_template; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_nodes
    ADD CONSTRAINT fk_workflow_nodes_template FOREIGN KEY (node_template_id) REFERENCES public.node_templates(id);


--
-- Name: workflows fk_workflows_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT fk_workflows_created_by FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: index_entries index_entries_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.index_entries
    ADD CONSTRAINT index_entries_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: integration_credentials integration_credentials_credential_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integration_credentials
    ADD CONSTRAINT integration_credentials_credential_id_fkey FOREIGN KEY (credential_id) REFERENCES public.credentials(id) ON DELETE CASCADE;


--
-- Name: invitations invitations_invited_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES public.users(id);


--
-- Name: job_runs job_runs_schedule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.job_runs
    ADD CONSTRAINT job_runs_schedule_id_fkey FOREIGN KEY (schedule_id) REFERENCES public.schedules(id) ON DELETE SET NULL;


--
-- Name: component_graph_edges kdg_edge_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.component_graph_edges
    ADD CONSTRAINT kdg_edge_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: component_graph_edges kdg_edge_target_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.component_graph_edges
    ADD CONSTRAINT kdg_edge_target_id_fkey FOREIGN KEY (target_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: knowledge_extractions knowledge_extractions_applied_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_extractions
    ADD CONSTRAINT knowledge_extractions_applied_document_id_fkey FOREIGN KEY (applied_document_id) REFERENCES public.components(id) ON DELETE SET NULL;


--
-- Name: knowledge_extractions knowledge_extractions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_extractions
    ADD CONSTRAINT knowledge_extractions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: knowledge_extractions knowledge_extractions_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_extractions
    ADD CONSTRAINT knowledge_extractions_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: knowledge_modules knowledge_module_component_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_modules
    ADD CONSTRAINT knowledge_module_component_id_fkey FOREIGN KEY (component_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: knowledge_units knowledge_unit_component_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_units
    ADD CONSTRAINT knowledge_unit_component_id_fkey FOREIGN KEY (component_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: ku_documents ku_document_component_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_documents
    ADD CONSTRAINT ku_document_component_id_fkey FOREIGN KEY (component_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: ku_indexes ku_index_component_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_indexes
    ADD CONSTRAINT ku_index_component_id_fkey FOREIGN KEY (component_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: ku_tables ku_table_component_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_tables
    ADD CONSTRAINT ku_table_component_id_fkey FOREIGN KEY (component_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: ku_tools ku_tool_component_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ku_tools
    ADD CONSTRAINT ku_tool_component_id_fkey FOREIGN KEY (component_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_invited_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES public.users(id);


--
-- Name: memberships memberships_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: task_generations task_building_runs_workflow_generation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_generations
    ADD CONSTRAINT task_building_runs_workflow_generation_id_fkey FOREIGN KEY (workflow_generation_id) REFERENCES public.workflow_generations(id) ON DELETE CASCADE;


--
-- Name: tasks task_component_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT task_component_id_fkey FOREIGN KEY (component_id) REFERENCES public.components(id) ON DELETE CASCADE;


--
-- Name: workflow_edges workflow_edges_from_node_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_from_node_uuid_fkey FOREIGN KEY (from_node_uuid) REFERENCES public.workflow_nodes(id);


--
-- Name: workflow_edges workflow_edges_to_node_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_to_node_uuid_fkey FOREIGN KEY (to_node_uuid) REFERENCES public.workflow_nodes(id);


--
-- Name: workflow_edges workflow_edges_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE CASCADE;


--
-- Name: workflow_generations workflow_generations_analysis_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_generations
    ADD CONSTRAINT workflow_generations_analysis_group_id_fkey FOREIGN KEY (analysis_group_id) REFERENCES public.analysis_groups(id) ON DELETE CASCADE;


--
-- Name: workflow_nodes workflow_nodes_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_nodes
    ADD CONSTRAINT workflow_nodes_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE CASCADE;


--
-- Name: workflow_runs workflow_runs_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.workflow_runs
    ADD CONSTRAINT workflow_runs_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE SET NULL;


--
--



-- =============================================================================
-- pg_partman registration (runtime state, not captured by pg_dump)
-- =============================================================================
-- Registers each partitioned parent with pg_partman. Adopts existing partitions
-- if any (fresh baseline should have none — partman creates initial set).

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.task_runs') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.task_runs',
      p_control := 'created_at', p_interval := '1 day', p_premake := 30, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.artifacts') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.artifacts',
      p_control := 'created_at', p_interval := '1 day', p_premake := 30, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.alerts') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.alerts',
      p_control := 'ingested_at', p_interval := '1 day', p_premake := 30, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.alert_analyses') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.alert_analyses',
      p_control := 'created_at', p_interval := '1 day', p_premake := 30, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.workflow_runs') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.workflow_runs',
      p_control := 'created_at', p_interval := '1 day', p_premake := 30, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.workflow_node_instances') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.workflow_node_instances',
      p_control := 'created_at', p_interval := '1 day', p_premake := 30, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.workflow_edge_instances') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.workflow_edge_instances',
      p_control := 'created_at', p_interval := '1 day', p_premake := 30, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.activity_audit_trails') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.activity_audit_trails',
      p_control := 'created_at', p_interval := '1 day', p_premake := 30, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.chat_messages') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.chat_messages',
      p_control := 'created_at', p_interval := '1 month', p_premake := 4, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.control_events') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.control_events',
      p_control := 'created_at', p_interval := '1 month', p_premake := 4, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.hitl_questions') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.hitl_questions',
      p_control := 'created_at', p_interval := '1 month', p_premake := 4, p_default_table := true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM partman.part_config WHERE parent_table = 'public.job_runs') THEN
    PERFORM partman.create_parent(p_parent_table := 'public.job_runs',
      p_control := 'created_at', p_interval := '1 month', p_premake := 4, p_default_table := true);
  END IF;
END $$;

-- Retention policies.
UPDATE partman.part_config SET retention = '90 days', retention_keep_table = false, infinite_time_partitions = true
  WHERE parent_table IN ('public.task_runs','public.artifacts','public.workflow_runs',
    'public.workflow_node_instances','public.workflow_edge_instances','public.control_events',
    'public.chat_messages','public.job_runs');

UPDATE partman.part_config SET retention = '180 days', retention_keep_table = false, infinite_time_partitions = true
  WHERE parent_table IN ('public.alerts','public.alert_analyses');

UPDATE partman.part_config SET retention = '180 days', retention_keep_table = false, infinite_time_partitions = false
  WHERE parent_table = 'public.hitl_questions';

UPDATE partman.part_config SET retention = '365 days', retention_keep_table = true, infinite_time_partitions = true
  WHERE parent_table = 'public.activity_audit_trails';

-- pg_cron scheduled maintenance (only if pg_cron is installed in this DB; the
-- test DB doesn't have pg_cron — tests call run_maintenance_proc() manually).
DO $cron_setup$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    BEGIN PERFORM cron.unschedule('pg-partman-maintenance'); EXCEPTION WHEN OTHERS THEN NULL; END;
    BEGIN PERFORM cron.unschedule('pg-partman-health-check'); EXCEPTION WHEN OTHERS THEN NULL; END;

    PERFORM cron.schedule('pg-partman-maintenance', '0 * * * *',
      'CALL partman.run_maintenance_proc()');

    -- Daily health check: warn if data ever lands in a _default partition
    -- (indicates a missing managed partition). Only check_default() is used
    -- — pg_partman v5.4 does not expose check_missing(), and run_maintenance()
    -- already creates any missing partitions every hour on its own.
    PERFORM cron.schedule('pg-partman-health-check', '0 6 * * *', $h$
      DO $inner$ BEGIN
        IF EXISTS (SELECT 1 FROM partman.check_default()) THEN
          RAISE WARNING 'pg_partman: data found in default partitions — investigate and re-route';
        END IF;
      END $inner$;
    $h$);
  END IF;
END $cron_setup$;

-- =============================================================================
-- Reference seed data (rows the schema dump cannot capture)
-- =============================================================================
-- Sentinel users — required by FKs like fk_component_created_by and as default
-- for created_by/updated_by/actor_id columns across the schema.
INSERT INTO users (id, keycloak_id, email, display_name) VALUES
  ('00000000-0000-0000-0000-000000000001', 'sentinel-system',  'system@analysi.internal',  'System'),
  ('00000000-0000-0000-0000-000000000002', 'sentinel-unknown', 'unknown@analysi.internal', 'Unknown User')
ON CONFLICT (id) DO NOTHING;

-- Default tenant — single-tenant deployments and tests rely on this id.
INSERT INTO tenants (id, name, status) VALUES ('default', 'Default', 'active')
ON CONFLICT (id) DO NOTHING;

--
--




--
-- Data for Name: dispositions; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.dispositions VALUES ('777ce9db-0e1a-4f96-b378-e1849b172c07', 'True Positive (Malicious)', 'Confirmed Compromise', 'Confirmed Compromise', '#DC2626', 'red', 1, 'Active compromise with impact. Immediate incident response required.', true, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('43caf142-ae7f-4c8f-857b-3e35f7d1a635', 'True Positive (Malicious)', 'Confirmed Malicious Attempt (Blocked/Prevented, No Impact)', 'Malicious Attempt Blocked', '#EA580C', 'orange', 2, 'Verified malicious activity, but blocked before causing harm. Important for intel/tuning, but not urgent containment.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('a791fd55-ab38-4f7d-a33e-c89ead1fa143', 'True Positive (Policy Violation)', 'Acceptable Use Violation (non-security but against policy)', 'Acceptable Use Violation', '#EAB308', 'yellow', 5, 'Typically HR/management follow-up. Not a direct technical threat.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('49a8410c-b679-4bbd-a6f6-927431390201', 'True Positive (Policy Violation)', 'Unauthorized Access / Privilege Misuse', 'Unauthorized Access', '#EA580C', 'orange', 3, 'Potential insider threat / misuse. Higher risk than acceptable use violation.', true, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('52292e45-8d7d-4377-b9e1-b0c4d2e4ef50', 'False Positive', 'Detection Logic Error', 'Detection Logic Error', '#EAB308', 'yellow', 6, 'Rule incorrectly designed or triggered. Needs rule fix.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('951906fd-e413-415f-861d-8347ac9c4f0e', 'False Positive', 'Rule Misconfiguration / Sensitivity Issue', 'Rule Misconfiguration', '#EAB308', 'yellow', 6, 'Tuning issue causing noise. Fixable but not dangerous.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('0e72b32b-b862-47e6-8a95-9e21b70213bf', 'False Positive', 'Vendor Signature Bug', 'Vendor Signature Bug', '#EAB308', 'yellow', 6, 'Upstream/vendor problem. Same urgency as other false positives.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('99c8b143-9b87-4adb-ac3d-bbf636427823', 'Security Testing / Expected Activity', 'Red Team / Pentest', 'Red Team Activity', '#2563EB', 'blue', 8, 'Expected malicious-like activity. Needs separation from real incidents.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('7d5ed2d9-5e0d-41ed-acd0-ad3a10b4349b', 'Security Testing / Expected Activity', 'Compliance / Audit', 'Compliance Testing', '#2563EB', 'blue', 8, 'Scheduled or approved test activity. Not a threat.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('91456abf-b938-435a-91f7-a2ae8821ed0e', 'Security Testing / Expected Activity', 'Training / Tabletop', 'Training Exercise', '#2563EB', 'blue', 8, 'Drill-only alerts. Must be tracked but not triaged as real incidents.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('ee67cabc-c2e9-461a-96e8-606000cf39b1', 'Benign Explained', 'Known Business Process', 'Business Process', '#16A34A', 'green', 9, 'Normal business behavior. Should be documented to avoid future noise.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('978116ca-19a9-496c-a4ea-7d3e3ea7b8a5', 'Benign Explained', 'IT Maintenance / Patch / Scanning', 'IT Maintenance', '#16A34A', 'green', 9, 'Routine IT activity (patch cycles, admin scripts, scans).', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('dda11420-44bf-457b-adee-25aa512917ea', 'Benign Explained', 'Environmental Noise (e.g., server patching or restart)', 'Environmental Noise', '#16A34A', 'green', 9, 'Background "chatter" or expected environmental activity.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('74fe9b01-4b1a-4c28-9352-9c5d91fb6d39', 'Undetermined', 'Suspicious, Not Confirmed', 'Suspicious Activity', '#9333EA', 'purple', 4, 'Needs more evidence. Potential threat but not validated.', true, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('02a8d897-73ff-4c32-8016-fb811962f02c', 'Undetermined', 'Insufficient Data / Logs Missing', 'Insufficient Data', '#9333EA', 'purple', 4, 'Cannot confirm due to lack of telemetry. Requires escalation or closure.', true, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('5d5eccf2-10da-4306-ad9e-8657b0fd8c96', 'Undetermined', 'Escalated for Review', 'Escalated for Review', '#9333EA', 'purple', 4, 'Passed to Tier 2/3 or specialized team. Unresolved.', true, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('51d0d70c-7f6b-4195-8a73-7d923e4d3a48', 'Analysis Stopped by User', 'Invalid Alert', 'Invalid Alert', '#6B7280', 'gray', 10, 'Analyst stopped analysis due to invalid trigger (e.g., malformed alert).', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');
INSERT INTO public.dispositions VALUES ('072ac1b2-6641-4349-bd1e-c3b30fd84500', 'Analysis Stopped by User', 'Known Issue / Duplicate', 'Known Issue/Duplicate', '#6B7280', 'gray', 10, 'Duplicate alert, or already tracked incident. Closed administratively.', false, true, '2026-04-22 20:32:27.601867+00', '2026-04-22 20:32:27.601867+00');


--
-- Data for Name: node_templates; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.node_templates VALUES ('f22db20a-338a-46cc-bd58-f09f5a0b92d3', '1f64e9ff-3f2e-44cc-8b03-b8757e383075', 'passthrough', 'Pass input to output unchanged', '{"type": "object"}', '{"type": "object"}', 'return inp', 'python', 'static', true, 1, '2026-04-22 20:32:26.499398+00', 'identity', NULL);
INSERT INTO public.node_templates VALUES ('9cca903d-6dce-49fc-9c2e-094f69db7a63', '983d2d01-100a-4bc0-b32b-af645b5a208a', 'pick_field', 'Extract specific field from input', '{"type": "object", "required": ["field_name"], "properties": {"field_name": {"type": "string"}}}', '{"type": "object", "properties": {"picked_value": {}}}', 'field_name = inp.get("field_name", "unknown")
result = inp.get("result", inp) if "result" in inp else inp
return {"picked_value": result.get(field_name) if isinstance(result, dict) else None}', 'python', 'static', true, 1, '2026-04-22 20:32:26.499398+00', 'identity', NULL);
INSERT INTO public.node_templates VALUES ('18999084-8f12-4690-ab41-bf33ae38e2b4', '6a4f4d3e-6c1f-4516-a477-4f14437f1f58', 'pick_primary_ip', 'Extract primary IP from alert data', '{"type": "object", "properties": {"alert": {"type": "object"}}}', '{"type": "object", "properties": {"primary_ip": {"type": ["string", "null"]}}}', 'alert = inp.get("result", inp).get("alert", {}) if "result" in inp else inp.get("alert", {})
ips = [alert.get("dest", {}).get("ip"), alert.get("src", {}).get("ip")]
primary = next((ip for ip in ips if ip), None)
return {"primary_ip": primary}', 'python', 'static', true, 1, '2026-04-22 20:32:26.499398+00', 'identity', NULL);
INSERT INTO public.node_templates VALUES ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'system_identity', 'Identity transformation - passes input through unchanged (T → T)', '{"type": "object"}', '{"type": "object"}', 'return inp', 'python', 'static', true, 1, '2026-04-22 20:32:30.362882+00', 'identity', NULL);
INSERT INTO public.node_templates VALUES ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000003', 'system_collect', 'Collect transformation - aggregates inputs into an array ([T1, T2] → [T1, T2])', '{"type": "array"}', '{"type": "array"}', '# Collect all inputs into an array (passthrough for arrays)
if isinstance(inp, list):
    return inp
return [inp]', 'python', 'static', true, 1, '2026-04-22 20:32:30.362882+00', 'collect', NULL);
INSERT INTO public.node_templates VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000002', 'system_merge', 'Deep merge - recursively combines nested objects with conflict detection (arrays must match)', '{"type": "array", "items": {"type": "object"}}', '{"type": "object"}', '# Deep merge with conflict detection
# Merges objects from parallel branches with support for nested object merging
# Allows branches to add different nested fields under the same parent key

if not isinstance(inp, list) or len(inp) == 0:
    return {}

# Helper to recursively merge two values
def deep_merge(v1, v2, path=""):
    # If both are dicts, merge recursively
    if isinstance(v1, dict) and isinstance(v2, dict):
        result = v1.copy()
        for key in v2:
            new_path = f"{path}.{key}" if path else key
            if key in result:
                # Recursively merge the nested values
                result[key] = deep_merge(result[key], v2[key], new_path)
            else:
                # New key from v2
                result[key] = v2[key]
        return result

    # If both are lists, check if they''re equal
    elif isinstance(v1, list) and isinstance(v2, list):
        if v1 == v2:
            return v1  # Same array, no conflict
        else:
            # CONFLICT: different array values
            raise ValueError(
                f"Merge conflict at ''{path}'': cannot merge different list values. "
                f"Both branches modified the same array field to different values."
            )

    # Different types or primitive values - check if equal
    else:
        # Check equality
        if type(v1) == type(v2) and v1 == v2:
            return v1
        else:
            # CONFLICT: same field, different primitive values or incompatible types
            raise ValueError(
                f"Merge conflict at ''{path}'': cannot merge {type(v1).__name__} and {type(v2).__name__} "
                f"with different values. Values must match or be mergeable objects/arrays."
            )

# Collect all fields from all branches with deep merging
result = {}

for idx, item in enumerate(inp):
    if not isinstance(item, dict):
        continue

    for key, value in item.items():
        if key in result:
            # Field already exists - deep merge the values
            try:
                result[key] = deep_merge(result[key], value, key)
            except ValueError as e:
                # Re-raise with branch context
                raise ValueError(str(e))
        else:
            # New field - add it
            result[key] = value

return result', 'python', 'static', true, 5, '2026-04-22 20:32:30.362882+00', 'merge', NULL);


--
--


