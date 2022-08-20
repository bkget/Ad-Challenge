{{ config(materialized='table') }} 
    
SELECT 
    ci.campaign_id, 
    ci.creative_id, 
    ci.auction_id, 
    ci."type", 
    ci.width, 
    ci.height, 
    ci.browser_ts, 
    ci.game_key_ci AS game_key, 
    ci.geo_country, 
    ci.site_name, 
    ci.platform_os, 
    ci.device_type, 
    ci.browser,
    br.campaign_name, 
    br.submission_date, 
    br.description, 
    br.campaign_objectives, 
    br."KPIs", 
    br."placement(s)", 
    br.start_date, 
    br.end_date, 
    br."serving_location(s)", 
    br."black/white/audience_list_included?" AS black_white_audience_list_included, 
    br."delivery_requirements_(black/audience/white_list)" AS delivery_requirements, 
    br.cost_centre, 
    br.currency, 
    br."buy_rate_(CPE)", 
    br.volume_agreed, 
    br."gross_cost/budget", 
    br.agency_fee, 
    br.percentage, 
    br.flat_fee, 
    br.net_cost,  
    gd.labels_engagement, 
    gd.labels_click_through, 
    gd.text_engagement, 
    gd.text_click_through, 
    gd.video_data, 
    gd.direction
       
FROM 
        
    {{ ref('campaign_inventory_model') }} ci

LEFT JOIN 

    {{ ref('briefing_model') }} br

ON     
    ci.campaign_id = br.campaign_id_br

LEFT JOIN 

    {{ ref('global_design_model') }} gd
ON     
    ci.game_key_ci = gd.game_key