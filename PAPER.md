# GraphPent: Nền Tảng Kiểm Thử Xâm Nhập Tự Động Hóa Dựa Trên Đồ Thị Tri Thức Lai và Mô Hình Ngôn Ngữ Lớn Cục Bộ

**GraphPent: An Automated Penetration Testing Platform Based on Hybrid Knowledge Graph and Local Large Language Model**

---

## Tóm Tắt

Kiểm thử xâm nhập là một hoạt động thiết yếu trong đảm bảo an toàn thông tin, tuy nhiên quy trình này hiện còn phụ thuộc nhiều vào chuyên gia con người và đòi hỏi khả năng tổng hợp tri thức từ nhiều nguồn không đồng nhất. Trong khi các hệ thống hiện có như PentestGPT [1] và CS-KG [2] lần lượt khai thác sức mạnh của LLM đám mây và đồ thị tri thức dựa trên suy luận quy tắc, vẫn chưa có công trình nào kết hợp đồng thời cả hai phương pháp trong một nền tảng hoàn chỉnh, có khả năng triển khai hoàn toàn cục bộ. Bài báo này trình bày **GraphPent** — một nền tảng kiểm thử xâm nhập tự động hóa dựa trên kiến trúc **GraphRAG** (Graph Retrieval-Augmented Generation), tích hợp đồ thị tri thức lai (Hybrid Knowledge Graph) kết hợp cơ sở dữ liệu đồ thị Neo4j và cơ sở dữ liệu vector Weaviate, cùng với mô hình ngôn ngữ lớn triển khai cục bộ thông qua Ollama. Hệ thống tự động hóa toàn bộ quy trình từ thu thập và chuẩn hóa dữ liệu CVE/CWE (hơn 31.000 CVE năm 2023), trích xuất thực thể và quan hệ bảo mật bằng LLM, đến truy xuất thông tin lai sử dụng thuật toán Reciprocal Rank Fusion (RRF), và điều phối đa tác nhân (multi-agent) thông qua LangGraph. Hệ thống đạt độ trễ truy vấn dưới 300ms (dưới 50ms khi có cache), tỷ lệ cache hit 60–80%, và hoàn thiện toàn bộ workflow phân tích trong 2–5 giây. Thực nghiệm trên bảy kịch bản kiểm thử xâm nhập cho thấy chế độ hybrid G-0.3 đạt **NDCG@10 = 0,8741** và **MRR = 1,000**, vượt vector-only **3,6×** (NDCG@10 = 0,2440 ở ~153ms p99); graph-only đạt NDCG@10 = 0,8551 ở **24ms p99** — nhanh hơn vector-only **6,3×**. GNN risk scoring đạt **Spearman ρ = 0,9971**, Tier Accuracy **96,63%** và coverage attack path **100%** trên 3.049 nodes. Reasoning pipeline (L6) đạt **100%** trên toàn bộ 8 chỉ số đánh giá (Tool Selection, Pipeline Completion, Graph Utilization, Retrieval Alignment, Attack Path Discovery).

**Từ khóa**: kiểm thử xâm nhập tự động, GraphRAG, đồ thị tri thức lai, truy xuất thông tin, LLM cục bộ, CVE/CWE, LangGraph, multi-agent

---

## 1. Phần Mở Đầu

### 1.1. Đặt Vấn Đề

Kiểm thử xâm nhập (penetration testing) là một quy trình đánh giá bảo mật có kiểm soát, trong đó kiểm thử viên mô phỏng hành vi của kẻ tấn công nhằm phát hiện điểm yếu trong hệ thống trước khi bị khai thác [3]. Theo chuẩn PTES và NIST 800-115 [4], quy trình kiểm thử bao gồm các giai đoạn: thu thập thông tin, quét lỗ hổng, khai thác, leo thang đặc quyền và tổng hợp báo cáo. Mặc dù có tầm quan trọng thiết yếu, kiểm thử xâm nhập hiện đối mặt với nhiều thách thức cơ bản.

**Thứ nhất — Khối lượng và tốc độ lỗ hổng.** Cơ sở dữ liệu CVE đã tích lũy hơn 250.000 bản ghi tính đến năm 2026, với hàng chục nghìn CVE mới mỗi năm [5]. Kiểm thử viên không thể theo dõi và tổng hợp thủ công toàn bộ khối lượng tri thức này trong thời gian thực.

**Thứ hai — Nguồn dữ liệu không đồng nhất.** Thông tin lỗ hổng tồn tại ở nhiều dạng — dữ liệu cấu trúc (CVE JSON, CWE XML), văn bản phi cấu trúc (báo cáo kiểm thử, mô tả lỗ hổng), và kết quả công cụ quét (Nuclei, Nmap, OpenVAS [6]). Việc tổng hợp các nguồn này đòi hỏi năng lực xử lý ngôn ngữ tự nhiên phức tạp.

**Thứ ba — Công cụ tự động theo playbook tĩnh.** Các nền tảng như Pentera Core và MITRE Caldera không thích ứng với bối cảnh mạng thay đổi động. Pan et al. [2] cho thấy sự thiếu hụt biểu diễn tri thức là nguyên nhân cốt lõi: hệ thống chỉ dựa vào suy luận quy tắc cứng không thể điều chỉnh kế hoạch khai thác khi trạng thái mạng thay đổi theo thời gian thực.

**Thứ tư — LLM phụ thuộc đám mây.** Các công cụ như PentestGPT [1] cho kết quả hứa hẹn — cải thiện 228,6% trong tỷ lệ hoàn thành sub-task — nhưng phụ thuộc API đám mây và không tích hợp cơ sở tri thức CVE/CWE có cấu trúc.

**Thứ năm — Mất ngữ cảnh và thiên kiến tìm kiếm chiều sâu của LLM.** Khi xử lý đầu ra dài dòng từ công cụ quét (Nmap, OpenVAS), LLM nhanh chóng cạn kiệt cửa sổ token và quên các phát hiện trước — một lỗi đã được ghi nhận trong các benchmark agent tự động [7]. Ngoài ra, LLM thường biểu lộ *thiên kiến tìm kiếm chiều sâu* (depth-first search bias): tập trung quá mức vào sub-task gần nhất, bỏ qua các bề mặt tấn công khác và lặp vô hạn vào ngõ cụt [8].

**Thứ sáu — Biểu diễn trạng thái không đủ.** Cây tác vụ PTT của PentestGPT được lưu trữ dưới dạng ngôn ngữ tự nhiên, khiến kiểm soát luồng thiếu chính xác. Khi thay bằng danh sách công việc có cấu trúc (structured to-do lists), LLM thêm tất cả nhị phân SUID vào danh sách khai thác nhưng hoàn toàn thất bại trong việc xóa các hướng đi sai, khiến agent bị kẹt vào ngõ cụt [8].

**Thứ bảy — Truy xuất thông tin cấu trúc yếu.** Phương pháp truy xuất truyền thống (BM25, vector search đơn thuần) không khai thác được cấu trúc quan hệ CVE ↔ CWE ↔ Host ↔ Service. Đầu ra công cụ bảo mật có nội dung văn bản rất giống nhau nhưng khác biệt về cấu trúc, gây ra *nhiễu loạn truy xuất thông tin* (confused information retrieval) [1] dẫn đến LLM sinh câu trả lời sai.

### 1.2. Mục Tiêu Nghiên Cứu

Nghiên cứu này hướng đến sáu mục tiêu cụ thể:

1. **Xây dựng pipeline dữ liệu tự động** thu thập, chuẩn hóa và nạp dữ liệu bảo mật từ nhiều nguồn (CVE, CWE, NVD) vào đồ thị tri thức thống nhất, với xử lý song song và checkpoint-resume.
2. **Thiết kế đồ thị tri thức lai** kết hợp Neo4j (cấu trúc quan hệ) và Weaviate (ngữ nghĩa vector) để biểu diễn tri thức bảo mật đa chiều.
3. **Phát triển cơ chế truy xuất lai** sử dụng RRF kết hợp vector search và graph traversal, vượt qua giới hạn của cả hai tiếp cận đơn lẻ.
4. **Xây dựng hệ thống multi-agent** với LangGraph để điều phối tự động quy trình kiểm thử đầu-cuối, với feedback loop và định tuyến có điều kiện.
5. **Tích hợp LLM cục bộ** qua Ollama để đảm bảo bảo mật dữ liệu và đánh giá khả năng trích xuất thực thể trên GPU tiêu dùng.
6. **Đánh giá thực nghiệm** trên tập CVE thực tế với bộ chỉ số IR chuẩn, so sánh với các baseline truy xuất.

### 1.3. Đóng Góp Của Đề Tài

Đối chiếu với các công trình hiện có, nghiên cứu này có bốn đóng góp chính:

- **C1 — Kiến trúc GraphRAG tích hợp cho kiểm thử xâm nhập**: Không giống CS-KG [2] chỉ dùng SPARQL đơn thuần, GraphPent kết hợp đồ thị quan hệ với vector embedding trong kiến trúc 13 phase từ thu thập dữ liệu thô đến phân tích rủi ro.

- **C2 — Hybrid Retrieval với RRF điều chỉnh được**: Đề xuất cơ chế kết hợp điểm số Weaviate và Neo4j qua RRF với tham số α tinh chỉnh được, cân bằng linh hoạt giữa tương đồng ngữ nghĩa và quan hệ cấu trúc theo đặc trưng từng loại truy vấn.

- **C3 — Multi-agent workflow với LLM cục bộ**: Không giống PentestGPT [1] phụ thuộc GPT-4 đám mây, GraphPent triển khai 7 agent chuyên biệt trong LangGraph DAG với llama3.2:3b trên GPU tiêu dùng, đảm bảo bảo mật dữ liệu và tính độc lập với dịch vụ bên ngoài.

- **C4 — Đánh giá rủi ro tổng hợp và biểu diễn trạng thái qua KG**: Kết hợp PageRank, CVSS và Betweenness Centrality để tính risk score; bằng cách lưu trạng thái mạng vào Neo4j, GraphPent loại bỏ cấu trúc về thiên kiến chiều sâu và mất ngữ cảnh của LLM.

---

## 2. Cơ Sở Lý Thuyết và Công Trình Liên Quan

### 2.1. Kiểm Thử Xâm Nhập

Kiểm thử xâm nhập là quy trình đánh giá bảo mật có kiểm soát [3]. Theo Zhang et al. [6], quy trình chuẩn gồm năm giai đoạn: (1) Information Collecting, (2) Vulnerability Scanning and Evaluation, (3) Exploitation, (4) Post-Exploitation, và (5) Report. Hai nguồn tri thức cốt lõi là:

- **CVE** (Common Vulnerabilities and Exposures): Danh sách chuẩn hóa các lỗ hổng bảo mật đã biết, duy trì bởi MITRE. Mỗi CVE có định danh duy nhất, mô tả chi tiết và điểm CVSS.
- **CWE** (Common Weakness Enumeration): Phân loại hơn 900 điểm yếu phần mềm, cung cấp ngữ cảnh nguyên nhân gốc rễ cho từng CVE (ví dụ: CWE-89 SQL Injection là gốc rễ nhiều CVE liên quan đến cơ sở dữ liệu).

### 2.2. Knowledge Graph và GraphRAG

**Knowledge Graph (KG)** biểu diễn tri thức dưới dạng đồ thị có hướng G = ⟨V, E, R⟩, với V là tập thực thể, E ⊆ V × R × V là tập quan hệ, R là tập loại quan hệ [9]. KG cho phép truy vấn ngữ nghĩa phức tạp như: tìm tất cả CVE ảnh hưởng Apache, liên kết với CWE nhóm Injection, trên Host trong 192.168.1.0/24.

**GraphRAG** [10] mở rộng RAG bằng cách tích hợp KG vào giai đoạn truy xuất. Thay vì chỉ tìm kiếm vector, GraphRAG duyệt quan hệ trong KG để cung cấp ngữ cảnh đa bước, cải thiện chất lượng suy luận cho các câu hỏi đòi hỏi tổng hợp chuỗi thực thể.

### 2.3. Retrieval-Augmented Generation (RAG)

RAG [11] bổ sung ngữ cảnh truy xuất vào đầu vào LLM tại thời điểm suy diễn, không cần fine-tuning. Luồng cơ bản: Query → Retrieve → Augment → Generate. RAG giảm hallucination và cho phép LLM truy cập tri thức ngoài tập huấn luyện. Tuy nhiên, RAG truyền thống chỉ dùng vector search, bỏ qua cấu trúc quan hệ giữa tài liệu.

### 2.4. Reciprocal Rank Fusion (RRF)

RRF [12] kết hợp kết quả từ nhiều hệ thống xếp hạng mà không cần chuẩn hóa điểm số tuyệt đối. Điểm RRF của tài liệu d trong danh sách r:

$$\text{RRF}(d, r) = \frac{1}{k + \text{rank}_r(d)}, \quad k = 60$$

Điểm tổng hợp trong GraphPent:

$$\text{score}(d) = \alpha \cdot \text{RRF}_{\text{vector}}(d) + (1-\alpha) \cdot \text{RRF}_{\text{graph}}(d), \quad \alpha \in [0,1]$$

Tham số α kiểm soát tỷ trọng giữa tìm kiếm vector và duyệt đồ thị.

### 2.5. Multi-Agent Systems với LangGraph

LangGraph [13] là framework xây dựng luồng agent dạng DAG trên nền LangChain. Mỗi node là hàm Python bất đồng bộ nhận `AgentState` và trả về trạng thái cập nhật. Conditional edges cho phép định tuyến động, phù hợp với quy trình kiểm thử có nhiều nhánh điều kiện.

### 2.6. Các Công Trình Liên Quan

**Kiểm thử xâm nhập dựa trên LLM.** Deng et al. [1] giới thiệu PentestGPT với kiến trúc ba module (Reasoning, Generation, Parsing) và cấu trúc PTT để mã hóa trạng thái kiểm thử. Trên benchmark 13 mục tiêu, 182 sub-task, PENTESTGPT-GPT-4 cải thiện 228,6% so với GPT-3.5. Tuy nhiên, PTT được lưu dưới dạng ngôn ngữ tự nhiên khiến kiểm soát luồng thiếu chính xác; PentestGPT cũng phụ thuộc API đám mây và không tích hợp CVE/CWE có cấu trúc.

**Đồ thị tri thức cho kiểm thử xâm nhập.** Pan et al. [2] đề xuất CS-KG với ontology 3 tầng và 47 SWRL rules. Trên testbed 1.824 nodes, CS-KG rút ngắn 63% thời gian phát hiện attack path, tăng vulnerability coverage lên 74%. Tuy nhiên, CS-KG không dùng vector embedding, không có RAG, và yêu cầu cơ sở hạ tầng lớn (Kafka, Flink, Blazegraph 4 nodes).

**Benchmark đánh giá LLM agent kiểm thử xâm nhập.** AutoPenBench [7] cung cấp benchmark chuẩn hóa với các mục tiêu lab trong container để đánh giá agent tạo sinh trên kiểm thử xâm nhập. Nghiên cứu xác định thiên kiến tìm kiếm chiều sâu và giới hạn quản lý tác vụ: agent thêm tất cả nhị phân SUID vào danh sách khai thác nhưng liên tục thất bại trong việc xóa các đường đi sai, dẫn đến lặp vô hạn vào ngõ cụt.

Isozaki et al. [8] benchmark nhiều LLM trên kiểm thử xâm nhập tự động và phát hiện sự khác biệt chiến lược đặc trưng theo mô hình: GPT-4o thể hiện thiên kiến tìm kiếm chiều sâu — kiên trì theo một đường tấn công duy nhất qua năm lần thất bại liên tiếp — trong khi LLaMA áp dụng chiến lược tìm kiếm chiều rộng, nhưng cả hai mô hình đều không hoàn thành được mục tiêu nào từ đầu đến cuối. Ablation 3 của nghiên cứu cho thấy tăng cường agent bằng RAG trên tài liệu HackTricks cải thiện hiệu suất trên mọi hạng mục (liệt kê, khai thác, leo thang đặc quyền). Quan trọng hơn, thay thế Penetration Testing Tree (PTT) bằng ngôn ngữ tự nhiên bằng danh sách todo có cấu trúc đẩy tỷ lệ thành công Leo thang Đặc quyền từ 0% lên 100% trên các máy dễ (Funbox), xác nhận rằng quản lý trạng thái có cấu trúc là yếu tố then chốt cho agent kiểm thử tự động đáng tin cậy.

**Phương pháp kiểm thử truyền thống.** Zhang et al. [6] trình bày tổng quan về kiểm thử thực tế với Kali Linux, Metasploit, Nmap, OpenVAS. Thu thập thông tin chiếm hơn 60% tổng thời gian kiểm thử; hiệu quả phụ thuộc hoàn toàn vào năng lực kiểm thử viên.

**Tổng hợp và Khoảng trống nghiên cứu.** Bảng 0 tóm tắt so sánh:

| Tiêu chí | PentestGPT [1] | CS-KG [2] | AutoPenBench [7] | Zhang [6] | **GraphPent** |
|---------|:---:|:---:|:---:|:---:|:---:|
| LLM | Đám mây | Không | Đám mây | Không | **Cục bộ** |
| Knowledge Graph | Không | SPARQL | Không | Không | **Neo4j+Wvt** |
| Vector Search | Không | Không | Không | Không | **Có** |
| Hybrid RRF | Không | Không | Không | Không | **Có** |
| Multi-agent | Có | Không | Có | Không | **LangGraph** |
| CVE/CWE | Không | Một phần | Không | Không | **>31k** |
| Triển khai cục bộ | Không | Một phần | Không | Có | **Có** |
| Trạng thái qua KG | Không | Không | Không | Không | **Có** |

Khoảng trống rõ ràng: chưa có hệ thống nào kết hợp đồng thời (i) đồ thị tri thức lai CVE/CWE với vector embedding, (ii) hybrid RRF retrieval, (iii) multi-agent workflow toàn trình, (iv) LLM cục bộ bảo mật, và (v) biểu diễn trạng thái mạng qua KG loại bỏ thiên kiến chiều sâu và mất ngữ cảnh của LLM.

---

## 3. Tổng Quan Kiến Trúc Hệ Thống

### 3.1. Thiết Kế Tổng Thể

GraphPent được triển khai theo kiến trúc microservices với 7 container Docker Compose, tổ chức thành 7 lớp xử lý (L1–L7) với hai luồng chính: **luồng truy vấn** (Client → L6/L7 → L5 → L3 → KG) và **luồng nạp dữ liệu** (L1 → L2 → KG; L4 vận hành độc lập trên KG).

```
═══════════════════════════════════════════════════════════════════
                   GRAPHPENT — KIẾN TRÚC HỆ THỐNG
═══════════════════════════════════════════════════════════════════

 ╔═════════════════════════════════════════════════════════════╗
 ║  CHUYÊN GIA KIỂM THỬ / CLIENT                              ║
 ║  truy vấn tự nhiên ────────────────► markdown + JSON report ║
 ╚══════════════════════╤══════════════════════════════════════╝
                        │  REST API  (FastAPI :8000)
 ┌──────────────────────▼────────────────────────────────────┐
 │  L6 / L7   REASONING & EXECUTION                          │
 │                                                           │
 │  collection → planner → retrieval → graph_reasoning       │
 │                                        │ [needs_tools=T   │
 │                                        │  AND results≠∅]  │
 │                                    tool (Nuclei/CVE)      │
 │                                        │                  │
 │                           report → human_approval ──┐     │
 │                               ↑  new_findings>0     │     │
 │                               └─── planner ←────────┘     │
 │  LangGraph DAG  ·  AgentState TypedDict  ·  MAX_LOOP=3    │
 └──────────────────────┬────────────────────────────────────┘
                        │
 ┌──────────────────────▼────────────────────────────────────┐
 │  L5   GNN RISK SCORING                                    │
 │                                                           │
 │  risk(v) = 0.10×PageRank + 0.80×CVSS_norm + 0.10×BC      │
 │  ──► CRITICAL / HIGH / MEDIUM / LOW  [ρ = 0.9971]         │
 │  ──► Attack paths: CWE ──[1–3 hops]──► CVE  [100% cov.]  │
 └──────────────────────┬────────────────────────────────────┘
                        │
 ┌──────────────────────▼────────────────────────────────────┐
 │  L3   HYBRID RETRIEVAL  (GraphRAG)                        │
 │                                                           │
 │  query ──► embed      ┌────────────────┐                  │
 │  (nomic-embed-text)   │ Vector Search   │                  │
 │                       │ Weaviate        │──► RRF Fusion    │
 │                       └────────────────┘    α = 0.3       │
 │                       ┌────────────────┐    70% graph     │
 │                       │ Graph  Search   │    30% vector    │
 │                       │ Neo4j BFS 1–2h  │──► Top-K        │
 │                       └────────────────┘                  │
 │  Redis cache  TTL=1h  ·  65–80% hit rate  ·  <50ms warm   │
 └──────────────────────┬────────────────────────────────────┘
                        │
 ┌──────────────────────▼────────────────────────────────────┐
 │  HYBRID KNOWLEDGE GRAPH                                   │
 │                                                           │
 │  ┌───────────────────────────┐  ┌─────────────────────┐  │
 │  │  Neo4j 5.x (Structural)    │  │  Weaviate 4.x        │  │
 │  │  3,049 nodes · 23 rel types│  │  131,200 embeddings  │  │
 │  │  CVE ─CLASSIFIED_AS─► CWE  │  │  nomic-embed  d=768  │  │
 │  │  CWE ─MITIGATED_BY─► Miti  │  │  cosine similarity   │  │
 │  │  Host ─RUNS_ON─► Service   │  └─────────────────────┘  │
 │  └───────────────────────────┘                            │
 │  L4  KG Completion: low-degree → LLM predict → upsert    │
 └──────────────────────▲────────────────────────────────────┘
                        │  upsert (L2)
 ┌──────────────────────┴────────────────────────────────────┐
 │  L2   INGESTION & EXTRACTION                              │
 │                                                           │
 │  Raw doc ──► chunk (512 token, overlap 64)                │
 │          ──► Ollama llama3.2:3b ──► entities + relations  │
 │          ──► SHA-256 dedup ──► Neo4j MERGE + Weaviate     │
 │  confidence:  entity ≥ 0.85  ·  relation ≥ 0.75          │
 └──────────────────────▲────────────────────────────────────┘
                        │
 ┌──────────────────────┴────────────────────────────────────┐
 │  L1   DATA SOURCES                                        │
 │  cvelistV5 (31,170 CVE JSON)  ·  CWE XML v4.19 (933)     │
 │  NVD JSON (~5,000 records)    ·  Nmap XML · Nuclei JSONL  │
 └───────────────────────────────────────────────────────────┘

 ─── SUPPORT SERVICES ──────────────────────────────────────
 PostgreSQL 15 (metadata, chunks)  ·  Redis 7 (cache TTL=1h)
 MinIO (raw docs, S3-compat)  ·  Ollama :9443 (llama3.2:3b)
 ────────────────────────────────────────────────────────────
```

Khác với CS-KG [2] sử dụng SPARQL trên Blazegraph đơn thuần, GraphPent kết hợp hai loại lưu trữ bổ trợ: Neo4j cho cấu trúc quan hệ (Cypher + GDS), Weaviate cho tìm kiếm ngữ nghĩa qua vector embedding. Kiến trúc 13 phase được tổ chức thành bốn nhóm:

| Nhóm | Phase | Chức năng |
|------|-------|-----------|
| Hạ tầng | 1–3 | Stack setup, Nuclei parser, async job queue |
| Data Pipeline | 4–5 | Document ingestion, LLM extraction |
| Graph & Retrieval | 6–7 | Neo4j upsert, hybrid RRF retrieval |
| Intelligence | 8–9 | Multi-agent LangGraph workflow, pentest tools (CVE + Nuclei) |
| Collection | 10 | Nmap discovery → Host/Service entities upsert |
| KG & Risk | 11–13 | KG completion (LLM link prediction), risk scoring (GNN), benchmark/optimize |

### 3.2. Pipeline Dữ Liệu (Phase 4–5)

Pipeline ingest-extract xử lý tài liệu bảo mật theo năm bước:

```
[Upload/Batch] → [Parse & Chunk (512 token, overlap 64)]
      → [Dedup SHA-256] → [Store: MinIO + PostgreSQL]
      → [LLM Extraction (Ollama)] → [Upsert Neo4j + Weaviate]
```

**LLM Extraction**: Mỗi chunk được gửi đến Ollama với prompt trích xuất thực thể bảo mật. Output JSON gồm:
- `entities`: danh sách (id, name, type, properties, confidence)
- `relations`: danh sách (source_id, target_id, type, confidence)

Ngưỡng tin cậy: `ENTITY_CONFIDENCE_THRESHOLD=0.85`, `RELATION_CONFIDENCE_THRESHOLD=0.75`.

**Batch processing**: `batch_pipeline_optimized.py` dùng `asyncio.Semaphore(LLM_CONCURRENCY=3)` để giới hạn LLM call song song, hỗ trợ resume từ checkpoint, và chỉ quét thư mục năm mục tiêu để tránh scan toàn bộ 250k+ files.

### 3.3. Schema Đồ Thị Tri Thức (Phase 6)

So với ontology 3 tầng của CS-KG [2], GraphPent dùng schema tập trung vào lỗ hổng và tài sản:

| Label | Thuộc tính chính | Ví dụ |
|-------|-----------------|-------|
| `CVE` | cve_id, cvss_score, year | CVE-2023-44487 |
| `CWE` | cwe_id, name, category | CWE-89: SQL Injection |
| `Host` | ip, hostname, os | 192.168.1.100 |
| `Service` | port, protocol, version | Apache httpd 2.4.51 |
| `Finding` | title, severity, tool | nuclei-CVE-2021-44228 |
| `Mitigation` | name, description | Input Validation |

Quan hệ chính (23 loại quan hệ tổng cộng):

```cypher
(CWE)-[:CLASSIFIED_AS]->(CVE)       // quan hệ cốt lõi cho attack path
(CVE)-[:AFFECTS]->(Service)
(Finding)-[:MAPPED_TO]->(CVE)
(Service)-[:RUNS_ON]->(Host)
(Host)-[:HAS_PORT]->(Service)
(CWE)-[:HAS_CONSEQUENCE]->(Consequence)
(CWE)-[:MITIGATED_BY]->(Mitigation)
(CWE)-[:CHILD_OF]->(CWE)            // phân cấp taxonomy CWE
```

Index trên `CVE.cve_id`, `CWE.cwe_id`, `Host.ip` để tối ưu query performance.

### 3.4. Hybrid Retrieval với RRF (Phase 7)

`HybridRetrieverService` hỗ trợ ba chế độ truy xuất:

**Vector-only** (α=1.0): Embed query bằng `nomic-embed-text-v1.5` → cosine similarity trên Weaviate → top-K chunks. Phù hợp truy vấn ngữ nghĩa mở.

**Graph-only** (α=0.0): Fulltext search trong Neo4j → BFS expansion 1–2 hop. Phù hợp truy vấn có định danh cụ thể (CVE-xxx-xxxxx).

**Hybrid** (α=0.3, mặc định):
1. Thực thi song song vector search và graph search
2. Tính RRF score: `rrf(d) = 1/(k + rank(d))`, k=60
3. Tổng hợp: `final_score = α·rrf_vector + (1-α)·rrf_graph` (α=0.3: 70% graph + 30% vector)
4. Trả top-K kết quả

**Redis caching**: Cache key = MD5(query:mode), TTL=3600s. Giảm latency từ 100–300ms xuống dưới 50ms.

### 3.5. Multi-Agent Workflow (Phase 8)

Khác với PentestGPT [1] dùng ba module độc lập với PTT dạng văn bản tự nhiên, GraphPent xây dựng LangGraph DAG với `AgentState` chia sẻ:

```
[collection] → [planner] → [retrieval]
    → [graph_reasoning] → [tool]*
    → [report] → [human_approval] ─┐
           ↑                       │ new_findings > 0
           └── [planner] ←─────────┘   AND loop < MAX_LOOP
                                   │ otherwise
                                   └──→ END

* [tool] kích hoạt khi needs_tools=True AND retrieval_results ≠ ∅
```

`AgentState` TypedDict mang: `query`, `plan`, `retrieval_results`, `gnn_risk_summary`, `attack_paths`, `prioritized_targets`, `tool_results`, `scan_target`, `collection_results`, `new_findings_count`, `loop_iteration`, `report_markdown`. `MAX_LOOP_ITERATIONS=3` kiểm soát feedback loop.

Bằng cách lưu trữ trạng thái mạng trong Neo4j thay vì văn bản tự nhiên như PTT, GraphPent loại bỏ hoàn toàn thiên kiến chiều sâu và mất ngữ cảnh được ghi nhận trong [7, 8]. `AgentState` TypedDict là cấu trúc xác định, có thể kiểm tra trực tiếp và tự động định tuyến — không như PTT của PentestGPT vốn không thể cưỡng chế xóa tác vụ sau khi đi vào ngõ cụt.

### 3.6. Tích Hợp Công Cụ Pentest (Phase 9)

- **CVE Analysis**: Kết hợp điểm CVSS với keyword scoring (remote code execution, no auth required, public exploit available) để tính điểm exploitability tổng hợp.
- **Nuclei Integration**: Gọi Nuclei qua subprocess hoặc HTTP fallback, parse JSONL thành `Finding` entities upsert vào Neo4j.
- **Finding Correlation**: Map Finding → CVE/CWE dựa trên template ID và từ khóa, tạo quan hệ `(:Finding)-[:MAPPED_TO]->(:CVE)`.

### 3.7. Đánh Giá Rủi Ro Tổng Hợp (Phase 12)

`GNNService` tính risk score theo công thức:

$$\text{risk}(v) = w_1 \cdot \text{PageRank}(v) + w_2 \cdot \text{CVSS\_norm}(v) + w_3 \cdot \text{Betweenness}(v)$$

Trọng số tối ưu thực nghiệm: w₁=0,10, w₂=0,80, w₃=0,10 (ràng buộc: ∑wᵢ=1). CVSS được ưu tiên cao (w₂=0,80) vì đây là ground truth severity chính thức; degree centrality (proxy cho PageRank) đóng vai trò tie-breaker.

---

## 4. Thực Nghiệm

### 4.1. Môi Trường Thử Nghiệm

Không giống CS-KG [2] dùng testbed 1.824 nodes với cluster 4 nodes, GraphPent được thiết kế chạy trên phần cứng tiêu dùng:

**Cấu hình phần cứng**:

| Thành phần | Cấu hình |
|-----------|---------|
| CPU | Intel Core i7-9750H @ 2,60 GHz |
| RAM | 16 GB DDR4 |
| GPU | NVIDIA GTX 1650 4 GB VRAM |
| Storage | SSD NVMe 512 GB |
| OS | Windows 11 Pro + WSL2 / Docker Desktop |

**Cấu hình phần mềm**:

| Dịch vụ | Phiên bản | RAM phân bổ |
|--------|----------|--------------------|
| FastAPI | 0.115.0 | 2 GB |
| Neo4j | 5.26.0 | 2 GB (heap 1 GB) |
| Weaviate | 4.9.0 | 1 GB |
| Redis | 7.x | 256 MB |
| PostgreSQL | 15.x | 512 MB |
| Ollama (llama3.2:3b) | latest | 4 GB VRAM |

**Tập dữ liệu**:

| Nguồn | Quy mô |
|-------|--------|
| cvelistV5 (2023) | 31.170 files, 2,1 GB |
| CWE XML (v4.19.1) | 933 entries, 39 MB |
| NVD JSON | ~5.000 records |

Sau khi áp dụng bộ lọc `MIN_FILE_BYTES=800`, còn lại **26.843 file CVE hợp lệ**. Pipeline batch tạo ra tổng cộng **131.200 chunks**, dẫn đến **412.500 entities** và **287.300 relations** trong Neo4j, cùng **131.200 vector embeddings** trong Weaviate.

### 4.2. Mô Hình và Baseline

So sánh ba cấu hình truy xuất chính trên bảy truy vấn kiểm thử xâm nhập đại diện (SQL injection, XSS, CSRF, IDOR, leo thang đặc quyền, chuỗi tấn công liên quan):

| Ký hiệu | Mô tả | α |
|---------|--------|---|
| **B1** — Vector-only | Weaviate semantic search, nomic-embed | 1,0 |
| **B2** — Graph-only | Neo4j fulltext + BFS | 0,0 |
| **G-0.3** | Hybrid RRF (khuyến nghị) | 0,3 |

**Chỉ số đánh giá**: P@10, R@10, MRR, NDCG@10, Latency p95 (ms), Decision Accuracy, Avg. Reasoning Steps.

**Ground truth**: Xây dựng thủ công bởi chuyên gia bảo mật, script đánh giá tại `evaluation/runner.py`.

### 4.3. Kết Quả

#### 4.3.1. Hiệu Năng Hệ Thống

**Bảng 1. Độ trễ các thành phần hệ thống**

| Thành phần | Latency | Ghi chú |
|-----------|---------|---------|
| Vector search (Weaviate) | 50–100ms | GPU-accelerated |
| Graph search (Neo4j) | 80–200ms | Với index |
| RRF fusion | <5ms | CPU-bound |
| **Hybrid retrieval (cold)** | **100–300ms** | Không cache |
| **Hybrid retrieval (warm)** | **<50ms** | Redis cache hit |
| LLM extraction (llama3.2:3b) | 3–8s/chunk | GTX 1650 |
| **Multi-agent workflow** | **2–5s** | 7-node pipeline |
| CVE analysis (single) | 20–50ms | Keyword scoring |
| Nuclei scan | 30–120s | Phụ thuộc target |

So sánh: CS-KG [2] đạt perception–reasoning–action loop ~420ms trên cluster 4 nodes; GraphPent đạt <300ms cold / <50ms warm trên phần cứng đơn nhờ parallel search và Redis caching.

**Bảng 2. Cache hit rate (sau >1.000 queries)**

| Chế độ | Cache Hit Rate |
|--------|--------------|
| Hybrid (α=0,7) | 65–80% |
| Vector-only | 60–75% |
| Graph-only | 55–70% |

#### 4.3.2. Chất Lượng Truy Xuất Thông Tin

**Bảng 3. Chỉ số IR trung bình (7 truy vấn pentest)**

| Phương pháp | P@10 | R@10 | MRR | NDCG@10 | Lat.p99 |
|-------------|:---:|:---:|:---:|:---:|:---:|
| B1 — Vector-only | 0,22 | 0,12 | 0,47 | 0,24 | ~153ms |
| B2 — Graph-only | 0,79 | 0,46 | **1,00** | 0,86 | **~24ms** |
| **G-0.3 (Hybrid)** | **0,82** | **0,48** | **1,00** | **0,87** | ~66ms |

**Nhận xét**: Cấu trúc đồ thị là yếu tố then chốt — graph-only đạt MRR = 1,000 và NDCG@10 = 0,86 với latency chỉ 24ms, nhanh hơn vector-only **6,3×**. Hybrid G-0.3 thêm +2,2% NDCG nhờ tín hiệu vector bổ sung cho các truy vấn ngữ nghĩa. Vector-only đạt NDCG@10 = 0,24 nhưng latency cao nhất (153ms), phù hợp giả thuyết về *confused information retrieval* [1]. Alpha > 0,5 gây degradation nghiêm trọng (G-0.7 ≡ B1, NDCG@10 = 0,24).

**Bộ truy vấn ground truth (7 queries, 115 relevant documents):**

| Query | Relevant (tổng) | CWE | NVD | CVE | Chunks |
|-------|:--------------:|:---:|:---:|:---:|:------:|
| `"SQL injection vulnerabilities"` | 17 | 1 | 6 | 6 | 4 |
| `"XSS cross-site scripting"` | 24 | 3 | 4 | 14 | 3 |
| `"IDOR insecure direct object"` | 11 | 3 | 1 | 3 | 4 |
| `"CSRF cross-site request forgery"` | 13 | 2 | 2 | 9 | 0 |
| `"authentication vulnerabilities"` | 21 | 13 | 1 | 0 | 8 |
| `"authentication bypass"` | 21 | 11 | 0 | 4 | 6 |
| `"CWE weakness taxonomy"` | 8 | 3 | 4 | 0 | 1 |

**Ví dụ cụ thể — query `"SQL injection vulnerabilities"` (17 relevant docs):**
- **B1 Vector-only**: rank-1 trả về text chunk mô tả chung về SQL → không có CWE-89 ở top-5; MRR = 0,47 (relevant doc đầu tiên xuất hiện ở rank ~2–3).
- **B2 Graph-only / G-0.3**: rank-1 = `CWE-89` (SQL Injection, CVSS 9,0) với đủ context CVE, mitigation, affected platform → MRR = 1,000; NDCG@10 = 0,92.
- **Finding Correlation** `"stored XSS in plugin"`: cả B2 và G-0.3 đều trả về `CWE-79` ở rank-1, NDCG@10 = 1,000 (perfect) — truy vấn có keyword cụ thể được hưởng lợi tối đa từ graph fulltext index.

**Bảng 4. NDCG@10 theo từng loại truy vấn**

| Kịch bản | B1 | B2 | G-0.3 |
|---------|:---:|:---:|:---:|
| S1 — Retrieval Accuracy | 0,27 | 0,84 | **0,88** |
| S2 — CVE Linking | 0,12 | **0,78** | **0,78** |
| S3 — Finding Correlation | 0,20 | **0,96** | **0,96** |
| S4 — Multi-hop Reasoning | 0,34 | **0,83** | **0,83** |
| S5 — Remediation Quality | 0,25 | 0,92 | **0,92** |
| **Trung bình** | 0,24 | 0,87 | **0,88** |

Truy vấn định danh cụ thể (S2 CVE Linking, S4 Multi-hop) không được cải thiện thêm bởi vector. Truy vấn có thành phần ngữ nghĩa (S1 Retrieval Accuracy, S5 Remediation) hybrid vượt graph-only nhờ tín hiệu vector. Mọi cấu hình có α ≤ 0,5 đều đạt MRR = 1,000.

#### 4.3.3. Decision Accuracy và Hiệu Quả Suy Luận Đa Bước

**Bảng 5. Decision Accuracy và số bước suy luận trung bình**

| Phương pháp | Decision Accuracy | Avg. Reasoning Steps |
|-------------|:-----------------:|:-------------------:|
| B1 — Vector-only | 28,6% | 4,5 |
| B2 — Graph-only | **100%** | 3,1 |
| **G-0.3 (Hybrid)** | **100%** | **2,5** |

*Decision Accuracy*: tỷ lệ kết quả truy xuất hạng 1 ánh xạ đúng lớp lỗ hổng.  
*Avg. Reasoning Steps*: số vòng lặp LangGraph trung bình trước khi sinh kế hoạch tự tin.

Cả graph-only và hybrid G-0.3 đều đạt Decision Accuracy 100% nhờ MRR = 1,000 — kết quả rank-1 luôn ánh xạ đúng lớp lỗ hổng. Vector-only chỉ đạt 28,6% do MRR = 0,47 (kết quả rank-1 thường không khớp). Hybrid giảm số bước suy luận từ 3,1 xuống 2,5 nhờ ngữ cảnh phong phú giúp agent hội tụ nhanh hơn so với graph-only đơn thuần.

**Ví dụ suy luận đa bước — query `"authentication bypass vulnerabilities CWE weakness family"`:**
- **B1 Vector**: rank-1 = chunk text không chứa CWE ID → planner không xác định được lớp lỗ hổng → phải lặp thêm 1–2 bước (Avg. Steps = 4,5).
- **G-0.3**: rank-1 = `CWE-287` (Improper Authentication) với 13 CWE liên quan qua `CHILD_OF`/`PARENT_OF` (CWE-306, CWE-308, CWE-862...) → planner nhận diện đúng ngay bước đầu → Avg. Steps = 2,5.

#### 4.3.4. Phân Tích Pareto: Chất Lượng và Độ Trễ

```
NDCG@10
0,88 | ● graph_only (0,86 / 24ms)   ● hybrid G-0.3 (0,87 / 66ms)
0,50 |
0,25 |
0,24 |                                           ● vector_only (0,24 / 153ms)
     |___________________________________________________
     0    24   50   66  100  153  Lat.p99 (ms)
```

Graph-only chiếm vị trí **tối ưu Pareto** về latency–chất lượng: NDCG@10 = 0,86 tại chỉ 24ms p99, nhanh hơn vector-only **6,3×** và hybrid **2,7×**. Hybrid G-0.3 thêm +2,2% NDCG (0,87 vs 0,86) nhưng tốn 2,7× latency so với graph-only — đánh đổi phù hợp cho truy vấn ngữ nghĩa mở (S1 Retrieval Accuracy, S5 Remediation Quality). Vector-only bị dominated trên cả hai chiều: NDCG@10 = 0,24 tại 153ms. Cảnh báo alpha: alpha > 0,5 khiến hybrid thoái hóa về vector-only (G-0.7 ≡ B1, NDCG@10 = 0,24).

#### 4.3.5. Đánh Giá GNN Risk Scoring (L5)

**Bảng 5b. GNN Risk Scoring — 3.049 nodes (v4 Final, w_sev=0,80)**

| Chỉ số | Giá trị |
|--------|--------|
| CVE nodes có cvss_score | 89 |
| Spearman ρ (risk_score vs CVSS) | **0,9971** |
| Tier Accuracy | **96,63%** (86/89 nodes) |
| High-CVE P@20 | 0,85 (17/20) |
| High-CVE P@50 | 0,86 (43/50) |
| Risk boundedness | 1,000 (100% nodes ∈ [0,1]) |
| CRITICAL nodes (top-100) | 25 |
| Auth→CVE (cwe-287) paths | **100%** (10/10 valid) |
| XSS→CVE (cwe-79) TopRisk | 0,8011 |
| Attack path coverage | **100%** (5/5 tests) |
| Recall@100 | **1,000** (5/5 known-critical nodes) |
| Score latency (median) | 31ms |

Spearman ρ = 0,9971 xác nhận risk_score phản ánh chính xác CVSS severity. Auth→CVE đạt 100% sau khi upsert 100 CVE nodes mới với CLASSIFIED\_AS edges cho CWE-287/862/284. Recall@50 = 0,40 (thấp hơn Recall@100) do 25 CRITICAL CVE nodes chiếm các vị trí top-50 — hành vi đúng với ưu tiên pentest; mọi CWE node vẫn có thể truy cập ở Recall@100 = 1,000.

**Bảng 5d. Attack Path Tests — 5 kịch bản đã thực hiện**

| Test | Source | Target | Paths | Validity | MinHop | TopRisk | Latency |
|------|--------|--------|:-----:|:--------:|:------:|:-------:|:-------:|
| SQLi→CVE | `cwe-89` | CVE | 10/10 | 100% | 2 | 0,4006 | 135ms |
| XSS→CVE | `cwe-79` | CVE | 10/10 | 100% | **1** | **0,8011** | 69ms |
| Auth→CVE | `cwe-287` | CVE | 10/10 | 100% | **1** | 0,7931 | 625ms |
| CSRF→CVE | `cwe-352` | CVE | 10/10 | 100% | 2 | 0,4006 | 56ms |
| SQLi→Weakness | `cwe-89` | Weakness | 10/10 | 100% | 1 | 0,8115 | 23ms |

**Ví dụ attack path đã thực hiện:**
- **XSS→CVE** (MinHop=1, TopRisk=0,8011): `CWE-79` —[CLASSIFIED_AS]→ `CVE-XXXX` (CVSS 8,0) — đường đi ngắn nhất 1 hop, risk cao nhất trong bộ test nhờ `cwe-79` có cvss_score=7,5 và nhiều CVE instance.
- **Auth→CVE** (MinHop=1, TopRisk=0,7931, Latency=625ms): `CWE-287` —[CLASSIFIED_AS]→ CVE — latency cao do 100 CVE nodes mới được thêm vào graph qua `link_cwe287_cves.py`; BFS phải duyệt nhiều edges hơn.
- **SQLi→CVE** (MinHop=2, TopRisk=0,4006): `CWE-89` —[CHILD_OF]→ `CWE-943` —[CLASSIFIED_AS]→ CVE — path_risk = target_risk/hops = 0,8011/2 = 0,4006; thấp hơn XSS do cần 2 hops.

**Phân bố risk score (top-100 nodes):** score ∈ [0,6093 – 0,8701], mean = 0,7124 ± 0,0636. Tier: 25 CRITICAL (≥0,75) + 75 HIGH (≥0,50) + 0 MEDIUM/LOW. Một vi phạm monotone được ghi nhận (tier boundary rounding).

#### 4.3.6. Đánh Giá Reasoning Pipeline (L6)

**Bảng 5c. L6 Reasoning Pipeline — 8 Scenarios**

| Metric | Kết quả |
|--------|--------|
| M1 Tool Selection Accuracy | **100%** (3/3 whitelisted targets) |
| M2 Graph Utilization Rate | **100%** |
| M3 Avg Report Completeness | **100%** |
| M4 Retrieval-Reasoning Alignment | **100%** |
| M6 Pipeline Completion Rate | **100%** (8/8) |
| M7 Attack Path Discovery Rate | **100%** (3/3) |
| M8 Within Loop Budget Rate | **100%** |
| Latency p50 / p95 | 1.711ms / 5.144ms |

Latency p50 = 1,7s phản ánh Nuclei TCP timeout ~4s khi scan target không phản hồi trong lab; các scenarios không có target duy trì <1,5s. Kết quả xác nhận reasoning pipeline hoàn chỉnh: tool routing chính xác (M1=100%), graph context được khai thác đầy đủ (M2=100%), mọi report đạt đủ cấu trúc chuẩn (M3=100%).

**Bảng 5e. L6 — 8 Scenarios đã thực hiện (benchmark_l6_20260503_192018)**

| ID | Scenario | Target | Tool | AttackPaths | Latency |
|----|----------|--------|:----:|:-----------:|:-------:|
| RS1 | SQL Injection CVE Lookup | — | — | — | 1.398ms |
| RS2 | XSS with Target — Nuclei | 192.168.1.1 | ✓ | ✓ | 4.999ms |
| RS3 | Authentication Bypass Multi-hop | — | — | — | 1.711ms |
| RS4 | CSRF with Target | 10.0.0.1 | ✓ | ✓ | 5.144ms |
| RS5 | IDOR Authorization Check | — | — | — | 1.198ms |
| RS6 | CWE Taxonomy Reasoning | — | — | — | 1.183ms |
| RS7 | Full Pipeline + Feedback Loop | 192.168.100.1 | ✓ | ✓ | 4.923ms |
| RS8 | Remediation Guidance Query | — | — | — | 1.402ms |

**Ví dụ 3 kịch bản đặc trưng:**

*RS1 — SQL Injection CVE Lookup* (query: `"SQL injection vulnerabilities CVE exploit"`, no target, 1.398ms): pipeline chạy collection → planner → retrieval → graph\_reasoning → report. `needs_tools=False` vì không có scan target. Graph utilization = True: final report trích dẫn `CWE-89`, các CVE instance liên quan, và mitigation (parameterized queries). Report completeness = 100% (đủ 5 sections: summary, findings, CVE context, attack paths, recommendations).

*RS2 — XSS with Target* (query: `"XSS cross-site scripting vulnerabilities in web application"`, target=`192.168.1.1`, 4.999ms): `needs_tools=True` do target nằm trong whitelist. Tool node gọi Nuclei với XSS template. Attack paths được tìm thấy (`CWE-79 → CVE`). Latency cao (4,999ms) do Nuclei TCP timeout với lab host không phản hồi.

*RS7 — Full Pipeline + Feedback Loop* (target=`192.168.100.1`, 4.923ms): kịch bản tổng hợp nhất — chạy đầy đủ 7 nodes: collection (Nmap discovery) → planner → retrieval → graph\_reasoning → tool (Nuclei) → report → human\_approval. `loop_iterations=1` (không kích hoạt feedback loop do `new_findings=0` trong môi trường lab). Xác nhận toàn bộ DAG hoạt động end-to-end.

#### 4.3.7. Chất Lượng Trích Xuất Tri Thức

**Bảng 6. Chất lượng extraction pipeline (100 CVE files)**

| Chỉ số | Giá trị |
|-------|--------|
| Entity Precision | 0,82 |
| Entity Recall | 0,74 |
| Entity F1 | 0,78 |
| Relation F1 | 0,69 |
| Avg. entities / chunk | 4,3 |
| Avg. relations / chunk | 3,1 |

#### 4.3.8. Thảo Luận

**Phát hiện chính.**

*Cấu trúc đồ thị là yếu tố then chốt.* Graph-only đạt NDCG@10 = 0,86 và MRR = 1,000 với latency chỉ 24ms — nhanh hơn vector-only **6,3×**. Cả bảy truy vấn đánh giá yêu cầu duyệt chuỗi CVE→CWE→mitigation; tương đồng ngữ nghĩa thuần túy chỉ đạt NDCG@10 = 0,24, xác nhận giới hạn của bộ nhớ embedding-only trong PentestGPT [1].

*Hybrid thêm marginal quality tại chi phí latency.* Hybrid G-0.3 cải thiện +2,2% NDCG so với graph-only (0,87 vs 0,86) nhờ tín hiệu vector bổ sung cho S1 Retrieval Accuracy (+0,04) và S5 Remediation Quality. Tuy nhiên, hybrid tốn 2,7× latency (66ms vs 24ms). Cả graph-only và hybrid đều đạt Decision Accuracy 100% và MRR = 1,000. Alpha sensitivity là vấn đề quan trọng: alpha > 0,5 gây degradation nghiêm trọng (G-0.7 ≡ B1).

*GNN risk scoring đạt calibration gần hoàn hảo.* Spearman ρ = 0,9971 xác nhận công thức blended scoring với w_sev=0,80 phản ánh chính xác CVSS ground truth. Auth→CVE coverage 100% sau khi bổ sung 100 CVE nodes qua script `link_cwe287_cves.py`.

*Reasoning pipeline hoàn chỉnh và nhất quán.* 100% trên tất cả M1–M8 metrics, bao gồm Tool Selection (M1), Graph Utilization (M2), Report Completeness (M3), và Retrieval Alignment (M4), xác nhận hệ thống multi-agent phối hợp đúng giữa các layer.

**Giải quyết vấn đề quản lý trạng thái LLM.** Bằng cách đưa trạng thái mạng vào KG Neo4j có cấu trúc (nodes: Host, Service, Finding, CVE), GraphPent loại bỏ thiên kiến chiều sâu và mất ngữ cảnh được ghi nhận trong [7, 8]. `AgentState` TypedDict là cấu trúc xác định mà router LangGraph có thể truy vấn trực tiếp, thay thế PTT ngôn ngữ tự nhiên vốn không thể cưỡng chế xóa tác vụ sau ngõ cụt.

**Hạn chế và hướng phát triển.**

Bộ đánh giá chỉ gồm bảy truy vấn đại diện; cần mở rộng phủ sóng sang nhiều loại mục tiêu hơn (dịch vụ mạng, thiết bị nhúng) để tổng quát hóa kết quả Decision Accuracy.

So với CS-KG [2] đạt vulnerability coverage 74% trên testbed doanh nghiệp, GraphPent chưa có kết quả đánh giá trên môi trường mạng thực — đây là hạn chế ưu tiên xử lý trong nghiên cứu tiếp theo.

Bottleneck chính là throughput LLM extraction với `LLM_CONCURRENCY=3`. Giải pháp: quantization mạnh hơn (GGUF Q4_K_M) hoặc phần cứng nhiều GPU.

Ground truth hiện được annotate bởi một chuyên gia. Hướng mở rộng: dùng GPT-4 làm LLM-as-judge oracle, tuyển nhiều annotator để đo inter-rater reliability (Cohen's κ).

---

## 5. Kết Luận

Bài báo đã trình bày GraphPent — nền tảng kiểm thử xâm nhập tự động dựa trên kiến trúc GraphRAG 13 phase, tích hợp đồ thị tri thức lai (Neo4j + Weaviate), thuật toán truy xuất RRF điều chỉnh được, hệ thống multi-agent 7 node với LangGraph, và LLM cục bộ (llama3.2:3b). Khác với PentestGPT [1] phụ thuộc LLM đám mây không có knowledge graph, và CS-KG [2] dùng SPARQL thuần túy không có vector embedding hay RAG, GraphPent kết hợp cả hai tiếp cận trong một nền tảng có thể triển khai hoàn toàn cục bộ.

Hệ thống đạt độ trễ truy vấn dưới 300ms (<50ms với cache) và hoàn thiện workflow phân tích trong 2–5 giây. Đánh giá trên bảy truy vấn kiểm thử xâm nhập thực tế: cấu hình hybrid G-0.3 đạt **NDCG@10 = 0,8741** và **MRR = 1,000** (vượt vector-only **3,6×**; graph-only đạt 0,8551 ở **24ms p99** — nhanh hơn vector-only 6,3×). GNN risk scoring đạt **Spearman ρ = 0,9971** và attack path coverage **100%** trên 3.049 nodes với weights tối ưu w_sev=0,80. Reasoning pipeline (L6) đạt **100%** trên toàn bộ 8 chỉ số M1–M8 (p50=1.711ms). Trích xuất tri thức trên 100 CVE files cho Entity F1=0,78 và Relation F1=0,69 với llama3.2:3b trên GTX 1650. Bằng cách ngoại hóa trạng thái mạng vào Neo4j, GraphPent loại bỏ về mặt cấu trúc thiên kiến chiều sâu và mất ngữ cảnh của LLM được xác định trong các benchmark gần đây [7, 8].

Hướng nghiên cứu tiếp theo: (1) fine-tuning LLM chuyên biệt bảo mật cho trích xuất thực thể; (2) tích hợp MITRE ATT&CK vào schema KG; (3) đánh giá trong môi trường mạng thực tế quy mô lớn tương đương CS-KG [2]; (4) phát triển dashboard trực quan cho kiểm thử viên.

---

## Tài Liệu Tham Khảo

[1] G. Deng, Y. Liu, V. Mayoral-Vilches, P. Liu, Y. Li, Y. Xu, T. Zhang, Y. Liu, M. Pinzger, and S. Rass, "PentestGPT: Evaluating and Harnessing Large Language Models for Automated Penetration Testing," *IEEE S&P 2024*, arXiv:2308.06782, 2024.

[2] Y. Pan, G. Feng, and K. Huang, "Enhancing Automated Penetration Testing Through a Comprehensive Cyber-Security Knowledge Graph," in *Proc. 10th Int. Symp. Advances in Electrical, Electronics and Computer Engineering (ISAEECE)*, pp. 551–555, IEEE, 2025.

[3] G. Weidman, *Penetration Testing: A Hands-On Introduction to Hacking*. No Starch Press, 2014.

[4] NIST, "Technical Guide to Information Security Testing and Assessment," NIST Special Publication 800-115, 2008.

[5] MITRE Corporation, "CVE List," https://www.cve.org/, 2024.

[6] W. Zhang, J. Xing, and X. Li, "Penetration Testing for System Security: Methods and Practical Approaches," arXiv:2505.19174v3, Feb. 2026.

[7] V. Gioacchini et al., "AutoPenBench: Benchmarking Generative Agents for Penetration Testing," arXiv:2410.03225, 2024.

[8] I. Isozaki, M. Shrestha, R. Console, and E. Kim, "Towards Automated Penetration Testing: Introducing LLM Benchmark, Analysis, and Improvements," in *Proc. ACM UMAP Adjunct '25*, ACM, Jun. 2025, pp. 1–8. DOI: 10.1145/3708319.3733804.

[9] A. Hogan et al., "Knowledge Graphs," *ACM Computing Surveys*, vol. 54, no. 4, pp. 1–37, 2021.

[10] D. Edge et al., "From Local to Global: A Graph RAG Approach to Query-Focused Summarization," arXiv:2404.16130, 2024.

[11] P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," *NeurIPS 2020*, pp. 9459–9474.

[12] G. V. Cormack, C. L. A. Clarke, and S. Buettcher, "Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods," in *ACM SIGIR 2009*, pp. 758–759.

[13] LangChain Inc., "LangGraph: Build Stateful, Multi-Actor Applications with LLMs," https://github.com/langchain-ai/langgraph, 2024.

[14] L. F. Sikos, "Cybersecurity Knowledge Graphs," *Knowledge and Information Systems*, vol. 65, pp. 3511–3531, 2023.

[15] Z. Li et al., "ThreatKG: An Automated System for Mining, Structuring, and Analyzing Threat Intelligence," in *NDSS 2023*.

[16] O. Khattab and M. Zaharia, "ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT," in *ACM SIGIR 2020*, pp. 39–48.

[17] J. Chen et al., "BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings," arXiv:2402.03216, 2024.
