CREATE TABLE IF NOT EXISTS public.briefing
(
    campaign_id_br character varying(50) COLLATE pg_catalog."default" NOT NULL,
    campaign_name character varying(128) COLLATE pg_catalog."default",
    "Submission Date" character varying(50) COLLATE pg_catalog."default",
    "Description" character varying(4096) COLLATE pg_catalog."default",
    "Campaign Objectives" character varying(256) COLLATE pg_catalog."default",
    "KPIs" character varying(50) COLLATE pg_catalog."default",
    "Placement(s)" character varying(128) COLLATE pg_catalog."default",
    "StartDate" character varying(50) COLLATE pg_catalog."default",
    "EndDate" character varying(50) COLLATE pg_catalog."default",
    "Serving Location(s)" character varying(50) COLLATE pg_catalog."default",
    "Black/white/audience list included?" character varying(128) COLLATE pg_catalog."default",
    "Delivery Requirements (Black/Audience/White List)" character varying(256) COLLATE pg_catalog."default",
    "Cost Centre" character varying(50) COLLATE pg_catalog."default",
    "Currency" character varying(50) COLLATE pg_catalog."default",
    "Buy Rate (CPE)" real,
    "Volume Agreed" integer,
    "Gross Cost/Budget" real,
    "Agency Fee" character varying(50) COLLATE pg_catalog."default",
    "Percentage" integer,
    "Net Cost" real,
    CONSTRAINT briefing_pk PRIMARY KEY (campaign_id_br)
)
        