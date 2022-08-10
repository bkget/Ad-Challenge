import numpy as np
import pandas as pd
import seaborn as sns 
import matplotlib.pyplot as plt

class FeatureHandler:
       
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df  
        print('Feature handler initialized...')

    def compute_kpi(self):
        """ Compute the KPI of the corresponding campaign_id's by calculating Engagement 
            and Click Through Rate
        """

        self.df = self.df.groupby(['campaign_id','type'])['type'].agg(count='count').reset_index()
        campaign_info = []
        er = 0; ctr= 0
        campaigns = list(self.df['campaign_id'].unique())
        for campaign in campaigns: 
            types = list(self.df[self.df['campaign_id'] == campaign]['type']) 

            if 'impression' in types:
                total_impression = list(self.df.query(f" campaign_id == '{campaign}' and type == 'impression'")['count'])[0]
                
                if 'first_dropped' in types:
                    first_dropped_count = list(self.df.query(f" campaign_id == '{campaign}' and type == 'first_dropped'")['count'])[0]
                    er = (first_dropped_count/total_impression) * 100

                if 'click-through-event' in types:
                    click_through_event_count = list(self.df.query(f" campaign_id == '{campaign}' and type == 'click-through-event'")['count'])[0]
                    ctr = (click_through_event_count/total_impression) * 100 

            campaign_info.append([campaign, er, ctr])

        self.df=pd.DataFrame(campaign_info, columns=['campaign_id','ER' , 'CTR'])
        
        return self.df

    