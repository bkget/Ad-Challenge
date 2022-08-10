import json
import pandas as pd
from sqlalchemy import create_engine

def read_json(json_file: str) -> list:
    """Reads a JSON file and returns a list of items.
    
    Parameters
    ----------
    json_file : json
        The path to the JSON file to extract data from

    Return
    ------
    data_list : list
    len(data_list): integer    
        A list of JSON file items to extract data from and the length of the list.
    """
    with open(json_file, 'r') as json_file:
        json_data = json.load(json_file)
    data = json_data.items()
    data_list = list(data)
    return len(data_list), data_list

class JsonDataExtractor:
    """Extract the data from a JSON file and send the extracted data to Postgres database.
    """

    def __init__(self, cmp_list):
        self.cmp_list = cmp_list
        print('Data Extraction in progress...')
    
    def gamekey_extractor(self, json_file: json):
        """Extracts the gamekey from a JSON file.

        Parameters
        ----------
        json_file : json
            The path to the json file to extract data from

        Return
        ------
        key : list
            A list of game_key to auto_generated_request_id link
        """
        f = open(json_file)
        data = json.load(f)
        key=[]
        for game_key in data:
            for auto_generated_request_id in data[game_key]:
                key.append(game_key+'/'+auto_generated_request_id)
        return key

    def labels_engagement_extractor(self):
        """Extracts the labels engagement from a JSON file.
        
        Return
        ------
        labels_engagement: list 
            A list of labels engagement
        """
        labels_engagement = [] 
        for x in self.cmp_list:
            for k, v in x[1].items():
                labels_engagement.append(",".join(v['labels']['engagement']))
        return labels_engagement

    def labels_click_through_extractor(self):
        """Extracts the labels click_through from a JSON file.
        
        Return
        ------
        labels_click_through: list 
            A list of labels click_through
        """ 
        labels_click_through = [] 
        for x in self.cmp_list:
            for k, v in x[1].items():
                labels_click_through.append(",".join(v['labels']['click_through']))
        return labels_click_through

    def texts_engagement_extractor(self):
        """Extracts the texts engagement from the JSON file and returns a list of texts engagements information.

        Return
        ------
        text_engagement: list 
            A list of text_engagement
        """
        texts_engagement = [] 
        for x in self.cmp_list:
            for k, v in x[1].items():
                texts_engagement.append(",".join(v['text']['engagement']))
        return texts_engagement

    def texts_click_through_extractor(self):
        """Extracts the texts click_through from the JSON file and returns a list of texts click_through engagement information.

        Return
        ------
        texts_click_through: list 
            A list of texts_click_through
        """
        texts_click_through = [] 
        for x in self.cmp_list:
            for k, v in x[1].items():
                texts_click_through.append(",".join(v['text']['click_through']))
        return texts_click_through

    def colors_engagement_extractor(self):
        """Extract colors_engagement from the given JSON file.
        
        Return
        ------
        colors_engagement: list
            A list of colors engagements
        """
        colors_engagement = [] 
        for x in self.cmp_list:
            for k, v in x[1].items():
                colors_engagement.append(v['colors']['engagement']) 
        return colors_engagement

    def colors_click_through_extractor(self):
        """Extract colors_click_through from the given JSON file.
        
        Return
        ------
        colors_click_through: list
            A list of colors click_through
        
        """
        colors_click_through = [] 
        for x in self.cmp_list:
            for k, v in x[1].items():
                colors_click_through.append(v['colors']['click_through']) 
        return colors_click_through

    def video_data_extractor(self):
        """Extract video data from the given JSON file.

        Return
        ------
        video_data: list
            A list of video_data information
        """
        video_data = [] 
        for x in self.cmp_list:
            for k, v in x[1].items():
                video_data.append(v['videos_data']['has_video']) 
        return video_data

    def direction_extractor(self):
        """Extract direction information from the given JSON file.

        Return
        ------
        direction: list
            A list of direction information        
        """
        direction = [] 
        for x in self.cmp_list:
            for k, v in x[1].items():
                direction.append(v['direction']['direction']) 
        return direction       

    def main(self, game_key, labels_engagement, labels_click_through, text_engagement, text_click_through, color_engagement, color_click_through, video_data, direction):
        """Save the extracted information from JSON file to a postgresql database.        
        """
        engine = create_engine('postgresql://airflow:airflow@localhost:5432/ad_lake')
        global_design_df = pd.DataFrame()
        global_design_df['game_key'] = game_key
        global_design_df['labels_engagement'] = labels_engagement 
        global_design_df['labels_click_through'] = labels_click_through
        global_design_df['text_engagement'] = text_engagement
        global_design_df['text_click_through'] = text_click_through
        global_design_df['color_engagement'] = color_engagement
        global_design_df['color_click_through'] = color_click_through
        global_design_df['video_data'] = video_data
        global_design_df['direction'] = direction

        try:
            # Execute the data engestion to the database
            global_design_df.to_sql('briefing_data', engine)
            print("Data Inserted to the Database Successfully!")

        except Exception as e: 
            print("Error: ", e)


if __name__ == "__main__":
    path = "../data/global_design_data.json"
    _, data_list = read_json(path)
    
    extractor = JsonDataExtractor(data_list)
    game_key = extractor.gamekey_extractor(path)
    labels_engagement = extractor.labels_engagement_extractor()
    labels_click_through = extractor.labels_click_through_extractor()
    text_engagement = extractor.texts_engagement_extractor()
    text_click_through = extractor.texts_click_through_extractor()
    color_engagement = extractor.colors_engagement_extractor()
    color_click_through = extractor.colors_click_through_extractor()
    video_data = extractor.video_data_extractor()
    direction = extractor.direction_extractor()

    extractor.main(game_key, labels_engagement,labels_click_through, text_engagement, text_click_through, color_engagement, color_click_through, video_data, direction)

