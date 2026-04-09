from pydantic import BaseModel
from typing import List, Dict

class BenchmarkConfig(BaseModel):
    base_url: str = "http://localhost:8000"
    num_runs: int = 5
    alpha_values: Dict[str, float] = {
        "vector_only": 1.0,
        "graph_only": 0.0,
        "hybrid": 0.65
    }
    k_values: List[int] = [5, 10]
    output_dir: str = "evaluation/results"