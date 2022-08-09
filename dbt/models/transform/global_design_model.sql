{{ config(materialized='table') }}

   SELECT     
        game_key, 
        labels_engagement, 
        labels_click_through, 
        text_engagement, 
        text_click_through, 
        video_data, 
        direction
       
   FROM  
        global_design