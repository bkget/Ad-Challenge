# Importing the necessary modules
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.models.baseoperator import chain

from datetime import datetime as dt
from sqlalchemy import Numeric
from datetime import timedelta
from sqlalchemy import Text
from airflow import DAG 
import pandas as pd


####################################################
#          Read data from the source               #
####################################################
#   
def read_briefing_data():
    data_df = pd.read_csv('/opt/airflow/data/briefing.csv')
    return data_df

def read_campaigns_inventory_data():
    data_df = pd.read_csv('/opt/airflow/data/campaigns_inventory_updated.csv')
    return data_df

def read_global_design_data_data():
    data_df = pd.read_csv('/opt/airflow/data/global_design_data.csv')
    return data_df

####################################################
#    Inserting the data to the postgres table      #
####################################################

def insert_briefing_data(): 
    pg_hook = PostgresHook(
    postgres_conn_id="pg_conn")
    conn = pg_hook.get_sqlalchemy_engine()
    data_df = read_briefing_data()

    data_df.to_sql("briefing",
        con=conn,
        if_exists="replace",
        index=False,
        dtype={
            "campaign_id_br": Text(), 
            "campaign_name": Text(), 
            "Submission Date": Text(), 
            "Description": Text(), 
            "Campaign Objectives": Text(), 
            "KPIs": Text(), 
            "Placement(s)": Text(), 
            "StartDate": Text(), 
            "EndDate": Text(), 
            "Serving Location(s)": Text(), 
            "Black/white/audience list included?": Text(), 
            "Delivery Requirements (Black/Audience/White List)": Text(),
            "Cost Centre": Text(), 
            "Currency": Text(), 
            "Buy Rate (CPE)": Numeric(), 
            "Volume Agreed": Numeric(), 
            "Gross Cost/Budget": Numeric(), 
            "Agency Fee": Text(), 
            "Percentage": Numeric(), 
            "Net Cost": Numeric()
            },
    )

def insert_campaigns_inventory_data(): 
    pg_hook = PostgresHook(
    postgres_conn_id="pg_conn")
    conn = pg_hook.get_sqlalchemy_engine()
    data_df = read_campaigns_inventory_data()

    data_df.to_sql("campaigns_inventory",
        con=conn,
        if_exists="replace",
        index=False,
        dtype={
            "width": Text(), 
            "height": Text(), 
            "campaign_id": Text(), 
            "creative_id": Text(), 
            "auction_id": Text(), 
            "browser_ts": Text(), 
            "game_key": Text(), 
            "geo_country": Text(), 
            "site_name": Text(), 
            "platform_os": Text(), 
            "device_type": Text(), 
            "browser": Text() 

        },
    )

def insert_global_design_data(): 
    pg_hook = PostgresHook(
    postgres_conn_id="pg_conn")
    conn = pg_hook.get_sqlalchemy_engine()
    data_df = read_global_design_data_data()

    data_df.to_sql("global_design",
        con=conn,
        if_exists="replace", 
        index=False,
        dtype={
            "game_key": Text(), 
            "labels_engagement": Text(), 
            "labels_click_through": Text(), 
            "text_engagement": Text(), 
            "text_click_through": Text(), 
            "color_engagement": Text(), 
            "color_click_through": Text(), 
            "video_data": Text(), 
            "direction": Text()

        },
    )

####################################################
#          Airflow DAG configurations              #
####################################################

# Specifing the default_args
default_args = {
    'owner': 'biruk',
    'depends_on_past': False,
    'email': ['bkgetmom@gmail.com'],
    'email_on_failure': True,
    'email_on_retry': True,
    'retries': 1,
    'start_date': dt(2022, 7, 18),
    'retry_delay': timedelta(minutes=5)
}

with DAG(
    dag_id='ELT_DAG',
    default_args=default_args,
    description='Upload data to Postgres and Transform it with dbt',
    schedule_interval='@once',
    catchup=False
) as pg_dag: 

 start = DummyOperator(task_id="start")
 end = DummyOperator(task_id="end")

 briefing_table_creator = PostgresOperator(
    task_id="create_briefing_table", 
    postgres_conn_id="pg_conn",
    sql = 'sql/briefing_schema.sql'
    )

 briefing_data_loader = PythonOperator(
    task_id="load_briefing_data",
    python_callable=insert_briefing_data
 )

 campaigns_inventory_table_creator = PostgresOperator(
    task_id="create_campaigns_inventory_table", 
    postgres_conn_id="pg_conn",
    sql = 'sql/campaigns_inventory_schema.sql'
    )

 campaigns_inventory_data_loader = PythonOperator(
    task_id="load_campaigns_inventory_data",
    python_callable=insert_campaigns_inventory_data
 )

 global_design_table_creator = PostgresOperator(
    task_id="create_global_design_table", 
    postgres_conn_id="pg_conn",
    sql = 'sql/briefing_schema.sql'
    )

 global_design_data_loader = PythonOperator(
    task_id="load_global_design_data",
    python_callable=insert_global_design_data 
 )

####################################################
#          dbt Transformation                      #
####################################################

 DBT_PROJECT_DIR = "/opt/airflow/dbt"
 dbt_run = BashOperator(
    task_id="dbt_run",
    bash_command=f"dbt run --profiles-dir {DBT_PROJECT_DIR} --project-dir {DBT_PROJECT_DIR}",
 )

 dbt_test = BashOperator(
    task_id="dbt_test",
    bash_command=f"dbt test --profiles-dir {DBT_PROJECT_DIR} --project-dir {DBT_PROJECT_DIR}",
 )

#  dbt_doc_generate = BashOperator(
#     task_id="dbt_doc_generate", 
#     bash_command="dbt docs generate --profiles-dir /opt/airflow/dbt --project-dir "
#                     "/opt/airflow/dbt"
#  )


####################################################
#          Task dependencies                       #
####################################################

chain(start, [campaigns_inventory_table_creator, briefing_table_creator, global_design_table_creator], [campaigns_inventory_data_loader, briefing_data_loader, global_design_data_loader], dbt_run, dbt_test, end)