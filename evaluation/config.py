from pydantic import BaseModel
from typing import List, Dict

class BenchmarkConfig(BaseModel):
    base_url: str = "http://localhost:8000"
    num_runs: int = 1   # System is deterministic — 1 run is sufficient
    # Keys map to paper labels:
    #   B1=vector_only, B2=graph_only
    #   G-0.1 ... G-0.7 = hybrid variants (alpha = vector weight)
    alpha_values: Dict[str, float] = {
        "B1_vector_only": 1.0,
        "B2_graph_only":  0.0,
        "G_0.1": 0.1,
        "G_0.2": 0.2,
        "G_0.3": 0.3,
        "G_0.5": 0.5,
        "G_0.7": 0.7,
    }
    k_values: List[int] = [5, 10]
    output_dir: str = "evaluation/results"
