{{ config(materialized='table') }}

    SELECT * from 
        
        {{ ref('campaign_inventory_model') }} ci

    LEFT JOIN 
        {{ ref('briefing_model') }} br

    ON     
        ci.campaign_id = br.campaign_id_br