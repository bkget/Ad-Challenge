-- Ingesting campaigns_inventory_updated.csv

DROP TABLE IF EXISTS campaigns_inventory;
CREATE TABLE campaigns_inventory (
    type text COLLATE pg_catalog."default",
    width text COLLATE pg_catalog."default",
    height text COLLATE pg_catalog."default",
    campaign_id text COLLATE pg_catalog."default",
    creative_id text COLLATE pg_catalog."default",
    auction_id text COLLATE pg_catalog."default",
    browser_ts text COLLATE pg_catalog."default",
    game_key text COLLATE pg_catalog."default",
    geo_country text COLLATE pg_catalog."default",
    site_name text COLLATE pg_catalog."default",
    platform_os text COLLATE pg_catalog."default",
    device_type text COLLATE pg_catalog."default",
    browser text COLLATE pg_catalog."default"
);

COPY campaigns_inventory("type", width ,  height ,  campaign_id ,  creative_id ,  auction_id ,
        browser_ts ,  game_key ,  geo_country ,  site_name ,  platform_os ,
        device_type ,  browser )
FROM '/home/biruk/Documents/source/campaigns_inventory_updated.csv'
DELIMITER ','
CSV HEADER;