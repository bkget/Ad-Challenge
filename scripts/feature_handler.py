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

    def features_correlation(self, X, Y):
        corr_df = pd.DataFrame(X.corrwith(Y)).sort_values(by=0, ascending=False)
        corr_df.rename({0: "ER"}, axis=1)
        corr = corr_df.T
        mask = np.zeros_like(corr, dtype=bool)
        mask[np.triu_indices_from(mask)] = True
        cmap = sns.diverging_palette(230, 20, as_cmap=True)
        fig, ax = plt.subplots(figsize=(18, 15))
        heatmap = sns.heatmap(corr, square=True, linewidths=.5,
                            vmin=-1, vmax=1, cmap='viridis', annot=True, fmt='.1f')
        heatmap.set_title('Correlation Between Features',
        fontdict={'fontsize': 16}, pad=12)
        