import logging

class Logging:
    def __init__(self,name=None):
        if name is None:
            logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')  
        else:
            #with open(f'./logs/{name}.log','w') as f:
            #    pass // This code has to be put somewhere 
            logging.basicConfig(filename=f"./logs/{name}.log",encoding='utf-8',level = logging.INFO)
        # Create a logger object
        self.logger = logging.getLogger(__name__)
#        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(logging.StreamHandler()) if name is None else None
        
        
        