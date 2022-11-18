 SELECT 
    ci.campaign_id, 
    ci.creative_id, 
    ci.auction_id, 
    ci."type", 
    ci.width, 
    ci.height, 
    ci.browser_ts, 
    ci.game_key, 
    ci.geo_country, 
    ci.site_name, 
    ci.platform_os, 
    ci.device_type, 
    ci.browser,
    br.campaign_name,
    br."Submission Date" AS "submission_date",
    br."Description", 
    br."Campaign Objectives" AS campaign_objectives, 
    br."KPIs",
    br."Placement(s)" AS "placement(s)",
    br."StartDate" AS "start_date",
    br."EndDate" AS "end_date",
    br."Serving Location(s)" AS "serving_location(s)",
    br."Black/white/audience list included?" AS black_white_audience_list_included,
    br."Delivery Requirements (Black/Audience/White List)" AS delivery_requirements,
    br."Cost Centre" AS "cost_centre",
    br."Currency",
    br."Buy Rate (CPE)" AS "buy_rate_(CPE)",
    br."Volume Agreed" AS volume_agreed,
    br."Gross Cost/Budget" AS "gross_cost/budget",
    br."Agency Fee" AS agency_fee,
    br."Percentage",
    br."Flat Fee",
    br."Net Cost" AS net_cost,
    gd.labels_engagement,
    gd.labels_click_through,
    gd.text_engagement,
    gd.text_click_through,
    gd.video_data,
    gd.direction
       
FROM 
        
    {{ ref('stg_campaigns_inventory') }} ci

LEFT JOIN 

    {{ ref('stg_briefing') }} br

ON     
    ci.campaign_id = br.campaign_id

LEFT JOIN 

    {{ ref('stg_global_design') }} gd
ON     
    ci.game_key = gd.game_key