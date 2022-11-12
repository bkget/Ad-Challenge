-- Ingesting briefing.csv

DROP TABLE IF EXISTS briefing;
CREATE TABLE briefing (
	campaign_id_br text COLLATE pg_catalog."default" NOT NULL,
    campaign_name text COLLATE pg_catalog."default",
    submission_date text COLLATE pg_catalog."default",
    description text COLLATE pg_catalog."default",
    campaign_objectives text COLLATE pg_catalog."default",
    "KPIs" text COLLATE pg_catalog."default",
    "placement(s)" text COLLATE pg_catalog."default",
    start_date text COLLATE pg_catalog."default",
    end_date text COLLATE pg_catalog."default",
    "serving_location(s)" text COLLATE pg_catalog."default",
    "black/white/audience_list_included?" text COLLATE pg_catalog."default",
    "delivery_requirements_(black/audience/white_list)" text COLLATE pg_catalog."default",
    cost_centre text COLLATE pg_catalog."default",
    currency text COLLATE pg_catalog."default",
    "buy_rate_(CPE)" double precision,
    volume_agreed double precision,
    "gross_cost/budget" double precision,
    agency_fee text COLLATE pg_catalog."default",
    percentage double precision,
    flat_fee double precision,
    net_cost double precision
    -- CONSTRAINT briefing_pkey PRIMARY KEY (campaign_id_br)
);

COPY briefing(campaign_id_br, campaign_name, submission_date, description,
       campaign_objectives, "KPIs", "placement(s)", start_date, end_date,
       "serving_location(s)", "black/white/audience_list_included?",
       "delivery_requirements_(black/audience/white_list)", cost_centre,
       currency, "buy_rate_(CPE)", volume_agreed, "gross_cost/budget",
       agency_fee, percentage, flat_fee, net_cost)
FROM '/home/biruk/Documents/source/briefing.csv'
DELIMITER ','
CSV HEADER;