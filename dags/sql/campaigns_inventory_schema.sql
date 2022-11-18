
CREATE TABLE IF NOT EXISTS public.campaigns_inventory
(
    type character varying(300) COLLATE pg_catalog."default",
    width text COLLATE pg_catalog."default",
    height text COLLATE pg_catalog."default",
    campaign_id character varying(300) COLLATE pg_catalog."default",
    creative_id character varying(300) COLLATE pg_catalog."default",
    auction_id character varying(300) COLLATE pg_catalog."default",
    browser_ts character varying(300) COLLATE pg_catalog."default",
    game_key_ci character varying(300) COLLATE pg_catalog."default",
    geo_country text COLLATE pg_catalog."default",
    site_name text COLLATE pg_catalog."default",
    platform_os character varying(300) COLLATE pg_catalog."default",
    device_type text COLLATE pg_catalog."default",
    browser character varying(300) COLLATE pg_catalog."default",
    ci_id integer NOT NULL DEFAULT nextval('campaigns_inventory_ci_id_seq'::regclass)
)