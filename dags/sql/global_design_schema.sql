CREATE TABLE IF NOT EXISTS public.global_design
(
    game_key character varying(255) COLLATE pg_catalog."default" NOT NULL,
    labels_engagement text COLLATE pg_catalog."default",
    labels_click_through text COLLATE pg_catalog."default",
    text_engagement text COLLATE pg_catalog."default",
    text_click_through text COLLATE pg_catalog."default",
    color_engagement text COLLATE pg_catalog."default",
    color_click_through text COLLATE pg_catalog."default",
    video_data character varying(10) COLLATE pg_catalog."default",
    direction character varying(50) COLLATE pg_catalog."default",
    CONSTRAINT global_design_data_pkey PRIMARY KEY (game_key)
)