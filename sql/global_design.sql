-- ingesting global_design.csv 

DROP TABLE IF EXISTS global_design;
CREATE TABLE global_design (
    game_key text COLLATE pg_catalog."default" NOT NULL,
    labels_engagement text COLLATE pg_catalog."default",
    labels_click_through text COLLATE pg_catalog."default",
    text_engagement text COLLATE pg_catalog."default",
    text_click_through text COLLATE pg_catalog."default",
    color_engagement text COLLATE pg_catalog."default",
    color_click_through text COLLATE pg_catalog."default",
    video_data text COLLATE pg_catalog."default",
    direction text COLLATE pg_catalog."default",
    CONSTRAINT global_design_pkey PRIMARY KEY (game_key)
);

COPY global_design (game_key, labels_engagement, labels_click_through, text_engagement, 
                    text_click_through, color_engagement, color_click_through, 
                    video_data, direction)
FROM '/home/biruk/Documents/source/global_design_data.csv' DELIMITER ',' CSV HEADER; 
