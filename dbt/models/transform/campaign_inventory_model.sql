{{ config(materialized='table') }}
   SELECT  
        campaign_id, 
        creative_id, 
        auction_id, 
        type, 
        width, 
        height, 
        browser_ts, 
        game_key_ci,
        geo_country, 
        site_name, 
        platform_os, 
        device_type, 
        browser
       
   FROM  
        campaigns_inventory