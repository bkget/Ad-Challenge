CREATE TABLE IF NOT EXISTS public.briefing
(
    "campaign_id_br" character varying(50) COLLATE pg_catalog.default NOT NULL,
    "campaign_name" character varying(128) COLLATE pg_catalog.default,
    "submission_date" character varying(50) COLLATE pg_catalog.default,
    "description" character varying(4096) COLLATE pg_catalog.default,
    "campaign_objectives" character varying(256) COLLATE pg_catalog.default,
    "KPIs" character varying(50) COLLATE pg_catalog.default,
    "placement(s)" character varying(128) COLLATE pg_catalog.default,
    "start_date" character varying(50) COLLATE pg_catalog.default,
    "end_date" character varying(50) COLLATE pg_catalog.default,
    "serving_location(s)" character varying(50) COLLATE pg_catalog.default,
    "black/white/audience_list_included?" character varying(128) COLLATE pg_catalog.default,
    "delivery_requirements_(black/audience/white_list)" character varying(256) COLLATE pg_catalog.default,
    "cost_centre" character varying(50) COLLATE pg_catalog.default,
    "currency" character varying(50) COLLATE pg_catalog.default,
    "buy_rate_(CPE)" real,
    "volume_agreed" integer,
    "gross_cost/budget" real,
    "agency_fee" character varying(50) COLLATE pg_catalog.default,
    "percentage" integer,
    "net_cost" real,
    CONSTRAINT briefing_pk PRIMARY KEY (campaign_id_br)
)
        