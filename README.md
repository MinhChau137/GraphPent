# GraphRAG Pentest Platform - Phase 1

## Khởi động nhanh (chạy được ngay)

```bash
# 1. Clone project (hoặc tạo thư mục)
mkdir graphrag-pentest && cd graphrag-pentest

# 2. Tạo các file theo hướng dẫn ở trên (copy-paste code)

# 3. Copy env
cp .env.example .env

# 4. Build & run
docker compose up --build -d

# 5. Kiểm tra
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/config