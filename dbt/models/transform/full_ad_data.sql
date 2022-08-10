{{ config(materialized='table') }}

SELECT 

    *
       
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