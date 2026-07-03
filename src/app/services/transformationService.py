import numpy as np


class transformationService:
    def __init__(self):
        pass

    def rocchio_embedding(q0, rel_embs, nonrel_embs=None, alpha=1.0, beta=0.75, gamma=0.15):
        q = alpha * np.array(q0)
        if rel_embs:
            q += beta * np.mean(rel_embs, axis=0)
        if nonrel_embs:
            q -= gamma * np.mean(nonrel_embs, axis=0)
        return q / np.linalg.norm(q)   
    
    

